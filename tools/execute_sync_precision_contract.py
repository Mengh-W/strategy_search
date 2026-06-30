#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build and execute a precise SyncPlan backend dry-run contract."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategy_search.backend_contract_runner import execute_backend_contract
from strategy_search.sync_contract_precision import build_sync_precision_contract_from_files
from strategy_search.sync_backend_dryrun_analyzer import write_sync_analysis_outputs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", required=True, help="Path to hivm-operation-backend or tools/fake_hivm_operation_backend.py")
    ap.add_argument("--ir", required=True, help="Input .hivm.mlir/.npuir.mlir")
    ap.add_argument("--selected-plan", required=True, help="selected_plan.json")
    ap.add_argument("--output-dir", required=True, help="Output directory")
    args = ap.parse_args()

    output_dir = Path(args.output_dir)
    contract_dir = output_dir / "sync_precision_contract"
    execution_dir = output_dir / "backend_execution"
    analysis_dir = output_dir / "sync_backend_dryrun_analysis"

    contract = build_sync_precision_contract_from_files(args.ir, args.selected_plan, contract_dir)
    contract_path = contract_dir / "sync_precision_contract.json"
    summary_path = contract_dir / "sync_precision_contract_summary.json"
    summary_path.write_text(json.dumps({
        "schema_version": "hivm_sync_precision_contract_summary_v1",
        "contract": str(contract_path),
        "overall_decision": contract.get("overall_decision"),
        "num_actions": len(contract.get("actions", [])),
        "num_events": contract.get("normalized_sync_inventory", {}).get("num_event_records"),
        "num_barriers": contract.get("normalized_sync_inventory", {}).get("num_barrier_records"),
        "num_sync_blocks": contract.get("normalized_sync_inventory", {}).get("num_sync_block_records"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    exec_summary = execute_backend_contract(
        Path(args.backend),
        Path(args.ir),
        contract_path,
        execution_dir,
        run_mutate=False,
        mutation_kind="sync_precision_contract",
    )
    dry_run_path = execution_dir / "backend_dry_run_contract.json"
    execution_summary_path = execution_dir / "backend_contract_execution_summary.json"
    analysis_summary = write_sync_analysis_outputs(
        contract_path,
        dry_run_path,
        analysis_dir,
        execution_summary_path=execution_summary_path,
    )

    print(json.dumps({
        "contract": str(contract_path),
        "execution_summary": str(execution_summary_path),
        "analysis_summary": str(analysis_dir / "sync_backend_dryrun_analysis_summary.json"),
        "overall_decision": analysis_summary.get("overall_decision"),
        "is_real_mlir_backend": analysis_summary.get("is_real_mlir_backend"),
        "action_count_contract": analysis_summary.get("action_count_contract"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
