# -*- coding: utf-8 -*-
import json
from pathlib import Path

from strategy_search.phase5_analysis import emit_phase5f_outputs


def test_phase5f_closes_with_locked_mutations(tmp_path: Path):
    (tmp_path / "phase5a_analysis_summary.json").write_text(json.dumps({
        "backend_status": "standalone_bridge_only_no_operation_backend"
    }), encoding="utf-8")
    (tmp_path / "phase5b_analysis_summary.json").write_text(json.dumps({
        "status": "passed_noop_roundtrip_and_verify_gate",
        "passed_noop_roundtrip_and_verify_gate": True,
    }), encoding="utf-8")
    (tmp_path / "phase5c_analysis_summary.json").write_text(json.dumps({
        "status": "pending_or_failed_operation_level_dry_run_gate",
        "passed_operation_level_dry_run_gate": False,
    }), encoding="utf-8")
    (tmp_path / "phase5d_analysis_summary.json").write_text(json.dumps({
        "status": "pending_or_failed_guarded_mutation_gate",
        "production_mutation_allowed": False,
        "mutation_performed": False,
    }), encoding="utf-8")
    (tmp_path / "phase5e_analysis_summary.json").write_text(json.dumps({
        "status": "pending_or_failed_limited_gm_roundtrip_deletion_gate",
        "production_mutation_allowed": False,
        "mutation_performed": False,
    }), encoding="utf-8")
    summary = emit_phase5f_outputs(out=tmp_path)
    assert summary["phase"] == "Phase-5F"
    assert summary["production_mutations_unlocked"]["q_load_hoist"] is False
    assert summary["production_mutations_unlocked"]["gm_roundtrip_deletion"] is False
    assert summary["remaining_blocker_count"] > 0
    assert (tmp_path / "phase5_closure_report.json").exists()
    assert (tmp_path / "phase5f_leadership_summary.json").exists()
