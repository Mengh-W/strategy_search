from pathlib import Path

from strategy_search.phase4_analysis import build_phase4c_q_load_hoist_prototype_report, emit_phase4c_outputs


def _q_decision(local=True):
    return {
        "decisions": [
            {
                "candidate_id": "q_hoist_0",
                "load_op_id": 3,
                "load_line": 12,
                "local_proof_passed": local,
                "gates": {
                    "target_parser_region_motion_proof": False,
                },
            }
        ]
    }


def test_phase4c_keeps_mutation_locked_without_region_motion_proof():
    report = build_phase4c_q_load_hoist_prototype_report(
        q_load_hoist_decision=_q_decision(True),
        loop_invariant_load_hoist_report={"candidates": [{"candidate_id": "q_hoist_0", "parent_loop": {"line": 10}}]},
        phase4a_summary={"target_parser_status": "tritonsim_des_trace_ran_both", "phase4a_blockers": []},
        phase4b_summary={"passed_external_des_trace_gate": True},
        buffer_liveness_report={"capacity_recheck": {"passed_conservative_capacity_recheck": True}},
        event_liveness_report={"passed_local_event_liveness": True},
    )
    assert report["backend_dry_run_ready_count"] == 1
    assert report["production_mutation_allowed_count"] == 0
    assert report["production_mutation_unlocked"] is False
    assert "target_region_motion_proof" in report["decisions"][0]["missing_gates"]


def test_phase4c_deferred_when_des_trace_gate_missing():
    report = build_phase4c_q_load_hoist_prototype_report(
        q_load_hoist_decision=_q_decision(True),
        phase4a_summary={"target_parser_status": "bridge_handshake_only_no_target_parser", "phase4a_blockers": ["target_parser_or_tritonsim_not_connected"]},
        phase4b_summary={"passed_external_des_trace_gate": False},
        buffer_liveness_report={"capacity_recheck": {"passed_conservative_capacity_recheck": True}},
        event_liveness_report={"passed_local_event_liveness": True},
    )
    assert report["backend_dry_run_ready_count"] == 0
    assert report["production_mutation_allowed_count"] == 0
    assert report["blockers"]


def test_emit_phase4c_outputs_writes_reports(tmp_path: Path):
    (tmp_path / "q_load_hoist_decision.json").write_text(
        '{"decisions":[{"candidate_id":"q_hoist_0","load_op_id":3,"load_line":12,"local_proof_passed":true,"gates":{"target_parser_region_motion_proof":false}}]}',
        encoding="utf-8",
    )
    (tmp_path / "loop_invariant_load_hoist_report.json").write_text('{"candidates":[{"candidate_id":"q_hoist_0"}]}', encoding="utf-8")
    (tmp_path / "buffer_liveness_report.json").write_text('{"capacity_recheck":{"passed_conservative_capacity_recheck":true}}', encoding="utf-8")
    (tmp_path / "event_liveness_report.json").write_text('{"passed_local_event_liveness":true}', encoding="utf-8")
    summary = emit_phase4c_outputs(
        out=tmp_path,
        phase4a_summary={"target_parser_status": "tritonsim_des_trace_ran_both", "phase4a_blockers": []},
        phase4b_summary={"passed_external_des_trace_gate": True},
    )
    assert summary["backend_dry_run_ready_count"] == 1
    assert (tmp_path / "phase4c_q_load_hoist_prototype_report.json").exists()
    assert (tmp_path / "phase4c_q_load_hoist_candidate_script.json").exists()
