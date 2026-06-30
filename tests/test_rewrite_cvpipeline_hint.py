# -*- coding: utf-8 -*-
"""CVPipeline safe hint rewrite regression tests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from strategy_search.rewrite import emit_strategy_rewrite_outputs


def _args(ir: Path, safety: str = "conservative") -> argparse.Namespace:
    return argparse.Namespace(
        enable_ir_rewrite=True,
        rewrite_mode="both",
        rewrite_safety=safety,
        kernel=str(ir),
        bound_report=None,
        counterfactual=None,
        vtriton_bindings=None,
        vtriton_compile_commands=None,
    )


def _selected(**extra):
    strategy = {
        "strategy_id": "candidate_cv_hint",
        "tile_m": 64,
        "tile_n": 64,
        "tile_k": 128,
        "block_dim": 16,
        "double_buffer": False,
        "ub_multiplier": 1,
        "l1_multiplier": 1,
        "buffer_multipliers_json": "{}",
        "sync_policy": "inject",
        "cv_pipeline_stage": 2,
        "cv_pipeline_template": "P2_stage2_balanced",
        "enable_mixed_cv": False,
        "tile_mix_cube_loop": 1,
        "tile_mix_vector_loop": 1,
        "auto_cv_balance": True,
        "producer_consumer_distance": 1,
        "stage_buffer_policy": "none",
    }
    strategy.update(extra)
    return {
        "strategy": strategy,
        "max_live_bytes": {"ub": 4096, "l1": 8192},
        "cost": {"predicted_cycles": 100.0},
    }


def test_cvpipeline_conservative_marks_cube_fixpipe_vector_but_not_store(tmp_path: Path) -> None:
    ir = tmp_path / "cv_kernel.mlir"
    ir.write_text(
        "module {\n"
        "  func.func @kernel() {\n"
        "    hivm.hir.load ins(%A) outs(%a_ub)\n"
        "    hivm.hir.mmad ins(%a_l1, %b_l1) outs(%c_l0c)\n"
        "    hivm.hir.fixpipe ins(%c_l0c) outs(%c_ub)\n"
        "    hivm.hir.vadd ins(%c_ub, %c_ub) outs(%c_ub)\n"
        "    hivm.hir.store ins(%c_ub) outs(%O)\n"
        "    return\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )

    emit_strategy_rewrite_outputs(tmp_path, _args(ir, "conservative"), _selected(), [], [])

    structural = (tmp_path / "optimized.safe_structural.hivm.mlir").read_text(encoding="utf-8")
    assert 'hivm.hir.mmad {hivm.cv.pipeline_hint = true' in structural
    assert 'hivm.cv.role = "cube"' in structural
    assert 'hivm.hir.fixpipe {hivm.cv.pipeline_hint = true' in structural
    assert 'hivm.cv.role = "fixpipe"' in structural
    assert 'hivm.hir.vadd {hivm.cv.pipeline_hint = true' in structural
    assert 'hivm.cv.role = "vector"' in structural
    assert 'hivm.hir.store ins' in structural  # conservative does not mark load/store boundary ops
    assert 'hivm.hir.store {hivm.cv.pipeline_hint' not in structural

    report = json.loads((tmp_path / "cv_pipeline_rewrite_report.json").read_text(encoding="utf-8"))
    assert report["schema_version"] == "hivm_cv_pipeline_rewrite_report_v1"
    assert report["capabilities"]["cv_op_level_hint_attrs"] is True
    assert report["capabilities"]["cv_pipeline_structural_reorder"] is False
    assert report["applied_changes_summary"]["cv_op_hints_added"] == 3
    assert report["op_inventory"]["has_cv_pipeline_opportunity"] is True

    cap = json.loads((tmp_path / "rewrite_capability_report.json").read_text(encoding="utf-8"))
    assert cap["capabilities"]["cv_pipeline_op_level_hint_attrs"] is True
    assert cap["capabilities"]["cv_pipeline_structural_reorder"] is False
    assert cap["applied_changes_summary"]["cv_op_hints_added"] == 3


def test_cvpipeline_balanced_also_marks_load_store_boundaries(tmp_path: Path) -> None:
    ir = tmp_path / "cv_kernel_balanced.mlir"
    ir.write_text(
        "module {\n"
        "  func.func @kernel() {\n"
        "    hivm.hir.load ins(%A) outs(%a_ub)\n"
        "    hivm.hir.mmadL1 ins(%a_l1, %b_l1) outs(%c_l0c)\n"
        "    hivm.hir.vreduce ins(%c_ub) outs(%m_ub) {reduce_op=\"max\"}\n"
        "    hivm.hir.store ins(%c_ub) outs(%O)\n"
        "    return\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )

    emit_strategy_rewrite_outputs(tmp_path, _args(ir, "balanced"), _selected(cv_pipeline_stage=4, cv_pipeline_template="P3_stage4_aggressive"), [], [])

    structural = (tmp_path / "optimized.safe_structural.hivm.mlir").read_text(encoding="utf-8")
    assert 'hivm.hir.load {hivm.cv.pipeline_hint = true' in structural
    assert 'hivm.cv.role = "load"' in structural
    assert 'hivm.hir.store {hivm.cv.pipeline_hint = true' in structural
    assert 'hivm.cv.role = "store"' in structural
    assert 'hivm.cv.stage = 4 : i64' in structural
    assert 'hivm.hir.vreduce {hivm.cv.pipeline_hint = true' in structural
    assert '{reduce_op="max"}' in structural  # original op-specific attrs are preserved after the hint attrs

    report = json.loads((tmp_path / "cv_pipeline_rewrite_report.json").read_text(encoding="utf-8"))
    assert report["capabilities"]["cv_load_store_boundary_hints"] is True
    assert report["capabilities"]["event_wait_insertion_for_cv_overlap"] is False
    assert report["applied_changes_summary"]["cv_op_hints_added"] == 4


def test_cvpipeline_stage1_emits_report_but_no_op_hints(tmp_path: Path) -> None:
    ir = tmp_path / "cv_kernel_stage1.mlir"
    ir.write_text(
        "module {\n"
        "  func.func @kernel() {\n"
        "    hivm.hir.mmad ins(%a_l1, %b_l1) outs(%c_l0c)\n"
        "    hivm.hir.vadd ins(%c_ub, %c_ub) outs(%c_ub)\n"
        "    return\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )

    emit_strategy_rewrite_outputs(tmp_path, _args(ir, "balanced"), _selected(cv_pipeline_stage=1, cv_pipeline_template="P0_no_cv_pipeline"), [], [])

    structural = (tmp_path / "optimized.safe_structural.hivm.mlir").read_text(encoding="utf-8")
    assert "hivm.cv.pipeline_hint" not in structural

    report = json.loads((tmp_path / "cv_pipeline_rewrite_report.json").read_text(encoding="utf-8"))
    assert report["capabilities"]["cv_op_level_hint_attrs"] is False
    assert report["fallback_reasons"]["cv_not_enabled"] == "selected cv_pipeline_stage <= 1"
