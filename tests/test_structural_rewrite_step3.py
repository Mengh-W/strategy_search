# -*- coding: utf-8 -*-
from pathlib import Path
from types import SimpleNamespace

from strategy_search.structural_rewrite import apply_structural_rewrite
from strategy_search.rewrite import emit_strategy_rewrite_outputs


def _strategy():
    return {
        "strategy_id": "struct_demo",
        "tile_m": 64,
        "tile_n": 64,
        "tile_k": 128,
        "double_buffer": True,
        "buffer_multipliers_json": "{}",
        "cv_pipeline_stage": 2,
        "cv_pipeline_template": "P2_stage2_balanced",
        "producer_consumer_distance": 1,
        "tile_mix_cube_loop": 1,
        "tile_mix_vector_loop": 1,
        "enable_mixed_cv": True,
        "auto_cv_balance": True,
        "sync_policy": "graph_sync_solver",
        "event_reuse": False,
        "event_id_policy": "static",
        "sync_granularity": "pipe",
        "sync_motion": "none",
        "barrier_level": "coarse",
    }


def test_apply_structural_rewrite_changes_operation_sequence():
    ir = """
module {
  func.func @fa(%Q_gm: memref<64x128xf16, #hivm.address_space<gm>>) {
    scf.for %j = %c0 to %c1024 step %c32 {
      hivm.hir.load ins(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>)
      hivm.hir.nd2nz ins(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%q_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.barrier {mode = "ALL"}
      hivm.hir.mmad ins(%q_l1, %k_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>, memref<32x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c : memref<64x32xf32, #hivm.address_space<cc>>)
      hivm.hir.fixpipe ins(%s_l0c : memref<64x32xf32, #hivm.address_space<cc>>) outs(%s_ub : memref<64x32xf32, #hivm.address_space<ub>>)
      hivm.hir.vexp ins(%s_ub : memref<64x32xf32, #hivm.address_space<ub>>) outs(%s_ub : memref<64x32xf32, #hivm.address_space<ub>>)
    }
    return
  }
}
""".lstrip()
    result = apply_structural_rewrite(ir, _strategy(), "balanced")
    assert result.changes
    assert "replaced coarse PIPE_ALL barrier" in result.text
    assert "hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_M>, <EVENT_ID0>]" in result.text
    assert "inserted CV directional sync before vector stage" in result.text
    assert result.text.index("hoisted invariant Q load/nd2nz") < result.text.index("scf.for")


def test_emit_step3_outputs(tmp_path: Path):
    ir_path = tmp_path / "kernel.hivm.mlir"
    ir_path.write_text("""
module {
  func.func @fa(%Q_gm: memref<64x128xf16, #hivm.address_space<gm>>) {
    scf.for %j = %c0 to %c1024 step %c32 {
      hivm.hir.load ins(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>)
      hivm.hir.nd2nz ins(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%q_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.barrier {mode = "ALL"}
      hivm.hir.mmad ins(%q_l1, %k_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>, memref<32x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c : memref<64x32xf32, #hivm.address_space<cc>>)
      hivm.hir.fixpipe ins(%s_l0c : memref<64x32xf32, #hivm.address_space<cc>>) outs(%s_ub : memref<64x32xf32, #hivm.address_space<ub>>)
      hivm.hir.vexp ins(%s_ub : memref<64x32xf32, #hivm.address_space<ub>>) outs(%s_ub : memref<64x32xf32, #hivm.address_space<ub>>)
    }
    return
  }
}
""".lstrip(), encoding="utf-8")
    args = SimpleNamespace(
        kernel=str(ir_path),
        enable_ir_rewrite=True,
        rewrite_mode="both",
        rewrite_safety="balanced",
        enable_structural_rewrite=True,
        structural_rewrite_safety="balanced",
        vtriton_hivm_crud=None,
        vtriton_crud_mode="roundtrip",
        vtriton_remove_gm_trips=0,
        bound_report=None,
        counterfactual=None,
        vtriton_bindings=None,
        vtriton_compile_commands=None,
    )
    selected = {"strategy": _strategy(), "max_live_bytes": {}, "cost": {"predicted_cycles": 1}}
    emit_strategy_rewrite_outputs(tmp_path, args, selected, [], [])
    assert (tmp_path / "optimized.structural.hivm.mlir").exists()
    assert (tmp_path / "structural_edit_script.json").exists()
    assert (tmp_path / "structural_rewrite_report.json").exists()
    txt = (tmp_path / "optimized.structural.hivm.mlir").read_text(encoding="utf-8")
    assert "Step-3 FORMAL structural" in txt
    assert "hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_M>, <EVENT_ID0>]" in txt
