from pathlib import Path

from strategy_search.phase5_analysis import emit_phase5c_outputs
from strategy_search.phase4_analysis import build_phase4d_hivmopseditor_dry_run_plan


def test_phase5c_pending_without_backend(tmp_path):
    (tmp_path / "phase5b_analysis_summary.json").write_text('{"passed_noop_roundtrip_and_verify_gate": false}', encoding="utf-8")
    (tmp_path / "phase4d_hivmopseditor_dry_run_plan.json").write_text('{"actions": []}', encoding="utf-8")
    summary = emit_phase5c_outputs(out=tmp_path, optimized_ir_text="module { hivm.hir.load }", operation_backend_binary=None)
    assert summary["production_mutation_allowed"] is False
    assert "operation_backend_not_connected" in summary["blockers"]


def test_phase5c_fake_backend_executes_dry_run(tmp_path):
    backend = Path(__file__).resolve().parents[1] / "tools" / "fake_hivm_operation_backend.py"
    plan = {
        "actions": [
            {"action_id": "a0", "type": "hoist_loop_invariant_q_load", "candidate_id": "c0", "load_line": 2}
        ]
    }
    (tmp_path / "phase4d_hivmopseditor_dry_run_plan.json").write_text(__import__("json").dumps(plan), encoding="utf-8")
    (tmp_path / "phase5b_analysis_summary.json").write_text('{"passed_noop_roundtrip_and_verify_gate": true}', encoding="utf-8")
    ir = "module {\n  hivm.hir.load %arg0 : memref<1xf16>\n}\n"
    summary = emit_phase5c_outputs(out=tmp_path, optimized_ir_text=ir, operation_backend_binary=str(backend))
    assert summary["candidate_action_count"] == 1
    assert summary["candidate_located_count"] == 1
    assert summary["production_mutation_allowed"] is False
    assert (tmp_path / "phase5c_operation_level_dry_run_report.json").exists()
