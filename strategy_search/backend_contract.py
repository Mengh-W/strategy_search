# -*- coding: utf-8 -*-
"""Backend contract generation for four-Plan HIVM rewrite.

This module turns the conservative rewrite readiness reports into a concrete
contract that a real vTriton/HivmOpsEditor backend can consume or validate.
It is deliberately *not* a new IR and it does not mutate MLIR.  Think of the
contract as the work order between the Python strategy search and the C++
Operation-level backend.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .hivm_official_rewrite_plan import build_hivm_inventory, build_four_plan_rewrite_plan
from .rewrite_readiness import build_rewrite_readiness_bundle


BACKEND_CONTRACT_VERSION = "hivm_four_plan_backend_contract_v1"


def _safe_line_anchor(op: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "line": op.get("line"),
        "op": op.get("op"),
        "text_preview": (op.get("text") or "")[:240],
        "inputs": op.get("inputs", []),
        "outputs": op.get("outputs", []),
        "notes": op.get("notes", []),
    }


def _first_n(items: Iterable[Dict[str, Any]], n: int = 8) -> List[Dict[str, Any]]:
    return [dict(x) for x in list(items)[:n]]


def _plan_status(readiness: Dict[str, Any], key: str) -> str:
    return readiness.get("reports", {}).get(key, {}).get("status", "UNKNOWN")


def _candidate_buffers(multibuffer_readiness: Dict[str, Any], limit: int = 8) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for c in multibuffer_readiness.get("anchors", {}).get("candidate_buffers", [])[:limit]:
        b = c.get("buffer", {})
        # Prefer buffers with observed producer+consumer.  Buffers with only one
        # side are still useful for backend dry-run but should not be mutated
        # without MLIR use-def/liveness proof.
        out.append({
            "target_buffer": b.get("name"),
            "address_space": b.get("space"),
            "alloc_line": b.get("line"),
            "type_text": b.get("type_text"),
            "candidate_score": c.get("candidate_score"),
            "producer_ops": _first_n(c.get("producer_ops", []), 4),
            "consumer_ops": _first_n(c.get("consumer_ops", []), 4),
            "requested_slots": c.get("backend_clone_request", {}).get("requested_slots"),
            "replacement_policy": c.get("backend_clone_request", {}).get("replacement_policy"),
            "mutation_allowed_without_backend_proof": False,
        })
    return out


def _stage_blocks(cv_readiness: Dict[str, Any]) -> List[Dict[str, Any]]:
    seq = cv_readiness.get("anchors", {}).get("stage_sequence_by_line", [])
    blocks: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    for item in seq:
        stage = item.get("stage")
        if current is None or current.get("stage") != stage:
            current = {"stage": stage, "ops": []}
            blocks.append(current)
        current["ops"].append({
            "line": item.get("line"),
            "op": item.get("op"),
            "text_preview": (item.get("text") or "")[:240],
        })
    return blocks


def build_backend_contract(selected_plan: Dict[str, Any], inventory: Dict[str, Any], readiness: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build a backend-facing contract from selected_plan + inventory.

    The result is intentionally explicit: every requested backend action names
    a mutation kind, anchors, proof obligations, and acceptance artifacts.  A
    real backend may reject any action; rejection with reasons is considered a
    valid dry-run result.
    """
    readiness = readiness or build_rewrite_readiness_bundle(selected_plan, inventory)
    reports = readiness.get("reports", {})
    sync = reports.get("sync_plan_readiness", {})
    mb = reports.get("multibuffer_plan_readiness", {})
    cv = reports.get("cv_pipeline_plan_readiness", {})
    tiling = reports.get("tiling_plan_readiness", {})

    unknown_ops = inventory.get("summary", {}).get("unknown_hivm_ops", [])

    sync_actions = []
    sync_ops = sync.get("anchors", {}).get("sync_ops", [])
    barriers = sync.get("anchors", {}).get("barrier_like_ops", [])
    event_ops = sync.get("anchors", {}).get("existing_event_ops", [])
    if barriers:
        sync_actions.append({
            "action_id": "sync_001_barrier_to_directional_event",
            "plan": "SyncPlan",
            "mutation_kind": "sync_barrier_to_directional_event",
            "mode": "dry_run_first",
            "anchors": {"barriers": [_safe_line_anchor(x) for x in barriers]},
            "backend_requirements": [
                "derive_producer_consumer_pair_from_real_use_def_or_DES_graph",
                "allocate_event_id_using_backend_event_allocator",
                "print_set_flag_wait_flag_with_backend_official_printer",
                "prove_no_wait_before_set_deadlock",
            ],
            "acceptance": ["dry_run_locates_barrier", "post_mutate_verify_passes", "event_liveness_passes"],
        })
    if event_ops:
        sync_actions.append({
            "action_id": "sync_002_existing_event_liveness_check",
            "plan": "SyncPlan",
            "mutation_kind": "validate_existing_set_wait_events",
            "mode": "dry_run_or_verify_only",
            "anchors": {"existing_events": [_safe_line_anchor(x) for x in event_ops]},
            "backend_requirements": [
                "parse_event_operands_or_legacy_attrs",
                "normalize_to_official_event_model_without_text_rewrite",
                "prove_event_live_ranges_do_not_conflict",
            ],
            "acceptance": ["event_pairs_reported", "no_deadlock_or_conflict_reported"],
        })

    buffer_actions = []
    for i, c in enumerate(_candidate_buffers(mb, limit=8), 1):
        buffer_actions.append({
            "action_id": f"mb_{i:03d}_clone_{str(c.get('target_buffer') or 'buffer').replace('%','')}",
            "plan": "MultiBufferPlan",
            "mutation_kind": "clone_local_buffer_slots_and_replace_uses",
            "mode": "dry_run_first",
            "target": c,
            "backend_requirements": [
                "resolve_alloc_to_MLIR_Value",
                "clone_alloc_or_create_equivalent_buffer_slots",
                "replace_all_selected_uses_by_iteration_or_stage_policy",
                "prove_all_uses_accounted_for",
                "run_capacity_recheck_after_extra_slots",
                "run_buffer_liveness_no_overwrite",
            ],
            "acceptance": [
                "dry_run_locates_target_buffer",
                "use_def_resolution_complete",
                "capacity_recheck_passes",
                "post_mutate_verify_passes",
            ],
        })

    cv_action = {
        "action_id": "cv_001_stage_reorder_contract",
        "plan": "CVPipelinePlan",
        "mutation_kind": "cv_pipeline_stage_reorder",
        "mode": "contract_only_until_sync_and_multibuffer_pass",
        "stage_blocks_by_line": _stage_blocks(cv),
        "backend_requirements": [
            "consume_successful_multibuffer_pingpong_slots",
            "consume_successful_sync_directional_events",
            "construct_prologue_steady_state_epilogue",
            "prove_stage_dependency_is_linear_or_scheduled",
            "reject_if_cross_tile_reduction_or_unknown_side_effect",
        ],
        "acceptance": [
            "dry_run_reports_stage_boundaries",
            "post_mutate_verify_passes",
            "DES_or_trace_shows_expected_overlap_before_claiming_success"],
    }

    tiling_action = {
        "action_id": "tiling_001_hint_and_legality_contract",
        "plan": "TilingPlan",
        "mutation_kind": "tiling_hint_or_restricted_loop_tiling",
        "mode": "hint_and_report_only_v1",
        "selected_tiles": tiling.get("backend_mutation_request_template", {}),
        "anchors": {
            "loops": tiling.get("anchors", {}).get("loop_ops", []),
            "cube_compute_ops": [_safe_line_anchor(x) for x in tiling.get("anchors", {}).get("cube_compute_ops", [])],
        },
        "backend_requirements": [
            "identify_loop_bounds_and_induction_values",
            "identify_load_store_slice_mapping",
            "define_tail_mask_semantics",
            "run_capacity_after_tiling",
        ],
        "acceptance": [
            "hint_emitted_or_reported", "no_true_tiling_claim_without_loop_index_slice_tailmask_change"],
    }

    actions = sync_actions + buffer_actions + [cv_action, tiling_action]
    first_backend_milestone_actions = [a["action_id"] for a in actions if a["plan"] in {"SyncPlan", "MultiBufferPlan"}]

    return {
        "schema_version": BACKEND_CONTRACT_VERSION,
        "producer": "strategy_search.backend_contract",
        "meaning": "Backend-facing work order, not a new IR and not a mutation result.",
        "input_summary": inventory.get("summary", {}),
        "global_policy": {
            "unknown_hivm_ops": unknown_ops,
            "unknown_op_rule": "unknown ops do not block inventory/report, but any true mutation touching their region must be rejected by backend dry-run",
            "python_may_emit": ["JSON contract", "annotation/hint", "readiness reports"],
            "python_must_not_emit": ["new official set_flag/wait_flag text", "real buffer clone", "real loop tiling", "stage reorder"],
            "real_mutation_owner": "vTriton/HivmOpsEditor Operation-level backend",
        },
        "backend_cli_contract": {
            "required_modes": ["--print-capabilities", "--inventory", "--roundtrip", "--verify-only", "--dry-run", "--mutate"],
            "common_args": ["--input", "--output", "--report", "--edit-script", "--mutation-kind"],
            "contract_files": ["hivm_ir_inventory.official.json", "four_plan_rewrite_plan.json", "four_plan_rewrite_readiness.json", "four_plan_backend_contract.json"],
        },
        "execution_order": [
            "inventory",
            "roundtrip",
            "verify_only",
            "dry_run_sync_and_multibuffer",
            "mutate_one_guarded_action_at_a_time",
            "post_mutate_verify",
            "DES_trace_if_available",
            "msprof_only_after_verified_optimized_IR_exists",
        ],
        "first_backend_milestone": {
            "name": "SyncPlan + MultiBufferPlan dry-run contract",
            "actions": first_backend_milestone_actions,
            "why": "These are the first two Plans that can realistically become true rewrite primitives. CVPipeline depends on them; Tiling is report/hint only in v1.",
            "requires_user_run_now": False,
            "requires_user_run_when": "after C++ backend compile path is ready or when validating real HivmOpsEditor API",
        },
        "plan_status": {
            "SyncPlan": _plan_status(readiness, "sync_plan_readiness"),
            "MultiBufferPlan": _plan_status(readiness, "multibuffer_plan_readiness"),
            "CVPipelinePlan": _plan_status(readiness, "cv_pipeline_plan_readiness"),
            "TilingPlan": _plan_status(readiness, "tiling_plan_readiness"),
        },
        "actions": actions,
        "do_not_claim": [
            "Do not claim real SyncPlan rewrite until backend mutation changes sync ops and verifier passes.",
            "Do not claim real MultiBufferPlan rewrite until cloned buffers and replaced uses are visible in optimized IR and capacity/liveness pass.",
            "Do not claim CVPipeline overlap until DES/trace shows expected overlap.",
            "Do not claim TilingPlan true rewrite until loop/index/slice/tail-mask change and verify passes.",
            "Do not claim performance improvement without msprof or accepted simulator evidence.",
        ],
    }


