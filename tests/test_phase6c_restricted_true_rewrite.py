from pathlib import Path

from strategy_search.phase6_analysis import emit_phase6c_outputs


def test_phase6c_restricted_true_rewrite_defaults(tmp_path: Path):
    summary = emit_phase6c_outputs(out=tmp_path)
    assert summary["restricted_true_mutation_count"] >= 2
    q_outputs = list(tmp_path.glob("optimized.phase6c.*q_load_hoist*.hivm.mlir"))
    gm_outputs = list(tmp_path.glob("optimized.phase6c.*gm_roundtrip_deletion*.hivm.mlir"))
    assert q_outputs
    assert gm_outputs
    q_text = q_outputs[0].read_text(encoding="utf-8")
    assert "[phase6c_true_rewrite] hoisted invariant Q load+nd2nz" in q_text
    assert q_text.index("hivm.hir.load") < q_text.index("scf.for")
    gm_text = gm_outputs[0].read_text(encoding="utf-8")
    assert "removed restricted redundant GM store round-trip" in gm_text
    assert "removed restricted redundant GM reload" in gm_text


def test_phase6c_refuses_unmarked_complex_fixture(tmp_path: Path):
    fixture = tmp_path / "unmarked.hivm.mlir"
    fixture.write_text("module { func.func @f() { scf.for %j = %c0 to %c1 step %c1 { hivm.hir.load } } }", encoding="utf-8")
    summary = emit_phase6c_outputs(out=tmp_path, fixture_paths=[str(fixture)])
    assert summary["restricted_true_mutation_count"] == 0
