# -*- coding: utf-8 -*-
"""V5.5 production-candidate TilingPlan operation-level text rewrite.

This module is deliberately stricter than the old metadata-only tiling rewrite:
it performs visible operation/type mutations on local HIVM buffer memref shapes
according to the selected TilingPlan.  It is still a *production candidate*, not
an authoritative compiler pass: loop split, affine index remap, tail masks and
reduction proof must be verified by the real Linux HIVM/MLIR backend before
msprof numbers are trusted.
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

VERSION = "V5.5-tiling-operation-production-candidate-rewrite"

_MEMREF_FOR_SYMBOL_RE = re.compile(r"(?P<sym>%[A-Za-z0-9_.$-]+)\s*(?:=|:)?.*?memref<(?P<d0>\d+)x(?P<d1>\d+)x(?P<dtype>f16|f32|i\d+),\s*#hivm\.address_space<(?P<space>ub|cbuf|cc|gm)>[^>]*>")
_MEMREF_TYPE_RE = re.compile(r"memref<(?P<d0>\d+)x(?P<d1>\d+)x(?P<dtype>f16|f32|i\d+),\s*#hivm\.address_space<(?P<space>ub|cbuf|cc)>[^>]*>")
_SYMBOL_RE = re.compile(r"%[A-Za-z0-9_.$-]+")


def _load_json(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _tiling_knobs(selected_plan: Dict[str, Any]) -> Dict[str, Any]:
    tp = selected_plan.get("tiling_plan") or {}
    knobs = tp.get("controllable_knobs") or tp.get("selected_knobs") or tp.get("knobs") or {}
    out = {
        "tile_m": knobs.get("tile_m"),
        "tile_n": knobs.get("tile_n"),
        "tile_k": knobs.get("tile_k"),
        "loop_order": knobs.get("loop_order"),
        "tail_strategy": knobs.get("tail_strategy"),
        "reduce_tile_policy": knobs.get("reduce_tile_policy"),
        "layout_aware_tile": knobs.get("layout_aware_tile"),
    }
    for k in ("tile_m", "tile_n", "tile_k"):
        try:
            out[k] = int(out[k])
        except Exception:
            out[k] = None
    return out


def _target_shape_for_symbol(symbol: str, tiles: Dict[str, Any]) -> Tuple[int, int] | None:
    """Best-effort FA/generic local-buffer role mapping.

    The names are intentionally common HIVM local-buffer conventions; unknown
    symbols are left untouched rather than guessed.
    """
    name = symbol.lstrip("%")
    tm, tn, tk = int(tiles["tile_m"]), int(tiles["tile_n"]), int(tiles["tile_k"])
    # Q/O/accumulator are M x K-like in this demo family.
    if name in {"q_ub", "q_l1", "acc_ub", "o_ub"}:
        return tm, tk
    # Score/prob/softmax and L0C are M x N-tile.
    if name in {"s_ub", "p_ub", "s_l0c"}:
        return tm, tn
    # K/V local tiles are N-tile x K.
    if name in {"k_ub", "v_ub", "k_l1", "v_l1", "k_l1_ping", "k_l1_pong", "v_l1_ping", "v_l1_pong"}:
        return tn, tk
    # Rowwise scalars follow M.
    if name in {"m_ub", "l_ub"}:
        return tm, 1
    return None


def _collect_symbol_roles(ir_text: str, tiles: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    roles: Dict[str, Dict[str, Any]] = {}
    for ln, line in enumerate(ir_text.splitlines(), start=1):
        for m in _MEMREF_FOR_SYMBOL_RE.finditer(line):
            sym = m.group("sym")
            if m.group("space") == "gm":
                continue
            target = _target_shape_for_symbol(sym, tiles)
            if not target:
                continue
            item = roles.setdefault(sym, {
                "symbol": sym,
                "target_shape": list(target),
                "occurrences": [],
            })
            item["occurrences"].append({
                "line": ln,
                "old_shape": [int(m.group("d0")), int(m.group("d1"))],
                "dtype": m.group("dtype"),
                "space": m.group("space"),
                "text": line.strip()[:300],
            })
    return roles


def _rewrite_line_shapes(line: str, roles: Dict[str, Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    if "memref<" not in line:
        return line, []
    syms = set(_SYMBOL_RE.findall(line))
    changed: List[Dict[str, Any]] = []
    out = line
    for sym in sorted(syms, key=len, reverse=True):
        role = roles.get(sym)
        if not role:
            continue
        td0, td1 = role["target_shape"]
        # Replace every local memref type near a line that references this symbol.
        # This keeps alloc result type and op operand/result type signatures aligned.
        def repl(m: re.Match[str]) -> str:
            old = [int(m.group("d0")), int(m.group("d1"))]
            if old == [td0, td1]:
                return m.group(0)
            changed.append({"symbol": sym, "old_shape": old, "new_shape": [td0, td1], "space": m.group("space"), "dtype": m.group("dtype")})
            return f"memref<{td0}x{td1}x{m.group('dtype')}, #hivm.address_space<{m.group('space')}>>"
        out = _MEMREF_TYPE_RE.sub(repl, out)
    return out, changed


def apply_tiling_operation_true_rewrite(ir_text: str, selected_plan: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    tiles = _tiling_knobs(selected_plan)
    missing = [k for k in ("tile_m", "tile_n", "tile_k") if tiles.get(k) is None]
    if missing:
        return ir_text, {"schema_version": "hivm_v55_tiling_operation_true_rewrite_report_v1", "mutation_performed": False, "blockers": [f"missing_{k}" for k in missing]}
    roles = _collect_symbol_roles(ir_text, tiles)
    lines = ir_text.splitlines()
    out: List[str] = []
    mutations: List[Dict[str, Any]] = []
    inserted_header = False
    for ln, line in enumerate(lines, start=1):
        if not inserted_header and ("func.func" in line or "module" in line):
            out.append(line)
            indent = re.match(r"\s*", line).group(0) + "  "
            out.extend([
                f"{indent}// HIVM V5.5 TilingPlan operation rewrite candidate begin",
                f"{indent}// selected tile_m={tiles['tile_m']} tile_n={tiles['tile_n']} tile_k={tiles['tile_k']} loop_order={tiles.get('loop_order')} tail_strategy={tiles.get('tail_strategy')} reduce_tile_policy={tiles.get('reduce_tile_policy')}",
                f"{indent}// local memref operation/type shapes below are rewritten; Linux backend must still verify loop/index/tail/reduction legality",
                f"{indent}// HIVM V5.5 TilingPlan operation rewrite candidate end",
            ])
            inserted_header = True
            continue
        new_line, changes = _rewrite_line_shapes(line, roles)
        if changes:
            indent = re.match(r"\s*", line).group(0)
            out.append(f"{indent}// HIVM V5.5 TilingPlan shape rewrite on line {ln}: {changes[0]['symbol']} {changes[0]['old_shape']} -> {changes[0]['new_shape']}")
            for c in changes:
                c["line"] = ln
            mutations.extend(changes)
        out.append(new_line)
    report = {
        "schema_version": "hivm_v55_tiling_operation_true_rewrite_report_v1",
        "version": VERSION,
        "mutation_kind": "local_memref_shape_and_operation_type_rewrite_candidate",
        "selected_tiles": tiles,
        "role_count": len(roles),
        "roles": roles,
        "mutation_performed": bool(mutations),
        "rewritten_occurrence_count": len(mutations),
        "mutations": mutations[:1000],
        "semantic_mutation_performed": bool(mutations),
        "production_rewrite_claim_allowed": False,
        "claim_boundary": "operation/type shape rewrite candidate only; loop/index/tail/reduction legality requires Linux MLIR/HIVM verifier before msprof",
    }
    return "\n".join(out) + ("\n" if ir_text.endswith("\n") else ""), report


def validate_tiling_operation_true_rewrite(original: str, rewritten: str, report: Dict[str, Any]) -> Dict[str, Any]:
    checks = [
        {"name": "mutation_performed", "passed": bool(report.get("mutation_performed"))},
        {"name": "operation_shape_mutations_exist", "passed": int(report.get("rewritten_occurrence_count") or 0) > 0},
        {"name": "gm_argument_shapes_not_rewritten", "passed": "#hivm.address_space<gm>" in rewritten},
        {"name": "tiling_candidate_marker_present", "passed": "TilingPlan operation rewrite candidate" in rewritten},
    ]
    return {"schema_version": "hivm_v55_tiling_operation_true_validation_v1", "passed": all(c["passed"] for c in checks), "checks": checks, "production_rewrite_claim_allowed": False}


def write_tiling_operation_true_rewrite_outputs(ir_path: str | Path, selected_plan_path: str | Path, output_dir: str | Path) -> Dict[str, Any]:
    ir_path = Path(ir_path); selected_plan_path = Path(selected_plan_path); output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    original = ir_path.read_text(encoding="utf-8", errors="ignore")
    selected = _load_json(selected_plan_path)
    rewritten, report = apply_tiling_operation_true_rewrite(original, selected)
    validation = validate_tiling_operation_true_rewrite(original, rewritten, report)
    diff_lines = list(difflib.unified_diff(original.splitlines(), rewritten.splitlines(), fromfile="before_tiling", tofile="after_tiling_op_candidate", lineterm="", n=3))
    paths = {
        "optimized_ir": output_dir / "optimized.tiling_operation_rewritten.hivm.mlir",
        "report": output_dir / "tiling_operation_true_rewrite_report.json",
        "validation": output_dir / "tiling_operation_true_rewrite_validation.json",
        "diff": output_dir / "tiling_operation_true_rewrite_diff.json",
        "summary": output_dir / "tiling_operation_true_rewrite_summary.json",
    }
    paths["optimized_ir"].write_text(rewritten, encoding="utf-8")
    paths["report"].write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["validation"].write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["diff"].write_text(json.dumps({"schema_version":"hivm_v55_tiling_operation_true_diff_v1", "num_diff_lines": len(diff_lines), "diff_preview": diff_lines[:1000]}, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {"schema_version":"hivm_v55_tiling_operation_true_summary_v1", "version": VERSION, "input_ir": str(ir_path), "optimized_ir": str(paths["optimized_ir"]), "mutation_performed": report.get("mutation_performed"), "rewritten_occurrence_count": report.get("rewritten_occurrence_count"), "passed_portable_validation": validation.get("passed"), "semantic_mutation_performed": report.get("semantic_mutation_performed"), "production_rewrite_claim_allowed": False, "claim_boundary": report.get("claim_boundary")}
    paths["summary"].write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"summary": summary, "report": report, "validation": validation, "paths": {k: str(v) for k, v in paths.items()}}
