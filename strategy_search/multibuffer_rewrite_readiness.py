# -*- coding: utf-8 -*-
"""MultiBufferPlan rewrite readiness and portable mutation-plan builder.

This module deliberately avoids pretending that we can safely clone/replace
HIVM buffers without the real MLIR verifier.  Instead it does the part that can
be made deterministic from text-level HIVM/NPU-IR today:

* identify buffer-like anchors, including real HIVM-style pointer_cast/subview
  chains rather than only memref.alloc;
* rank anchors for potential ping-pong/double-buffer rewrite;
* emit a conservative mutation_plan.json that is isomorphic to the future
  HivmOpsEditor implementation path;
* optionally create an annotated MLIR copy that marks proposed anchors but does
  not alter semantics.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

MULTIBUFFER_READINESS_VERSION = "hivm_multibuffer_rewrite_readiness_v1"
MULTIBUFFER_PORTABLE_ANNOTATION_VERSION = "hivm_multibuffer_portable_annotation_v1"

_ASSIGN_RE = re.compile(r"^\s*(?P<var>%[A-Za-z0-9_.$-]+)\s*=\s*(?P<expr>.*)$")
_POINTER_CAST_RE = re.compile(r"hivm\.hir\.pointer_cast\((?P<args>[^)]*)\)\s*:\s*(?P<type>.*)$")
_MEMREF_ALLOC_RE = re.compile(r"memref\.alloc(?:a)?\b.*:\s*(?P<type>memref<.*>)")
_MEMREF_SUBVIEW_RE = re.compile(r"memref\.subview\s+(?P<src>%[A-Za-z0-9_.$-]+).*:\s*(?P<type>.*)$")
_MEMREF_REINTERPRET_RE = re.compile(r"memref\.reinterpret_cast\s+(?P<src>%[A-Za-z0-9_.$-]+).*:\s*(?P<type>.*)$")
_MEMREF_CAST_RE = re.compile(r"memref\.cast\s+(?P<src>%[A-Za-z0-9_.$-]+).*:\s*(?P<type>.*)$")
_ADDR_SPACE_RE = re.compile(r"#hivm\.address_space<(?P<space>[^>]+)>")
_MEMREF_SHAPE_RE = re.compile(r"memref<(?P<body>[^,>]+)")
_HIVM_OP_RE = re.compile(r"hivm\.hir\.(?P<op>[A-Za-z0-9_]+)")

TRANSFER_OPS = {"load", "store", "nd2nz", "fixpipe"}
COMPUTE_OPS = {
    "mmadL1", "vadd", "vsub", "vmul", "vmax", "vexp", "vsel", "vcmp", "vcast",
    "vnot", "vand", "vbrc", "vreduce", "varange",
}
SYNC_OPS = {"set_flag", "wait_flag", "pipe_barrier", "sync_block_set", "sync_block_wait"}
LOCAL_SPACES = {"ub", "ubuf", "cbuf", "cc", "ca", "cb", "l0a", "l0b", "l0c"}
GM_SPACES = {"gm", "global"}


def _is_comment(line: str) -> bool:
    return line.strip().startswith("//")


def _addr_space(text: str) -> str:
    m = _ADDR_SPACE_RE.search(text or "")
    return (m.group("space").lower() if m else "unknown")


def _scope_from_space(space: str) -> str:
    s = (space or "unknown").lower()
    if s in {"ub", "ubuf"}:
        return "UB"
    if s == "cbuf":
        return "L1_CBUF"
    if s in {"cc", "l0c"}:
        return "L0C"
    if s in {"ca", "l0a"}:
        return "L0A"
    if s in {"cb", "l0b"}:
        return "L0B"
    if s in GM_SPACES:
        return "GM"
    return "UNKNOWN"


def _shape_rank(type_text: str) -> int | None:
    m = _MEMREF_SHAPE_RE.search(type_text or "")
    if not m:
        return None
    dims = [d.strip() for d in m.group("body").split("x")]
    dims = [d for d in dims if d and not d.startswith("#")]
    # Last token often embeds element type; treat known scalar element suffixes as not a dimension.
    if dims and re.search(r"[A-Za-z]", dims[-1]):
        dims = dims[:-1]
    return len(dims) if dims else None


def _extract_offsets_from_pointer_cast(args: str) -> List[str]:
    return [x.strip() for x in (args or "").split(",") if x.strip()]


def _classify_def(var: str, expr: str, line_no: int, line: str) -> Dict[str, Any] | None:
    m = _POINTER_CAST_RE.search(expr)
    if m:
        type_text = m.group("type")
        space = _addr_space(type_text)
        return {
            "id": f"buffer_anchor_{line_no}_{var[1:].replace('%','')}",
            "symbol": var,
            "line": line_no,
            "kind": "hivm_pointer_cast",
            "address_space": space,
            "scope": _scope_from_space(space),
            "type": type_text.strip(),
            "shape_rank": _shape_rank(type_text),
            "pointer_offsets": _extract_offsets_from_pointer_cast(m.group("args")),
            "text": line.strip()[:300],
            "source_symbol": None,
        }
    m = _MEMREF_ALLOC_RE.search(expr)
    if m:
        type_text = m.group("type")
        space = _addr_space(type_text)
        return {
            "id": f"buffer_anchor_{line_no}_{var[1:].replace('%','')}",
            "symbol": var,
            "line": line_no,
            "kind": "memref_alloc",
            "address_space": space,
            "scope": _scope_from_space(space),
            "type": type_text.strip(),
            "shape_rank": _shape_rank(type_text),
            "pointer_offsets": [],
            "text": line.strip()[:300],
            "source_symbol": None,
        }
    for kind, rx in [
        ("memref_subview", _MEMREF_SUBVIEW_RE),
        ("memref_reinterpret_cast", _MEMREF_REINTERPRET_RE),
        ("memref_cast", _MEMREF_CAST_RE),
    ]:
        m = rx.search(expr)
        if m:
            type_text = m.group("type")
            space = _addr_space(type_text)
            return {
                "id": f"buffer_view_{line_no}_{var[1:].replace('%','')}",
                "symbol": var,
                "line": line_no,
                "kind": kind,
                "address_space": space,
                "scope": _scope_from_space(space),
                "type": type_text.strip(),
                "shape_rank": _shape_rank(type_text),
                "pointer_offsets": [],
                "text": line.strip()[:300],
                "source_symbol": m.group("src"),
            }
    return None


def _ops_using_symbol(lines: List[str], symbol: str, def_line: int) -> Dict[str, Any]:
    var_rx = re.compile(r"(?<![A-Za-z0-9_.$-])" + re.escape(symbol) + r"(?![A-Za-z0-9_.$-])")
    uses: List[Dict[str, Any]] = []
    op_counts: Dict[str, int] = {}
    first_use = None
    last_use = None
    for i, line in enumerate(lines, start=1):
        if i == def_line or _is_comment(line):
            continue
        if not var_rx.search(line):
            continue
        op = "unknown"
        m = _HIVM_OP_RE.search(line)
        if m:
            op = f"hivm.hir.{m.group('op')}"
        elif "memref.subview" in line:
            op = "memref.subview"
        elif "memref.cast" in line:
            op = "memref.cast"
        elif "memref.reinterpret_cast" in line:
            op = "memref.reinterpret_cast"
        elif "memref.load" in line:
            op = "memref.load"
        elif "memref.store" in line:
            op = "memref.store"
        op_counts[op] = op_counts.get(op, 0) + 1
        first_use = i if first_use is None else min(first_use, i)
        last_use = i if last_use is None else max(last_use, i)
        uses.append({"line": i, "op": op, "text": line.strip()[:260]})
    return {
        "use_count": len(uses),
        "op_counts": op_counts,
        "first_use_line": first_use,
        "last_use_line": last_use,
        "live_line_span": (last_use - def_line) if last_use is not None else 0,
        "uses": uses[:120],
    }


def _score_anchor(anchor: Dict[str, Any], uses: Dict[str, Any], selected_plan: Dict[str, Any] | None) -> Dict[str, Any]:
    scope = anchor.get("scope")
    kind = anchor.get("kind")
    op_counts = uses.get("op_counts", {})
    use_count = int(uses.get("use_count") or 0)
    blockers: List[str] = []
    warnings: List[str] = []
    reasons: List[str] = []
    score = 0

    if scope == "GM":
        blockers.append("gm_buffer_is_source_sink_not_local_pingpong_target")
    elif scope == "UNKNOWN":
        blockers.append("unknown_address_space")
    elif scope in {"L1_CBUF", "UB"}:
        score += 30
        reasons.append("local_memory_scope_candidate")
    elif scope in {"L0A", "L0B", "L0C"}:
        score += 8
        warnings.append("l0_scope_is_compute_fragment_high_risk_for_multibuffer")
    else:
        warnings.append("unrecognized_local_scope_review_required")

    if kind == "hivm_pointer_cast":
        score += 20
        reasons.append("hivm_pointer_cast_anchor_matches_real_hivm_style")
    elif kind == "memref_alloc":
        score += 15
        reasons.append("explicit_alloc_anchor")
    elif kind and kind.startswith("memref_"):
        score += 6
        warnings.append("view_anchor_should_follow_base_buffer_before_mutation")

    transfer_hits = sum(v for k, v in op_counts.items() if any(k.endswith(x) for x in ["load", "store", "nd2nz", "fixpipe"]))
    compute_hits = sum(v for k, v in op_counts.items() if any(k.endswith(x) for x in COMPUTE_OPS))
    sync_hits = sum(v for k, v in op_counts.items() if any(k.endswith(x) for x in SYNC_OPS))
    view_hits = sum(v for k, v in op_counts.items() if k.startswith("memref."))

    if transfer_hits:
        score += min(25, 5 * transfer_hits)
        reasons.append("used_by_transfer_ops")
    if compute_hits:
        score += min(18, 3 * compute_hits)
        reasons.append("used_by_compute_ops")
    if view_hits:
        score += min(12, 2 * view_hits)
        reasons.append("has_view_chain")
    if sync_hits:
        warnings.append("sync_ops_reference_anchor_or_neighborhood_review_required")
    if use_count == 0:
        blockers.append("no_detected_uses")
    if uses.get("live_line_span", 0) > 400:
        warnings.append("long_live_range_may_increase_aliasing_risk")
    if anchor.get("shape_rank") is not None and anchor.get("shape_rank") <= 1:
        warnings.append("rank_le_1_buffer_less_likely_to_be_main_tile_buffer")

    knobs = ((selected_plan or {}).get("multibuffer_plan") or {}).get("controllable_knobs") or {}
    requested_double = bool(knobs.get("double_buffer"))
    if not requested_double:
        blockers.append("selected_multibuffer_plan_does_not_request_double_buffer")
    else:
        reasons.append("selected_plan_requests_double_buffer")
        score += 12

    if blockers:
        readiness = "BLOCKED"
    elif score >= 65 and not any("long_live" in w for w in warnings):
        readiness = "READY_FOR_GUARDED_PLAN"
    elif score >= 45:
        readiness = "REVIEW_REQUIRED"
    else:
        readiness = "LOW_PRIORITY"

    risk = "BLOCKED" if blockers else ("LOW" if readiness == "READY_FOR_GUARDED_PLAN" else "MEDIUM" if readiness == "REVIEW_REQUIRED" else "HIGH")
    return {
        "score": score,
        "readiness": readiness,
        "risk_level": risk,
        "reasons": reasons,
        "warnings": warnings,
        "blockers": blockers,
        "feature_counts": {
            "transfer_hits": transfer_hits,
            "compute_hits": compute_hits,
            "sync_hits": sync_hits,
            "view_hits": view_hits,
            "use_count": use_count,
        },
    }


def analyze_multibuffer_readiness(ir_text: str, selected_plan: Dict[str, Any] | None = None, max_candidates: int = 50) -> Dict[str, Any]:
    lines = ir_text.splitlines()
    anchors: List[Dict[str, Any]] = []
    for i, line in enumerate(lines, start=1):
        if _is_comment(line):
            continue
        m = _ASSIGN_RE.match(line)
        if not m:
            continue
        anchor = _classify_def(m.group("var"), m.group("expr"), i, line)
        if not anchor:
            continue
        uses = _ops_using_symbol(lines, anchor["symbol"], anchor["line"])
        score = _score_anchor(anchor, uses, selected_plan)
        anchor.update({"uses_summary": {k: v for k, v in uses.items() if k != "uses"}, "sample_uses": uses["uses"][:20]})
        anchor.update(score)
        anchors.append(anchor)

    anchors_sorted = sorted(anchors, key=lambda a: (a.get("readiness") == "READY_FOR_GUARDED_PLAN", a.get("score", 0)), reverse=True)
    counts: Dict[str, int] = {}
    scope_counts: Dict[str, int] = {}
    for a in anchors:
        counts[a["readiness"]] = counts.get(a["readiness"], 0) + 1
        scope_counts[a["scope"]] = scope_counts.get(a["scope"], 0) + 1

    selected = [a for a in anchors_sorted if a.get("readiness") in {"READY_FOR_GUARDED_PLAN", "REVIEW_REQUIRED"}][:max_candidates]
    return {
        "schema_version": MULTIBUFFER_READINESS_VERSION,
        "anchor_count": len(anchors),
        "readiness_counts": counts,
        "scope_counts": scope_counts,
        "selected_candidate_count": len(selected),
        "selected_candidates": selected,
        "all_candidates_preview": anchors_sorted[:200],
        "selected_plan_multibuffer_knobs": (((selected_plan or {}).get("multibuffer_plan") or {}).get("controllable_knobs") or {}),
        "claim_boundary": "readiness/mutation-plan only; no semantic buffer cloning or use replacement is performed without real verifier",
    }


def build_multibuffer_mutation_plan(readiness: Dict[str, Any]) -> Dict[str, Any]:
    actions: List[Dict[str, Any]] = []
    for idx, c in enumerate(readiness.get("selected_candidates", [])):
        action_id = f"multibuffer_plan_action_{idx:04d}"
        actions.append({
            "action_id": action_id,
            "mutation_kind": "double_buffer_candidate_plan",
            "status": "PLANNED_NOT_MUTATED",
            "risk_level": c.get("risk_level"),
            "readiness": c.get("readiness"),
            "target": {
                "symbol": c.get("symbol"),
                "line": c.get("line"),
                "kind": c.get("kind"),
                "scope": c.get("scope"),
                "address_space": c.get("address_space"),
                "type": c.get("type"),
                "text": c.get("text"),
            },
            "proposed_rewrite_steps": [
                "clone_or_create_ping_pong_buffer_slot_for_target_scope",
                "rewrite producer stage to write slot[iteration % 2]",
                "rewrite consumer stage to read slot[(iteration + required_lag) % 2]",
                "insert_or_reuse SyncPlan event edges between producer/consumer stages",
                "run real MLIR verifier and DES/trace validation before accepting",
            ],
            "hivmopseditor_migration": {
                "required_capabilities": [
                    "find_defining_operation_by_symbol_or_location",
                    "clone_pointer_cast_or_alloc_with_adjusted_offset",
                    "replace_uses_in_stage_region",
                    "insert_sync_edges_if_needed",
                    "exportToFile",
                    "mlir::verify",
                ],
                "current_status": "requires_real_operation_level_backend",
            },
            "blockers_before_real_mutation": [
                "need_dominance_and_alias_analysis",
                "need_loop_iteration_parity_expression",
                "need_producer_consumer_stage_boundary",
                "need_capacity_gate_for_extra_buffer_slot",
                "need_real_verifier",
            ],
        })
    decision = "MULTIBUFFER_REWRITE_PLAN_READY_NOT_MUTATED" if actions else "NO_SAFE_MULTIBUFFER_CANDIDATES"
    return {
        "schema_version": "hivm_multibuffer_mutation_plan_v1",
        "overall_decision": decision,
        "action_count": len(actions),
        "actions": actions,
        "production_rewrite_claim_allowed": False,
    }


def annotate_multibuffer_candidates(ir_text: str, mutation_plan: Dict[str, Any], max_annotations: int | None = None) -> Tuple[str, Dict[str, Any]]:
    """Return a semantically unchanged MLIR copy with comments above planned anchors."""
    lines = ir_text.splitlines()
    line_to_actions: Dict[int, List[Dict[str, Any]]] = {}
    actions = mutation_plan.get("actions", [])
    if max_annotations is not None:
        actions = actions[:max_annotations]
    for a in actions:
        target = a.get("target") or {}
        try:
            ln = int(target.get("line"))
        except Exception:
            continue
        line_to_actions.setdefault(ln, []).append(a)
    out: List[str] = []
    inserted = 0
    for i, line in enumerate(lines, start=1):
        for a in line_to_actions.get(i, []):
            target = a.get("target") or {}
            out.append(f"// HIVM V4.8 MultiBufferPlan candidate: {a.get('action_id')} risk={a.get('risk_level')} readiness={a.get('readiness')}")
            out.append(f"//   target={target.get('symbol')} scope={target.get('scope')} rewrite=planned_not_mutated")
            inserted += 1
        out.append(line)
    report = {
        "schema_version": MULTIBUFFER_PORTABLE_ANNOTATION_VERSION,
        "annotation_performed": inserted > 0,
        "inserted_annotation_count": inserted,
        "semantic_mutation_performed": False,
        "claim_boundary": "comments only; original IR operations are not changed",
    }
    return "\n".join(out) + ("\n" if ir_text.endswith("\n") else ""), report


def write_multibuffer_outputs(
    ir_path: str | Path,
    selected_plan_path: str | Path,
    output_dir: str | Path,
    max_candidates: int = 50,
    max_annotations: int | None = 20,
) -> Dict[str, Any]:
    ir_path = Path(ir_path)
    selected_plan_path = Path(selected_plan_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ir_text = ir_path.read_text(encoding="utf-8")
    selected_plan = json.loads(selected_plan_path.read_text(encoding="utf-8")) if selected_plan_path.exists() else {}
    readiness = analyze_multibuffer_readiness(ir_text, selected_plan, max_candidates=max_candidates)
    plan = build_multibuffer_mutation_plan(readiness)
    annotated, annotation_report = annotate_multibuffer_candidates(ir_text, plan, max_annotations=max_annotations)

    readiness_path = output_dir / "multibuffer_rewrite_readiness.json"
    plan_path = output_dir / "multibuffer_mutation_plan.json"
    annotated_path = output_dir / "multibuffer_annotated_not_mutated.hivm.mlir"
    annotation_report_path = output_dir / "multibuffer_annotation_report.json"
    summary_path = output_dir / "multibuffer_rewrite_readiness_summary.json"

    readiness_path.write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    annotated_path.write_text(annotated, encoding="utf-8")
    annotation_report_path.write_text(json.dumps(annotation_report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "version": "V4.8-multibuffer-rewrite-readiness",
        "schema_version": "hivm_multibuffer_rewrite_readiness_summary_v1",
        "input_ir": str(ir_path),
        "anchor_count": readiness.get("anchor_count"),
        "readiness_counts": readiness.get("readiness_counts"),
        "scope_counts": readiness.get("scope_counts"),
        "selected_candidate_count": readiness.get("selected_candidate_count"),
        "mutation_plan_action_count": plan.get("action_count"),
        "annotation_performed": annotation_report.get("annotation_performed"),
        "semantic_mutation_performed": False,
        "production_rewrite_claim_allowed": False,
        "next_step": "operation-level double-buffer mutation requires real verifier/dominance/alias/stage-boundary analysis",
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "readiness_path": str(readiness_path),
        "mutation_plan_path": str(plan_path),
        "annotated_ir_path": str(annotated_path),
        "annotation_report_path": str(annotation_report_path),
        "summary_path": str(summary_path),
        "summary": summary,
    }
