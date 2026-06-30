#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run V5.2 TilingPlan restricted metadata true rewrite."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from strategy_search.tiling_true_rewrite import write_tiling_true_rewrite_outputs

def main() -> int:
    ap = argparse.ArgumentParser(description="Run restricted metadata true TilingPlan rewrite.")
    ap.add_argument("--ir", required=True)
    ap.add_argument("--selected-plan", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()
    result = write_tiling_true_rewrite_outputs(args.ir, args.selected_plan, args.output_dir)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
