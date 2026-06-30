from pathlib import Path

from strategy_search.phase4_analysis import (
    build_phase4d_operation_rewrite_dry_run_report,
    emit_phase4d_outputs,
)


def _candidate_script():
    return {
        "edits": [
            {
                "type": "hoist_loop_invariant_q_load",
                "candidate_id": "q_hoist_0",
                "load_op_id": 3,
                "load_line": 12,
            }
        ]
    }


def test_phase4d_never_unlocks_production_mutation():
    report = build_phase4d_operation_rewrite_dry_run_report(
        phase4c_candidate_script=_candidate_script(),
        phase4a_summary={"target_parser_status": "tritonsim_des_trace_ran_both", "phase4a_blockers": []},
        phase4b_summary={"passed_external_des_trace_gate": True},
        phase4c_summary={"backend_dry_run_ready_count": 1},
    )
    assert report["dry_run_action_count"] == 1
    assert report["production_mutation_unlocked"] is False
    assert report["actions"][0]["allowed_to_mutate_now"] is False
    assert "operation_level_dominance_and_region_motion_backend_not_connected" in report["blockers"]


def test_emit_phase4d_outputs_writes_official_contract(tmp_path: Path):
    (tmp_path / "phase4c_q_load_hoist_candidate_script.json").write_text(
        '{"edits":[{"type":"hoist_loop_invariant_q_load","candidate_id":"q_hoist_0","load_op_id":3,"load_line":12}]}',
        encoding="utf-8",
    )
    summary = emit_phase4d_outputs(
        out=tmp_path,
        phase4a_summary={"target_parser_status": "tritonsim_des_trace_ran_both", "phase4a_blockers": []},
        phase4b_summary={"passed_external_des_trace_gate": True},
        phase4c_summary={"backend_dry_run_ready_count": 1},
    )
    assert summary["dry_run_action_count"] == 1
    assert (tmp_path / "phase4d_operation_rewrite_dry_run_report.json").exists()
    assert (tmp_path / "phase4d_hivmopseditor_dry_run_plan.json").exists()
    assert (tmp_path / "phase4d_official_mlir_compliance_report.json").exists()
