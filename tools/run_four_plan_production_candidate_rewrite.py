#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run V5.5 four-plan production-candidate rewrite pipeline.

This command is intentionally stricter than the old V5.3 pipeline: every plan
must perform a visible semantic/textual operation mutation, otherwise the final
summary marks the four-plan rewrite incomplete.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategy_search.tiling_operation_true_rewrite_v55 import write_tiling_operation_true_rewrite_outputs
from strategy_search.multibuffer_true_rewrite import write_multibuffer_true_rewrite_outputs
from strategy_search.cvpipeline_true_rewrite import write_cvpipeline_true_rewrite_outputs
from strategy_search.sync_event_true_rewrite_v55 import write_sync_event_true_rewrite_outputs
from strategy_search.parameter_rewrite_coverage import write_parameter_coverage_outputs, build_parameter_rewrite_coverage

VERSION = "V5.5-four-plan-production-candidate-rewrite"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def run_four_plan_production_candidate_rewrite(
    ir_path: str | Path,
    selected_plan_path: str | Path,
    output_dir: str | Path,
    max_multibuffer_candidates: int = 80,
    max_multibuffer_actions: int = 3,
    max_cvpipeline_windows: int = 50,
    max_cvpipeline_actions: int = 2,
) -> dict:
    ir_path = Path(ir_path)
    selected_plan_path = Path(selected_plan_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stages = output_dir / "stages"
    stages.mkdir(exist_ok=True)

    selected_plan = _load_json(selected_plan_path)
    coverage = build_parameter_rewrite_coverage(selected_plan)
    (output_dir / "parameter_rewrite_coverage_initial.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")

    # 1. Tiling operation/type-shape candidate rewrite.
    tiling_dir = stages / "01_tiling_operation_rewrite"
    tiling = write_tiling_operation_true_rewrite_outputs(ir_path, selected_plan_path, tiling_dir)
    tiling_ir = Path(tiling["paths"]["optimized_ir"])

    # 2. MultiBuffer restricted true rewrite.
    mb_dir = stages / "02_multibuffer_true_rewrite"
    mb = write_multibuffer_true_rewrite_outputs(tiling_ir, selected_plan_path, mb_dir, max_candidates=max_multibuffer_candidates, max_actions=max_multibuffer_actions)
    mb_ir = Path(mb["optimized_ir_path"])

    # 3. CVPipeline restricted true rewrite.
    cv_dir = stages / "03_cvpipeline_true_rewrite"
    cv = write_cvpipeline_true_rewrite_outputs(mb_ir, selected_plan_path, cv_dir, max_windows=max_cvpipeline_windows, max_actions=max_cvpipeline_actions)
    cv_ir = Path(cv["optimized_ir_path"])

    # 4. SyncPlan visible operation normalization rewrite.
    sync_dir = stages / "04_sync_event_true_rewrite"
    sync = write_sync_event_true_rewrite_outputs(cv_ir, selected_plan_path, sync_dir)
    sync_ir = Path(sync["paths"]["optimized_ir"])

    # 5. Embed full parameter coverage metadata on the final output.
    final_ir = output_dir / "optimized.four_plan_production_candidate.hivm.mlir"
    coverage_out = write_parameter_coverage_outputs(selected_plan_path, sync_ir, final_ir, output_dir)

    stage_summaries = {
        "tiling": tiling.get("summary", {}),
        "multibuffer": mb.get("summary", {}),
        "cvpipeline": cv.get("summary", {}),
        "sync": sync.get("summary", {}),
        "parameter_coverage": coverage_out.get("summary", {}),
    }
    stage_mutation = {k: bool(v.get("semantic_mutation_performed")) for k, v in stage_summaries.items() if k in {"tiling", "multibuffer", "cvpipeline", "sync"}}
    stage_validation = {k: bool(v.get("passed_portable_validation")) for k, v in stage_summaries.items() if k in {"tiling", "multibuffer", "cvpipeline", "sync"}}
    four_plan_mutated = all(stage_mutation.values())
    portable_validated = all(stage_validation.values()) and bool(stage_summaries["parameter_coverage"].get("all_controllable_parameters_rewritten_back_to_ir"))
    summary = {
        "schema_version": "hivm_v55_four_plan_production_candidate_summary_v1",
        "version": VERSION,
        "input_ir": str(ir_path),
        "selected_plan": str(selected_plan_path),
        "optimized_ir": str(final_ir),
        "four_plan_rewrite_order": ["tiling_operation_shape", "multibuffer_pingpong", "cvpipeline_sync_edges", "sync_event_normalization", "parameter_metadata_coverage"],
        "stage_mutation": stage_mutation,
        "stage_validation": stage_validation,
        "stage_summaries": stage_summaries,
        "four_plan_operation_mutation_performed": four_plan_mutated,
        "all_portable_validations_passed": portable_validated,
        "all_controllable_parameters_rewritten_back_to_ir": stage_summaries["parameter_coverage"].get("all_controllable_parameters_rewritten_back_to_ir"),
        "all_controllable_parameters_semantic_operation_rewrite": False,
        "linux_msprof_ready": False,
        "production_rewrite_claim_allowed": False,
        "claim_boundary": "four-plan visible operation/text mutation candidate. It produces an optimized HIVM candidate file, but Linux MLIR/HIVM parse/verify/backend compile/result-correctness/msprof must pass before claiming real performance improvement.",
        "required_linux_validation_sequence": [
            "hivm-opt/MLIR parse optimized.four_plan_production_candidate.hivm.mlir",
            "HivmOpsEditor roundtrip + verifier",
            "backend compile to executable/kernel artifact",
            "functional correctness check against original output",
            "msprof baseline original.hivm.mlir",
            "msprof optimized optimized.four_plan_production_candidate.hivm.mlir",
            "compare median latency/cycles over repeated runs",
        ],
    }
    (output_dir / "four_plan_production_candidate_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Run V5.5 four-plan production-candidate rewrite pipeline")
    ap.add_argument("--ir", required=True)
    ap.add_argument("--selected-plan", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--max-multibuffer-candidates", type=int, default=80)
    ap.add_argument("--max-multibuffer-actions", type=int, default=3)
    ap.add_argument("--max-cvpipeline-windows", type=int, default=50)
    ap.add_argument("--max-cvpipeline-actions", type=int, default=2)
    args = ap.parse_args()
    summary = run_four_plan_production_candidate_rewrite(args.ir, args.selected_plan, args.output_dir, args.max_multibuffer_candidates, args.max_multibuffer_actions, args.max_cvpipeline_windows, args.max_cvpipeline_actions)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("four_plan_operation_mutation_performed") and summary.get("all_portable_validations_passed") else 1

if __name__ == "__main__":
    raise SystemExit(main())
