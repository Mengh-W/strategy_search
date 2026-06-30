# -*- coding: utf-8 -*-
from pathlib import Path

from strategy_search.tiling_true_rewrite import (
    scan_tiling_anchors,
    build_tiling_true_rewrite_actions,
    apply_tiling_true_rewrite,
    validate_tiling_true_rewrite,
    write_tiling_true_rewrite_outputs,
)


def test_tiling_metadata_rewrite_inserts_constants_and_annotations(tmp_path):
    ir = """module {
  %c32 = arith.constant 32 : index
  %c64 = arith.constant 64 : index
  func.func @k() {
    return
  }
}
"""
    plan = {"tiling_plan": {"controllable_knobs": {"tile_m": 32, "tile_n": 64, "tile_k": 128}}}
    scan = scan_tiling_anchors(ir, {"tile_m": 32, "tile_n": 64, "tile_k": 128})
    actions = build_tiling_true_rewrite_actions(plan, scan)
    out, report = apply_tiling_true_rewrite(ir, actions)
    validation = validate_tiling_true_rewrite(ir, out, report)
    assert report["mutation_performed"] is True
    assert "%hivm_tile_m_v52 = arith.constant 32 : index" in out
    assert "%hivm_tile_n_v52 = arith.constant 64 : index" in out
    assert "%hivm_tile_k_v52 = arith.constant 128 : index" in out
    assert 'hivm.tiling.axis = "m"' in out
    assert validation["passed"] is True


def test_write_tiling_outputs(tmp_path):
    ir_path = tmp_path / "x.mlir"
    plan_path = tmp_path / "selected_plan.json"
    ir_path.write_text("module {\n  %c32 = arith.constant 32 : index\n}\n", encoding="utf-8")
    plan_path.write_text('{"tiling_plan":{"controllable_knobs":{"tile_m":32,"tile_n":64,"tile_k":128}}}', encoding="utf-8")
    result = write_tiling_true_rewrite_outputs(ir_path, plan_path, tmp_path / "out")
    assert result["summary"]["mutation_performed"] is True
    assert result["summary"]["passed_portable_validation"] is True
    assert Path(result["paths"]["optimized_ir"]).exists()
