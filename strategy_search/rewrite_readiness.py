# -*- coding: utf-8 -*-
"""Four-Plan rewrite readiness reports.

This module sits between the strategy search result and the real
vTriton/HivmOpsEditor backend.  It does not mutate HIVM IR.  Its job is to
turn:

  selected_plan.json + official-doc-guided HIVM inventory

into four small, auditable reports answering:

  * which concrete IR anchors could this Plan affect?
  * what backend mutation would be requested?
  * what is still blocking a true mutation?

The reports are intentionally conservative.  They should be treated as the
"construction checklist" before calling a real HivmOpsEditor mutation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .hivm_official_rewrite_plan import (
    CUBE_OPS,
    DATA_MOVE_OPS,
    LAYOUT_OPS,
    SYNC_OPS,
    VECTOR_OPS,
    build_four_plan_rewrite_plan,
    build_hivm_inventory,
)
from .tiling_operation_readiness import build_tiling_operation_readiness


LOCAL_BUFFER_SPACES = {"ub", "cbuf", "l1", "l0a", "l0b", "l0c", "cc"}


def _plan_knobs(selected_plan: Dict[str, Any], plan_key: str) -> Dict[str, Any]:
    return dict(selected_plan.get(plan_key, {}).get("controllable_knobs", {}) or {})


def _ops_named(inventory: Dict[str, Any], names: Iterable[str]) -> List[Dict[str, Any]]:
    names = set(names)
    return [op for op in inventory.get("operations", []) if op.get("op") in names]


def _ops_with_role(inventory: Dict[str, Any], role: str) -> List[Dict[str, Any]]:
    return [op for op in inventory.get("operations", []) if role in op.get("roles", [])]


def _local_buffers(inventory: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [b for b in inventory.get("buffers", []) if b.get("space") in LOCAL_BUFFER_SPACES]


def _buffer_use_map(inventory: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build a lightweight text-level use map from operation ins/outs.

    This is not a replacement for MLIR SSA use-def.  It is enough for readable
    readiness reports and for deciding which buffers need real backend
    resolution.
    """
    usage: Dict[str, Dict[str, Any]] = {}
    for b in inventory.get("buffers", []):
        usage[b["name"]] = {
            "buffer": b,
            "producer_ops": [],
            "consumer_ops": [],
            "unknown_use_count": 0,
        }
    for op in inventory.get("operations", []):
        for v in op.get("outputs", []):
            if v in usage:
                usage[v]["producer_ops"].append({"line": op["line"], "op": op["op"], "text": op["text"]})
        for v in op.get("inputs", []):
            if v in usage:
                usage[v]["consumer_ops"].append({"line": op["line"], "op": op["op"], "text": op["text"]})
    return usage


def _status(ok: bool, blocked: bool = False) -> str:
    if blocked:
        return "BLOCKED_OR_BACKEND_REQUIRED"
    return "READY_FOR_BACKEND_DRY_RUN" if ok else "REPORT_ONLY"


