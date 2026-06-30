#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run CVPipelinePlan staged rewrite planner."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategy_search.cvpipeline_stage_planner import write_cvpipeline_stage_outputs


def main() -> int:
    ap = argparse.ArgumentParser(description="Build CVPipelinePlan stage report and rewrite-plan scaffold.")
    ap.add_argument("--ir", required=True, help="Input HIVM/NPU-IR MLIR file")
    ap.add_argument("--selected-plan", required=True, help="selected_plan.json")
    ap.add_argument("--output-dir", required=True, help="Output directory")
    ap.add_argument("--multibuffer-stage-report", default=None, help="Optional V4.9 multibuffer_stage_boundary_report.json")
    ap.add_argument("--max-windows", type=int, default=50)
    ap.add_argument("--max-annotations", type=int, default=20)
    args = ap.parse_args()
    result = write_cvpipeline_stage_outputs(
        args.ir,
        args.selected_plan,
        args.output_dir,
        multibuffer_stage_report_path=args.multibuffer_stage_report,
        max_windows=args.max_windows,
        max_annotations=args.max_annotations,
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
