#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Analyze backend dry-run output and select a guarded mutation action."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategy_search.backend_dryrun_analyzer import write_analysis_outputs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", required=True, help="Backend contract JSON, usually sync_multibuffer_backend_contract.json")
    ap.add_argument("--dry-run-report", required=True, help="backend_dry_run_contract.json produced by execute_backend_contract.py")
    ap.add_argument("--output-dir", required=True, help="Directory for dry-run analysis and guarded mutation selection")
    ap.add_argument("--execution-summary", help="Optional backend_contract_execution_summary.json")
    args = ap.parse_args()

    summary = write_analysis_outputs(
        Path(args.contract),
        Path(args.dry_run_report),
        Path(args.output_dir),
        execution_summary_path=Path(args.execution_summary) if args.execution_summary else None,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
