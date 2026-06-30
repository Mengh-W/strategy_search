from pathlib import Path

from strategy_search.structural_rewrite import (
    apply_structural_rewrite,
    build_backend_execution_plan,
    validate_python_structural_result,
)


def _strategy():
    return {
        "strategy_id": "phase2a_test",
        "sync_policy": "graph_sync_solver",
        "cv_pipeline_stage": 2,
        "double_buffer": True,
    }


def test_backend_execution_plan_auto_falls_back_to_python():
    plan = build_backend_execution_plan("auto", None, None, None)
    assert plan["selected_backend"] == "python_fallback"
    assert "official_backend_target" in plan


def test_backend_execution_plan_dry_run():
    plan = build_backend_execution_plan("dry_run", None, None, None)
    assert plan["selected_backend"] == "dry_run"


def test_python_structural_validation_reports_op_delta():
    ir = """
module {
  func.func @k() {
    hivm.hir.barrier {mode = "ALL"}
    hivm.hir.mmad ins(%a) outs(%b)
    hivm.hir.fixpipe ins(%b) outs(%c)
    hivm.hir.vexp ins(%c) outs(%c)
    return
  }
}
""".lstrip()
    result = apply_structural_rewrite(ir, _strategy(), "balanced")
    report = validate_python_structural_result(ir, result.text, result)
    assert report["passed"] is True
    assert report["op_count_delta"]["barrier_all"] < 0
    assert report["op_count_delta"]["set_flag"] >= 1
    assert report["op_count_delta"]["wait_flag"] >= 1