def build_sync_readiness(selected_plan: Dict[str, Any], inventory: Dict[str, Any]) -> Dict[str, Any]:
    knobs = _plan_knobs(selected_plan, "sync_plan")
    sync_ops = _ops_named(inventory, SYNC_OPS)
    barriers = [op for op in sync_ops if op.get("op") in {"hivm.hir.pipe_barrier", "hivm.hir.barrier"} or "barrier" in op.get("text", "")]
    event_ops = [op for op in sync_ops if op.get("op") in {"hivm.hir.set_flag", "hivm.hir.wait_flag"}]
    producer_ops = _ops_named(inventory, ["hivm.hir.load", "hivm.hir.nd2nz", "hivm.hir.copy"] + list(CUBE_OPS))
    consumer_ops = _ops_named(inventory, list(CUBE_OPS) + list(VECTOR_OPS) + ["hivm.hir.store"])
    unknown_ops = inventory.get("summary", {}).get("unknown_hivm_ops", [])

    requested = knobs.get("policy") in {"graph_sync_solver", "directional_event"} or knobs.get("remove_redundant_sync")
    blockers: List[str] = []
    if unknown_ops:
        blockers.append("unknown_hivm_ops_present_in_file; true sync mutation must avoid/understand those regions")
    if not sync_ops:
        blockers.append("no_sync_anchor_found")
    if not requested:
        blockers.append("selected_plan_does_not_request_directional_or_redundant_sync_rewrite")

    return {
        "plan": "SyncPlan",
        "purpose": "把粗粒度 barrier/pipe barrier 转成更细粒度的 set_flag/wait_flag，或者删除冗余同步。",
        "selected_knobs": knobs,
        "anchors": {
            "sync_ops": sync_ops,
            "barrier_like_ops": barriers,
            "existing_event_ops": event_ops,
            "possible_producer_ops": producer_ops[:16],
            "possible_consumer_ops": consumer_ops[:16],
        },
        "backend_mutation_request_template": {
            "mutation_kind": "sync_barrier_to_directional_event_or_sync_cleanup",
            "input_policy": knobs.get("policy"),
            "event_id_policy": knobs.get("event_id_policy"),
            "sync_motion": knobs.get("sync_motion"),
            "remove_redundant_sync": knobs.get("remove_redundant_sync"),
            "must_use_backend_to_print_event_ops": True,
        },
        "must_prove_before_mutate": [
            "producer_consumer_pair_proven_by_backend_or_DES_graph",
            "fresh_or_non_overlapping_event_id",
            "no_wait_before_set_deadlock",
            "no_cross_iteration_dependency_removed",
            "roundtrip_and_verify_pass",
        ],
        "blocked_or_missing": blockers,
        "status": _status(bool(sync_ops and requested), bool(blockers)),
    }


def _candidate_buffer_score(name: str) -> int:
    n = name.lower()
    score = 0
    for token in ["q", "k", "v", "ub", "l1", "ping", "pong", "softmax", "logits", "p_"]:
        if token in n:
            score += 1
    return score


def build_multibuffer_readiness(selected_plan: Dict[str, Any], inventory: Dict[str, Any]) -> Dict[str, Any]:
    knobs = _plan_knobs(selected_plan, "multibuffer_plan")
    buffers = _local_buffers(inventory)
    use_map = _buffer_use_map(inventory)
    requested = bool(knobs.get("double_buffer")) or (knobs.get("input_buffer_multiplier") or 1) > 1 or (knobs.get("stage_buffer_multiplier") or 1) > 1
    unknown_ops = inventory.get("summary", {}).get("unknown_hivm_ops", [])

    candidates: List[Dict[str, Any]] = []
    for b in sorted(buffers, key=lambda x: (-_candidate_buffer_score(x.get("name", "")), x.get("line", 0))):
        name = b["name"]
        usage = use_map.get(name, {})
        score = _candidate_buffer_score(name)
        if score <= 0 and b.get("space") not in {"ub", "cbuf", "l1"}:
            continue
        producer_ops = usage.get("producer_ops", [])
        consumer_ops = usage.get("consumer_ops", [])
        candidates.append({
            "buffer": b,
            "candidate_score": score,
            "producer_ops": producer_ops[:8],
            "consumer_ops": consumer_ops[:8],
            "backend_clone_request": {
                "mutation_kind": "clone_local_buffer_slots",
                "target_buffer": name,
                "requested_slots": max(int(knobs.get("input_buffer_multiplier") or 1), int(knobs.get("stage_buffer_multiplier") or 1), 2 if knobs.get("double_buffer") else 1),
                "replacement_policy": knobs.get("stage_buffer_policy") or "pingpong_if_loop_index_available_else_report_only",
            },
            "local_legality_observation": {
                "has_known_local_address_space": b.get("space") in LOCAL_BUFFER_SPACES,
                "has_observed_producer_or_consumer": bool(producer_ops or consumer_ops),
                "requires_backend_use_def_resolution": True,
            },
        })

    blockers: List[str] = []
    if unknown_ops:
        blockers.append("unknown_hivm_ops_present; true buffer clone must verify all uses in backend")
    if not requested:
        blockers.append("selected_plan_does_not_request_extra_buffer_slots")
    if not candidates:
        blockers.append("no_local_buffer_candidate_found")

    return {
        "plan": "MultiBufferPlan",
        "purpose": "把 nbuf/double_buffer 从 hint 变成真实 buffer slot clone 与 operand 替换。",
        "selected_knobs": knobs,
        "anchors": {
            "candidate_buffers": candidates[:32],
            "num_local_buffers": len(buffers),
        },
        "backend_mutation_request_template": {
            "mutation_kind": "clone_local_buffers_and_replace_uses",
            "requires_iteration_or_stage_policy": True,
            "requires_capacity_recheck": True,
            "requires_backend_use_def_resolution": True,
        },
        "must_prove_before_mutate": [
            "all_uses_resolved_by_MLIR_use_def",
            "target_buffer_does_not_escape_to_unknown_side_effect_op",
            "capacity_recheck_passes_after_extra_slots",
            "buffer_liveness_no_overwrite",
            "roundtrip_and_verify_pass",
        ],
        "blocked_or_missing": blockers,
        "status": _status(bool(candidates and requested), bool(blockers)),
    }


