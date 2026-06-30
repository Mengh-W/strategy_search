#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the unified four-plan rewrite controller."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategy_search.four_plan_rewrite_controller import write_unified_four_plan_controller_outputs


def main() -> int:
    ap = argparse.ArgumentParser(description="Run unified HIVM four-plan rewrite controller")
    ap.add_argument("--ir", required=True)
    ap.add_argument("--selected-plan", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--max-sync-actions", type=int, default=999999)
    ap.add_argument("--max-multibuffer-candidates", type=int, default=80)
    ap.add_argument("--max-cvpipeline-windows", type=int, default=50)
    ap.add_argument("--max-annotations", type=int, default=20)
    ap.add_argument("--allow-pipe-all", action="store_true")
    args = ap.parse_args()
    result = write_unified_four_plan_controller_outputs(
        args.ir,
        args.selected_plan,
        args.output_dir,
        max_sync_actions=args.max_sync_actions,
        max_multibuffer_candidates=args.max_multibuffer_candidates,
        max_cvpipeline_windows=args.max_cvpipeline_windows,
        max_annotations=args.max_annotations,
        allow_pipe_all=args.allow_pipe_all,
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0 if result["summary"].get("sync_portable_rewrite_passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
