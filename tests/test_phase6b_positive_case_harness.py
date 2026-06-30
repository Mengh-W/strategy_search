from pathlib import Path

from strategy_search.phase6_analysis import emit_phase6b_outputs


def test_phase6b_writes_reports_without_real_backend(tmp_path: Path):
    fixture = tmp_path / "simple.hivm.mlir"
    fixture.write_text(
        """
module {
  func.func @fa(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) {
    %q_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    scf.for %j = %c0 to %c10 step %c1 {
      hivm.hir.load ins(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>)
    }
  }
}
""".strip(),
        encoding="utf-8",
    )
    summary = emit_phase6b_outputs(out=tmp_path, fixture_paths=[str(fixture)])
    assert summary["fixture_count"] == 1
    assert summary["candidate_fixture_count"] == 1
    assert summary["production_mutation_allowed"] is False
    assert (tmp_path / "phase6b_positive_case_validation_report.json").exists()
    assert (tmp_path / "phase6b_fixture_acceptance_matrix.json").exists()
    assert (tmp_path / "phase6b_real_backend_validation_commands.sh").exists()


def test_phase6b_missing_fixture_is_blocked(tmp_path: Path):
    summary = emit_phase6b_outputs(out=tmp_path, fixture_paths=[str(tmp_path / "missing.mlir")])
    assert summary["candidate_fixture_count"] == 0
    assert "no_restricted_positive_fixture_identified_by_static_triage" in summary["blockers"]
