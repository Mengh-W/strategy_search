# -*- coding: utf-8 -*-
from pathlib import Path

from strategy_search.hivm_official_rewrite_plan import build_hivm_inventory
from strategy_search.tiling_operation_readiness import (
    build_tiling_operation_readiness,
    parse_memref_shape,
    write_tiling_operation_readiness_outputs,
)
from strategy_search.rewrite_readiness import build_tiling_readiness


def test_parse_memref_shape_static_dims():
    assert parse_memref_shape("memref<64x128xf16, #hivm.address_space<ub>>") == [64, 128]
    assert parse_memref_shape("memref<96x128xf32>") == [96, 128]


def test_tiling_operation_readiness_builds_dry_run_plan():
    ir = """module {
  func.func @fa(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>, %K_gm : memref<1024x128xf16, #hivm.address_space<gm>>, %O_gm : memref<64x128xf16, #hivm.address_space<gm>>) {
    %q_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    %k_ub = memref.alloc() : memref<96x128xf16, #hivm.address_space<ub>>
    %q_l1 = memref.alloc() : memref<64x128xf16, #hivm.address_space<cbuf>>
    %k_l1 = memref.alloc() : memref<96x128xf16, #hivm.address_space<cbuf>>
    %s_l0c = memref.alloc() : memref<64x96xf32, #hivm.address_space<cc>>
    hivm.hir.load ins(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>)
    scf.for %j = %c0 to %cE step %cB {
      hivm.hir.load ins(%K_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%k_ub : memref<96x128xf16, #hivm.address_space<ub>>)
      hivm.hir.mmad ins(%q_l1, %k_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>, memref<96x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c : memref<64x96xf32, #hivm.address_space<cc>>)
    }
    hivm.hir.store ins(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%O_gm : memref<64x128xf16, #hivm.address_space<gm>>)
  }
}
"""
    selected = {"tiling_plan": {"controllable_knobs": {"tile_m": 32, "tile_n": 64, "tile_k": 128, "loop_order": "outer_mkn", "tail_strategy": "mask_or_pad", "reduce_tile_policy": "half_k", "layout_aware_tile": True}}}
    inventory = build_hivm_inventory(ir, source_name="unit.mlir")
    report = build_tiling_operation_readiness(selected, inventory)
    assert report["overall_status"] in {"READY_FOR_LINUX_BACKEND_ANCHOR_DRY_RUN", "BLOCKED_UNTIL_BACKEND_ANCHORS_RESOLVED"}
    assert report["dry_run_operation_plan"]["loop_split_requests"][0]["axis"] == "m"
    assert any(p["parameter"] == "tile_k" and p["readiness_level"] == "LEVEL_2_DRY_RUN_OPERATION_PLAN" for p in report["parameter_readiness"])
    assert report["production_rewrite_claim_allowed"] is False


def test_rewrite_readiness_tiling_is_no_longer_report_only():
    ir = """module {
  func.func @fa(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>, %K_gm : memref<1024x128xf16, #hivm.address_space<gm>>, %O_gm : memref<64x128xf16, #hivm.address_space<gm>>) {
    %q_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    %k_ub = memref.alloc() : memref<96x128xf16, #hivm.address_space<ub>>
    %q_l1 = memref.alloc() : memref<64x128xf16, #hivm.address_space<cbuf>>
    %k_l1 = memref.alloc() : memref<96x128xf16, #hivm.address_space<cbuf>>
    %s_l0c = memref.alloc() : memref<64x96xf32, #hivm.address_space<cc>>
    hivm.hir.load ins(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>)
    scf.for %j = %c0 to %cE step %cB {
      hivm.hir.load ins(%K_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%k_ub : memref<96x128xf16, #hivm.address_space<ub>>)
      hivm.hir.mmad ins(%q_l1, %k_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>, memref<96x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c : memref<64x96xf32, #hivm.address_space<cc>>)
    }
    hivm.hir.store ins(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%O_gm : memref<64x128xf16, #hivm.address_space<gm>>)
  }
}
"""
    selected = {"tiling_plan": {"controllable_knobs": {"tile_m": 32, "tile_n": 64, "tile_k": 128, "loop_order": "outer_mkn", "tail_strategy": "mask_or_pad", "reduce_tile_policy": "half_k", "layout_aware_tile": True}}}
    inventory = build_hivm_inventory(ir, source_name="unit.mlir")
    readiness = build_tiling_readiness(selected, inventory)
    assert readiness["status"] != "REPORT_AND_HINT_ONLY_V1"
    assert "dry_run_operation_plan" in readiness
    assert readiness["backend_mutation_request_template"]["python_mutation_enabled"] is False


def test_write_tiling_operation_readiness_outputs(tmp_path):
    ir_path = tmp_path / "x.mlir"
    plan_path = tmp_path / "selected_plan.json"
    ir_path.write_text("""module {
  func.func @fa(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>, %K_gm : memref<1024x128xf16, #hivm.address_space<gm>>, %O_gm : memref<64x128xf16, #hivm.address_space<gm>>) {
    %q_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    %k_ub = memref.alloc() : memref<96x128xf16, #hivm.address_space<ub>>
    %q_l1 = memref.alloc() : memref<64x128xf16, #hivm.address_space<cbuf>>
    %k_l1 = memref.alloc() : memref<96x128xf16, #hivm.address_space<cbuf>>
    %s_l0c = memref.alloc() : memref<64x96xf32, #hivm.address_space<cc>>
    hivm.hir.load ins(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>)
    scf.for %j = %c0 to %cE step %cB {
      hivm.hir.load ins(%K_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%k_ub : memref<96x128xf16, #hivm.address_space<ub>>)
      hivm.hir.mmad ins(%q_l1, %k_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>, memref<96x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c : memref<64x96xf32, #hivm.address_space<cc>>)
    }
    hivm.hir.store ins(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%O_gm : memref<64x128xf16, #hivm.address_space<gm>>)
  }
}
""", encoding="utf-8")
    plan_path.write_text('{"tiling_plan":{"controllable_knobs":{"tile_m":32,"tile_n":64,"tile_k":128,"loop_order":"outer_mkn","tail_strategy":"mask_or_pad","reduce_tile_policy":"half_k","layout_aware_tile":true}}}', encoding="utf-8")
    result = write_tiling_operation_readiness_outputs(ir_path, plan_path, tmp_path / "out")
    assert result["summary"]["ready_for_linux_dry_run_count"] >= 7
    assert Path(result["paths"]["report"]).exists()
