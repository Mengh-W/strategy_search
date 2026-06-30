# -*- coding: utf-8 -*-
from pathlib import Path
from strategy_search.operation_rewrite.four_plan_operation_rewriter import run_four_plan_operation_rewrite


def test_v56_four_plan_operation_rewrite_sample(tmp_path: Path):
    summary = run_four_plan_operation_rewrite(
        "sample_input/fa_best.hivm.mlir",
        "artifacts/latest_smoke_run/selected_plan.json",
        tmp_path,
        max_multibuffer_actions=4,
        max_cvpipeline_actions=2,
    )
    assert summary["four_plan_operation_rewrite_performed"] is True
    assert summary["portable_validation_passed"] is True
    assert summary["stage_mutation"] == {"tiling": True, "multibuffer": True, "cvpipeline": True, "sync": True}
    assert summary["linux_compile_ready_claim"] is False
    text = Path(summary["optimized_ir"]).read_text(encoding="utf-8")
    assert "HIVM V5.6 TilingPlan semantic operation rewrite begin" in text
    assert "scf.for %m_outer" in text and "scf.for %n_outer" in text and "scf.for %k_outer" in text
    assert "MultiBufferPlan true rewrite" in text
    assert "CVPipelinePlan sync edge" in text
    assert "SyncPlan operation rewrite" in text
    cov = Path(tmp_path / "operation_parameter_coverage.json").read_text(encoding="utf-8")
    assert "insert_M_outer_tile_loop" in cov
    assert "ping_pong_alloc_clone" in cov


def test_v56_tiling_reports_all_core_parameters(tmp_path: Path):
    summary = run_four_plan_operation_rewrite(
        "sample_input/fa_best.hivm.mlir",
        "artifacts/latest_smoke_run/selected_plan.json",
        tmp_path,
        max_multibuffer_actions=1,
        max_cvpipeline_actions=1,
    )
    report = Path(tmp_path / "stages/01_tiling_semantic_operation_rewrite/tiling_loop_semantic_rewrite_report.json").read_text(encoding="utf-8")
    for p in ["tile_m", "tile_n", "tile_k", "loop_order", "tail_strategy", "reduce_tile_policy", "layout_aware_tile"]:
        assert p in report
    assert summary["all_controllable_parameters_have_operation_action_mvp"] is True
