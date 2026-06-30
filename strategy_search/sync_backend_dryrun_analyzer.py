# -*- coding: utf-8 -*-
"""Analyze backend dry-run results for precise SyncPlan contracts.

This module consumes ``sync_precision_contract.json`` and a backend dry-run
report.  It is intentionally check-only: SyncPlan mutation remains disabled
until a real HivmOpsEditor backend proves precise target location, event
operands, event liveness, and deadlock safety.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

SYNC_BACKEND_DRYRUN_ANALYSIS_VERSION = "hivm_sync_backend_dryrun_analysis_v1"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _actions_by_id(obj: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(a.get("action_id")): a for a in obj.get("actions", []) if isinstance(a, dict) and a.get("action_id")}


def _dry_actions_by_id(obj: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(a.get("action_id")): a for a in obj.get("actions", []) if isinstance(a, dict) and a.get("action_id")}


def _bool_from(obj: Dict[str, Any], key: str) -> Optional[bool]:
    if key in obj:
        return bool(obj.get(key))
    for field in ("proofs", "checks", "acceptance"):
        sub = obj.get(field)
        if isinstance(sub, dict) and key in sub:
            return bool(sub.get(key))
    passed = obj.get("passed_checks")
    failed = obj.get("failed_checks")
    if isinstance(passed, list) and key in passed:
        return True
    if isinstance(failed, list) and key in failed:
        return False
    return None


def _blockers(obj: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for key in ("blockers", "errors", "failed_checks", "warnings", "reasons"):
        val = obj.get(key)
        if isinstance(val, list):
            out.extend(str(x) for x in val)
        elif isinstance(val, str):
            out.append(val)
    return out


def _required_checks(action: Dict[str, Any]) -> List[str]:
    kind = action.get("mutation_kind")
    if kind == "validate_existing_event_pair_liveness":
        return [
            "operation_found",
            "located",
            "backend_parsed_event_operands",
            "event_pairs_reported",
            "event_liveness_passed",
            "no_deadlock_or_conflict_reported",
        ]
    if kind == "barrier_to_directional_event_pair":
        return [
            "operation_found",
            "located",
            "target_barrier_located_by_backend",
            "producer_consumer_pair_reported",
            "fresh_or_safe_reused_event_reported",
            "backend_can_print_official_set_wait_ops",
            "event_liveness_passes_after_dry_run_plan",
        ]
    if kind == "classify_sync_block_scope":
        return [
            "operation_found",
            "located",
            "backend_reports_sync_block_mode_and_scope",
        ]
    return ["operation_found", "located"]


def analyze_sync_backend_dryrun(
    contract: Dict[str, Any],
    dry_run: Dict[str, Any],
    *,
    execution_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    contract_actions = _actions_by_id(contract)
    dry_actions = _dry_actions_by_id(dry_run)
    is_real = bool(dry_run.get("is_real_mlir_backend") or (execution_summary or {}).get("is_real_mlir_backend"))

    reports: List[Dict[str, Any]] = []
    for aid, action in contract_actions.items():
        dry = dry_actions.get(aid, {})
        req = _required_checks(action)
        missing: List[str] = []
        failed: List[str] = []
        passed: List[str] = []
        for check in req:
            value = _bool_from(dry, check)
            if value is True:
                passed.append(check)
            elif value is False:
                failed.append(check)
            else:
                missing.append(check)
        bl = _blockers(dry)

        if not dry:
            decision = "BLOCKED_ACTION_NOT_REPORTED_BY_BACKEND"
            reason = "backend dry-run did not return a per-action result"
        elif not is_real:
            decision = "FAKE_BACKEND_CHECK_ONLY"
            reason = "fake backend can locate textual anchors only; not valid for production sync rewrite"
        elif failed or missing or bl:
            decision = "REAL_BACKEND_PROOF_INCOMPLETE"
            reason = "real backend did not provide all required SyncPlan proofs"
        else:
            # Even with complete dry-run proofs, SyncPlan V4.1 is still check-only.
            decision = "SYNC_DRY_RUN_PROOFS_COMPLETE_MUTATION_STILL_GUARDED"
            reason = "proofs complete; next step is manual review and a separate single-action guarded mutation design"

        reports.append({
            "action_id": aid,
            "mutation_kind": action.get("mutation_kind"),
            "mode": action.get("mode"),
            "dry_run_seen": bool(dry),
            "backend_located": bool(_bool_from(dry, "located") or _bool_from(dry, "operation_found")),
            "required_checks": req,
            "passed_checks": passed,
            "missing_checks": missing,
            "failed_checks": failed,
            "blockers": bl,
            "decision": decision,
            "reason": reason,
            "mutation_allowed_by_contract": bool(action.get("mutation_allowed")),
        })

    counts: Dict[str, int] = {}
    for r in reports:
        counts[r["decision"]] = counts.get(r["decision"], 0) + 1

    if not is_real:
        overall = "WAIT_FOR_REAL_BACKEND"
    elif any(r["decision"] == "SYNC_DRY_RUN_PROOFS_COMPLETE_MUTATION_STILL_GUARDED" for r in reports):
        overall = "REAL_BACKEND_SYNC_PROOFS_AVAILABLE_REVIEW_REQUIRED"
    elif reports:
        overall = "REAL_BACKEND_SYNC_PROOFS_INCOMPLETE"
    else:
        overall = "NO_SYNC_ACTIONS"

    return {
        "schema_version": SYNC_BACKEND_DRYRUN_ANALYSIS_VERSION,
        "contract_schema_version": contract.get("schema_version"),
        "dry_run_schema_version": dry_run.get("schema_version"),
        "backend": dry_run.get("backend") or (execution_summary or {}).get("backend"),
        "is_real_mlir_backend": is_real,
        "action_count_contract": len(contract_actions),
        "action_count_dry_run": len(dry_actions),
        "decision_counts": counts,
        "overall_decision": overall,
        "actions": reports,
        "notes": [
            "SyncPlan V4.1 remains dry-run/check-only; it does not authorize mutation.",
            "Existing event validation and barrier-to-event planning require real parser/event-liveness/deadlock proofs.",
            "Fake backend output is useful only for CLI/report plumbing.",
        ],
    }


def write_sync_analysis_outputs(
    contract_path: Path,
    dry_run_path: Path,
    output_dir: Path,
    *,
    execution_summary_path: Optional[Path] = None,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    contract = load_json(contract_path)
    dry_run = load_json(dry_run_path)
    execution_summary = load_json(execution_summary_path) if execution_summary_path and execution_summary_path.exists() else None
    analysis = analyze_sync_backend_dryrun(contract, dry_run, execution_summary=execution_summary)
    out = output_dir / "sync_backend_dryrun_analysis.json"
    out.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "schema_version": "hivm_sync_backend_dryrun_analysis_outputs_v1",
        "analysis": str(out),
        "overall_decision": analysis.get("overall_decision"),
        "is_real_mlir_backend": analysis.get("is_real_mlir_backend"),
        "action_count_contract": analysis.get("action_count_contract"),
        "decision_counts": analysis.get("decision_counts"),
    }
    summary_path = output_dir / "sync_backend_dryrun_analysis_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


__all__ = [
    "SYNC_BACKEND_DRYRUN_ANALYSIS_VERSION",
    "analyze_sync_backend_dryrun",
    "write_sync_analysis_outputs",
]
