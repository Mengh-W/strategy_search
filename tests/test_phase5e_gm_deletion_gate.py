# -*- coding: utf-8 -*-
import json
from pathlib import Path

from strategy_search.phase5_analysis import emit_phase5e_outputs


def _write_phase5b_ok(tmp_path: Path) -> None:
    (tmp_path / "phase5b_analysis_summary.json").write_text(json.dumps({
        "passed_noop_roundtrip_and_verify_gate": True
    }), encoding="utf-8")


def test_phase5e_no_candidates_stays_locked(tmp_path: Path):
    _write_phase5b_ok(tmp_path)
    (tmp_path / "gm_roundtrip_deletion_decision.json").write_text(json.dumps({
        "decisions": [],
        "candidate_count": 0,
        "delete_allowed_count": 0,
    }), encoding="utf-8")
    summary = emit_phase5e_outputs(
        out=tmp_path,
        optimized_ir_text="module { hivm.hir.load }",
        operation_backend_binary=None,
    )
    assert summary["production_mutation_allowed"] is False
    assert summary["candidate_count_total"] == 0
    assert "no_gm_roundtrip_candidates_from_phase3c" in summary["blockers"]
    assert (tmp_path / "phase5e_limited_gm_roundtrip_deletion_report.json").exists()


def test_phase5e_deferred_candidate_not_dispatched(tmp_path: Path):
    _write_phase5b_ok(tmp_path)
    (tmp_path / "gm_roundtrip_deletion_decision.json").write_text(json.dumps({
        "decisions": [{
            "gm_var": "%tmp_gm",
            "store_op_id": 1,
            "store_line": 10,
            "load_op_id": 2,
            "load_line": 12,
            "delete_permission": False,
            "decision": "deferred",
            "reason": "blocked gates: same_static_offset_slice_proven",
            "gates": {"same_textual_gm_var": True, "same_static_offset_slice_proven": False},
        }]
    }), encoding="utf-8")
    fake = Path(__file__).resolve().parents[1] / "tools" / "fake_hivm_operation_backend.py"
    summary = emit_phase5e_outputs(
        out=tmp_path,
        optimized_ir_text="module { hivm.hir.load hivm.hir.store }",
        operation_backend_binary=str(fake),
    )
    assert summary["candidate_count_total"] == 1
    assert summary["executable_action_count"] == 0
    assert summary["production_mutation_allowed"] is False
    assert "all_gm_roundtrip_candidates_deferred_by_phase3c_gate" in summary["blockers"]
    report = json.loads((tmp_path / "phase5e_limited_gm_roundtrip_deletion_report.json").read_text(encoding="utf-8"))
    assert report["backend_mutation"]["ran"] is False


def test_phase5e_fake_backend_refused_for_allowed_candidate(tmp_path: Path):
    _write_phase5b_ok(tmp_path)
    (tmp_path / "gm_roundtrip_deletion_decision.json").write_text(json.dumps({
        "decisions": [{
            "gm_var": "%tmp_gm",
            "store_op_id": 1,
            "store_line": 10,
            "load_op_id": 2,
            "load_line": 12,
            "delete_permission": True,
            "decision": "allowed_by_phase3c_gate",
            "reason": "all conservative gates passed",
            "gates": {
                "same_textual_gm_var": True,
                "same_static_offset_slice_proven": True,
                "memoryssa_unique_reaching_def": True,
                "no_unknown_side_effect": True,
                "not_observable_boundary": True,
            },
        }]
    }), encoding="utf-8")
    fake = Path(__file__).resolve().parents[1] / "tools" / "fake_hivm_operation_backend.py"
    summary = emit_phase5e_outputs(
        out=tmp_path,
        optimized_ir_text="module { hivm.hir.store hivm.hir.load }",
        operation_backend_binary=str(fake),
    )
    assert summary["candidate_count_total"] == 1
    assert summary["executable_action_count"] == 1
    assert summary["production_mutation_allowed"] is False
    assert summary["deleted_pair_count"] == 0
    assert "gm_deletion_backend_is_not_real_mlir_or_hivmopseditor_backend" in summary["blockers"]
