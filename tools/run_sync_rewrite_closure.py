#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the complete portable SyncPlan restricted rewrite closure.

This is the no-vTriton-environment path.  It builds the precise SyncPlan
contract, applies the restricted text-level rewrite, validates the structural
op-count/event-pair delta, and emits a single closure summary.
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
from strategy_search.sync_rewrite_executor import apply_restricted_sync_rewrite_from_files
from strategy_search.sync_rewrite_validator import validate_restricted_sync_rewrite_files


def main() -> int:
    ap = argparse.ArgumentParser(description="Run portable restricted SyncPlan rewrite closure")
    ap.add_argument("--ir", required=True)
    ap.add_argument("--selected-plan", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--max-actions", type=int, default=1)
    ap.add_argument("--allow-pipe-all", action="store_true")
    args = ap.parse_args()

    out = Path(args.output_dir)
    contract_dir = out / "sync_precision_contract"
    contract = build_sync_precision_contract_from_files(args.ir, args.selected_plan, contract_dir)
    contract_path = contract_dir / "sync_precision_contract.json"

    optimized_ir = out / "optimized.sync_portable_rewritten.hivm.mlir"
    rewrite_report = out / "sync_portable_rewrite_report.json"
    validation_report = out / "sync_portable_rewrite_validation.json"

    rewrite = apply_restricted_sync_rewrite_from_files(
        args.ir,
        contract_path,
        optimized_ir,
        rewrite_report,
        max_actions=args.max_actions,
        allow_pipe_all=args.allow_pipe_all,
    )
    validation = validate_restricted_sync_rewrite_files(args.ir, optimized_ir, rewrite_report, validation_report)

    summary = {
        "schema_version": "hivm_sync_portable_rewrite_closure_summary_v1",
        "version": "V4.5-syncplan-portable-rewrite-closure",
        "input_ir": args.ir,
        "selected_plan": args.selected_plan,
        "contract": str(contract_path),
        "optimized_ir": str(optimized_ir),
        "rewrite_report": str(rewrite_report),
        "validation_report": str(validation_report),
        "contract_overall_decision": contract.get("overall_decision"),
        "mutation_performed": rewrite.get("mutation_performed"),
        "rewritten_action_count": rewrite.get("rewritten_action_count"),
        "passed_portable_validation": validation.get("passed_portable_validation"),
        "production_rewrite_claim_allowed": False,
        "claim_boundary": "portable restricted text-level SyncPlan rewrite; real HivmOpsEditor verify/DES/msprof still required",
    }
    (out / "sync_portable_rewrite_closure_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if validation.get("passed_portable_validation") else 1


if __name__ == "__main__":
    raise SystemExit(main())
