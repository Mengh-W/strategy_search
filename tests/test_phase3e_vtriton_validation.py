# -*- coding: utf-8 -*-
import json
from pathlib import Path

from strategy_search.phase3_analysis import (
    build_phase3e_validation_report,
    emit_phase3e_validation_outputs,
)


def _original_ir() -> str:
    return r'''
module {
  func.func @k(%A_gm : memref<64x128xf16, #hivm.address_space<gm>>) {
    %q_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    hivm.hir.load ins(%A_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>)
    hivm.hir.barrier {mode = "ALL"}
    return
  }
}
'''


def _optimized_ir() -> str:
    return r'''
module {
  func.func @k(%A_gm : memref<64x128xf16, #hivm.address_space<gm>>) {
    %q_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    hivm.hir.load ins(%A_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>)
    hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_M>, <EVENT_ID0>]
    hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_M>, <EVENT_ID0>]
    return
  }
}
'''


def test_phase3e_pending_without_tritonsim():
    report = build_phase3e_validation_report(
        _original_ir(),
        _optimized_ir(),
        tritonsim_validation_report=None,
        structural_validation_summary={"passed_local_validation": True},
    )
    assert report["schema_version"] == "hivm_phase3e_des_trace_validation_report_v1"
    assert report["validation_status"] == "pending_or_failed_external_des_trace_validation"
    assert report["external_tritonsim"]["ran_both"] is False
    assert report["local_inventory_comparison"]["delta"]["op_count_delta"] >= 0


def test_phase3e_emit_outputs(tmp_path: Path):
    summary = emit_phase3e_validation_outputs(tmp_path, _original_ir(), _optimized_ir())
    assert summary["phase"] == "Phase-3E"
    assert (tmp_path / "vtriton_des_trace_validation_report.json").exists()
    assert (tmp_path / "phase3e_analysis_summary.json").exists()
    assert (tmp_path / "trace_comparison_report.html").exists()
    payload = json.loads((tmp_path / "vtriton_des_trace_validation_report.json").read_text())
    assert payload["validation_status"] == "pending_or_failed_external_des_trace_validation"