def build_cv_pipeline_readiness(selected_plan: Dict[str, Any], inventory: Dict[str, Any]) -> Dict[str, Any]:
    knobs = _plan_knobs(selected_plan, "cv_pipeline_plan")
    loads = _ops_named(inventory, ["hivm.hir.load"])
    layout = _ops_named(inventory, LAYOUT_OPS)
    copies = _ops_named(inventory, ["hivm.hir.copy"])
    cube = _ops_named(inventory, CUBE_OPS)
    vector = _ops_named(inventory, VECTOR_OPS)
    fixpipe = _ops_named(inventory, ["hivm.hir.fixpipe"])
    stores = _ops_named(inventory, ["hivm.hir.store"])
    sync_ops = _ops_named(inventory, SYNC_OPS)
    stage_ops = sorted(loads + layout + copies + cube + vector + fixpipe + stores + sync_ops, key=lambda o: o.get("line", 0))
    stage_sequence = []
    for op in stage_ops:
        stage = "unknown"
        if op["op"] == "hivm.hir.load":
            stage = "load"
        elif op["op"] in LAYOUT_OPS or op["op"] == "hivm.hir.copy":
            stage = "transform_or_copy"
        elif op["op"] in CUBE_OPS:
            stage = "cube_compute"
        elif op["op"] in VECTOR_OPS:
            stage = "vector_compute"
        elif op["op"] == "hivm.hir.fixpipe":
            stage = "fixpipe"
        elif op["op"] == "hivm.hir.store":
            stage = "store"
        elif op["op"] in SYNC_OPS:
            stage = "sync"
        stage_sequence.append({"line": op["line"], "stage": stage, "op": op["op"], "text": op["text"]})

    requested = int(knobs.get("stage_num") or 1) > 1
    has_basic_stage_pattern = bool(loads and cube and (stores or fixpipe or vector))
    blockers: List[str] = []
    if not requested:
        blockers.append("selected_plan_stage_num_is_1")
    if not has_basic_stage_pattern:
        blockers.append("load_compute_store_or_fixpipe_stage_pattern_not_detected")
    if not sync_ops:
        blockers.append("no_sync_ops_available_for_stage_boundary; backend_may_need_to_insert_fresh_events")

    return {
        "plan": "CVPipelinePlan",
        "purpose": "把 load/transform/compute/store 拆成流水 stage；真实 overlap 依赖 MultiBuffer ping-pong 与 SyncPlan event。",
        "selected_knobs": knobs,
        "anchors": {
            "stage_sequence_by_line": stage_sequence,
            "load_ops": loads,
            "layout_ops": layout,
            "copy_ops": copies,
            "cube_ops": cube,
            "vector_ops": vector,
            "fixpipe_ops": fixpipe,
            "store_ops": stores,
            "sync_ops": sync_ops,
        },
        "backend_mutation_request_template": {
            "mutation_kind": "cv_pipeline_stage_reorder",
            "requested_stage_num": knobs.get("stage_num"),
            "producer_consumer_distance": knobs.get("producer_consumer_distance"),
            "requires_multibuffer_pingpong": True,
            "requires_syncplan_events": True,
        },
        "must_prove_before_mutate": [
            "stage_dependency_is_linear_or_backend_can_schedule",
            "no_cross_tile_reduction_or_side_effect_blocks_reorder",
            "pingpong_buffer_available_for_prefetch_or_overlap",
            "prologue_steady_state_epilogue_constructed",
            "DES_or_trace_shows_expected_overlap_before_claiming_pipeline_success",
        ],
        "blocked_or_missing": blockers,
        "status": _status(bool(requested and has_basic_stage_pattern), bool(blockers and blockers != ["no_sync_ops_available_for_stage_boundary; backend_may_need_to_insert_fresh_events"])),
    }


