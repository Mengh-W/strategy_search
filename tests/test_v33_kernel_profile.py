from pathlib import Path
from types import SimpleNamespace

from strategy_search.core import (
    build_artifact_profile,
    build_kernel_cost_profile,
    parse_kernel_features,
    apply_cost_model_config,
    load_json,
    merge_search_space,
    auto_generate_search_space,
    refresh_dynamic_candidate_space,
    apply_v2_focus_space,
    build_layered_candidates,
    feasible_with_relax,
    estimate_cost,
)


def _sample_kernel(tmp_path: Path) -> Path:
    text = r'''
func.func @kernel() {
  %0 = arith.constant 0 : i32
  scf.for %i = %c0 to %c8 step %c1 {
    %1 = arith.addi %0, %0 : i32
    %2 = arith.index_cast %1 : i32 to index
    %3 = hivm.hir.pointer_cast %arg0 : memref<16x16xf16, #hivm.address_space<ub>> to memref<16x16xf16, #hivm.address_space<ub>>
    hivm.hir.set_flag {event = "E0", pipe = "MTE2"}
    hivm.hir.wait_flag {event = "E0", pipe = "CUBE"}
    hivm.hir.pipe_barrier
    hivm.hir.copy %arg0, %arg1 : memref<16x16xf16, #hivm.address_space<gm>> to memref<16x16xf16, #hivm.address_space<ub>>
    hivm.hir.nd2nz %arg1 : memref<16x16xf16, #hivm.address_space<ub>>
    hivm.hir.mmadL1 %arg1, %arg2, %arg3 : memref<16x16xf16, #hivm.address_space<l1>>, memref<16x16xf16, #hivm.address_space<l1>>, memref<16x16xf32, #hivm.address_space<l0c>>
    hivm.hir.fixpipe %arg3 : memref<16x16xf32, #hivm.address_space<l0c>>
    hivm.hir.vadd %arg4, %arg5 : memref<16x16xf16, #hivm.address_space<ub>>
  }
  return
}
'''
    p = tmp_path / "kernel.mlir"
    p.write_text(text, encoding="utf-8")
    return p


def test_v33_extracts_advanced_mlir_features(tmp_path):
    kernel = _sample_kernel(tmp_path)
    art = build_artifact_profile(str(kernel), [], [])
    mlir = art.mlir_evidence
    adv = mlir["advanced_mlir_features"]
    assert adv["loop_weighted"]["inner_loop_sync_count"] >= 1
    assert adv["memory_path"]["path_counts"]
    assert adv["sync_criticality"]["cross_pipe_event_pairs"] >= 1
    assert "cv_pipeline_opportunity_proxy" in adv["sequence_patterns"]


def test_v33_kernel_profile_changes_weights(tmp_path):
    kernel = _sample_kernel(tmp_path)
    kf = parse_kernel_features(str(kernel))
    art = build_artifact_profile(str(kernel), [], [])
    profile = build_kernel_cost_profile(kf, art.__dict__, enabled=True)
    assert profile["enabled"] is True
    assert profile["uses_profiling_target"] is False
    assert profile["weights"]["scalar_cycle_correction"] != 1.0
    assert profile["weights"]["sync_cycle_correction"] >= 0.90
    assert 0.75 <= profile["weights"]["overlap_confidence"] <= 1.05
    # Backward-compatible aliases are kept for existing reports.
    assert profile["weights"]["scalar_control_multiplier"] == profile["weights"]["scalar_cycle_correction"]
    assert "advanced_mlir_features" in profile["raw_features"]
