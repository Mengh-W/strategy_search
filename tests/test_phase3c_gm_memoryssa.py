from pathlib import Path

from strategy_search.phase3_analysis import (
    build_hivm_op_inventory,
    build_gm_alias_report,
    build_gm_memory_ssa_report,
    build_gm_roundtrip_deletion_decision_report,
    build_rewrite_legality_gate_report,
    build_phase3a_analysis,
    build_phase3b_analysis,
    emit_phase3c_analysis_outputs,
)


def _ir_roundtrip() -> str:
    return r'''
module {
  func.func @k(%A_gm : memref<64xf16, #hivm.address_space<gm>>) {
    %tmp_ub = memref.alloc() : memref<64xf16, #hivm.address_space<ub>>
    hivm.hir.store ins(%tmp_ub : memref<64xf16, #hivm.address_space<ub>>) outs(%A_gm : memref<64xf16, #hivm.address_space<gm>>)
    hivm.hir.load ins(%A_gm : memref<64xf16, #hivm.address_space<gm>>) outs(%tmp_ub : memref<64xf16, #hivm.address_space<ub>>)
    return
  }
}
'''


def test_gm_memoryssa_detects_reaching_def_but_deletion_deferred():
    inv = build_hivm_op_inventory(_ir_roundtrip())
    alias = build_gm_alias_report(_ir_roundtrip(), inv)
    ssa = build_gm_memory_ssa_report(_ir_roundtrip(), inv, alias)
    decision = build_gm_roundtrip_deletion_decision_report(_ir_roundtrip(), inv, alias, ssa)
    assert ssa["schema_version"] == "hivm_gm_memory_ssa_report_v1"
    assert alias["gm_roundtrip_candidate_count"] == 1
    assert ssa["unique_reaching_use_count"] >= 1
    assert decision["schema_version"] == "hivm_gm_roundtrip_deletion_decision_v1"
    assert decision["candidate_count"] == 1
    # Same textual GM var is not enough; boundary/offset proof is still missing.
    assert decision["deletion_unlocked"] is False
    assert decision["decisions"][0]["delete_permission"] is False


def test_rewrite_legality_gate_keeps_dangerous_rewrites_locked():
    phase3a = build_phase3a_analysis(_ir_roundtrip())
    phase3b = build_phase3b_analysis(_ir_roundtrip(), phase3a)
    ssa = build_gm_memory_ssa_report(_ir_roundtrip(), phase3a["inventory"], phase3b["gm_alias"])
    dec = build_gm_roundtrip_deletion_decision_report(_ir_roundtrip(), phase3a["inventory"], phase3b["gm_alias"], ssa)
    gate = build_rewrite_legality_gate_report(phase3a["inventory"], phase3a["dependency_graph"], phase3a["event_liveness"], phase3b["buffer_liveness"], phase3b["gm_alias"], ssa, dec)
    assert gate["schema_version"] == "hivm_rewrite_legality_gate_report_v1"
    assert gate["rewrite_gate_status"]["gm_roundtrip_deletion"] is False
    assert gate["rewrite_gate_status"]["real_double_buffer"] is False


def test_emit_phase3c_outputs(tmp_path: Path):
    summary = emit_phase3c_analysis_outputs(tmp_path, _ir_roundtrip())
    assert (tmp_path / "gm_memory_ssa_report.json").exists()
    assert (tmp_path / "gm_roundtrip_deletion_decision.json").exists()
    assert (tmp_path / "rewrite_legality_gate_report.json").exists()
    assert (tmp_path / "phase3c_analysis_summary.json").exists()
    assert summary["schema_version"] == "hivm_phase3c_analysis_summary_v1"
    assert summary["rewrite_gates_unlocked"]["gm_roundtrip_deletion"] is False
