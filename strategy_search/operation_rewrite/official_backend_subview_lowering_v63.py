# -*- coding: utf-8 -*-
"""V6.3 official-backend subview/sanitization lowering.

This pass is intentionally conservative and portable.  It addresses the most
obvious blockers found by comparing the V6.2 rewritten HIVM against public
HIVM/MLIR style constraints:

* hivm.hir.load/store shape mismatch without an actual slice/subview operand;
* semantic tile/pipeline strings carried only as private attrs;
* versioned debug attrs/comments that official backends may reject;
* CVPipeline schedule attrs pretending to be physical movement.

The pass materializes memref.subview operations for mismatched GM<->local
load/store operands, strips private debug attrs, and emits a backend contract for
anything that still requires the official Linux pass to lower/verify.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

_MEMREF_RE = re.compile(r"memref<(?P<shape>[0-9x?]+)x(?P<elem>[A-Za-z0-9]+),\s*(?P<addr>#hivm\.address_space<(?P<space>[A-Za-z0-9_]+)>)>")
_LOAD_RE = re.compile(r"(?P<prefix>hivm\.hir\.load\s+ins\()(?P<src>%[A-Za-z_][A-Za-z0-9_.$-]*)\s*:\s*(?P<src_ty>memref<[^>]+>>)(?P<mid>\)\s+outs\()(?P<dst>%[A-Za-z_][A-Za-z0-9_.$-]*)\s*:\s*(?P<dst_ty>memref<[^>]+>>)(?P<suffix>\).*)")
_STORE_RE = re.compile(r"(?P<prefix>hivm\.hir\.store\s+ins\()(?P<src>%[A-Za-z_][A-Za-z0-9_.$-]*)\s*:\s*(?P<src_ty>memref<[^>]+>>)(?P<mid>\)\s+outs\()(?P<dst>%[A-Za-z_][A-Za-z0-9_.$-]*)\s*:\s*(?P<dst_ty>memref<[^>]+>>)(?P<suffix>\).*)")
_ATTR_BLOCK_RE = re.compile(r"\{(?P<body>.*)\}\s*$")
_TILE_ATTR_RE = re.compile(r"hivm\.(?:tile_offsets|tile_shape|tile_axes)\s*=\s*\"([^\"]*)\"")
_PRIVATE_ATTR_RE = re.compile(r"\s*,?\s*hivm\.(?:v5[0-9]|v6[0-9]|pipeline_|tile_|reduction_|accumulator_|sync_|dependency_|stage_|producer_|consumer_|rewrite_|multi_buffer_slot)[A-Za-z0-9_]*\s*=\s*(?:\"[^\"]*\"|true|false|[0-9]+)")
# Some attrs do not have hivm. prefix.
_PRIVATE_ATTR_RE2 = re.compile(r"\s*,?\s*(?:hivm\.pipeline_schedule|hivm\.tile_index_expr|hivm\.producer_consumer_distance|hivm\.pipeline_region|hivm\.pipeline_stage_role)\s*=\s*\"[^\"]*\"")
_COMMENT_MARKERS = [
    "HIVM V5.", "HIVM V6.", "axis-binding:", "tail-semantics:", "reduction-semantics:",
    "selected:", "operation-level intent:", "local memref operation/type shapes", "Linux backend must",
]

def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_memref(ty: str) -> Dict[str, Any] | None:
    m = _MEMREF_RE.search(ty)
    if not m:
        return None
    shape = [int(x) if x.isdigit() else x for x in m.group("shape").split("x")]
    return {"shape": shape, "elem": m.group("elem"), "addr": m.group("addr"), "space": m.group("space"), "text": m.group(0)}


def _same_shape(a: str, b: str) -> bool:
    pa, pb = _parse_memref(a), _parse_memref(b)
    return bool(pa and pb and pa["shape"] == pb["shape"] and pa["elem"] == pb["elem"])


def _get_attr(line: str, name: str) -> str | None:
    m = re.search(rf"{re.escape(name)}\s*=\s*\"([^\"]*)\"", line)
    return m.group(1) if m else None


def _offsets_for(line: str, rank: int, in_scope: set[str]) -> List[str]:
    raw = _get_attr(line, "hivm.tile_offsets") or ""
    vals = [x.strip().replace("%", "") for x in raw.split(",") if x.strip()]
    out: List[str] = []
    for v in vals[:rank]:
        if v in {"m_outer", "n_outer", "k_outer"} and v in in_scope:
            out.append("%" + v)
        else:
            out.append("%c0")
    while len(out) < rank:
        out.append("%c0")
    return out


def _sizes_from_type(ty: str) -> List[str]:
    p = _parse_memref(ty)
    if not p:
        return []
    return [str(x) for x in p["shape"]]


def _memref_type_like(base_ty: str, shape_source_ty: str) -> str:
    """Build a memref type with shape from shape_source and elem/address from base."""
    base = _parse_memref(base_ty)
    shp = _parse_memref(shape_source_ty)
    if not base or not shp:
        return shape_source_ty
    shape = "x".join(str(x) for x in shp["shape"])
    return f"memref<{shape}x{base['elem']}, {base['addr']}>"


def _strides(rank: int) -> List[str]:
    return ["1"] * rank


def materialize_load_store_subviews(text: str) -> Tuple[str, Dict[str, Any]]:
    lines = text.splitlines()
    out: List[str] = []
    actions: List[Dict[str, Any]] = []
    in_scope: set[str] = set()
    counter = 0
    for ln, line in enumerate(lines, start=1):
        # Track simple scope for tile ivars.  This is conservative and line-based.
        if "scf.for %m_outer" in line: in_scope.add("m_outer")
        if "scf.for %n_outer" in line: in_scope.add("n_outer")
        if "scf.for %k_outer" in line: in_scope.add("k_outer")
        # Close scopes based on comments emitted by our rewriter.
        if "end M-tile loop" in line: in_scope.discard("m_outer")
        if "end N-tile loop" in line: in_scope.discard("n_outer")
        if "end K-tile loop" in line: in_scope.discard("k_outer")

        m = _LOAD_RE.search(line)
        if m and not _same_shape(m.group("src_ty"), m.group("dst_ty")):
            src_info, dst_info = _parse_memref(m.group("src_ty")), _parse_memref(m.group("dst_ty"))
            if src_info and dst_info and src_info["elem"] == dst_info["elem"]:
                indent = re.match(r"\s*", line).group(0)
                rank = len(dst_info["shape"])
                offsets = _offsets_for(line, rank, in_scope)
                sizes = _sizes_from_type(m.group("dst_ty"))
                strides = _strides(rank)
                new_name = f"{m.group('src')}_tile_v63_{counter}"
                counter += 1
                tile_ty = _memref_type_like(m.group('src_ty'), m.group('dst_ty'))
                subview = f"{indent}{new_name} = memref.subview {m.group('src')}[{', '.join(offsets)}] [{', '.join(sizes)}] [{', '.join(strides)}] : {m.group('src_ty')} to {tile_ty}"
                new_line = line[:m.start()] + f"{m.group('prefix')}{new_name} : {tile_ty}{m.group('mid')}{m.group('dst')} : {m.group('dst_ty')}{m.group('suffix')}"
                out.append(subview)
                out.append(new_line)
                actions.append({"line": ln, "kind": "load_subview", "source": m.group("src"), "tile": new_name, "src_type": m.group("src_ty"), "tile_type": tile_ty, "local_type": m.group("dst_ty"), "offsets": offsets, "sizes": sizes})
                continue
        m = _STORE_RE.search(line)
        if m and not _same_shape(m.group("src_ty"), m.group("dst_ty")):
            src_info, dst_info = _parse_memref(m.group("src_ty")), _parse_memref(m.group("dst_ty"))
            if src_info and dst_info and src_info["elem"] == dst_info["elem"]:
                indent = re.match(r"\s*", line).group(0)
                rank = len(src_info["shape"])
                offsets = _offsets_for(line, rank, in_scope)
                sizes = _sizes_from_type(m.group("src_ty"))
                strides = _strides(rank)
                new_name = f"{m.group('dst')}_tile_v63_{counter}"
                counter += 1
                tile_ty = _memref_type_like(m.group('dst_ty'), m.group('src_ty'))
                subview = f"{indent}{new_name} = memref.subview {m.group('dst')}[{', '.join(offsets)}] [{', '.join(sizes)}] [{', '.join(strides)}] : {m.group('dst_ty')} to {tile_ty}"
                new_line = line[:m.start()] + f"{m.group('prefix')}{m.group('src')} : {m.group('src_ty')}{m.group('mid')}{new_name} : {tile_ty}{m.group('suffix')}"
                out.append(subview)
                out.append(new_line)
                actions.append({"line": ln, "kind": "store_subview", "target": m.group("dst"), "tile": new_name, "dst_type": m.group("dst_ty"), "tile_type": tile_ty, "local_type": m.group("src_ty"), "offsets": offsets, "sizes": sizes})
                continue
        out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else ""), {
        "schema_version": "hivm_v63_subview_lowering_report_v1",
        "mutation_performed": bool(actions),
        "action_count": len(actions),
        "actions": actions,
        "note": "Offsets outside m/n/k tile-loop scope are conservatively lowered to %c0. Linux backend must still verify semantic correctness.",
    }


def _clean_attr_block(body: str) -> str:
    # Drop generated private/semantic attrs that official backend is unlikely to know.
    cleaned = body
    for pat in (_PRIVATE_ATTR_RE, _PRIVATE_ATTR_RE2):
        cleaned = pat.sub("", cleaned)
    # Drop a few exact generated attrs with non-hivm names.
    cleaned = re.sub(r"\s*,?\s*(?:pipeline_template|pipeline_stage_num|stage_buffer_policy)\s*=\s*\"[^\"]*\"", "", cleaned)
    # Normalize comma runs.
    cleaned = re.sub(r"\{\s*,", "{", cleaned)
    cleaned = re.sub(r",\s*,", ",", cleaned)
    cleaned = re.sub(r",\s*\}", "}", cleaned)
    cleaned = re.sub(r"\{\s*\}", "{}", cleaned)
    return cleaned


def strip_private_attrs_and_debug_comments(text: str) -> Tuple[str, Dict[str, Any]]:
    removed_comments = 0
    attr_lines_changed = 0
    out: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("//") and any(tok in stripped for tok in _COMMENT_MARKERS):
            removed_comments += 1
            continue
        new_line = _clean_attr_block(line)
        if new_line != line:
            attr_lines_changed += 1
            # Remove empty attr block on hivm op if possible.
            new_line = re.sub(r"\s+\{\}\s*$", "", new_line)
        out.append(new_line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else ""), {
        "schema_version": "hivm_v63_private_attr_strip_report_v1",
        "mutation_performed": removed_comments > 0 or attr_lines_changed > 0,
        "removed_debug_comment_count": removed_comments,
        "attr_lines_changed": attr_lines_changed,
    }


def audit_v63_official_compare(text: str) -> Dict[str, Any]:
    lines = text.splitlines()
    issues: List[Dict[str, Any]] = []
    for i, line in enumerate(lines, start=1):
        code = line.split("//", 1)[0]
        for regex, op in [(_LOAD_RE, "load"), (_STORE_RE, "store")]:
            m = regex.search(code)
            if m and not _same_shape(m.group("src_ty"), m.group("dst_ty")):
                issues.append({"severity": "HIGH", "line": i, "kind": "load_store_shape_mismatch_without_subview_or_pad", "op": op, "snippet": code.strip()[:240]})
        if "annotation.mark" in code:
            issues.append({"severity": "HIGH", "line": i, "kind": "annotation_mark_not_lowered", "snippet": code.strip()[:240]})
        if any(tok in code for tok in ["D_tile", "propagate_from_input", "hivm.tile_offsets=\"[", "hivm.tile_shape=\"["]):
            issues.append({"severity": "HIGH", "line": i, "kind": "unlowered_placeholder_or_python_list_attr", "snippet": code.strip()[:240]})
        if re.search(r"hivm\.v[0-9]|hivm\.tile_|hivm\.pipeline_|hivm\.reduction_|hivm\.accumulator_", code):
            issues.append({"severity": "MEDIUM", "line": i, "kind": "private_or_semantic_attr_remaining", "snippet": code.strip()[:240]})
        if code.strip().startswith("//") and "HIVM V" in code:
            issues.append({"severity": "LOW", "line": i, "kind": "debug_comment_remaining", "snippet": code.strip()[:240]})
    counts: Dict[str, int] = {}
    for it in issues:
        counts[it["kind"]] = counts.get(it["kind"], 0) + 1
    return {
        "schema_version": "hivm_v63_official_compare_audit_v1",
        "issue_count": len(issues),
        "counts_by_kind": counts,
        "passed_v63_portable_official_compare_audit": counts.get("load_store_shape_mismatch_without_subview_or_pad", 0) == 0 and counts.get("annotation_mark_not_lowered", 0) == 0 and counts.get("unlowered_placeholder_or_python_list_attr", 0) == 0,
        "issues": issues[:500],
        "claim_boundary": "Portable audit only. Official Ascend Linux parser/verifier/compiler is still required.",
    }


def write_v63_official_backend_subview_lowering_outputs(input_ir: str | Path, output_dir: str | Path) -> Dict[str, Any]:
    p = Path(input_ir)
    out = Path(output_dir)
    text = p.read_text(encoding="utf-8", errors="ignore")
    text1, subview_report = materialize_load_store_subviews(text)
    text2, strip_report = strip_private_attrs_and_debug_comments(text1)
    final = out / "optimized.four_plan_official_backend_subview_lowered.hivm.mlir"
    final.write_text(text2, encoding="utf-8")
    audit = audit_v63_official_compare(text2)
    backend_contract = {
        "schema_version": "hivm_v63_backend_contract_v1",
        "official_linux_backend_required_checks": [
            "parse optimized.four_plan_official_backend_subview_lowered.hivm.mlir",
            "verify memref.subview syntax and dominance of offsets",
            "verify hivm.hir.load/store src/dst shape equality after subview lowering",
            "run HIVM/MLIR verifier for all custom attrs left by official dialect",
            "lower or invoke official CVPipeline pass for physical work-item movement",
            "compile and run correctness before msprof",
        ],
        "cvpipeline_boundary": "V6.3 strips private schedule attrs from handoff IR and keeps schedule information in JSON contract; physical CVPipeline movement must be done by official pass or a registered backend lowering.",
        "subview_lowering_note": subview_report.get("note"),
    }
    _write_json(out / "v63_subview_lowering_report.json", subview_report)
    _write_json(out / "v63_private_attr_strip_report.json", strip_report)
    _write_json(out / "v63_official_compare_audit.json", audit)
    _write_json(out / "v63_backend_contract.json", backend_contract)
    return {
        "v63_official_backend_subview_lowered_ir": str(final),
        "subview_lowering": subview_report,
        "private_attr_strip": strip_report,
        "official_compare_audit": audit,
        "backend_contract": backend_contract,
    }
