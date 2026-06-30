#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run a bound end-to-end HIVM strategy search + four-plan portable rewrite.

This command deliberately prevents the common mistake of rewriting an input IR
with a stale selected_plan.json from a previous smoke run. It first runs
``auto_strategy_search.py`` into ``<output-dir>/01_search`` and then feeds that
fresh ``selected_plan.json`` into ``tools/run_four_plan_true_rewrite.py`` under
``<output-dir>/02_four_plan_rewrite``.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def run_search_and_four_plan_rewrite(
    *,
    kernel: str | Path,
    hardware_config: str | Path,
    cost_model_config: str | Path,
    output_dir: str | Path,
    cost_risk_mode: str = "conservative",
    candidate_space: str = "standard",
    max_multibuffer_candidates: int = 80,
    max_multibuffer_actions: int = 3,
    max_cvpipeline_windows: int = 50,
    max_cvpipeline_actions: int = 2,
    max_sync_actions: int = 999999,
) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    search_dir = output_dir / "01_search"
    rewrite_dir = output_dir / "02_four_plan_rewrite"
    search_dir.mkdir(parents=True, exist_ok=True)
    rewrite_dir.mkdir(parents=True, exist_ok=True)

    search_cmd = [
        sys.executable,
        str(ROOT / "auto_strategy_search.py"),
        "--kernel", str(kernel),
        "--hardware-config", str(hardware_config),
        "--cost-model-config", str(cost_model_config),
        "--cost-risk-mode", str(cost_risk_mode),
        "--candidate-space", str(candidate_space),
        "--output-dir", str(search_dir),
    ]
    search_proc = _run(search_cmd, cwd=ROOT)
    (search_dir / "command.stdout.txt").write_text(search_proc.stdout, encoding="utf-8")
    (search_dir / "command.stderr.txt").write_text(search_proc.stderr, encoding="utf-8")
    selected_plan = search_dir / "selected_plan.json"

    rewrite_summary: dict = {}
    rewrite_returncode = None
    if search_proc.returncode == 0 and selected_plan.exists():
        rewrite_cmd = [
            sys.executable,
            str(ROOT / "tools" / "run_four_plan_true_rewrite.py"),
            "--ir", str(kernel),
            "--selected-plan", str(selected_plan),
            "--output-dir", str(rewrite_dir),
            "--max-multibuffer-candidates", str(max_multibuffer_candidates),
            "--max-multibuffer-actions", str(max_multibuffer_actions),
            "--max-cvpipeline-windows", str(max_cvpipeline_windows),
            "--max-cvpipeline-actions", str(max_cvpipeline_actions),
            "--max-sync-actions", str(max_sync_actions),
        ]
        rewrite_proc = _run(rewrite_cmd, cwd=ROOT)
        rewrite_returncode = rewrite_proc.returncode
        (rewrite_dir / "command.stdout.txt").write_text(rewrite_proc.stdout, encoding="utf-8")
        (rewrite_dir / "command.stderr.txt").write_text(rewrite_proc.stderr, encoding="utf-8")
        summary_path = rewrite_dir / "four_plan_true_rewrite_summary.json"
        if summary_path.exists():
            rewrite_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    else:
        rewrite_returncode = None

    selected_plan_bound = search_proc.returncode == 0 and selected_plan.exists()
    rewrite_summary_loaded = bool(rewrite_summary)
    rewrite_process_succeeded = rewrite_returncode == 0
    all_portable_validations_passed = bool(rewrite_summary.get("all_portable_validations_passed", False))
    end_to_end_passed = bool(
        selected_plan_bound
        and rewrite_summary_loaded
        and rewrite_process_succeeded
        and all_portable_validations_passed
    )

    summary = {
        "schema_version": "hivm_v531_bound_search_rewrite_summary_v2",
        "version": "V5.3.1-bound-search-plus-four-plan-portable-rewrite-honest-exit",
        "kernel": str(kernel),
        "hardware_config": str(hardware_config),
        "cost_model_config": str(cost_model_config),
        "output_dir": str(output_dir),
        "search_dir": str(search_dir),
        "rewrite_dir": str(rewrite_dir),
        "selected_plan": str(selected_plan),
        "search_returncode": search_proc.returncode,
        "rewrite_returncode": rewrite_returncode,
        "selected_plan_bound_to_same_input": selected_plan_bound,
        "rewrite_summary_loaded": rewrite_summary_loaded,
        "rewrite_process_succeeded": rewrite_process_succeeded,
        # Backward-compatible field name, but now means full successful closure rather than only stale-plan avoidance.
        "search_and_rewrite_bound_to_same_input": end_to_end_passed,
        "end_to_end_passed": end_to_end_passed,
        "rewrite_optimized_ir": rewrite_summary.get("optimized_ir"),
        "all_portable_validations_passed": all_portable_validations_passed,
        "failure_reason": None if end_to_end_passed else (
            "search_failed" if search_proc.returncode != 0 else
            "selected_plan_missing" if not selected_plan.exists() else
            "rewrite_summary_missing" if not rewrite_summary_loaded else
            "rewrite_process_failed" if not rewrite_process_succeeded else
            "portable_validation_failed"
        ),
        "production_rewrite_claim_allowed": False,
        "claim_boundary": "fresh selected_plan is bound to the same input IR; portable rewrite only; real HivmOpsEditor/MLIR verifier/DES/msprof still required",
    }
    (output_dir / "bound_search_rewrite_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Run bound search + four-plan portable rewrite")
    ap.add_argument("--kernel", required=True)
    ap.add_argument("--hardware-config", default="configs/ascend_910b.json")
    ap.add_argument("--cost-model-config", default="configs/cost_model_conservative.json")
    ap.add_argument("--cost-risk-mode", default="conservative", choices=["conservative", "balanced", "aggressive"])
    ap.add_argument("--candidate-space", default="standard")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--max-multibuffer-candidates", type=int, default=80)
    ap.add_argument("--max-multibuffer-actions", type=int, default=3)
    ap.add_argument("--max-cvpipeline-windows", type=int, default=50)
    ap.add_argument("--max-cvpipeline-actions", type=int, default=2)
    ap.add_argument("--max-sync-actions", type=int, default=999999)
    args = ap.parse_args()
    summary = run_search_and_four_plan_rewrite(
        kernel=args.kernel,
        hardware_config=args.hardware_config,
        cost_model_config=args.cost_model_config,
        cost_risk_mode=args.cost_risk_mode,
        candidate_space=args.candidate_space,
        output_dir=args.output_dir,
        max_multibuffer_candidates=args.max_multibuffer_candidates,
        max_multibuffer_actions=args.max_multibuffer_actions,
        max_cvpipeline_windows=args.max_cvpipeline_windows,
        max_cvpipeline_actions=args.max_cvpipeline_actions,
        max_sync_actions=args.max_sync_actions,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("end_to_end_passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
