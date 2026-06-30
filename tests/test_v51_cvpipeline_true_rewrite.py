# -*- coding: utf-8 -*-
from pathlib import Path

from strategy_search.cvpipeline_stage_planner import analyze_cvpipeline_stages, build_cvpipeline_rewrite_plan
from strategy_search.cvpipeline_true_rewrite import (
    build_cvpipeline_true_rewrite_actions,
    apply_cvpipeline_true_rewrite,
    validate_cvpipeline_true_rewrite,
    write_cvpipeline_true_rewrite_outputs,
)


def _sample_ir() -> str:
    return """
func.func @k() {
  scf.for %i = %c0 to %c8 step %c1 {
    %buf = hivm.hir.pointer_cast(%arg0) : memref<1xf32>
    %buf_mb0_ping = hivm.hir.pointer_cast(%arg0) : memref<1xf32>
    %buf_mb0_pong = hivm.hir.pointer_cast(%arg0) : memref<1xf32>
    hivm.hir.load ins(%arg1 : memref<1xf32>) outs(%buf_mb0_ping : memref<1xf32>)
    hivm.hir.pipe_barrier[<PIPE_MTE2>]
    %x = hivm.hir.vadd ins(%buf_mb0_ping, %buf_mb0_ping : memref<1xf32>, memref<1xf32>) outs(%buf_mb0_ping : memref<1xf32>)
    hivm.hir.store ins(%buf_mb0_ping : memref<1xf32>) outs(%arg2 : memref<1xf32>)
  }
}
"""


def test_cvpipeline_true_rewrite_inserts_sync_edges():
    ir = _sample_ir()
    stage_report = analyze_cvpipeline_stages(ir, selected_plan={}, max_windows=5)
    stage_plan = build_cvpipeline_rewrite_plan(stage_report)
    actions = build_cvpipeline_true_rewrite_actions(stage_plan, ir, max_actions=1)
    assert actions
    rewritten, report = apply_cvpipeline_true_rewrite(ir, actions)
    assert report["mutation_performed"] is True
    assert "CVPipelinePlan group begin" in rewritten
    assert "hivm.hir.set_flag" in rewritten
    assert "hivm.hir.wait_flag" in rewritten
    validation = validate_cvpipeline_true_rewrite(ir, rewritten, report)
    assert validation["passed"] is True


def test_cvpipeline_true_rewrite_write_outputs(tmp_path: Path):
    ir_path = tmp_path / "x.mlir"
    plan_path = tmp_path / "selected_plan.json"
    ir_path.write_text(_sample_ir(), encoding="utf-8")
    plan_path.write_text("{}", encoding="utf-8")
    out = write_cvpipeline_true_rewrite_outputs(ir_path, plan_path, tmp_path / "out", max_windows=5, max_actions=1)
    assert Path(out["optimized_ir_path"]).exists()
    assert Path(out["rewrite_report_path"]).exists()
    assert out["summary"]["mutation_performed"] is True
    assert out["summary"]["passed_portable_validation"] is True
