# -*- coding: utf-8 -*-
from pathlib import Path

from strategy_search.phase3_analysis import (
    build_phase3a_analysis,
    build_phase3b_analysis,
    build_phase3d_analysis,
    emit_phase3d_analysis_outputs,
)


def _ir_q_load_inside_loop() -> str:
    return r'''
func.func @kernel(%Q_gm: memref<64x128xf16, #hivm.address_space<gm>>, %K_gm: memref<64x128xf16, #hivm.address_space<gm>>) {
  %q_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
  %q_l1 = memref.alloc() : memref<64x128xf16, #hivm.address_space<cbuf>>
  %k_ub = memref.alloc() : memref<32x128xf16, #hivm.address_space<ub>>
  scf.for %j = %c0 to %c1024 step %c32 {
    hivm.hir.load ins(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>)
    hivm.hir.nd2nz ins(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%q_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>)
    hivm.hir.load ins(%K_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%k_ub : memref<32x128xf16, #hivm.address_space<ub>>)
  }
}
'''


def test_phase3d_finds_q_load_hoist_candidate():
    ir = _ir_q_load_inside_loop()
    p3a = build_phase3a_analysis(ir)
    p3b = build_phase3b_analysis(ir, p3a)
    p3d = build_phase3d_analysis(ir, p3a, p3b)
    report = p3d["loop_invariant_load_hoist"]
    decision = p3d["q_load_hoist_decision"]
    assert report["candidate_count"] >= 1
    assert decision["candidate_count"] >= 1
    assert decision["local_proof_passed_count"] >= 1
    # Production mutation is still locked until a target parser confirms region motion.
    assert decision["hoist_allowed_count"] == 0
    assert decision["hoist_unlocked"] is False


def test_phase3d_emit_outputs(tmp_path: Path):
    summary = emit_phase3d_analysis_outputs(tmp_path, _ir_q_load_inside_loop())
    assert summary["phase"] == "Phase-3D"
    assert (tmp_path / "loop_invariant_load_hoist_report.json").exists()
    assert (tmp_path / "q_load_hoist_decision.json").exists()
    assert (tmp_path / "phase3d_analysis_summary.json").exists()
