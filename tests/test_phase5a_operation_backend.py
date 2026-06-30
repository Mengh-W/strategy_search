from pathlib import Path
import json

from strategy_search.phase5_analysis import (
    build_phase5a_operation_backend_readiness_report,
    emit_phase5a_outputs,
)


IR = '''module {
  func.func @main() {
    %q = hivm.hir.load %gm_q : memref<128xf16, 1> -> memref<128xf16, 3>
    hivm.hir.barrier {mode = "ALL"}
    return
  }
}
'''


def test_phase5a_without_real_backend_keeps_mutation_locked():
    report = build_phase5a_operation_backend_readiness_report(
        original_ir_text=IR,
        optimized_ir_text=IR,
        phase4d_dry_run_plan={"actions": [{"candidate_id": "q_hoist_0"}]},
        operation_backend_binary=None,
    )
    assert report["phase"] == "Phase-5A"
    assert report["readiness"]["production_mutation_allowed"] is False
    assert "real_operation_backend_binary_not_configured_or_not_found" in report["phase5a_blockers"]
    assert report["local_inventory_baseline"]["original"]["source"] == "local_conservative_scanner"


def test_emit_phase5a_outputs_writes_expected_reports(tmp_path: Path):
    (tmp_path / "phase4d_hivmopseditor_dry_run_plan.json").write_text(
        json.dumps({"actions": [{"candidate_id": "q_hoist_0"}]}), encoding="utf-8"
    )
    (tmp_path / "phase4_closure_report.json").write_text(
        json.dumps({"phase4_status": "closed_bridge_validation_and_dry_run_contract"}), encoding="utf-8"
    )
    summary = emit_phase5a_outputs(
        out=tmp_path,
        original_ir_text=IR,
        optimized_ir_text=IR,
    )
    assert summary["phase"] == "Phase-5A"
    assert summary["production_mutation_allowed"] is False
    assert (tmp_path / "phase5a_operation_backend_readiness_report.json").exists()
    assert (tmp_path / "phase5a_inventory_alignment_report.json").exists()
    assert (tmp_path / "phase5a_analysis_summary.json").exists()
