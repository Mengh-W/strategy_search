#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
from pathlib import Path

from strategy_search.sync_contract_precision import build_sync_precision_contract_from_files
from strategy_search.sync_rewrite_executor import apply_restricted_sync_rewrite_from_files


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply restricted SyncPlan pipe_barrier rewrite")
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
    output_ir = out / "optimized.sync_rewritten.hivm.mlir"
    report_path = out / "sync_rewrite_report.json"
    report = apply_restricted_sync_rewrite_from_files(
        args.ir,
        contract_path,
        output_ir,
        report_path,
        max_actions=args.max_actions,
        allow_pipe_all=args.allow_pipe_all,
    )
    summary = {
        "schema_version": "hivm_sync_rewrite_cli_summary_v1",
        "contract": str(contract_path),
        "output_ir": str(output_ir),
        "report": str(report_path),
        "contract_overall_decision": contract.get("overall_decision"),
        "mutation_performed": report.get("mutation_performed"),
        "rewritten_action_count": report.get("rewritten_action_count"),
        "production_rewrite_claim_allowed": report.get("production_rewrite_claim_allowed"),
    }
    (out / "sync_rewrite_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
