# -*- coding: utf-8 -*-
"""Analyze real/fake backend dry-run reports and select guarded mutation actions.

This module deliberately does *not* mutate HIVM IR.  It consumes:

* a backend contract generated from the four-Plan strategy result, and
* a backend dry-run report produced by ``execute_backend_contract.py``.

It then answers two operational questions:

1. Which contract actions did the backend actually locate/prove?
2. Which single action, if any, is safe enough to try as a guarded mutation?

The selector is conservative by design.  Fake backend output is always blocked
from mutation.  Sync validation actions are treated as verify-only checks.  The
first true mutation milestone is restricted to one MultiBufferPlan buffer-clone
action at a time, and only after a real MLIR/HivmOpsEditor backend proves the
required dry-run checks.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

DRYRUN_ANALYZER_VERSION = "hivm_backend_dryrun_analysis_v1"
GUARDED_SELECTOR_VERSION = "hivm_guarded_mutation_selector_v1"

# These names are intentionally generic because real backends may report only a
# subset.  Missing proof fields are not accepted for real mutation; they are
# listed as missing proofs in the analysis.
COMMON_PROOF_FIELDS = [
    "operation_found",
    "located",
]
MULTIBUFFER_REQUIRED_PROOFS = [
    "use_def_resolution_ok",
    "all_uses_accounted_for",
    "capacity_recheck_passed",
    "buffer_liveness_passed",
    "post_mutate_verify_expected",
]
SYNC_REQUIRED_PROOFS = [
    "event_pairs_reported",
    "event_liveness_passed",
    "no_deadlock_or_conflict_reported",
]


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _actions_by_id(contract: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(a.get("action_id")): a for a in contract.get("actions", []) if isinstance(a, dict) and a.get("action_id")}


def _dry_actions_by_id(dry_run: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for a in dry_run.get("actions", []) or []:
        if isinstance(a, dict) and a.get("action_id"):
            out[str(a.get("action_id"))] = a
    return out


def _bool_proof(obj: Dict[str, Any], key: str) -> Optional[bool]:
    """Read a proof field from multiple possible backend encodings."""
    if key in obj:
        return bool(obj.get(key))
    proofs = obj.get("proofs")
    if isinstance(proofs, dict) and key in proofs:
        return bool(proofs.get(key))
    checks = obj.get("checks")
    if isinstance(checks, dict) and key in checks:
        return bool(checks.get(key))
    acceptance = obj.get("acceptance")
    if isinstance(acceptance, dict) and key in acceptance:
        return bool(acceptance.get(key))
    passed = obj.get("passed_checks")
    if isinstance(passed, list) and key in passed:
        return True
    failed = obj.get("failed_checks")
    if isinstance(failed, list) and key in failed:
        return False
    return None


def _blockers_from(obj: Dict[str, Any]) -> List[str]:
    blockers: List[str] = []
    for key in ["blockers", "errors", "failed_checks", "reasons"]:
        val = obj.get(key)
        if isinstance(val, list):
            blockers.extend(str(x) for x in val)
        elif isinstance(val, str):
            blockers.append(val)
    return blockers


def _contract_action_complexity(action: Dict[str, Any]) -> Dict[str, Any]:
    target = action.get("target") or {}
    producer_ops = target.get("producer_ops") or []
    consumer_ops = target.get("consumer_ops") or []
    address_space = target.get("address_space")
    text_blob = json.dumps(action, ensure_ascii=False)
    has_gm_store_consumer = "hivm.hir.store" in text_blob or "address_space<gm>" in text_blob and "outs(%O_gm" in text_blob
    has_self_update_hint = False
    target_buffer = target.get("target_buffer")
    if target_buffer:
        for op in list(producer_ops) + list(consumer_ops):
            txt = op.get("text", "") if isinstance(op, dict) else ""
            # If buffer appears in both ins and outs of same op, clone/use replacement is harder.
            if f"ins({target_buffer}" in txt and f"outs({target_buffer}" in txt:
                has_self_update_hint = True
    score = 0
    reasons: List[str] = []
    if action.get("plan") == "MultiBufferPlan":
        score += 10
    if address_space in {"ub", "cbuf"}:
        score += 3
    if len(producer_ops) == 1:
        score += 2
    else:
        reasons.append(f"producer_count={len(producer_ops)}")
    if len(consumer_ops) == 1:
        score += 2
    else:
        reasons.append(f"consumer_count={len(consumer_ops)}")
    if has_gm_store_consumer:
        score -= 4
        reasons.append("gm_store_or_output_boundary_seen")
    if has_self_update_hint:
        score -= 3
        reasons.append("self_update_op_seen")
    if target.get("candidate_score") is not None:
        try:
            score += int(target.get("candidate_score"))
        except Exception:
            pass
    return {
        "target_buffer": target_buffer,
        "address_space": address_space,
        "producer_count": len(producer_ops),
        "consumer_count": len(consumer_ops),
        "has_gm_store_consumer": has_gm_store_consumer,
        "has_self_update_hint": has_self_update_hint,
        "static_priority_score": score,
        "static_risk_reasons": reasons,
    }


def _required_proofs_for_action(action: Dict[str, Any]) -> List[str]:
    plan = action.get("plan")
    if plan == "SyncPlan":
        return COMMON_PROOF_FIELDS + SYNC_REQUIRED_PROOFS
    if plan == "MultiBufferPlan":
        return COMMON_PROOF_FIELDS + MULTIBUFFER_REQUIRED_PROOFS
    return COMMON_PROOF_FIELDS


def analyze_backend_dryrun(contract: Dict[str, Any], dry_run: Dict[str, Any], *, execution_summary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    contract_actions = _actions_by_id(contract)
    dry_actions = _dry_actions_by_id(dry_run)
    is_real_backend = bool(
        dry_run.get("is_real_mlir_backend")
        or (execution_summary or {}).get("is_real_mlir_backend")
    )
    backend_status = dry_run.get("status") or "UNKNOWN"
    action_reports: List[Dict[str, Any]] = []

    for action_id, action in contract_actions.items():
        dry = dry_actions.get(action_id, {})
        blockers = _blockers_from(dry)
        required = _required_proofs_for_action(action)
        missing_proofs: List[str] = []
        failed_proofs: List[str] = []
        passed_proofs: List[str] = []
        for proof in required:
            value = _bool_proof(dry, proof)
            if value is True:
                passed_proofs.append(proof)
            elif value is False:
                failed_proofs.append(proof)
            else:
                missing_proofs.append(proof)

        plan = action.get("plan")
        mode = action.get("mode")
        static_complexity = _contract_action_complexity(action)

        if plan == "SyncPlan" and action.get("mutation_kind") == "validate_existing_set_wait_events":
            decision = "VERIFY_ONLY_NOT_MUTATION"
            reason = "existing event validation is a prerequisite check; it should not be mutated as the first guarded action"
        elif not is_real_backend:
            decision = "BLOCKED_FAKE_BACKEND"
            reason = "fake backend cannot prove MLIR/HivmOpsEditor legality or perform production mutation"
        elif blockers or failed_proofs or missing_proofs:
            decision = "BLOCKED_DRY_RUN_PROOF_INCOMPLETE"
            reason = "real backend dry-run did not provide all required proofs"
        elif plan == "MultiBufferPlan":
            # Additional policy: first guarded mutation should be simple local buffer clone.
            if static_complexity["producer_count"] == 1 and static_complexity["consumer_count"] == 1 and not static_complexity["has_gm_store_consumer"] and not static_complexity["has_self_update_hint"]:
                decision = "ELIGIBLE_FOR_SINGLE_ACTION_GUARDED_MUTATION"
                reason = "real backend dry-run passed and static action shape is simple enough for first guarded mutation"
            else:
                decision = "DRY_RUN_PASSED_BUT_DEFER_COMPLEX_ACTION"
                reason = "dry-run proofs passed but action shape is not the simplest first mutation candidate"
        else:
            decision = "DRY_RUN_ONLY"
            reason = "only Sync/MultiBuffer first-milestone actions are eligible for initial guarded mutation"

        action_reports.append({
            "action_id": action_id,
            "plan": plan,
            "mutation_kind": action.get("mutation_kind"),
            "mode": mode,
            "dry_run_seen": bool(dry),
            "backend_located": bool(_bool_proof(dry, "located") or _bool_proof(dry, "operation_found")),
            "passed_proofs": passed_proofs,
            "missing_proofs": missing_proofs,
            "failed_proofs": failed_proofs,
            "blockers": blockers,
            "static_complexity": static_complexity,
            "decision": decision,
            "reason": reason,
        })

    counts: Dict[str, int] = {}
    for item in action_reports:
        counts[item["decision"]] = counts.get(item["decision"], 0) + 1

    return {
        "schema_version": DRYRUN_ANALYZER_VERSION,
        "contract_schema_version": contract.get("schema_version"),
        "dry_run_schema_version": dry_run.get("schema_version"),
        "backend": dry_run.get("backend") or (execution_summary or {}).get("backend"),
        "backend_status": backend_status,
        "is_real_mlir_backend": is_real_backend,
        "action_count_contract": len(contract_actions),
        "action_count_dry_run": len(dry_actions),
        "decision_counts": counts,
        "actions": action_reports,
        "overall_decision": (
            "HAS_GUARDED_MUTATION_CANDIDATE"
            if any(x["decision"] == "ELIGIBLE_FOR_SINGLE_ACTION_GUARDED_MUTATION" for x in action_reports)
            else ("WAIT_FOR_REAL_BACKEND" if not is_real_backend else "NO_MUTATION_CANDIDATE_YET")
        ),
        "notes": [
            "This report analyzes dry-run proof completeness only; it does not mutate IR.",
            "Fake backend output is always blocked from production mutation.",
            "The first mutation milestone is restricted to one MultiBufferPlan action at a time.",
        ],
    }


def select_guarded_mutation_action(contract: Dict[str, Any], dryrun_analysis: Dict[str, Any]) -> Dict[str, Any]:
    actions_by_id = _actions_by_id(contract)
    eligible = [a for a in dryrun_analysis.get("actions", []) if a.get("decision") == "ELIGIBLE_FOR_SINGLE_ACTION_GUARDED_MUTATION"]
    eligible.sort(key=lambda x: x.get("static_complexity", {}).get("static_priority_score", 0), reverse=True)
    selected = eligible[0] if eligible else None

    if selected is None:
        return {
            "schema_version": GUARDED_SELECTOR_VERSION,
            "selected": False,
            "selected_action_id": None,
            "reason": "no action passed real-backend dry-run proofs and guarded mutation filters",
            "single_action_contract": None,
            "eligible_action_count": 0,
            "blocked_summary": dryrun_analysis.get("decision_counts", {}),
        }

    action_id = selected["action_id"]
    action = actions_by_id[action_id]
    single_contract = dict(contract)
    single_contract["schema_version"] = str(contract.get("schema_version", "contract")) + "_single_guarded_action"
    single_contract["actions"] = [action]
    single_contract["guarded_mutation_policy"] = {
        "selected_action_id": action_id,
        "allowed_mutation_kind": action.get("mutation_kind"),
        "single_action_only": True,
        "requires_post_mutate_verify": True,
        "requires_des_trace_if_available": True,
        "requires_manual_review_before_msprof": True,
        "do_not_batch_mutate": True,
    }
    return {
        "schema_version": GUARDED_SELECTOR_VERSION,
        "selected": True,
        "selected_action_id": action_id,
        "selected_plan": selected.get("plan"),
        "selected_mutation_kind": action.get("mutation_kind"),
        "reason": selected.get("reason"),
        "eligible_action_count": len(eligible),
        "selected_static_complexity": selected.get("static_complexity"),
        "single_action_contract": single_contract,
    }


def write_analysis_outputs(
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
    analysis = analyze_backend_dryrun(contract, dry_run, execution_summary=execution_summary)
    selector = select_guarded_mutation_action(contract, analysis)

    analysis_path = output_dir / "backend_dryrun_analysis.json"
    selector_path = output_dir / "guarded_mutation_selection.json"
    analysis_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    selector_path.write_text(json.dumps(selector, ensure_ascii=False, indent=2), encoding="utf-8")

    single_path: Optional[Path] = None
    if selector.get("selected") and selector.get("single_action_contract"):
        single_path = output_dir / "single_guarded_action_contract.json"
        single_path.write_text(json.dumps(selector["single_action_contract"], ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "schema_version": "hivm_backend_dryrun_analysis_outputs_v1",
        "analysis": str(analysis_path),
        "selection": str(selector_path),
        "single_guarded_action_contract": str(single_path) if single_path else None,
        "overall_decision": analysis.get("overall_decision"),
        "selected_action_id": selector.get("selected_action_id"),
        "selected": selector.get("selected"),
    }
    (output_dir / "backend_dryrun_analysis_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
