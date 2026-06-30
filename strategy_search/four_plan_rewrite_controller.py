# -*- coding: utf-8 -*-
"""Unified Four-Plan rewrite controller.

V4.11 does not pretend that all four plans can be semantically mutated without a
real MLIR/HIVM verifier.  It provides a single orchestration layer that runs the
currently available rewrite/readiness modules in a deterministic order:

1. SyncPlan audited portable rewrite (semantic text-level rewrite available).
2. MultiBufferPlan readiness and stage-boundary analysis (planned, not mutated).
3. CVPipelinePlan staged rewrite planner (planned, not mutated).
4. TilingPlan feasibility scan (planned, not mutated).

The output is a controller report with stage gates, blockers, artifacts, and a
combined HivmOpsEditor migration queue.  This is the project-level bridge from
isolated plan experiments to a maintainable rewrite pipeline.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .sync_contract_precision import build_sync_precision_contract_from_files
from .sync_rewrite_executor import apply_restricted_sync_rewrite_from_files, select_rewritable_sync_actions
from .sync_rewrite_validator import validate_restricted_sync_rewrite_files
from .sync_rewrite_diff import write_sync_rewrite_diff_report
from .sync_liveness_report import write_sync_liveness_report
from .sync_rewrite_audit import write_sync_rewrite_audit_report
from .multibuffer_rewrite_readiness import write_multibuffer_outputs
from .multibuffer_stage_boundary import write_multibuffer_stage_outputs
from .cvpipeline_stage_planner import write_cvpipeline_stage_outputs

FOUR_PLAN_CONTROLLER_VERSION = "hivm_four_plan_rewrite_controller_v1"

_FOR_RE = re.compile(r"\b(?:scf|affine)\.for\b")
_HIVM_OP_RE = re.compile(r"hivm\.hir\.(?P<op>[A-Za-z0-9_]+)")
_TILE_HINT_RE = re.compile(r"tile[_-]?(m|n|k)|loop_trip|outer_iterations|tile_m|tile_n|tile_k", re.I)


def _read_json(path: str | Path | None) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(path: str | Path, obj: Any) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def _safe_status(ok: bool, blocked: bool = False, review: bool = False) -> str:
    if blocked:
        return "BLOCKED"
    if ok:
        return "PASSED"
    if review:
        return "REVIEW_REQUIRED"
    return "FAILED"


def run_syncplan_audited_rewrite(
    ir_path: str | Path,
    selected_plan_path: str | Path,
    output_dir: str | Path,
    max_sync_actions: int = 999999,
    allow_pipe_all: bool = False,
) -> Dict[str, Any]:
    """Run V4.7 audited SyncPlan portable rewrite as a controller stage."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    contract_dir = out / "sync_precision_contract"
    contract = build_sync_precision_contract_from_files(ir_path, selected_plan_path, contract_dir)
    contract_path = contract_dir / "sync_precision_contract.json"
    candidate_actions = select_rewritable_sync_actions(contract, max_actions=max_sync_actions, allow_pipe_all=allow_pipe_all)
    candidate_report = {
        "schema_version": "hivm_controller_sync_candidate_report_v1",
        "num_candidate_actions": len(candidate_actions),
        "max_sync_actions": max_sync_actions,
        "allow_pipe_all": bool(allow_pipe_all),
        "candidate_actions": [
            {
                "action_id": a.get("action_id"),
                "line": a.get("_rewrite_line"),
                "pipe": a.get("_rewrite_pipe"),
                "risk": "medium_same_pipe_barrier_emulation",
                "reason_selected": "pipe_barrier action with textual line anchor; PIPE_ALL skipped unless explicitly enabled",
            }
            for a in candidate_actions
        ],
    }
    candidate_path = _write_json(out / "sync_full_rewrite_candidates.json", candidate_report)

    before_liveness_path = out / "sync_liveness_before.json"
    after_liveness_path = out / "sync_liveness_after.json"
    optimized_ir = out / "optimized.sync_controller_rewritten.hivm.mlir"
    rewrite_report_path = out / "sync_controller_rewrite_report.json"
    validation_report_path = out / "sync_controller_rewrite_validation.json"
    diff_report_path = out / "sync_controller_rewrite_diff.json"
    audit_report_path = out / "sync_rewrite_safety_audit.json"

    before_liveness = write_sync_liveness_report(ir_path, before_liveness_path)
    rewrite = apply_restricted_sync_rewrite_from_files(
        ir_path, contract_path, optimized_ir, rewrite_report_path,
        max_actions=max_sync_actions, allow_pipe_all=allow_pipe_all
    )
    validation = validate_restricted_sync_rewrite_files(ir_path, optimized_ir, rewrite_report_path, validation_report_path)
    after_liveness = write_sync_liveness_report(optimized_ir, after_liveness_path)
    diff = write_sync_rewrite_diff_report(ir_path, optimized_ir, diff_report_path)
    audit = write_sync_rewrite_audit_report(
        ir_path, optimized_ir, contract_path, rewrite_report_path, validation_report_path,
        before_liveness_path, after_liveness_path, audit_report_path,
    )
    passed = bool(rewrite.get("mutation_performed")) and bool(validation.get("passed_portable_validation")) and bool(after_liveness.get("passed_portable_liveness")) and bool(audit.get("audit_passed_portable_level"))
    summary = {
        "stage": "SyncPlan",
        "stage_status": _safe_status(passed),
        "rewrite_level": "portable_text_level_audited",
        "contract_overall_decision": contract.get("overall_decision"),
        "candidate_action_count": len(candidate_actions),
        "mutation_performed": rewrite.get("mutation_performed"),
        "rewritten_action_count": rewrite.get("rewritten_action_count"),
        "skipped_action_count": rewrite.get("skipped_action_count"),
        "passed_portable_validation": validation.get("passed_portable_validation"),
        "passed_portable_liveness_after": after_liveness.get("passed_portable_liveness"),
        "num_sync_related_diff_lines": diff.get("num_sync_related_diff_lines"),
        "audit_decision": audit.get("audit_decision"),
        "audit_risk_counts": audit.get("risk_counts"),
        "hivmopseditor_migration_action_count": len(audit.get("hivmopseditor_migration_action_list", [])),
        "semantic_mutation_performed": True,
        "production_rewrite_claim_allowed": False,
        "artifacts": {
            "contract": str(contract_path),
            "candidate_report": candidate_path,
            "optimized_ir": str(optimized_ir),
            "rewrite_report": str(rewrite_report_path),
            "validation_report": str(validation_report_path),
            "diff_report": str(diff_report_path),
            "audit_report": str(audit_report_path),
            "before_liveness": str(before_liveness_path),
            "after_liveness": str(after_liveness_path),
        },
    }
    _write_json(out / "sync_controller_stage_summary.json", summary)
    return summary


