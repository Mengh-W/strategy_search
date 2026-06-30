from pathlib import Path

from strategy_search.phase3_analysis import (
    build_hivm_op_inventory,
    build_buffer_liveness_report,
    build_gm_alias_report,
    emit_phase3b_analysis_outputs,
)


def _ir() -> str:
    return r'''
module {
  func.func @k(%A_gm : memref<64x128xf16, #hivm.address_space<gm>>, %O_gm : memref<64x128xf16, #hivm.address_space<gm>>) {
    %q_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    %q_l1 = memref.alloc() : memref<64x128xf16, #hivm.address_space<cbuf>>
    %acc_ub = memref.alloc() : memref<64x128xf32, #hivm.address_space<ub>>
    scf.for %j = %c0 to %c1024 step %c32 {
      hivm.hir.load ins(%A_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>)
      hivm.hir.nd2nz ins(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%q_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>)
    }
    hivm.hir.store ins(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%O_gm : memref<64x128xf16, #hivm.address_space<gm>>)
    return
  }
}
'''


def test_buffer_liveness_capacity_and_roles():
    inv = build_hivm_op_inventory(_ir())
    rep = build_buffer_liveness_report(_ir(), inv)
    assert rep["schema_version"] == "hivm_buffer_liveness_report_v1"
    buffers = {b["var"]: b for b in rep["buffers"]}
    assert buffers["%q_ub"]["space"] == "ub"
    assert buffers["%q_l1"]["space"] == "l1"
    assert buffers["%acc_ub"]["buffer_role"] == "accumulator"
    assert rep["capacity_recheck"]["peak_by_space"]["ub"]["conservative_peak_bytes"] >= 64 * 128 * 2
    assert "rewrite_implications" in rep


def test_gm_alias_report_is_precheck_only():
    inv = build_hivm_op_inventory(_ir())
    rep = build_gm_alias_report(_ir(), inv)
    assert rep["schema_version"] == "hivm_gm_alias_report_v1"
    assert rep["gm_access_count"] >= 2
    assert rep["deletion_unlocked"] is False
    assert "required_next_gates" in rep


def test_emit_phase3b_outputs(tmp_path: Path):
    summary = emit_phase3b_analysis_outputs(tmp_path, _ir())
    assert (tmp_path / "buffer_liveness_report.json").exists()
    assert (tmp_path / "capacity_recheck_report.json").exists()
    assert (tmp_path / "gm_alias_report.json").exists()
    assert (tmp_path / "phase3b_analysis_summary.json").exists()
    assert summary["schema_version"] == "hivm_phase3b_analysis_summary_v1"
    assert summary["rewrite_gates_unlocked"]["gm_roundtrip_deletion"] is False