def build_tiling_readiness(selected_plan: Dict[str, Any], inventory: Dict[str, Any]) -> Dict[str, Any]:
    """Build TilingPlan Linux prevalidation readiness.

    Earlier versions reported TilingPlan as hint-only.  This version upgrades it
    to a conservative operation-readiness dry-run: it still refuses Python
    text-level loop/index mutation, but it now exposes concrete loop/compute/
    load/store anchors, axis evidence, and backend mutation requests for Linux
    prevalidation.
    """
    operation_report = build_tiling_operation_readiness(selected_plan, inventory)
    knobs = operation_report.get("selected_knobs", {})
    anchors = operation_report.get("operation_anchors", {})
    dry_run = operation_report.get("dry_run_operation_plan", {})

    blockers: List[str] = list(dry_run.get("blockers_or_backend_required") or [])
    # Keep the honest boundary in the old field name, but do not downgrade the
    # status to report-only when anchors are available.
    blockers.append("production_loop_index_slice_tailmask_mutation_still_backend_required")

    return {
        "plan": "TilingPlan",
        "purpose": "把 tile_m/tile_n/tile_k 从策略参数推进到 Linux backend 可检查的 loop split、index remap、load/store slice、tail mask dry-run 计划。",
        "selected_knobs": knobs,
        "anchors": {
            "loop_ops": anchors.get("loops", []),
            "cube_compute_ops": anchors.get("cube_compute_ops", []),
            "vector_compute_ops": anchors.get("vector_compute_ops", []),
            "load_ops": anchors.get("load_ops", []),
            "store_ops": anchors.get("store_ops", []),
            "candidate_buffers": anchors.get("candidate_buffers", []),
        },
        "axis_evidence": operation_report.get("axis_evidence", {}),
        "backend_mutation_request_template": {
            "mutation_kind": "tiling_loop_index_slice_tailmask_rewrite_dry_run",
            "tile_m": knobs.get("tile_m"),
            "tile_n": knobs.get("tile_n"),
            "tile_k": knobs.get("tile_k"),
            "loop_order": knobs.get("loop_order"),
            "tail_strategy": knobs.get("tail_strategy"),
            "reduce_tile_policy": knobs.get("reduce_tile_policy"),
            "layout_aware_tile": knobs.get("layout_aware_tile"),
            "python_mutation_enabled": False,
            "linux_backend_prevalidation_enabled": True,
        },
        "dry_run_operation_plan": dry_run,
        "parameter_readiness": operation_report.get("parameter_readiness", []),
        "must_prove_before_mutate": operation_report.get("must_prove_on_linux_before_true_mutation", []),
        "linux_validation_commands": operation_report.get("linux_validation_commands", []),
        "blocked_or_missing": blockers,
        "status": operation_report.get("overall_status", "BLOCKED_UNTIL_BACKEND_ANCHORS_RESOLVED"),
        "production_rewrite_claim_allowed": False,
        "claim_boundary": "ready for Linux backend anchor/dry-run validation; not a Python production operation rewrite",
    }


