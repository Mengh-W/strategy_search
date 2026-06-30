#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the most complete portable SyncPlan rewrite closure available without real vTriton.

This command is intentionally still portable/text-level.  It rewrites all
selected non-PIPE_ALL pipe_barrier actions up to --max-actions, validates the
structural delta, emits before/after liveness reports, and writes a unified diff.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategy_search.sync_contract_precision import build_sync_precision_contract_from_files
from strategy_search.sync_rewrite_executor import apply_restricted_sync_rewrite_from_files, select_rewritable_sync_actions
from strategy_search.sync_rewrite_validator import validate_restricted_sync_rewrite_files
from strategy_search.sync_rewrite_diff import write_sync_rewrite_diff_report
from strategy_search.sync_liveness_report import write_sync_liveness_report
from strategy_search.sync_rewrite_audit import write_sync_rewrite_audit_report


def main() -> int:
    ap = argparse.ArgumentParser(description="Run portable full SyncPlan rewrite closure")
    ap.add_argument("--ir", required=True)
    ap.add_argument("--selected-plan", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--max-actions", type=int, default=999999)
    ap.add_argument("--allow-pipe-all", action="store_true")
    args = ap.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    contract_dir = out / "sync_precision_contract"
    contract = build_sync_precision_contract_from_files(args.ir, args.selected_plan, contract_dir)
    contract_path = contract_dir / "sync_precision_contract.json"

    candidate_actions = select_rewritable_sync_actions(contract, max_actions=args.max_actions, allow_pipe_all=args.allow_pipe_all)
    candidate_report = {
        "schema_version": "hivm_sync_full_rewrite_candidate_report_v1",
        "num_candidate_actions": len(candidate_actions),
        "max_actions": args.max_actions,
        "allow_pipe_all": bool(args.allow_pipe_all),
        "candidate_actions": [
            {
                "action_id": a.get("action_id"),
                "line": a.get("_rewrite_line"),
                "pipe": a.get("_rewrite_pipe"),
                "risk": "medium_same_pipe_barrier_emulation",
                "reason_selected": "non_PIPE_ALL pipe_barrier action with textual line anchor",
            }
            for a in candidate_actions
        ],
    }
    (out / "sync_full_rewrite_candidates.json").write_text(json.dumps(candidate_report, indent=2, ensure_ascii=False), encoding="utf-8")

    before_liveness = write_sync_liveness_report(args.ir, out / "sync_liveness_before.json")
    optimized_ir = out / "optimized.sync_full_portable_rewritten.hivm.mlir"
    rewrite_report = out / "sync_full_portable_rewrite_report.json"
    validation_report = out / "sync_full_portable_rewrite_validation.json"
    diff_report = out / "sync_full_portable_rewrite_diff.json"
    audit_report = out / "sync_rewrite_safety_audit.json"

    rewrite = apply_restricted_sync_rewrite_from_files(
        args.ir,
        contract_path,
        optimized_ir,
        rewrite_report,
        max_actions=args.max_actions,
        allow_pipe_all=args.allow_pipe_all,
    )
    validation = validate_restricted_sync_rewrite_files(args.ir, optimized_ir, rewrite_report, validation_report)
    after_liveness = write_sync_liveness_report(optimized_ir, out / "sync_liveness_after.json")
    diff = write_sync_rewrite_diff_report(args.ir, optimized_ir, diff_report)
    audit = write_sync_rewrite_audit_report(
        args.ir, optimized_ir, contract_path, rewrite_report, validation_report,
        out / "sync_liveness_before.json", out / "sync_liveness_after.json", audit_report
    )

    closure_passed = bool(rewrite.get("mutation_performed")) and bool(validation.get("passed_portable_validation")) and bool(after_liveness.get("passed_portable_liveness")) and bool(audit.get("audit_passed_portable_level"))
    summary = {
        "schema_version": "hivm_sync_full_portable_rewrite_closure_summary_v1",
        "version": "V4.7-syncplan-rewrite-safety-audit",
        "input_ir": args.ir,
        "selected_plan": args.selected_plan,
        "contract": str(contract_path),
        "optimized_ir": str(optimized_ir),
        "candidate_report": str(out / "sync_full_rewrite_candidates.json"),
        "rewrite_report": str(rewrite_report),
        "validation_report": str(validation_report),
        "diff_report": str(diff_report),
        "audit_report": str(audit_report),
        "before_liveness_report": str(out / "sync_liveness_before.json"),
        "after_liveness_report": str(out / "sync_liveness_after.json"),
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
        "audit_batch_warnings": audit.get("batch_warnings"),
        "hivmopseditor_migration_action_count": len(audit.get("hivmopseditor_migration_action_list", [])),
        "portable_full_rewrite_closure_passed": closure_passed,
        "production_rewrite_claim_allowed": False,
        "claim_boundary": "audited portable/text-level SyncPlan rewrite closure; real HivmOpsEditor verifier/DES/msprof still required for production claim",
    }
    (out / "sync_full_portable_rewrite_closure_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if closure_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
