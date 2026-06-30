#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run V5.3 unified restricted true rewrite for all four plans.

Order:
1. TilingPlan metadata true rewrite
2. MultiBufferPlan restricted true rewrite
3. CVPipelinePlan restricted true rewrite
4. SyncPlan audited portable rewrite cleanup
5. Parameter coverage metadata block insertion
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategy_search.tiling_true_rewrite import write_tiling_true_rewrite_outputs
from strategy_search.multibuffer_true_rewrite import write_multibuffer_true_rewrite_outputs
from strategy_search.cvpipeline_true_rewrite import write_cvpipeline_true_rewrite_outputs
from strategy_search.parameter_rewrite_coverage import write_parameter_coverage_outputs, build_parameter_rewrite_coverage

VERSION = "V5.3-four-plan-true-rewrite-with-parameter-coverage"


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _run_sync(input_ir: Path, selected_plan: Path, output_dir: Path, max_actions: int) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(ROOT / "tools" / "run_sync_full_rewrite.py"),
        "--ir", str(input_ir),
        "--selected-plan", str(selected_plan),
        "--output-dir", str(output_dir),
        "--max-actions", str(max_actions),
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        (output_dir / "sync_stage_error.stdout.txt").write_text(proc.stdout, encoding="utf-8")
        (output_dir / "sync_stage_error.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    summary_path = output_dir / "sync_full_portable_rewrite_closure_summary.json"
    summary = _load_json(summary_path)
    summary["subprocess_returncode"] = proc.returncode
    return summary


def run_four_plan_true_rewrite(
    ir_path: str | Path,
    selected_plan_path: str | Path,
    output_dir: str | Path,
    max_multibuffer_candidates: int = 80,
    max_multibuffer_actions: int = 3,
    max_cvpipeline_windows: int = 50,
    max_cvpipeline_actions: int = 2,
    max_sync_actions: int = 999999,
) -> dict:
    ir_path = Path(ir_path)
    selected_plan_path = Path(selected_plan_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stages = output_dir / "stages"
    stages.mkdir(exist_ok=True)

    # Coverage is computed first so the user can answer whether every selected parameter has a consumer.
    selected_plan = _load_json(selected_plan_path)
    coverage = build_parameter_rewrite_coverage(selected_plan)
    (output_dir / "parameter_rewrite_coverage_initial.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")

    # 1. Tiling metadata rewrite.
    tiling_dir = stages / "01_tiling_true_rewrite"
    tiling = write_tiling_true_rewrite_outputs(ir_path, selected_plan_path, tiling_dir)
    tiling_ir = Path(tiling["paths"]["optimized_ir"])

    # 2. MultiBuffer true rewrite on the tiling output.
    mb_dir = stages / "02_multibuffer_true_rewrite"
    mb = write_multibuffer_true_rewrite_outputs(
        tiling_ir, selected_plan_path, mb_dir,
        max_candidates=max_multibuffer_candidates,
        max_actions=max_multibuffer_actions,
    )
    mb_ir = Path(mb["optimized_ir_path"])

    # 3. CVPipeline true rewrite on the MultiBuffer output.
    cv_dir = stages / "03_cvpipeline_true_rewrite"
    cv = write_cvpipeline_true_rewrite_outputs(
        mb_ir, selected_plan_path, cv_dir,
        max_windows=max_cvpipeline_windows,
        max_actions=max_cvpipeline_actions,
    )
    cv_ir = Path(cv["optimized_ir_path"])

    # 4. SyncPlan rewrite cleanup on the CVPipeline output.
    sync_dir = stages / "04_syncplan_true_rewrite"
    sync = _run_sync(cv_ir, selected_plan_path, sync_dir, max_actions=max_sync_actions)
    sync_ir = sync_dir / "optimized.sync_full_portable_rewritten.hivm.mlir"
    if not sync_ir.exists():
        sync_ir = cv_ir

    # 5. Embed every selected controllable parameter back to final IR metadata.
    final_ir = output_dir / "optimized.four_plan_true_rewritten.hivm.mlir"
    coverage_out = write_parameter_coverage_outputs(selected_plan_path, sync_ir, final_ir, output_dir)

    stage_summaries = {
        "tiling": tiling.get("summary", {}),
        "multibuffer": mb.get("summary", {}),
        "cvpipeline": cv.get("summary", {}),
        "sync": sync,
        "parameter_coverage": coverage_out.get("summary", {}),
    }
    all_validations_passed = all([
        bool(stage_summaries["tiling"].get("passed_portable_validation")),
        bool(stage_summaries["multibuffer"].get("passed_portable_validation")),
        bool(stage_summaries["cvpipeline"].get("passed_portable_validation")),
        bool(stage_summaries["sync"].get("portable_full_rewrite_closure_passed", stage_summaries["sync"].get("passed_portable_validation"))),
        bool(stage_summaries["parameter_coverage"].get("all_controllable_parameters_rewritten_back_to_ir")),
    ])

    semantic_mutation_count = sum(bool(stage_summaries[k].get("semantic_mutation_performed")) for k in ["tiling", "multibuffer", "cvpipeline"])
    semantic_mutation_count += 1 if bool(stage_summaries["sync"].get("mutation_performed")) else 0

    summary = {
        "schema_version": "hivm_v53_four_plan_true_rewrite_summary_v1",
        "version": VERSION,
        "input_ir": str(ir_path),
        "selected_plan": str(selected_plan_path),
        "optimized_ir": str(final_ir),
        "stage_summaries": stage_summaries,
        "four_plan_rewrite_order": ["tiling", "multibuffer", "cvpipeline", "sync_cleanup", "parameter_metadata_coverage"],
        "semantic_mutation_count": semantic_mutation_count,
        "four_plan_restricted_true_rewrite_performed": semantic_mutation_count >= 4,
        "all_portable_validations_passed": all_validations_passed,
        "all_controllable_parameters_rewritten_back_to_ir": stage_summaries["parameter_coverage"].get("all_controllable_parameters_rewritten_back_to_ir"),
        "all_controllable_parameters_semantic_operation_rewrite": stage_summaries["parameter_coverage"].get("all_controllable_parameters_semantic_operation_rewrite"),
        "production_rewrite_claim_allowed": False,
        "claim_boundary": "restricted portable true rewrite with parameter metadata coverage; real HivmOpsEditor verifier/DES/msprof still required for production claim",
    }
    (output_dir / "four_plan_true_rewrite_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Run unified V5.3 four-plan restricted true rewrite pipeline")
    ap.add_argument("--ir", required=True)
    ap.add_argument("--selected-plan", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--max-multibuffer-candidates", type=int, default=80)
    ap.add_argument("--max-multibuffer-actions", type=int, default=3)
    ap.add_argument("--max-cvpipeline-windows", type=int, default=50)
    ap.add_argument("--max-cvpipeline-actions", type=int, default=2)
    ap.add_argument("--max-sync-actions", type=int, default=999999)
    args = ap.parse_args()
    summary = run_four_plan_true_rewrite(
        args.ir, args.selected_plan, args.output_dir,
        max_multibuffer_candidates=args.max_multibuffer_candidates,
        max_multibuffer_actions=args.max_multibuffer_actions,
        max_cvpipeline_windows=args.max_cvpipeline_windows,
        max_cvpipeline_actions=args.max_cvpipeline_actions,
        max_sync_actions=args.max_sync_actions,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("all_portable_validations_passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
