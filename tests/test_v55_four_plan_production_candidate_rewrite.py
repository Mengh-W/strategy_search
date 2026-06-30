from pathlib import Path
import json

from tools.run_four_plan_production_candidate_rewrite import run_four_plan_production_candidate_rewrite


def test_v55_four_plan_production_candidate_rewrite(tmp_path):
    root = Path(__file__).resolve().parents[1]
    out = tmp_path / "v55_four_plan"
    summary = run_four_plan_production_candidate_rewrite(
        root / "sample_input" / "fa_best.hivm.mlir",
        root / "artifacts" / "latest_smoke_run" / "selected_plan.json",
        out,
        max_multibuffer_actions=2,
        max_cvpipeline_actions=1,
    )
    assert summary["four_plan_operation_mutation_performed"] is True
    assert summary["all_portable_validations_passed"] is True
    assert summary["stage_mutation"] == {"tiling": True, "multibuffer": True, "cvpipeline": True, "sync": True}
    optimized = Path(summary["optimized_ir"])
    assert optimized.exists()
    text = optimized.read_text(encoding="utf-8")
    assert "TilingPlan operation rewrite candidate" in text
    assert "MultiBufferPlan" in text
    assert "CVPipelinePlan" in text
    assert "SyncPlan operation rewrite" in text
