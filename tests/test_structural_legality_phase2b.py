from strategy_search.structural_legality import (
    analyze_hivm_ir_for_structural_rewrite,
    build_structural_legality_report,
)
from strategy_search.structural_rewrite import build_structural_edit_script


def _strategy():
    return {
        "strategy_id": "phase2b_test",
        "sync_policy": "graph_sync_solver",
        "cv_pipeline_stage": 2,
        "double_buffer": True,
    }


def _ir():
    return """
module {
  func.func @k() {
    scf.for %j = %c0 to %c1024 step %c32 {
      hivm.hir.load ins(%Q_gm) outs(%q_ub)
      hivm.hir.nd2nz ins(%q_ub) outs(%q_l1)
      hivm.hir.barrier {mode = "ALL"}
      hivm.hir.mmad ins(%q_l1, %k_l1) outs(%acc)
      hivm.hir.fixpipe ins(%acc) outs(%tmp)
      hivm.hir.vexp ins(%tmp) outs(%tmp)
    }
    return
  }
}
""".lstrip()


def test_anchor_analysis_finds_phase2b_candidates():
    analysis = analyze_hivm_ir_for_structural_rewrite(_ir())
    assert analysis["op_counts"]["barrier_all"] == 1
    assert analysis["op_counts"]["vector"] == 1
    assert analysis["anchors"]["cv_boundary_candidates"]
    assert analysis["anchors"]["q_hoist_candidates"]


def test_structural_legality_report_links_edit_script_to_anchors():
    script = build_structural_edit_script(_strategy(), "balanced")
    report = build_structural_legality_report(_ir(), script, "balanced")
    assert report["summary"]["total_edits"] >= 3
    assert report["summary"]["local_precheck_passed"] >= 3
    assert report["summary"]["production_backend_required"] is True
    types = {e["type"] for e in report["edit_prechecks"]}
    assert "replace_barrier_all_with_directional_sync" in types
    assert "insert_sync_before_first_vector_op" in types