def build_rewrite_readiness_bundle(selected_plan: Dict[str, Any], inventory: Dict[str, Any]) -> Dict[str, Any]:
    sync = build_sync_readiness(selected_plan, inventory)
    mb = build_multibuffer_readiness(selected_plan, inventory)
    cv = build_cv_pipeline_readiness(selected_plan, inventory)
    tiling = build_tiling_readiness(selected_plan, inventory)
    return {
        "schema_version": "four_plan_rewrite_readiness_v1",
        "producer": "strategy_search.rewrite_readiness",
        "meaning": "This is not a new IR and it does not mutate HIVM. It is the checklist/mutation-plan layer between selected_plan.json and HivmOpsEditor.",
        "input_summary": inventory.get("summary", {}),
        "readiness_order": ["SyncPlan", "MultiBufferPlan", "CVPipelinePlan", "TilingPlan"],
        "reports": {
            "sync_plan_readiness": sync,
            "multibuffer_plan_readiness": mb,
            "cv_pipeline_plan_readiness": cv,
            "tiling_plan_readiness": tiling,
        },
        "recommended_next_backend_milestone": {
            "name": "SyncPlan + MultiBufferPlan backend dry-run",
            "why": "SyncPlan is the safest first true rewrite; MultiBuffer buffer clone is the necessary foundation for CVPipeline overlap.",
            "requires_user_run": False,
            "requires_user_run_when": "Only when compiling/running real vTriton/HivmOpsEditor backend.",
        },
    }


def build_readiness_reports(ir_path: Path, selected_plan_path: Path, output_dir: Path) -> Dict[str, Path]:
    ir_text = ir_path.read_text(encoding="utf-8")
    selected_plan = json.loads(selected_plan_path.read_text(encoding="utf-8"))
    inventory = build_hivm_inventory(ir_text, source_name=str(ir_path))
    rewrite_plan = build_four_plan_rewrite_plan(selected_plan, inventory)
    bundle = build_rewrite_readiness_bundle(selected_plan, inventory)

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "inventory": output_dir / "hivm_ir_inventory.official.json",
        "rewrite_plan": output_dir / "four_plan_rewrite_plan.json",
        "readiness_bundle": output_dir / "four_plan_rewrite_readiness.json",
        "sync": output_dir / "sync_plan_readiness.json",
        "multibuffer": output_dir / "multibuffer_plan_readiness.json",
        "cv_pipeline": output_dir / "cv_pipeline_plan_readiness.json",
        "tiling": output_dir / "tiling_plan_readiness.json",
    }
    paths["inventory"].write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["rewrite_plan"].write_text(json.dumps(rewrite_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["readiness_bundle"].write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["sync"].write_text(json.dumps(bundle["reports"]["sync_plan_readiness"], ensure_ascii=False, indent=2), encoding="utf-8")
    paths["multibuffer"].write_text(json.dumps(bundle["reports"]["multibuffer_plan_readiness"], ensure_ascii=False, indent=2), encoding="utf-8")
    paths["cv_pipeline"].write_text(json.dumps(bundle["reports"]["cv_pipeline_plan_readiness"], ensure_ascii=False, indent=2), encoding="utf-8")
    paths["tiling"].write_text(json.dumps(bundle["reports"]["tiling_plan_readiness"], ensure_ascii=False, indent=2), encoding="utf-8")
    return paths
