from pathlib import Path
import json
import sys

from strategy_search.phase5_analysis import (
    build_phase5b_roundtrip_verifier_gate_report,
    emit_phase5b_outputs,
)

IR = '''module {
  func.func @main() {
    %q = hivm.hir.load %gm_q : memref<128xf16, 1> -> memref<128xf16, 3>
    hivm.hir.barrier {mode = "ALL"}
    return
  }
}
'''


def test_phase5b_without_backend_is_pending(tmp_path: Path):
    report = build_phase5b_roundtrip_verifier_gate_report(
        out=tmp_path,
        original_ir_text=IR,
        optimized_ir_text=IR,
        operation_backend_binary=None,
    )
    assert report["phase"] == "Phase-5B"
    assert report["passed_noop_roundtrip_and_verify_gate"] is False
    assert "operation_backend_not_connected" in report["blockers"]
    assert report["production_mutation_allowed"] is False


def test_phase5b_fake_backend_passes_noop_gate(tmp_path: Path):
    backend = Path(__file__).resolve().parents[1] / "tools" / "fake_hivm_operation_backend.py"
    report = build_phase5b_roundtrip_verifier_gate_report(
        out=tmp_path,
        original_ir_text=IR,
        optimized_ir_text=IR,
        operation_backend_binary=str(backend),
    )
    assert report["passed_noop_roundtrip_and_verify_gate"] is True
    assert report["status"] == "passed_noop_roundtrip_and_verify_gate"
    assert report["original"]["roundtrip"]["output_exists"] is True
    assert report["optimized"]["verify_only"]["ok"] is True
    assert report["production_mutation_allowed"] is False


def test_emit_phase5b_outputs_writes_reports(tmp_path: Path):
    backend = Path(__file__).resolve().parents[1] / "tools" / "fake_hivm_operation_backend.py"
    (tmp_path / "phase5a_analysis_summary.json").write_text(
        json.dumps({"phase": "Phase-5A", "backend_status": "operation_backend_capability_complete_not_yet_executed"}),
        encoding="utf-8",
    )
    summary = emit_phase5b_outputs(
        out=tmp_path,
        original_ir_text=IR,
        optimized_ir_text=IR,
        operation_backend_binary=str(backend),
    )
    assert summary["phase"] == "Phase-5B"
    assert summary["passed_noop_roundtrip_and_verify_gate"] is True
    assert (tmp_path / "phase5b_roundtrip_verifier_gate_report.json").exists()
    assert (tmp_path / "phase5b_backend_execution_plan.json").exists()
    assert (tmp_path / "phase5b_analysis_summary.json").exists()
