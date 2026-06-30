# -*- coding: utf-8 -*-
from pathlib import Path

from strategy_search.cvpipeline_stage_planner import (
    analyze_cvpipeline_stages,
    build_cvpipeline_rewrite_plan,
    write_cvpipeline_stage_outputs,
)


def test_cvpipeline_stage_planner_detects_window():
    ir = """
func.func @k() {
  scf.for %i = %c0 to %c8 step %c1 {
    %buf = hivm.hir.pointer_cast(%arg0) : memref<1xf32>
    hivm.hir.load ins(%arg1 : memref<1xf32>) outs(%buf : memref<1xf32>)
    hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_V>, %e0]
    hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_V>, %e0]
    %x = hivm.hir.vadd ins(%buf, %buf : memref<1xf32>, memref<1xf32>) outs(%buf : memref<1xf32>)
    hivm.hir.store ins(%buf : memref<1xf32>) outs(%arg2 : memref<1xf32>)
  }
}
"""
    report = analyze_cvpipeline_stages(ir, selected_plan={})
    assert report["pipeline_window_count"] >= 1
    assert report["stage_counts"].get("load", 0) >= 1
    assert report["stage_counts"].get("compute", 0) >= 1
    assert report["stage_counts"].get("store", 0) >= 1
    plan = build_cvpipeline_rewrite_plan(report)
    assert plan["action_count"] >= 1
    assert plan["semantic_mutation_performed"] is False


def test_cvpipeline_write_outputs(tmp_path: Path):
    ir_path = tmp_path / "x.mlir"
    plan_path = tmp_path / "selected_plan.json"
    ir_path.write_text(
        """
func.func @k() {
  scf.for %i = %c0 to %c8 step %c1 {
    %buf = hivm.hir.pointer_cast(%arg0) : memref<1xf32>
    hivm.hir.load ins(%arg1 : memref<1xf32>) outs(%buf : memref<1xf32>)
    hivm.hir.pipe_barrier[<PIPE_MTE2>]
    hivm.hir.vadd ins(%buf, %buf : memref<1xf32>, memref<1xf32>) outs(%buf : memref<1xf32>)
    hivm.hir.store ins(%buf : memref<1xf32>) outs(%arg2 : memref<1xf32>)
  }
}
""",
        encoding="utf-8",
    )
    plan_path.write_text("{}", encoding="utf-8")
    out = write_cvpipeline_stage_outputs(ir_path, plan_path, tmp_path / "out", max_windows=5)
    assert Path(out["stage_report_path"]).exists()
    assert Path(out["rewrite_plan_path"]).exists()
    assert Path(out["annotated_ir_path"]).exists()
    assert out["summary"]["production_rewrite_claim_allowed"] is False
