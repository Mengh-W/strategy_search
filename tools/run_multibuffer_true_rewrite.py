#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run V5.0 MultiBufferPlan restricted true rewrite."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategy_search.multibuffer_true_rewrite import write_multibuffer_true_rewrite_outputs


def main() -> int:
    ap = argparse.ArgumentParser(description="Run restricted true MultiBufferPlan rewrite and validation.")
    ap.add_argument("--ir", required=True, help="Input HIVM/NPU-IR MLIR file")
    ap.add_argument("--selected-plan", required=True, help="selected_plan.json")
    ap.add_argument("--output-dir", required=True, help="Output directory")
    ap.add_argument("--max-candidates", type=int, default=80)
    ap.add_argument("--max-actions", type=int, default=3)
    args = ap.parse_args()
    result = write_multibuffer_true_rewrite_outputs(
        args.ir,
        args.selected_plan,
        args.output_dir,
        max_candidates=args.max_candidates,
        max_actions=args.max_actions,
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
