# -*- coding: utf-8 -*-
import json
from pathlib import Path

from strategy_search.phase5_analysis import emit_phase5d_outputs


def test_phase5d_rejects_missing_backend(tmp_path: Path):
    (tmp_path / "phase4d_hivmopseditor_dry_run_plan.json").write_text(json.dumps({
        "actions": [{"action_id": "a0", "candidate_id": "c0", "load_line": 3}]
    }), encoding="utf-8")
    (tmp_path / "phase5b_analysis_summary.json").write_text(json.dumps({
        "passed_noop_roundtrip_and_verify_gate": True
    }), encoding="utf-8")
    (tmp_path / "phase5c_analysis_summary.json").write_text(json.dumps({
        "passed_operation_level_dry_run_gate": True
    }), encoding="utf-8")
    summary = emit_phase5d_outputs(out=tmp_path, optimized_ir_text="module { hivm.hir.load }", operation_backend_binary=None)
    assert summary["production_mutation_allowed"] is False
    assert "operation_backend_not_connected" in summary["blockers"]
    assert (tmp_path / "phase5d_guarded_mutation_execution_report.json").exists()


def test_phase5d_fake_backend_contract_runs_but_is_not_production(tmp_path: Path):
    fake = Path(__file__).resolve().parents[1] / "tools" / "fake_hivm_operation_backend.py"
    (tmp_path / "phase4d_hivmopseditor_dry_run_plan.json").write_text(json.dumps({
        "actions": [{"action_id": "a0", "candidate_id": "c0", "load_line": 3}]
    }), encoding="utf-8")
    (tmp_path / "phase5b_analysis_summary.json").write_text(json.dumps({
        "passed_noop_roundtrip_and_verify_gate": True
    }), encoding="utf-8")
    (tmp_path / "phase5c_analysis_summary.json").write_text(json.dumps({
        "passed_operation_level_dry_run_gate": True
    }), encoding="utf-8")
    summary = emit_phase5d_outputs(
        out=tmp_path,
        optimized_ir_text="module {\n  hivm.hir.load\n}\n",
        operation_backend_binary=str(fake),
    )
    assert summary["mutation_performed"] is False
    assert summary["production_mutation_allowed"] is False
    assert "mutation_backend_is_not_real_mlir_or_hivmopseditor_backend" in summary["blockers"]
    report = json.loads((tmp_path / "phase5d_guarded_mutation_execution_report.json").read_text(encoding="utf-8"))
    assert report["backend_mutation"]["output_exists"] is True
    assert report["evidence_summary"]["backend_is_real_mlir_backend"] is False
