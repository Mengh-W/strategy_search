import json
import shutil
import subprocess
from pathlib import Path

import pytest

from strategy_search.structural_rewrite import build_structural_edit_script, try_run_external_strategy_rewriter


def _strategy():
    return {
        "strategy_id": "phase2c_cpp_bridge_test",
        "sync_policy": "graph_sync_solver",
        "cv_pipeline_stage": 2,
        "double_buffer": True,
    }


def _ir():
    return """
module {
  func.func @k() {
    hivm.hir.barrier {mode = "ALL"}
    hivm.hir.mmad ins(%a) outs(%b)
    hivm.hir.vexp ins(%b) outs(%b)
    return
  }
}
""".lstrip()


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ is not available")
def test_phase2c_cpp_bridge_compiles_and_rewrites_barrier(tmp_path):
    root = Path(__file__).resolve().parents[1]
    src = root / "vtriton_adapter" / "hivm_strategy_rewrite.cpp"
    exe = tmp_path / "hivm-strategy-rewrite"
    subprocess.run(["g++", "-std=c++17", str(src), "-o", str(exe)], check=True)

    input_path = tmp_path / "input.hivm.mlir"
    script_path = tmp_path / "structural_edit_script.json"
    output_path = tmp_path / "optimized.structural.hivm.mlir"
    report_path = tmp_path / "structural_rewrite.external_vtriton_report.json"
    input_path.write_text(_ir(), encoding="utf-8")
    script_path.write_text(json.dumps(build_structural_edit_script(_strategy(), "balanced"), indent=2), encoding="utf-8")

    status = try_run_external_strategy_rewriter(input_path, script_path, output_path, report_path, str(exe))
    assert status["returncode"] == 0
    assert status["vtriton_strategy_rewriter_used"] is True
    out = output_path.read_text(encoding="utf-8")
    assert 'hivm.hir.barrier {mode = "ALL"}' not in "\n".join(
        line for line in out.splitlines() if not line.lstrip().startswith("//")
    )
    assert "hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_M>, <EVENT_ID0>]" in out
    assert "hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_M>, <EVENT_ID0>]" in out
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["success"] is True
    assert report["backend_mode"] == "standalone_cpp_strict_bridge"
    assert report["applied_changes"] >= 1
