from pathlib import Path

from strategy_search.phase4_analysis import build_phase4b_des_trace_execution_report, emit_phase4b_outputs
from strategy_search.structural_rewrite import try_run_tritonsim_validation


def _ir_file(tmp_path: Path, name: str, extra: str = "") -> Path:
    p = tmp_path / name
    p.write_text(
        """
module {
  func.func @main() {
    hivm.hir.load %A, %ub
    hivm.hir.vadd %ub, %ub
    hivm.hir.store %ub, %B
"""
        + extra
        + """
    return
  }
}
""",
        encoding="utf-8",
    )
    return p


def test_phase4b_report_stays_pending_without_tritonsim():
    report = build_phase4b_des_trace_execution_report(tritonsim_validation_report=None, tritonsim_hivm=None)
    assert report["phase"] == "Phase-4B"
    assert report["passed_external_des_trace_gate"] is False
    assert report["status"] == "pending_or_failed_des_trace_execution"
    assert report["mutation_readiness"]["can_start_guarded_q_load_hoist_prototype"] is False


def test_phase4b_fixture_tritonsim_can_pass_gate(tmp_path):
    original = _ir_file(tmp_path, "original.hivm.mlir")
    optimized = _ir_file(tmp_path, "optimized.hivm.mlir", "    hivm.hir.set_flag[<PIPE_FIX>, <PIPE_V>, <EVENT_ID0>]\n")
    fake = Path(__file__).resolve().parents[1] / "tools" / "fake_tritonsim_hivm.py"
    val_dir = tmp_path / "validation"
    validation = {
        "input_ir": try_run_tritonsim_validation(original, str(fake), val_dir, "original"),
        "optimized_structural_ir": try_run_tritonsim_validation(optimized, str(fake), val_dir, "optimized"),
    }
    summary = emit_phase4b_outputs(
        out=tmp_path,
        tritonsim_validation_report=validation,
        phase4a_summary={"target_parser_status": "binary_available_but_not_validated_in_this_run"},
        tritonsim_hivm=str(fake),
        original_ir_path=str(original),
        optimized_ir_path=str(optimized),
    )
    assert summary["passed_external_des_trace_gate"] is True
    assert (tmp_path / "phase4b_des_trace_execution_report.json").exists()
    assert (tmp_path / "phase4b_validation_commands.sh").exists()
