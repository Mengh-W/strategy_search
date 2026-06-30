from pathlib import Path
import json

from strategy_search.phase4_analysis import build_phase4e_closure_report, emit_phase4e_outputs


def test_phase4e_closure_keeps_risky_mutations_locked():
    report = build_phase4e_closure_report(
        phase4a_summary={"phase4a_blockers": []},
        phase4b_summary={"passed_external_des_trace_gate": True},
        phase4c_summary={"backend_dry_run_ready_count": 1},
        phase4d_summary={"dry_run_action_count": 1},
    )
    assert report["production_mutations_unlocked"]["q_load_hoist"] is False
    assert report["production_mutations_unlocked"]["gm_roundtrip_deletion"] is False
    assert "real_hivmopseditor_or_mlir_operation_backend_not_connected" in report["remaining_blockers"]
    assert report["capability_matrix"]["guarded_q_load_hoist"]["phase4_status"] == "dry_run_contract_ready"


def test_emit_phase4e_outputs_writes_closure_files(tmp_path: Path):
    summary = emit_phase4e_outputs(
        out=tmp_path,
        phase4a_summary={"phase4a_blockers": []},
        phase4b_summary={"passed_external_des_trace_gate": True},
        phase4c_summary={"backend_dry_run_ready_count": 1},
        phase4d_summary={"dry_run_action_count": 1},
    )
    assert summary["phase"] == "Phase-4E"
    assert (tmp_path / "phase4_closure_report.json").exists()
    assert (tmp_path / "phase4e_analysis_summary.json").exists()
    data = json.loads((tmp_path / "phase4_closure_report.json").read_text())
    assert data["phase4_status"] == "closed_bridge_validation_and_dry_run_contract"
