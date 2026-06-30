from pathlib import Path

from strategy_search.phase4_analysis import build_phase4a_target_parser_validation_report, emit_phase4a_outputs


def _ir():
    return """
module {
  func.func @main() {
    hivm.hir.set_flag[<PIPE_FIX>, <PIPE_V>, <EVENT_ID0>]
    hivm.hir.wait_flag[<PIPE_FIX>, <PIPE_V>, <EVENT_ID0>]
    hivm.hir.vadd
    return
  }
}
"""


def test_phase4a_report_keeps_production_mutations_locked_without_target_parser(tmp_path):
    report = build_phase4a_target_parser_validation_report(
        original_ir_text=_ir(),
        optimized_ir_text=_ir(),
        edit_script={"edits": [{"type": "insert_sync_before_first_vector_op", "enabled": True}]},
        bridge_manifest={"coverage_by_edit_type": {"insert_sync_before_first_vector_op": {"covered": True}}},
        backend_plan={"selected_backend": "python"},
        strategy_rewriter_binary=None,
        hivm_crud_binary=None,
        tritonsim_hivm=None,
        tritonsim_validation_report=None,
    )
    assert report["phase"] == "Phase-4A"
    assert report["target_parser_status"] in {"not_connected", "bridge_handshake_only_no_target_parser"}
    assert report["readiness"]["can_start_guarded_gm_deletion_prototype"] is False
    assert "target_parser_or_tritonsim_not_connected" in report["phase4a_blockers"]


def test_emit_phase4a_outputs_writes_report_and_summary(tmp_path):
    summary = emit_phase4a_outputs(
        out=tmp_path,
        original_ir_text=_ir(),
        optimized_ir_text=_ir(),
        edit_script={"edits": []},
        bridge_manifest={},
        backend_plan={},
    )
    assert (tmp_path / "target_parser_validation_report.json").exists()
    assert (tmp_path / "phase4a_analysis_summary.json").exists()
    assert summary["phase"] == "Phase-4A"
