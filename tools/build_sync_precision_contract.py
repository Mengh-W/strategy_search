#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build precise SyncPlan dry-run contract from IR + selected_plan.json."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategy_search.sync_contract_precision import build_sync_precision_contract_from_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Build precise SyncPlan dry-run contract")
    parser.add_argument("--ir", required=True, help="Input HIVM/NPUIR MLIR file")
    parser.add_argument("--selected-plan", required=True, help="selected_plan.json")
    parser.add_argument("--output-dir", required=True, help="output directory")
    args = parser.parse_args()

    contract = build_sync_precision_contract_from_files(args.ir, args.selected_plan, args.output_dir)
    summary = {
        "schema_version": contract.get("schema_version"),
        "overall_decision": contract.get("overall_decision"),
        "num_actions": len(contract.get("actions", [])),
        "num_events": contract.get("normalized_sync_inventory", {}).get("num_event_records"),
        "num_barriers": contract.get("normalized_sync_inventory", {}).get("num_barrier_records"),
        "num_sync_blocks": contract.get("normalized_sync_inventory", {}).get("num_sync_block_records"),
        "output_dir": str(Path(args.output_dir)),
    }
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    (Path(args.output_dir) / "sync_precision_contract_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