def analyze_tiling_rewrite_feasibility(ir_path: str | Path, selected_plan_path: str | Path, output_dir: str | Path) -> Dict[str, Any]:
    """Conservative TilingPlan feasibility scan.

    This is deliberately not a tiling mutation.  It only records whether the IR
    exposes enough loop/tile anchors for a future operation-level tiling rewrite.
    """
    ir_path = Path(ir_path)
    selected_plan_path = Path(selected_plan_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    text = ir_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    selected_plan = _read_json(selected_plan_path)
    tiling_plan = selected_plan.get("tiling_plan", {})
    knobs = tiling_plan.get("controllable_knobs", {})
    derived = tiling_plan.get("derived_features", {})
    loop_records: List[Dict[str, Any]] = []
    tile_hint_records: List[Dict[str, Any]] = []
    compute_records: List[Dict[str, Any]] = []
    memory_records: List[Dict[str, Any]] = []
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        if _FOR_RE.search(line):
            loop_records.append({"line": idx, "text": stripped[:220]})
        if _TILE_HINT_RE.search(line):
            tile_hint_records.append({"line": idx, "text": stripped[:220]})
        m = _HIVM_OP_RE.search(line)
        if m:
            op = m.group("op")
            if op.lower().startswith("v") or "mad" in op.lower() or op in {"mmad", "mmadL1", "nd2nz", "fixpipe"}:
                compute_records.append({"line": idx, "op": f"hivm.hir.{op}", "text": stripped[:220]})
            if op in {"load", "store", "nd2nz", "fixpipe", "pointer_cast"}:
                memory_records.append({"line": idx, "op": f"hivm.hir.{op}", "text": stripped[:220]})
    blockers = [
        "operation-level loop split/index remap is not implemented without real MLIR verifier",
        "tail mask/pad legality cannot be proven from text-only analysis",
        "address calculation and use-def dominance require real MLIR/HIVM environment",
    ]
    has_plan_knobs = bool(knobs)
    has_loop_anchors = bool(loop_records)
    has_compute_memory = bool(compute_records and memory_records)
    if has_plan_knobs and has_loop_anchors and has_compute_memory:
        readiness = "READY_FOR_TILING_PLAN_SCAFFOLD"
        risk = "HIGH"
    elif has_plan_knobs and has_compute_memory:
        readiness = "REVIEW_REQUIRED_NO_EXPLICIT_LOOP_ANCHOR"
        risk = "HIGH"
    else:
        readiness = "BLOCKED_INSUFFICIENT_TILING_EVIDENCE"
        risk = "BLOCKED"
    report = {
        "schema_version": "hivm_tiling_rewrite_feasibility_v1",
        "version": "V4.11-unified-four-plan-rewrite-controller",
        "input_ir": str(ir_path),
        "tiling_knobs": knobs,
        "derived_features": derived,
        "loop_anchor_count": len(loop_records),
        "tile_hint_count": len(tile_hint_records),
        "compute_anchor_count": len(compute_records),
        "memory_anchor_count": len(memory_records),
        "readiness": readiness,
        "risk": risk,
        "semantic_mutation_performed": False,
        "production_rewrite_claim_allowed": False,
        "loop_anchors_sample": loop_records[:50],
        "tile_hints_sample": tile_hint_records[:50],
        "proposed_rewrite_steps": [
            "derive canonical loop nest and logical axes from MLIR regions",
            "split or retile loop bounds according to selected TilingPlan knobs",
            "rewrite load/compute/store offsets and tail masks",
            "compose with MultiBufferPlan slot parity when applicable",
            "run real HivmOpsEditor/MLIR verifier before accepting",
        ],
        "blockers_before_semantic_mutation": blockers,
    }
    path = out / "tiling_rewrite_feasibility.json"
    _write_json(path, report)
    summary = {
        "stage": "TilingPlan",
        "stage_status": "REVIEW_REQUIRED" if not readiness.startswith("BLOCKED") else "BLOCKED",
        "readiness": readiness,
        "risk": risk,
        "loop_anchor_count": len(loop_records),
        "tile_hint_count": len(tile_hint_records),
        "compute_anchor_count": len(compute_records),
        "memory_anchor_count": len(memory_records),
        "semantic_mutation_performed": False,
        "production_rewrite_claim_allowed": False,
        "artifacts": {"tiling_feasibility_report": str(path)},
    }
    _write_json(out / "tiling_rewrite_feasibility_summary.json", summary)
    return summary


def _collect_hivmopseditor_queue(sync_summary: Dict[str, Any], mb_stage_summary: Dict[str, Any], cv_summary: Dict[str, Any], tiling_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    queue: List[Dict[str, Any]] = []
    if sync_summary.get("hivmopseditor_migration_action_count", 0):
        queue.append({
            "plan": "SyncPlan",
            "priority": 1,
            "operation_level_api": ["addSetFlagWaitFlagBefore", "deleteOp", "exportToFile", "verify"],
            "action_count": sync_summary.get("hivmopseditor_migration_action_count"),
            "status": "portable_rewrite_available_waiting_for_real_verifier",
            "source_artifact": sync_summary.get("artifacts", {}).get("audit_report"),
        })
    if mb_stage_summary.get("stage_mutation_plan_action_count", 0):
        queue.append({
            "plan": "MultiBufferPlan",
            "priority": 2,
            "operation_level_api": ["clone/create buffer slot", "rewrite producer uses", "rewrite consumer uses", "insert/reuse sync edge", "verify"],
            "action_count": mb_stage_summary.get("stage_mutation_plan_action_count"),
            "status": "planned_not_mutated_requires_dominance_alias_capacity_proof",
            "source_artifact": mb_stage_summary.get("stage_plan_path") or mb_stage_summary.get("artifacts", {}).get("stage_plan"),
        })
    if cv_summary.get("cvpipeline_rewrite_plan_action_count", 0):
        queue.append({
            "plan": "CVPipelinePlan",
            "priority": 3,
            "operation_level_api": ["split stage", "move/clone ops across prologue/steady/epilogue", "compose multibuffer slots", "insert sync edges", "verify"],
            "action_count": cv_summary.get("cvpipeline_rewrite_plan_action_count"),
            "status": "planner_available_no_semantic_op_motion_yet",
            "source_artifact": cv_summary.get("rewrite_plan_path") or cv_summary.get("artifacts", {}).get("rewrite_plan"),
        })
    if tiling_summary.get("readiness") and not str(tiling_summary.get("readiness")).startswith("BLOCKED"):
        queue.append({
            "plan": "TilingPlan",
            "priority": 4,
            "operation_level_api": ["split/rewrite loops", "rewrite indices", "tail mask/pad", "verify"],
            "action_count": None,
            "status": "feasibility_only_high_risk",
            "source_artifact": tiling_summary.get("artifacts", {}).get("tiling_feasibility_report"),
        })
    return queue


def write_unified_four_plan_controller_outputs(
    ir_path: str | Path,
    selected_plan_path: str | Path,
    output_dir: str | Path,
    max_sync_actions: int = 999999,
    max_multibuffer_candidates: int = 80,
    max_cvpipeline_windows: int = 50,
    max_annotations: int = 20,
    allow_pipe_all: bool = False,
) -> Dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stages_dir = out / "stages"
    stages_dir.mkdir(parents=True, exist_ok=True)

    sync_summary = run_syncplan_audited_rewrite(
        ir_path, selected_plan_path, stages_dir / "01_syncplan",
        max_sync_actions=max_sync_actions, allow_pipe_all=allow_pipe_all,
    )
    # Downstream planners use original IR by default.  The SyncPlan-rewritten IR is
    # available as a separate artifact, but using it as input could hide original
    # barrier structure before real verifier proves semantic equivalence.
    mb_readiness_result = write_multibuffer_outputs(
        ir_path, selected_plan_path, stages_dir / "02_multibuffer_readiness",
        max_candidates=max_multibuffer_candidates,
        max_annotations=max_annotations,
    )
    mb_stage_result = write_multibuffer_stage_outputs(
        ir_path, selected_plan_path, stages_dir / "03_multibuffer_stage_boundary",
        max_candidates=max_multibuffer_candidates,
        max_annotations=max_annotations,
    )
    cv_result = write_cvpipeline_stage_outputs(
        ir_path, selected_plan_path, stages_dir / "04_cvpipeline_stage_planner",
        multibuffer_stage_report_path=mb_stage_result.get("stage_report_path"),
        max_windows=max_cvpipeline_windows,
        max_annotations=max_annotations,
    )
    tiling_summary = analyze_tiling_rewrite_feasibility(ir_path, selected_plan_path, stages_dir / "05_tiling_feasibility")

    mb_readiness_summary = mb_readiness_result.get("summary", {})
    mb_stage_summary = mb_stage_result.get("summary", {}) | {
        "stage_report_path": mb_stage_result.get("stage_report_path"),
        "stage_plan_path": mb_stage_result.get("stage_plan_path"),
    }
    cv_summary = cv_result.get("summary", {}) | {
        "stage_report_path": cv_result.get("stage_report_path"),
        "rewrite_plan_path": cv_result.get("rewrite_plan_path"),
    }

    controller_stages = [sync_summary, mb_readiness_summary, mb_stage_summary, cv_summary, tiling_summary]
    semantic_mutation_count = sum(1 for s in controller_stages if s.get("semantic_mutation_performed"))
    planned_only_count = sum(1 for s in controller_stages if not s.get("semantic_mutation_performed"))
    blocked_count = sum(1 for s in controller_stages if s.get("stage_status") == "BLOCKED")
    review_count = sum(1 for s in controller_stages if s.get("stage_status") == "REVIEW_REQUIRED")
    hivmopseditor_queue = _collect_hivmopseditor_queue(sync_summary, mb_stage_summary, cv_summary, tiling_summary)

    overall_decision = "PORTABLE_SYNC_REWRITE_PLUS_MULTI_PLAN_SCAFFOLD_READY"
    if not sync_summary.get("stage_status") == "PASSED":
        overall_decision = "REVIEW_REQUIRED_SYNCPLAN_NOT_CLOSED"
    elif blocked_count > 0:
        overall_decision = "PORTABLE_SYNC_REWRITE_READY_OTHER_PLANS_PARTIALLY_BLOCKED"

    report = {
        "schema_version": FOUR_PLAN_CONTROLLER_VERSION,
        "version": "V4.11-unified-four-plan-rewrite-controller",
        "input_ir": str(ir_path),
        "selected_plan": str(selected_plan_path),
        "overall_decision": overall_decision,
        "claim_boundary": "Only SyncPlan has audited portable/text-level semantic rewrite. MultiBuffer/CVPipeline/Tiling are scaffold/readiness/planner stages until real HivmOpsEditor verifier is available.",
        "semantic_mutation_count": semantic_mutation_count,
        "planned_only_count": planned_only_count,
        "blocked_stage_count": blocked_count,
        "review_required_stage_count": review_count,
        "stage_summaries": {
            "syncplan": sync_summary,
            "multibuffer_readiness": mb_readiness_summary,
            "multibuffer_stage_boundary": mb_stage_summary,
            "cvpipeline_stage_planner": cv_summary,
            "tiling_feasibility": tiling_summary,
        },
        "hivmopseditor_migration_queue": hivmopseditor_queue,
        "execution_order_policy": [
            "1. Apply/prove SyncPlan event rewrite first because it provides explicit synchronization edges.",
            "2. Use MultiBufferPlan readiness and stage-boundary evidence to select ping-pong candidates.",
            "3. Use CVPipelinePlan windows only after buffer slots and sync edges are known.",
            "4. Treat TilingPlan as high-risk until operation-level loop/index rewrite is available.",
        ],
        "production_rewrite_claim_allowed": False,
    }
    report_path = out / "four_plan_rewrite_controller_report.json"
    _write_json(report_path, report)
    summary = {
        "schema_version": "hivm_four_plan_rewrite_controller_summary_v1",
        "version": "V4.11-unified-four-plan-rewrite-controller",
        "input_ir": str(ir_path),
        "selected_plan": str(selected_plan_path),
        "overall_decision": overall_decision,
        "sync_rewritten_action_count": sync_summary.get("rewritten_action_count"),
        "sync_portable_rewrite_passed": sync_summary.get("stage_status") == "PASSED",
        "multibuffer_ready_count": mb_stage_summary.get("stage_boundary_status_counts", {}).get("READY_FOR_PINGPONG_PLAN"),
        "cvpipeline_window_count": cv_summary.get("pipeline_window_count"),
        "cvpipeline_ready_count": cv_summary.get("pipeline_window_status_counts", {}).get("READY_FOR_CVPIPELINE_PLAN"),
        "tiling_readiness": tiling_summary.get("readiness"),
        "hivmopseditor_migration_queue_count": len(hivmopseditor_queue),
        "semantic_mutation_count": semantic_mutation_count,
        "planned_only_count": planned_only_count,
        "production_rewrite_claim_allowed": False,
        "controller_report": str(report_path),
    }
    summary_path = out / "four_plan_rewrite_controller_summary.json"
    _write_json(summary_path, summary)
    return {
        "controller_report_path": str(report_path),
        "controller_summary_path": str(summary_path),
        "summary": summary,
        "report": report,
    }


__all__ = [
    "FOUR_PLAN_CONTROLLER_VERSION",
    "run_syncplan_audited_rewrite",
    "analyze_tiling_rewrite_feasibility",
    "write_unified_four_plan_controller_outputs",
]
