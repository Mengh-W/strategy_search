# -*- coding: utf-8 -*-
"""Precise SyncPlan dry-run contracts for vTriton/HivmOpsEditor.

This module refines SyncPlan from a coarse readiness report into explicit,
backend-facing check / dry-run actions.  It never mutates MLIR text.  The output
is a small JSON work order that a real HivmOpsEditor backend can validate before
any guarded mutation is considered.

Why this layer exists:
  * selected_plan.json says *what policy* we want, e.g. graph_sync_solver;
  * HIVM inventory says *what sync ops* exist in the input IR;
  * this module says *which exact sync anchors* need backend proof and what
    fields are required before mutation.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .hivm_official_rewrite_plan import build_hivm_inventory, build_four_plan_rewrite_plan
from .rewrite_readiness import build_rewrite_readiness_bundle


SYNC_PRECISION_SCHEMA_VERSION = "hivm_sync_precision_contract_v1"

_PIPE_LEGACY_RE = re.compile(r"pipe\s*=\s*\"?([A-Za-z0-9_]+)\"?")
_EVENT_LEGACY_RE = re.compile(r"event\s*=\s*\"?([A-Za-z0-9_]+)\"?")
_OFFICIAL_BRACKET_RE = re.compile(r"\[\s*([^\]]+?)\s*\]")

# Coarse producer / consumer groups used only as textual anchors.  The real
# producer-consumer proof must come from MLIR use-def or DES graph in backend.
_PRODUCER_OPS = {
    "hivm.hir.load",
    "hivm.hir.copy",
    "hivm.hir.nd2nz",
    "hivm.hir.nz2nd",
    "hivm.hir.fixpipe",
    "hivm.hir.mmad",
    "hivm.hir.mmadL1",
    "hivm.hir.matmul",
    "hivm.hir.mix_matmul",
}
_CONSUMER_OPS = {
    "hivm.hir.store",
    "hivm.hir.copy",
    "hivm.hir.nd2nz",
    "hivm.hir.nz2nd",
    "hivm.hir.fixpipe",
    "hivm.hir.mmad",
    "hivm.hir.mmadL1",
    "hivm.hir.matmul",
    "hivm.hir.mix_matmul",
    "hivm.hir.vadd",
    "hivm.hir.vsub",
    "hivm.hir.vmul",
    "hivm.hir.vdiv",
    "hivm.hir.vexp",
    "hivm.hir.vreduce",
}


def _op_anchor(op: Dict[str, Any], index: Optional[int] = None) -> Dict[str, Any]:
    return {
        "op_index": index,
        "line": op.get("line"),
        "op": op.get("op"),
        "text_preview": (op.get("text") or "")[:260],
        "inputs": op.get("inputs", []),
        "outputs": op.get("outputs", []),
        "notes": op.get("notes", []),
    }


def _extract_pipe_event(text: str, op_name: str) -> Dict[str, Any]:
    """Extract a best-effort pipe/event model from legacy or official syntax.

    The result is intentionally labelled as parse confidence.  Python can read
    and normalize these anchors, but must not print new event ops itself.
    """
    legacy_pipe = _PIPE_LEGACY_RE.search(text)
    legacy_event = _EVENT_LEGACY_RE.search(text)
    if legacy_pipe or legacy_event:
        pipe = legacy_pipe.group(1) if legacy_pipe else None
        return {
            "syntax_detected": "legacy_attr_or_sample_attr",
            "parse_confidence": "medium",
            "set_pipe": pipe if op_name.endswith("set_flag") else None,
            "wait_pipe": pipe if op_name.endswith("wait_flag") else None,
            "pipe": pipe,
            "event_id": legacy_event.group(1) if legacy_event else None,
            "backend_must_reparse": True,
            "python_must_not_print_new_event_op": True,
        }

    bracket = _OFFICIAL_BRACKET_RE.search(text)
    if bracket:
        parts = [p.strip().strip('"') for p in bracket.group(1).split(",")]
        return {
            "syntax_detected": "official_bracket_like",
            "parse_confidence": "medium",
            "set_pipe": parts[0] if len(parts) > 0 else None,
            "wait_pipe": parts[1] if len(parts) > 1 else None,
            "event_id": parts[2] if len(parts) > 2 else None,
            "backend_must_reparse": True,
            "python_must_not_print_new_event_op": True,
        }

    return {
        "syntax_detected": "unparsed_or_attrless",
        "parse_confidence": "low",
        "set_pipe": None,
        "wait_pipe": None,
        "pipe": None,
        "event_id": None,
        "backend_must_reparse": True,
        "python_must_not_print_new_event_op": True,
    }


def _window_ops(ops: List[Dict[str, Any]], line: int, *, before: bool, limit: int = 4) -> List[Dict[str, Any]]:
    if before:
        candidates = [o for o in ops if (o.get("line") or 0) < line]
        candidates = candidates[-limit:]
    else:
        candidates = [o for o in ops if (o.get("line") or 0) > line]
        candidates = candidates[:limit]
    return [_op_anchor(o) for o in candidates]


def _nearest_producer_consumer(inventory: Dict[str, Any], line: int) -> Dict[str, Any]:
    ops = sorted(inventory.get("operations", []), key=lambda x: x.get("line") or 0)
    producers = [o for o in ops if o.get("op") in _PRODUCER_OPS]
    consumers = [o for o in ops if o.get("op") in _CONSUMER_OPS]
    return {
        "producer_candidates_before": _window_ops(producers, line, before=True, limit=4),
        "consumer_candidates_after": _window_ops(consumers, line, before=False, limit=4),
        "proof_status": "textual_anchor_only_backend_must_prove_real_dependency",
    }


def _normalize_event_records(inventory: Dict[str, Any]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for idx, op in enumerate(inventory.get("operations", [])):
        name = op.get("op")
        if name not in {"hivm.hir.set_flag", "hivm.hir.wait_flag"}:
            continue
        model = _extract_pipe_event(op.get("text") or "", name)
        event_id = model.get("event_id") or f"UNKNOWN_EVENT_AT_LINE_{op.get('line')}"
        records.append({
            "record_id": f"event_{len(records)+1:03d}_{name.split('.')[-1]}_line_{op.get('line')}",
            "kind": "set" if name.endswith("set_flag") else "wait",
            "anchor": _op_anchor(op, idx),
            "normalized_event": model,
            "event_id_key": event_id,
        })
    return records


def _event_pair_reports(event_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for rec in event_records:
        key = rec.get("event_id_key") or "UNKNOWN_EVENT"
        grouped.setdefault(key, {"set": [], "wait": []})[rec["kind"]].append(rec)

    reports: List[Dict[str, Any]] = []
    for event_id, sides in sorted(grouped.items()):
        sets = sorted(sides["set"], key=lambda r: r["anchor"].get("line") or 0)
        waits = sorted(sides["wait"], key=lambda r: r["anchor"].get("line") or 0)
        first_set_line = sets[0]["anchor"].get("line") if sets else None
        first_wait_line = waits[0]["anchor"].get("line") if waits else None
        possible_wait_before_set = bool(first_set_line and first_wait_line and first_wait_line < first_set_line)
        reports.append({
            "event_id": event_id,
            "set_count": len(sets),
            "wait_count": len(waits),
            "set_records": sets[:8],
            "wait_records": waits[:8],
            "pairing_status": (
                "HAS_SET_AND_WAIT" if sets and waits else
                "ONLY_SET_NO_WAIT" if sets else
                "ONLY_WAIT_NO_SET" if waits else "EMPTY"
            ),
            "text_order_warning": "WAIT_BEFORE_SET_IN_TEXT_ORDER" if possible_wait_before_set else None,
            "backend_required_proofs": [
                "parse_event_operands_with_real_HIVM_parser",
                "prove_event_live_ranges_non_overlapping_or_intentionally_reused",
                "prove_wait_is_reachable_after_matching_set_in_schedule_not_just_text_order",
                "prove_no_deadlock_under_pipe_schedule",
            ],
        })
    return reports


def _barrier_records(inventory: Dict[str, Any]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for idx, op in enumerate(inventory.get("operations", [])):
        name = op.get("op")
        text = op.get("text") or ""
        if name not in {"hivm.hir.pipe_barrier", "hivm.hir.barrier"} and "barrier" not in text:
            continue
        line = op.get("line") or 0
        records.append({
            "record_id": f"barrier_{len(records)+1:03d}_line_{line}",
            "anchor": _op_anchor(op, idx),
            "normalized_barrier": _extract_pipe_event(text, name or ""),
            "nearby_dependency_anchors": _nearest_producer_consumer(inventory, line),
            "rewrite_candidate_kind": "barrier_to_directional_event_pair_dry_run",
            "backend_required_fields_before_mutate": [
                "target_op_index_or_operation_id",
                "insert_position_before_or_after",
                "set_pipe",
                "wait_pipe",
                "event_id_or_backend_fresh_event_allocator",
                "producer_operation_id",
                "consumer_operation_id",
                "proof_dependency_edge_exists",
                "proof_barrier_has_no_other_required_dependents",
            ],
        })
    return records


def _sync_block_records(inventory: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for idx, op in enumerate(inventory.get("operations", [])):
        name = op.get("op") or ""
        if "sync_block" not in name:
            continue
        out.append({
            "record_id": f"syncblock_{len(out)+1:03d}_line_{op.get('line')}",
            "anchor": _op_anchor(op, idx),
            "action": "classify_only_in_v1",
            "backend_required_proofs": [
                "identify_sync_block_scope",
                "identify_mode_and_participants",
                "reject_mutation_until_deadlock_and_participant_analysis_exists",
            ],
        })
    return out


def build_sync_precision_contract(selected_plan: Dict[str, Any], inventory: Dict[str, Any]) -> Dict[str, Any]:
    readiness = build_rewrite_readiness_bundle(selected_plan, inventory)
    event_records = _normalize_event_records(inventory)
    pair_reports = _event_pair_reports(event_records)
    barriers = _barrier_records(inventory)
    sync_blocks = _sync_block_records(inventory)

    knobs = selected_plan.get("sync_plan", {}).get("controllable_knobs", {}) or {}
    requested_policy = knobs.get("policy") or knobs.get("sync_policy") or "unknown"

    actions: List[Dict[str, Any]] = []
    for report in pair_reports:
        actions.append({
            "action_id": f"sync_check_event_{report['event_id']}",
            "plan": "SyncPlan",
            "mutation_kind": "validate_existing_event_pair_liveness",
            "mode": "verify_or_dry_run_only",
            "mutation_allowed": False,
            "reason_mutation_blocked": "existing_event_check_only_in_v1",
            "event_report": report,
            "acceptance": [
                "backend_parses_event_operands",
                "backend_reports_set_wait_pairs",
                "event_liveness_non_conflicting_or_explained_reuse",
                "no_deadlock_warning",
            ],
        })

    for barrier in barriers:
        actions.append({
            "action_id": f"sync_dryrun_{barrier['record_id']}",
            "plan": "SyncPlan",
            "mutation_kind": "barrier_to_directional_event_pair",
            "mode": "dry_run_first",
            "mutation_allowed": False,
            "reason_mutation_blocked": "precise_backend_dependency_and_event_proofs_required_before_mutation",
            "target": barrier,
            "required_backend_proofs": barrier["backend_required_fields_before_mutate"] + [
                "roundtrip_passes",
                "verify_passes",
                "event_liveness_passes_after_dry_run_plan",
            ],
            "acceptance": [
                "target_barrier_located_by_backend",
                "producer_consumer_pair_reported",
                "fresh_or_safe_reused_event_reported",
                "backend_can_print_official_set_wait_ops",
            ],
        })

    for sb in sync_blocks:
        actions.append({
            "action_id": f"sync_classify_{sb['record_id']}",
            "plan": "SyncPlan",
            "mutation_kind": "classify_sync_block_scope",
            "mode": "dry_run_or_report_only",
            "mutation_allowed": False,
            "reason_mutation_blocked": "sync_block_mutation_requires_participant_and_deadlock_analysis",
            "target": sb,
            "acceptance": ["backend_reports_sync_block_mode_and_scope"],
        })

    if not actions:
        overall = "REPORT_ONLY_NO_SYNC_ANCHOR"
    elif barriers:
        overall = "READY_FOR_PRECISE_BACKEND_DRY_RUN_BARRIER_ACTIONS"
    elif event_records or sync_blocks:
        overall = "READY_FOR_PRECISE_BACKEND_DRY_RUN_CHECKS_ONLY"
    else:
        overall = "REPORT_ONLY"

    return {
        "schema_version": SYNC_PRECISION_SCHEMA_VERSION,
        "producer": "strategy_search.sync_contract_precision",
        "meaning": "Precise SyncPlan dry-run/check contract; not an IR and not a mutation result.",
        "selected_sync_policy": requested_policy,
        "inventory_summary": inventory.get("summary", {}),
        "readiness_status": readiness.get("reports", {}).get("sync_plan_readiness", {}).get("status"),
        "normalized_sync_inventory": {
            "num_event_records": len(event_records),
            "num_event_pair_reports": len(pair_reports),
            "num_barrier_records": len(barriers),
            "num_sync_block_records": len(sync_blocks),
            "event_records": event_records[:64],
            "event_pair_reports": pair_reports[:64],
            "barrier_records": barriers[:64],
            "sync_block_records": sync_blocks[:64],
        },
        "global_backend_policy": {
            "python_may": ["parse anchors", "emit JSON contract", "classify sync structures"],
            "python_must_not": ["print new set_flag/wait_flag MLIR", "delete barriers", "change event IDs"],
            "real_mutation_owner": "vTriton/HivmOpsEditor backend",
            "first_mutation_candidate": "only after real backend proves exact producer-consumer and event-liveness fields",
        },
        "actions": actions,
        "overall_decision": overall,
        "next_step": (
            "Run real backend dry-run against these actions once hivm-operation-backend is compiled; "
            "do not mutate until a single action has all required backend proofs."
        ),
    }


def build_sync_precision_contract_from_files(ir_path: str | Path, selected_plan_path: str | Path, output_dir: str | Path) -> Dict[str, Any]:
    ir_path = Path(ir_path)
    selected_plan_path = Path(selected_plan_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ir_text = ir_path.read_text(encoding="utf-8", errors="replace")
    selected_plan = json.loads(selected_plan_path.read_text(encoding="utf-8"))
    inventory = build_hivm_inventory(ir_text, source_name=str(ir_path))
    rewrite_plan = build_four_plan_rewrite_plan(selected_plan, inventory)
    contract = build_sync_precision_contract(selected_plan, inventory)

    (output_dir / "hivm_ir_inventory.official.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "four_plan_rewrite_plan.json").write_text(json.dumps(rewrite_plan, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "sync_precision_contract.json").write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
    return contract


__all__ = [
    "SYNC_PRECISION_SCHEMA_VERSION",
    "build_sync_precision_contract",
    "build_sync_precision_contract_from_files",
]
