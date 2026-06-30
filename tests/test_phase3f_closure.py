from strategy_search.phase3_analysis import build_phase3f_closure_report, emit_phase3f_closure_outputs


def _summaries():
    p3a = {
        "inventory": {"op_count": 10, "unknown_op_count": 0},
        "dependency_graph": {"edge_count": 8, "edge_counts": {"memory_raw": 5}},
        "event_liveness": {"passed_local_event_liveness": True, "event_count": 2},
    }
    p3b = {
        "buffer_liveness": {
            "buffer_count": 4,
            "capacity_recheck": {"passed_conservative_capacity_recheck": True},
        },
        "gm_alias": {"gm_access_count": 2, "gm_roundtrip_candidate_count": 0},
    }
    p3c = {
        "gm_memory_ssa": {"gm_access_count": 2, "memory_event_count": 2, "candidate_count": 0},
        "gm_roundtrip_deletion_decision": {"candidate_count": 0, "delete_allowed_count": 0},
        "rewrite_gates_unlocked": {"barrier_or_sync_local_rewrite_audit": True, "gm_roundtrip_deletion": False},
    }
    p3d = {
        "hoist_candidates": {"candidate_count": 1, "local_proof_passed_count": 1, "hoist_allowed_count": 0}
    }
    p3e = {"validation_status": "pending_or_failed_external_des_trace_validation", "external_tritonsim_ran_both": False, "des_trace_artifacts_available": False}
    return p3a, p3b, p3c, p3d, p3e


def test_phase3f_closure_report_keeps_dangerous_rewrites_locked():
    report = build_phase3f_closure_report(*_summaries())
    assert report["phase3_status"] == "closed_analysis_foundation"
    assert report["rewrite_gate_status"]["safe_local_sync_audit"] is True
    assert report["rewrite_gate_status"]["gm_roundtrip_deletion"] is False
    assert report["phase4_candidates"]["q_load_hoist"]["phase4_status"] == "eligible_for_guarded_prototype"
    assert any("external tritonsim" in x for x in report["remaining_blockers"])


def test_emit_phase3f_closure_outputs(tmp_path):
    summary = emit_phase3f_closure_outputs(tmp_path, *_summaries())
    assert (tmp_path / "phase3_closure_report.json").exists()
    assert (tmp_path / "phase3f_analysis_summary.json").exists()
    assert summary["next_phase"].startswith("Phase-4A")
    assert summary["phase4_candidate_status"]["real_double_buffer_pingpong"] == "locked"
