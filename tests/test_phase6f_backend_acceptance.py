from pathlib import Path

from strategy_search.phase6_analysis import emit_phase6f_outputs


def test_phase6f_without_backend_keeps_mutation_locked(tmp_path):
    fixture = Path('sample_input/phase6_positive_fixtures/restricted_gm_roundtrip_positive.hivm.mlir')
    summary = emit_phase6f_outputs(
        out=tmp_path,
        fixture_paths=[str(fixture)],
        operation_backend_binary=None,
        tritonsim_hivm=None,
    )
    assert summary['phase'] == 'Phase-6F'
    assert summary['production_mutation_allowed'] is False
    assert summary['accepted_backend_for_restricted_mutation_trials'] is False
    assert (tmp_path / 'phase6f_backend_acceptance_report.json').exists()
    assert (tmp_path / 'phase6_closure_report.json').exists()
    assert (tmp_path / 'phase6f_smoke_command_matrix.json').exists()
