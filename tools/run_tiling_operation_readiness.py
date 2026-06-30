#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build TilingPlan operation-level Linux prevalidation reports."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from strategy_search.tiling_operation_readiness import write_tiling_operation_readiness_outputs


def main() -> int:
    ap = argparse.ArgumentParser(description="Build TilingPlan operation readiness dry-run plan.")
    ap.add_argument("--ir", required=True)
    ap.add_argument("--selected-plan", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()
    result = write_tiling_operation_readiness_outputs(args.ir, args.selected_plan, args.output_dir)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
