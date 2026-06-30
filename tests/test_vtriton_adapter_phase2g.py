import json
import shutil
import subprocess
from pathlib import Path

import pytest

from strategy_search.structural_rewrite import (
    build_backend_execution_plan,
    build_structural_edit_script,
    build_vtriton_adapter_manifest,
    try_query_strategy_rewriter_capabilities,
)


def _strategy():
    return {
        "strategy_id": "phase2g_manifest_test",
        "sync_policy": "graph_sync_solver",
        "cv_pipeline_stage": 2,
        "double_buffer": True,
    }


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ is not available")
def test_phase2g_cpp_bridge_prints_capabilities_and_manifest_records_coverage(tmp_path):
    root = Path(__file__).resolve().parents[1]
    src = root / "vtriton_adapter" / "hivm_strategy_rewrite.cpp"
    exe = tmp_path / "hivm-strategy-rewrite"
    subprocess.run(["g++", "-std=c++17", str(src), "-o", str(exe)], check=True)

    caps = try_query_strategy_rewriter_capabilities(str(exe))
    assert caps["available"] is True
    assert caps["bridge_phase"] == "Phase-2G"
    assert caps["supports_print_capabilities"] is True
    assert "replace_barrier_all_with_directional_sync" in caps["supported_edits"]
    assert "insert_sync_before_first_vector_op" in caps["supported_edits"]
    assert "remove_redundant_gm_roundtrip" in caps["supported_edits"]

    script = build_structural_edit_script(_strategy(), "balanced")
    plan = build_backend_execution_plan("vtriton", str(exe), None, None)
    manifest = build_vtriton_adapter_manifest(plan, script, str(exe), None, None, _strategy())
    assert manifest["schema_version"] == "hivm_vtriton_adapter_manifest_v1"
    assert manifest["external_strategy_rewriter_capabilities"]["available"] is True
    assert "hoist_invariant_q_load_from_simple_loop" in manifest["external_backend_coverage"]["missing_required_edits_in_external_backend"]
    assert manifest["known_binaries"]["vtriton_strategy_rewriter_sha256"]


def test_phase2g_manifest_without_external_backend_is_explicit():
    script = build_structural_edit_script(_strategy(), "balanced")
    plan = build_backend_execution_plan("auto", None, None, None)
    manifest = build_vtriton_adapter_manifest(plan, script, None, None, None, _strategy())
    assert manifest["external_strategy_rewriter_capabilities"]["available"] is False
    cov = manifest["external_backend_coverage"]["coverage_by_edit_type"]
    assert cov["replace_barrier_all_with_directional_sync"] is None
    assert manifest["interface_contract"]["capability_cli"] == "hivm-strategy-rewrite --print-capabilities"
