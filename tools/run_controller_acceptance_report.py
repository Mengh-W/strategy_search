#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run V4.12 acceptance report generation.

By default this tool first runs the unified four-plan controller, then converts
its JSON outputs into Markdown/HTML acceptance reports.  It can also consume an
existing controller report via --controller-report.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategy_search.four_plan_rewrite_controller import write_unified_four_plan_controller_outputs
from strategy_search.controller_acceptance_report import write_acceptance_outputs


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate HIVM four-plan controller acceptance report")
    ap.add_argument("--ir")
    ap.add_argument("--selected-plan")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--controller-report")
    ap.add_argument("--controller-summary")
    ap.add_argument("--max-sync-actions", type=int, default=999999)
    ap.add_argument("--max-multibuffer-candidates", type=int, default=80)
    ap.add_argument("--max-cvpipeline-windows", type=int, default=50)
    ap.add_argument("--max-annotations", type=int, default=20)
    ap.add_argument("--allow-pipe-all", action="store_true")
    args = ap.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    if args.controller_report:
        controller_report = Path(args.controller_report)
        controller_summary = Path(args.controller_summary) if args.controller_summary else None
    else:
        if not args.ir or not args.selected_plan:
            ap.error("--ir and --selected-plan are required unless --controller-report is provided")
        controller_dir = out / "controller_run"
        result = write_unified_four_plan_controller_outputs(
            args.ir,
            args.selected_plan,
            controller_dir,
            max_sync_actions=args.max_sync_actions,
            max_multibuffer_candidates=args.max_multibuffer_candidates,
            max_cvpipeline_windows=args.max_cvpipeline_windows,
            max_annotations=args.max_annotations,
            allow_pipe_all=args.allow_pipe_all,
        )
        controller_report = Path(result["controller_report_path"])
        controller_summary = Path(result["controller_summary_path"])

    acceptance = write_acceptance_outputs(controller_report, out / "acceptance_report", controller_summary)
    print(json.dumps(acceptance["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
