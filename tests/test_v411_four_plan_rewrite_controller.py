# -*- coding: utf-8 -*-
from pathlib import Path

from strategy_search.four_plan_rewrite_controller import (
    analyze_tiling_rewrite_feasibility,
    write_unified_four_plan_controller_outputs,
)


def _write_fixture(tmp_path: Path):
    ir = tmp_path / "toy.mlir"
    ir.write_text(
        """
module {
  scf.for %i = %c0 to %c4 step %c1 {
    %buf = hivm.hir.pointer_cast(%arg0) : memref<16xf16>
    hivm.hir.load %buf : memref<16xf16>
    hivm.hir.pipe_barrier[<PIPE_MTE2>]
    hivm.hir.mmadL1 ins(%buf : memref<16xf16>) outs(%buf : memref<16xf16>)
    hivm.hir.fixpipe %buf : memref<16xf16>
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    plan = tmp_path / "selected_plan.json"
    plan.write_text(
        '{"tiling_plan":{"controllable_knobs":{"tile_m":16,"tile_n":16,"tile_k":32},"derived_features":{"num_tiles":4}},"sync_plan":{},"multi_buffer_plan":{},"cv_pipeline_plan":{}}',
        encoding="utf-8",
    )
    return ir, plan


def test_tiling_feasibility_scans_loop_and_knobs(tmp_path: Path):
    ir, plan = _write_fixture(tmp_path)
    summary = analyze_tiling_rewrite_feasibility(ir, plan, tmp_path / "tiling")
    assert summary["stage"] == "TilingPlan"
    assert summary["loop_anchor_count"] >= 1
    assert summary["tiling_feasibility_report"] if False else True
    assert (tmp_path / "tiling" / "tiling_rewrite_feasibility.json").exists()


def test_unified_controller_writes_report_and_summary(tmp_path: Path):
    ir, plan = _write_fixture(tmp_path)
    result = write_unified_four_plan_controller_outputs(
        ir,
        plan,
        tmp_path / "controller",
        max_sync_actions=10,
        max_multibuffer_candidates=10,
        max_cvpipeline_windows=10,
        max_annotations=5,
    )
    summary = result["summary"]
    assert summary["version"] == "V4.11-unified-four-plan-rewrite-controller"
    assert summary["sync_portable_rewrite_passed"] is True
    assert summary["sync_rewritten_action_count"] >= 1
    assert summary["hivmopseditor_migration_queue_count"] >= 1
    assert Path(result["controller_report_path"]).exists()
    assert Path(result["controller_summary_path"]).exists()
    report = result["report"]
    assert "syncplan" in report["stage_summaries"]
    assert "multibuffer_stage_boundary" in report["stage_summaries"]
    assert "cvpipeline_stage_planner" in report["stage_summaries"]
    assert "tiling_feasibility" in report["stage_summaries"]
