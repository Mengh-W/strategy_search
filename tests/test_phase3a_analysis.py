from pathlib import Path

from strategy_search.phase3_analysis import (
    build_hivm_op_inventory,
    build_dependency_graph,
    build_event_liveness_report,
    emit_phase3a_analysis_outputs,
)


def _ir():
    return """
func.func @kernel() {
  %q = hivm.hir.load ins(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>)
  %k = hivm.hir.nd2nz ins(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%q_l1 : memref<64x128xf16, #hivm.address_space<l1>>)
  hivm.hir.mmadL1 ins(%q_l1 : memref<64x128xf16, #hivm.address_space<l1>>) outs(%acc : memref<64x64xf32, #hivm.address_space<l0c>>)
  hivm.hir.fixpipe ins(%acc : memref<64x64xf32, #hivm.address_space<l0c>>) outs(%o_ub : memref<64x64xf16, #hivm.address_space<ub>>)
  hivm.hir.set_flag[<PIPE_FIX>, <PIPE_V>, <EVENT_ID1>]
  hivm.hir.wait_flag[<PIPE_FIX>, <PIPE_V>, <EVENT_ID1>]
  hivm.hir.vadd ins(%o_ub : memref<64x64xf16, #hivm.address_space<ub>>) outs(%o_ub : memref<64x64xf16, #hivm.address_space<ub>>)
  hivm.hir.store ins(%o_ub : memref<64x64xf16, #hivm.address_space<ub>>) outs(%O_gm : memref<64x64xf16, #hivm.address_space<gm>>)
}
"""


def test_phase3a_inventory_classifies_core_ops():
    inv = build_hivm_op_inventory(_ir())
    assert inv["op_count"] >= 8
    assert inv["role_counts"]["load"] == 1
    assert inv["role_counts"]["cube"] == 1
    assert inv["role_counts"]["vector"] == 1
    assert inv["unknown_op_count"] == 0


def test_phase3a_dependency_graph_has_memory_and_event_edges():
    inv = build_hivm_op_inventory(_ir())
    dep = build_dependency_graph(inv)
    assert dep["edge_counts"].get("memory_raw", 0) >= 3
    assert dep["edge_counts"].get("event_set_wait", 0) == 1


def test_phase3a_event_liveness_pairs_set_wait():
    inv = build_hivm_op_inventory(_ir())
    ev = build_event_liveness_report(inv)
    assert ev["event_count"] == 1
    assert ev["safe_pair_count"] == 1
    assert ev["passed_local_event_liveness"] is True


def test_emit_phase3a_outputs(tmp_path: Path):
    summary = emit_phase3a_analysis_outputs(tmp_path, _ir())
    assert (tmp_path / "hivm_ir_inventory.json").exists()
    assert (tmp_path / "dependency_graph_report.json").exists()
    assert (tmp_path / "event_liveness_report.json").exists()
    assert (tmp_path / "phase3a_analysis_summary.json").exists()
    assert summary["phase"] == "Phase-3A"
