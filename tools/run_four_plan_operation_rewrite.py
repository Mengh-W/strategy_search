#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from strategy_search.operation_rewrite.four_plan_operation_rewriter import run_four_plan_operation_rewrite

def main() -> int:
    ap = argparse.ArgumentParser(description="Run V6.0 four-plan operation rewrite with real operation materialization")
    ap.add_argument("--ir", required=True)
    ap.add_argument("--selected-plan", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--max-multibuffer-candidates", type=int, default=80)
    ap.add_argument("--max-multibuffer-actions", type=int, default=4)
    ap.add_argument("--max-cvpipeline-windows", type=int, default=50)
    ap.add_argument("--max-cvpipeline-actions", type=int, default=3)
    args = ap.parse_args()
    summary = run_four_plan_operation_rewrite(args.ir, args.selected_plan, args.output_dir, args.max_multibuffer_candidates, args.max_multibuffer_actions, args.max_cvpipeline_windows, args.max_cvpipeline_actions)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("four_plan_operation_rewrite_performed") and summary.get("portable_validation_passed") else 1
if __name__ == "__main__":
    raise SystemExit(main())
