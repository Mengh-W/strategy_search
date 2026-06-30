# -*- coding: utf-8 -*-
"""TilingPlan operation-level readiness planner.

This module intentionally stops *before* unsafe text-level loop mutation.  It
turns selected TilingPlan knobs plus a conservative HIVM inventory into a
backend-consumable dry-run plan:

* identify loop / compute / load / store / buffer anchors;
* infer lightweight M/N/K axis evidence from memref shapes and conventional
  tensor names;
* produce per-parameter readiness levels;
* produce dry-run operation requests that a real MLIR/HivmOpsEditor backend can
  validate on Linux before any production mutation is enabled.

The output is stronger than metadata-only rewrite because every knob is mapped
to concrete anchor checks and mutation preconditions.  It is still not a claim
that Python has rewritten loop bounds/index maps/tail masks correctly.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .hivm_official_rewrite_plan import CUBE_OPS, DATA_MOVE_OPS, VECTOR_OPS, build_hivm_inventory

SCHEMA_VERSION = "hivm_tiling_operation_readiness_v1"

_MEMREF_RE = re.compile(r"memref<(?P<body>[^>]+)>")
_INT_DIMS_RE = re.compile(r"^-?\d+$")


def _load_json(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _plan_knobs(selected_plan: Dict[str, Any]) -> Dict[str, Any]:
    tp = selected_plan.get("tiling_plan") or {}
    knobs = dict(tp.get("controllable_knobs") or tp.get("selected_knobs") or tp.get("knobs") or {})
    # Keep compatibility with old selected_plan variants.
    for k in ["tile_m", "tile_n", "tile_k", "loop_order", "tail_strategy", "reduce_tile_policy", "layout_aware_tile"]:
        if k not in knobs and k in tp:
            knobs[k] = tp[k]
    for k in ["tile_m", "tile_n", "tile_k"]:
        try:
            if knobs.get(k) is not None:
                knobs[k] = int(knobs[k])
        except Exception:
            pass
    return knobs


def parse_memref_shape(type_text: str) -> List[int]:
    """Extract static integer dims from a memref type, ignoring dtype/layout."""
    m = _MEMREF_RE.search(type_text or "")
    if not m:
        return []
    body = m.group("body")
    # Shape dims appear before dtype.  In current samples this is 64x128xf16,
    # 64x128xf32, etc.  Dynamic dims are deliberately ignored.
    dims: List[int] = []
    for part in body.split(",", 1)[0].split("x"):
        part = part.strip()
        if _INT_DIMS_RE.match(part):
            dims.append(int(part))
        else:
            break
    return dims


def _buffer_shape_map(inventory: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for b in inventory.get("buffers", []):
        shape = parse_memref_shape(b.get("type_text") or b.get("text") or "")
        out[b.get("name", "")] = {**b, "shape": shape}
    return out


def _op_kind(op: Dict[str, Any]) -> str:
    name = op.get("op")
    if name in CUBE_OPS:
        return "cube_compute"
    if name in VECTOR_OPS:
        return "vector_compute"
    if name in DATA_MOVE_OPS or name in {"hivm.hir.load", "hivm.hir.store"}:
        return "data_movement"
    return "other"


def _shape_role_from_name(name: str, shape: List[int]) -> List[str]:
    n = name.lower().lstrip("%")
    roles: List[str] = []
    if not shape:
        return roles
    if n.startswith("q") or n.startswith("o") or "acc" in n:
        roles.append("m_axis_candidate_from_first_dim")
        if len(shape) >= 2:
            roles.append("k_or_d_axis_candidate_from_second_dim")
    if n.startswith("k") or n.startswith("v"):
        roles.append("n_or_sequence_axis_candidate_from_first_dim")
        if len(shape) >= 2:
            roles.append("k_or_d_axis_candidate_from_second_dim")
    if n.startswith("s") or n.startswith("p"):
        roles.append("m_axis_candidate_from_first_dim")
        if len(shape) >= 2:
            roles.append("n_tile_axis_candidate_from_second_dim")
    return roles


def build_axis_evidence(selected_knobs: Dict[str, Any], inventory: Dict[str, Any]) -> Dict[str, Any]:
    buffers = _buffer_shape_map(inventory)
    tile_m, tile_n, tile_k = selected_knobs.get("tile_m"), selected_knobs.get("tile_n"), selected_knobs.get("tile_k")
    evidence_buffers: List[Dict[str, Any]] = []
    for name, b in sorted(buffers.items(), key=lambda kv: (kv[1].get("line", 0), kv[0])):
        shape = b.get("shape") or []
        roles = _shape_role_from_name(name, shape)
        matches = {
            "dim_matches_tile_m": tile_m in shape if isinstance(tile_m, int) else False,
            "dim_matches_tile_n": tile_n in shape if isinstance(tile_n, int) else False,
            "dim_matches_tile_k": tile_k in shape if isinstance(tile_k, int) else False,
        }
        if roles or any(matches.values()):
            evidence_buffers.append({
                "buffer": name,
                "line": b.get("line"),
                "space": b.get("space"),
                "shape": shape,
                "type_text": b.get("type_text"),
                "name_based_axis_roles": roles,
                "selected_tile_dim_matches": matches,
            })

    conventional = {
        "q_like_buffers": [b for b in evidence_buffers if b["buffer"].lower().lstrip("%").startswith("q")],
        "k_like_buffers": [b for b in evidence_buffers if b["buffer"].lower().lstrip("%").startswith("k")],
        "v_like_buffers": [b for b in evidence_buffers if b["buffer"].lower().lstrip("%").startswith("v")],
        "score_or_prob_buffers": [b for b in evidence_buffers if b["buffer"].lower().lstrip("%").startswith(("s", "p"))],
    }
    confidence = "LOW"
    if conventional["q_like_buffers"] and conventional["k_like_buffers"] and conventional["v_like_buffers"]:
        confidence = "MEDIUM"
    if evidence_buffers and all(isinstance(selected_knobs.get(k), int) for k in ["tile_m", "tile_n", "tile_k"]):
        if any(b["selected_tile_dim_matches"]["dim_matches_tile_m"] for b in evidence_buffers) and any(b["selected_tile_dim_matches"]["dim_matches_tile_k"] for b in evidence_buffers):
            confidence = "MEDIUM_HIGH" if confidence == "MEDIUM" else "MEDIUM"
    return {
        "axis_evidence_version": "tiling_axis_evidence_v1",
        "confidence": confidence,
        "evidence_buffers": evidence_buffers[:80],
        "conventional_tensor_groups": {k: v[:20] for k, v in conventional.items()},
        "notes": [
            "name/shape evidence only; backend must confirm exact indexing maps and logical axes",
            "axis evidence is sufficient for Linux anchor validation, not sufficient for production loop rewrite",
        ],
    }


def _ops_named(inventory: Dict[str, Any], names: Iterable[str]) -> List[Dict[str, Any]]:
    s = set(names)
    return [op for op in inventory.get("operations", []) if op.get("op") in s]


def build_tiling_operation_anchors(selected_knobs: Dict[str, Any], inventory: Dict[str, Any]) -> Dict[str, Any]:
    buffers = _buffer_shape_map(inventory)
    cube_ops = _ops_named(inventory, CUBE_OPS)
    vector_ops = _ops_named(inventory, VECTOR_OPS)
    loads = _ops_named(inventory, ["hivm.hir.load"])
    stores = _ops_named(inventory, ["hivm.hir.store"])
    loops = inventory.get("loops", [])

    def enrich_op(op: Dict[str, Any]) -> Dict[str, Any]:
        ins = []
        outs = []
        for v in op.get("inputs", []):
            if v in buffers:
                ins.append({"value": v, "shape": buffers[v].get("shape"), "space": buffers[v].get("space")})
            else:
                ins.append({"value": v, "shape": [], "space": "unknown_or_func_arg"})
        for v in op.get("outputs", []):
            if v in buffers:
                outs.append({"value": v, "shape": buffers[v].get("shape"), "space": buffers[v].get("space")})
            else:
                outs.append({"value": v, "shape": [], "space": "unknown_or_func_arg"})
        return {"line": op.get("line"), "op": op.get("op"), "kind": _op_kind(op), "text": op.get("text"), "inputs": ins, "outputs": outs}

    return {
        "anchor_version": "tiling_operation_anchor_scan_v1",
        "loops": loops,
        "compute_ops": [enrich_op(op) for op in cube_ops + vector_ops],
        "cube_compute_ops": [enrich_op(op) for op in cube_ops],
        "vector_compute_ops": [enrich_op(op) for op in vector_ops],
        "load_ops": [enrich_op(op) for op in loads],
        "store_ops": [enrich_op(op) for op in stores],
        "candidate_buffers": [
            {"name": name, "line": b.get("line"), "space": b.get("space"), "shape": b.get("shape"), "type_text": b.get("type_text")}
            for name, b in sorted(buffers.items(), key=lambda kv: (kv[1].get("line", 0), kv[0]))
            if b.get("shape")
        ],
    }


def _tile_tail_relation(total: Optional[int], tile: Any) -> Dict[str, Any]:
    if not isinstance(total, int) or not isinstance(tile, int) or tile <= 0:
        return {"known": False, "needs_tail_guard": True, "reason": "unknown_total_or_tile"}
    return {
        "known": True,
        "total": total,
        "tile": tile,
        "num_full_tiles": total // tile,
        "tail": total % tile,
        "needs_tail_guard": total % tile != 0,
    }


def _guess_problem_totals(axis_evidence: Dict[str, Any]) -> Dict[str, Optional[int]]:
    # Conservative, name/shape-based.  For FA-like samples: q first dim -> M;
    # k first dim -> N/sequence; q/k second dim -> K or D.
    groups = axis_evidence.get("conventional_tensor_groups", {})
    q = (groups.get("q_like_buffers") or [])
    k = (groups.get("k_like_buffers") or [])
    totals: Dict[str, Optional[int]] = {"m_total": None, "n_total": None, "k_total": None}
    if q and q[0].get("shape"):
        sh = q[0]["shape"]
        if len(sh) >= 1:
            totals["m_total"] = sh[0]
        if len(sh) >= 2:
            totals["k_total"] = sh[1]
    if k and k[0].get("shape"):
        sh = k[0]["shape"]
        if len(sh) >= 1:
            totals["n_total"] = sh[0]
        if totals.get("k_total") is None and len(sh) >= 2:
            totals["k_total"] = sh[1]
    return totals


def build_tiling_dry_run_plan(selected_knobs: Dict[str, Any], anchors: Dict[str, Any], axis_evidence: Dict[str, Any]) -> Dict[str, Any]:
    tile_m, tile_n, tile_k = selected_knobs.get("tile_m"), selected_knobs.get("tile_n"), selected_knobs.get("tile_k")
    totals = _guess_problem_totals(axis_evidence)
    loop_order = selected_knobs.get("loop_order") or "preserve_existing"
    tail_strategy = selected_knobs.get("tail_strategy") or "preserve_existing_tail_behavior"
    reduce_policy = selected_knobs.get("reduce_tile_policy") or "preserve_existing_reduce_tile_policy"

    loop_split_requests = [
        {"axis": "m", "tile": tile_m, "total_evidence": totals.get("m_total"), "tail_relation": _tile_tail_relation(totals.get("m_total"), tile_m)},
        {"axis": "n", "tile": tile_n, "total_evidence": totals.get("n_total"), "tail_relation": _tile_tail_relation(totals.get("n_total"), tile_n)},
        {"axis": "k", "tile": tile_k, "total_evidence": totals.get("k_total"), "tail_relation": _tile_tail_relation(totals.get("k_total"), tile_k), "is_reduction_axis_candidate": True},
    ]

    slice_requests: List[Dict[str, Any]] = []
    for op_group, axis_hint in [("load_ops", "load_slice"), ("store_ops", "store_slice"), ("cube_compute_ops", "compute_tile"), ("vector_compute_ops", "vector_tile")]:
        for op in anchors.get(op_group, []):
            slice_requests.append({
                "request_kind": axis_hint,
                "op_line": op.get("line"),
                "op": op.get("op"),
                "inputs": op.get("inputs", []),
                "outputs": op.get("outputs", []),
                "requires_backend_indexing_map": True,
            })

    blockers: List[str] = []
    if not anchors.get("loops"):
        blockers.append("no_loop_anchor_found")
    if not anchors.get("cube_compute_ops"):
        blockers.append("no_cube_compute_anchor_found")
    if not (anchors.get("load_ops") and anchors.get("store_ops")):
        blockers.append("load_or_store_anchor_missing")
    if not all(isinstance(selected_knobs.get(k), int) for k in ["tile_m", "tile_n", "tile_k"]):
        blockers.append("tile_m_n_k_not_all_static_integers")
    if axis_evidence.get("confidence") in {"LOW"}:
        blockers.append("axis_mapping_confidence_low_backend_must_resolve")

    return {
        "dry_run_plan_version": "tiling_operation_dry_run_plan_v1",
        "status": "READY_FOR_LINUX_BACKEND_ANCHOR_DRY_RUN" if not blockers or blockers == ["axis_mapping_confidence_low_backend_must_resolve"] else "BLOCKED_UNTIL_BACKEND_ANCHORS_RESOLVED",
        "selected_tiles": {"tile_m": tile_m, "tile_n": tile_n, "tile_k": tile_k},
        "requested_loop_order": loop_order,
        "requested_tail_strategy": tail_strategy,
        "requested_reduce_tile_policy": reduce_policy,
        "problem_totals_from_evidence": totals,
        "loop_split_requests": loop_split_requests,
        "slice_rewrite_requests": slice_requests[:80],
        "tail_guard_requests": [r for r in loop_split_requests if r.get("tail_relation", {}).get("needs_tail_guard")],
        "reduction_requests": [{
            "axis": "k",
            "policy": reduce_policy,
            "must_prove": [
                "partial_accumulator_initialization_is_preserved",
                "partial_accumulator_update_order_is_preserved",
                "final_store_occurs_after_all_k_tiles",
            ],
        }],
        "blockers_or_backend_required": blockers,
        "mutation_disabled_in_python": True,
        "backend_mutation_kind": "tiling_loop_index_slice_tailmask_rewrite_dry_run",
    }


def build_parameter_readiness(selected_knobs: Dict[str, Any], dry_run_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    base_status = dry_run_plan.get("status")
    has_anchor_dry_run = base_status in {"READY_FOR_LINUX_BACKEND_ANCHOR_DRY_RUN", "BLOCKED_UNTIL_BACKEND_ANCHORS_RESOLVED"}
    specs = [
        ("tile_m", "LEVEL_2_DRY_RUN_OPERATION_PLAN", "loop split on M + load/store/compute slice request"),
        ("tile_n", "LEVEL_2_DRY_RUN_OPERATION_PLAN", "loop split on N + load/store/compute slice request"),
        ("tile_k", "LEVEL_2_DRY_RUN_OPERATION_PLAN", "reduction-loop split + partial accumulation proof request"),
        ("loop_order", "LEVEL_1_BACKEND_ANCHOR_VALIDATION", "loop permutation legality check; mutation deferred"),
        ("tail_strategy", "LEVEL_1_BACKEND_ANCHOR_VALIDATION", "tail guard/mask semantics check; mutation deferred"),
        ("reduce_tile_policy", "LEVEL_1_BACKEND_ANCHOR_VALIDATION", "reduction accumulation policy check; mutation deferred"),
        ("layout_aware_tile", "LEVEL_1_BACKEND_ANCHOR_VALIDATION", "layout-sensitive tile-shape proof; mutation deferred"),
    ]
    out = []
    for name, level, meaning in specs:
        present = name in selected_knobs
        out.append({
            "parameter": name,
            "selected_value": selected_knobs.get(name),
            "present_in_selected_plan": present,
            "readiness_level": level if present or name in {"tile_m", "tile_n", "tile_k"} else "NOT_SELECTED",
            "linux_prevalidation_status": "READY_FOR_LINUX_DRY_RUN" if has_anchor_dry_run and present else ("MISSING_FROM_SELECTED_PLAN" if not present else "NEEDS_BACKEND_ANCHOR_RESOLUTION"),
            "operation_level_claim": "dry_run_plan_only_no_python_mutation",
            "meaning": meaning,
        })
    return out


def build_tiling_operation_readiness(selected_plan: Dict[str, Any], inventory: Dict[str, Any]) -> Dict[str, Any]:
    knobs = _plan_knobs(selected_plan)
    anchors = build_tiling_operation_anchors(knobs, inventory)
    axis_evidence = build_axis_evidence(knobs, inventory)
    dry_run_plan = build_tiling_dry_run_plan(knobs, anchors, axis_evidence)
    params = build_parameter_readiness(knobs, dry_run_plan)
    return {
        "schema_version": SCHEMA_VERSION,
        "plan": "TilingPlan",
        "selected_knobs": knobs,
        "overall_status": dry_run_plan.get("status"),
        "readiness_meaning": "Linux backend prevalidation is now prepared: anchor scan + axis evidence + dry-run operation mutation requests. Python still does not rewrite loop/index/slice/tail semantics.",
        "operation_anchors": anchors,
        "axis_evidence": axis_evidence,
        "dry_run_operation_plan": dry_run_plan,
        "parameter_readiness": params,
        "must_prove_on_linux_before_true_mutation": [
            "MLIR parser can resolve the recorded loop/compute/load/store anchors",
            "backend can map logical M/N/K axes to actual induction variables and indexing maps",
            "backend can materialize loop split without changing tensor semantics",
            "backend can rewrite load/store slices and compute shapes consistently",
            "tail mask or padding semantics are explicit and verified",
            "reduction partial accumulation is preserved for tile_k changes",
            "roundtrip + verifier pass after a guarded single-parameter mutation",
        ],
        "linux_validation_commands": [
            "python tools/build_four_plan_rewrite_readiness.py --ir <input.hivm.mlir> --selected-plan <selected_plan.json> --output-dir artifacts/latest_rewrite_readiness",
            "python tools/run_tiling_operation_readiness.py --ir <input.hivm.mlir> --selected-plan <selected_plan.json> --output-dir artifacts/latest_tiling_operation_readiness",
            "# then on Linux backend: run inventory/roundtrip/verify before enabling any loop/index mutation",
        ],
        "production_rewrite_claim_allowed": False,
    }


def write_tiling_operation_readiness_outputs(ir_path: str | Path, selected_plan_path: str | Path, output_dir: str | Path) -> Dict[str, Any]:
    ir_path = Path(ir_path)
    selected_plan_path = Path(selected_plan_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ir_text = ir_path.read_text(encoding="utf-8", errors="ignore")
    selected_plan = _load_json(selected_plan_path)
    inventory = build_hivm_inventory(ir_text, source_name=str(ir_path))
    report = build_tiling_operation_readiness(selected_plan, inventory)
    paths = {
        "inventory": output_dir / "hivm_ir_inventory.official.json",
        "report": output_dir / "tiling_operation_readiness.json",
        "dry_run_plan": output_dir / "tiling_operation_dry_run_plan.json",
        "parameter_readiness": output_dir / "tiling_parameter_readiness.json",
        "summary": output_dir / "tiling_operation_readiness_summary.json",
    }
    summary = {
        "schema_version": "tiling_operation_readiness_summary_v1",
        "overall_status": report.get("overall_status"),
        "selected_knobs": report.get("selected_knobs"),
        "parameter_count": len(report.get("parameter_readiness") or []),
        "ready_for_linux_dry_run_count": sum(1 for p in report.get("parameter_readiness") or [] if p.get("linux_prevalidation_status") == "READY_FOR_LINUX_DRY_RUN"),
        "loop_anchor_count": len(report.get("operation_anchors", {}).get("loops") or []),
        "compute_anchor_count": len(report.get("operation_anchors", {}).get("compute_ops") or []),
        "load_anchor_count": len(report.get("operation_anchors", {}).get("load_ops") or []),
        "store_anchor_count": len(report.get("operation_anchors", {}).get("store_ops") or []),
        "axis_evidence_confidence": report.get("axis_evidence", {}).get("confidence"),
        "production_rewrite_claim_allowed": False,
    }
    paths["inventory"].write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["report"].write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["dry_run_plan"].write_text(json.dumps(report["dry_run_operation_plan"], ensure_ascii=False, indent=2), encoding="utf-8")
    paths["parameter_readiness"].write_text(json.dumps(report["parameter_readiness"], ensure_ascii=False, indent=2), encoding="utf-8")
    paths["summary"].write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"summary": summary, "paths": {k: str(v) for k, v in paths.items()}, "report": report}