def build_backend_contract_reports(ir_path: Path, selected_plan_path: Path, output_dir: Path) -> Dict[str, Path]:
    ir_text = ir_path.read_text(encoding="utf-8")
    selected_plan = json.loads(selected_plan_path.read_text(encoding="utf-8"))
    inventory = build_hivm_inventory(ir_text, source_name=str(ir_path))
    rewrite_plan = build_four_plan_rewrite_plan(selected_plan, inventory)
    readiness = build_rewrite_readiness_bundle(selected_plan, inventory)
    contract = build_backend_contract(selected_plan, inventory, readiness)

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "inventory": output_dir / "hivm_ir_inventory.official.json",
        "rewrite_plan": output_dir / "four_plan_rewrite_plan.json",
        "readiness": output_dir / "four_plan_rewrite_readiness.json",
        "contract": output_dir / "four_plan_backend_contract.json",
        "sync_multibuffer_contract": output_dir / "sync_multibuffer_backend_contract.json",
    }
    paths["inventory"].write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["rewrite_plan"].write_text(json.dumps(rewrite_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["readiness"].write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["contract"].write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")

    first_ids = set(contract["first_backend_milestone"]["actions"])
    sync_mb = dict(contract)
    sync_mb["actions"] = [a for a in contract["actions"] if a.get("action_id") in first_ids]
    sync_mb["schema_version"] = BACKEND_CONTRACT_VERSION + "_sync_multibuffer_subset"
    paths["sync_multibuffer_contract"].write_text(json.dumps(sync_mb, ensure_ascii=False, indent=2), encoding="utf-8")
    return paths
