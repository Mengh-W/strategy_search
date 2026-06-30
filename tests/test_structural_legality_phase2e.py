
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from strategy_search.structural_legality import analyze_hivm_ir_for_structural_rewrite, build_structural_legality_report
from strategy_search.structural_rewrite import build_structural_edit_script, try_run_external_strategy_rewriter


def _strategy():
    return {
        "strategy_id": "phase2e_gm_roundtrip_test",
        "sync_policy": "graph_sync_solver",
        "cv_pipeline_stage": 2,
        "double_buffer": True,
        "dma_policy": "remove_gm_roundtrip",
    }


def _ir_with_candidate():
    return """
module {
  func.func @k() {
    hivm.hir.store ins(%tmp_ub : memref<1024xf16, #hivm.address_space<ub>>) outs(%tmp_gm : memref<1024xf16, #hivm.address_space<gm>>)
    hivm.hir.load ins(%tmp_gm : memref<1024xf16, #hivm.address_space<gm>>) outs(%tmp2_ub : memref<1024xf16, #hivm.address_space<ub>>)
    hivm.hir.mmad ins(%tmp2_ub) outs(%acc)
    hivm.hir.vexp ins(%acc) outs(%acc)
    return
  }
}
""".lstrip()


def test_phase2e_legality_detects_but_defers_gm_roundtrip_candidate():
    analysis = analyze_hivm_ir_for_structural_rewrite(_ir_with_candidate())
    assert analysis["op_counts"]["gm_roundtrip_candidate"] == 1
    cand = analysis["anchors"]["gm_roundtrip_candidates"][0]
    assert cand["same_gm_vars"] == ["%tmp_gm"]
    assert cand["delete_permission"] is False

    script = build_structural_edit_script(_strategy(), "balanced")
    types = [e["type"] for e in script["edits"]]
    assert "remove_redundant_gm_roundtrip" in types
    report = build_structural_legality_report(_ir_with_candidate(), script, "balanced")
    gm = [e for e in report["edit_prechecks"] if e["type"] == "remove_redundant_gm_roundtrip"][0]
    assert gm["local_precheck"]["passed_local_precheck"] is False
    assert gm["local_precheck"]["evidence"]["candidate_count"] == 1
    assert gm["local_precheck"]["evidence"]["deletion_deferred"] is True


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ is not available")
def test_phase2e_cpp_bridge_reports_gm_roundtrip_as_deferred(tmp_path):
    root = Path(__file__).resolve().parents[1]
    src = root / "vtriton_adapter" / "hivm_strategy_rewrite.cpp"
    exe = tmp_path / "hivm-strategy-rewrite"
    subprocess.run(["g++", "-std=c++17", str(src), "-o", str(exe)], check=True)

    input_path = tmp_path / "input.hivm.mlir"
    script_path = tmp_path / "structural_edit_script.json"
    output_path = tmp_path / "optimized.structural.hivm.mlir"
    report_path = tmp_path / "structural_rewrite.external_vtriton_report.json"
    input_path.write_text(_ir_with_candidate(), encoding="utf-8")
    script_path.write_text(json.dumps(build_structural_edit_script(_strategy(), "balanced"), indent=2), encoding="utf-8")

    status = try_run_external_strategy_rewriter(input_path, script_path, output_path, report_path, str(exe))
    assert status["returncode"] == 0
    out = output_path.read_text(encoding="utf-8")
    # Phase-2E must not delete the candidate yet; it only reports detection.
    assert "hivm.hir.store" in out
    assert "hivm.hir.load" in out
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["bridge_phase"] == "Phase-2G"
    assert any("remove_redundant_gm_roundtrip" in x and "deferred" in x for x in report["skipped"])
