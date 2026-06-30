from pathlib import Path

from strategy_search.phase6_analysis import emit_phase6a_outputs


def test_phase6a_missing_real_backend_writes_required_inputs(tmp_path: Path):
    summary = emit_phase6a_outputs(out=tmp_path)
    assert summary["phase"] == "Phase-6A"
    assert summary["accepted_for_phase6_positive_case"] is False
    assert "built HIVM Operation backend binary" in summary["need_user_inputs"]
    assert (tmp_path / "phase6a_real_backend_integration_report.json").exists()
    assert (tmp_path / "phase6a_required_inputs.json").exists()


def test_phase6a_rejects_fake_backend(tmp_path: Path):
    backend = Path(__file__).resolve().parents[1] / "tools" / "fake_hivm_operation_backend.py"
    summary = emit_phase6a_outputs(out=tmp_path, operation_backend_binary=str(backend))
    assert summary["accepted_for_phase6_positive_case"] is False
    matrix = (tmp_path / "phase6a_backend_acceptance_matrix.json").read_text(encoding="utf-8")
    assert "declares real MLIR backend" in matrix
    assert "backend_does_not_declare_real_mlir_backend" in (tmp_path / "phase6a_real_backend_integration_report.json").read_text(encoding="utf-8")
