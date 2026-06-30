# -*- coding: utf-8 -*-
"""Step-1 annotation rewrite regression tests.

These tests make sure strategy search results can be written back as machine-
readable IR attributes plus sidecar JSON without performing unsafe structural
IR transformations.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from strategy_search.rewrite import emit_strategy_rewrite_outputs


def test_step1_annotation_outputs_ir_attrs_and_sidecars(tmp_path: Path) -> None:
    ir = tmp_path / "kernel.mlir"
    ir.write_text(
        "module {\n"
        "  func.func @kernel() attributes {existing = true} {\n"
        "    return\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    selected = {
        "strategy": {
            "strategy_id": "candidate_test",
            "model_version": "unit",
            "tile_m": 16,
            "tile_n": 32,
            "tile_k": 128,
            "block_dim": 8,
            "loop_order": "outer_mkn",
            "tail_strategy": "mask_or_pad",
            "reduce_tile_policy": "half_k",
            "layout_aware_tile": True,
            "double_buffer": True,
            "ub_multiplier": 1,
            "l1_multiplier": 1,
            "buffer_multipliers_json": "{}",
            "multibuffer_template": "M1_input_double_buffer",
            "stage_buffer_policy": "none",
            "memory_reuse_level": "level1",
            "dma_policy": "keep_existing",
            "cv_pipeline_stage": 2,
            "cv_pipeline_template": "P2_stage2_balanced",
            "cv_split_ratio": "1:1",
            "enable_mixed_cv": False,
            "tile_mix_cube_loop": 1,
            "tile_mix_vector_loop": 1,
            "auto_cv_balance": True,
            "producer_consumer_distance": 1,
            "fusion": "keep_existing",
            "sync_policy": "graph_sync_solver",
            "sync_template": "Y2_graph_sync_solver",
            "barrier_level": "low",
            "event_reuse": True,
            "sync_granularity": "stage",
            "event_id_policy": "reuse",
            "sync_motion": "local_move",
        },
        "max_live_bytes": {"ub": 1024},
        "cost": {"predicted_cycles": 123.0},
    }
    args = argparse.Namespace(
        enable_ir_rewrite=True,
        rewrite_mode="annotation",
        rewrite_safety="conservative",
        kernel=str(ir),
        bound_report=None,
        counterfactual=None,
        vtriton_bindings=None,
        vtriton_compile_commands=None,
    )

    emit_strategy_rewrite_outputs(tmp_path, args, selected, [], [])

    annotated = (tmp_path / "optimized.annotated.hivm.mlir").read_text(encoding="utf-8")
    assert "hivm.strategy.tile_m = 16 : i64" in annotated
    assert "hivm.strategy.cv_pipeline_stage = 2 : i64" in annotated
    assert "hivm.strategy.event_reuse = true" in annotated
    assert "hivm.strategy.multibuffer_template" in annotated
    assert "hivm.strategy.sync_template" in annotated
    assert "memref.alloc" not in annotated  # no structural buffer rewrite in annotation mode

    pass_cfg = json.loads((tmp_path / "pass_pipeline_config.json").read_text(encoding="utf-8"))
    assert pass_cfg["schema_version"] == "hivm_pass_pipeline_config_v1"
    assert [p["name"] for p in pass_cfg["passes"]] == [
        "TileLoop", "MarkMultiBuffer", "CVPipelining", "GraphSyncSolver", "PlanMemory"
    ]

    edit_script = json.loads((tmp_path / "strategy_edit_script.json").read_text(encoding="utf-8"))
    assert edit_script["schema_version"] == "hivm_strategy_edit_v1"
    assert any(e.get("key") == "hivm.strategy.tile_n" for e in edit_script["edits"])
    assert (tmp_path / "rewrite_audit.md").exists()
    assert (tmp_path / "vtriton_candidate_bundle.json").exists()


def test_step1_module_attr_ignores_diagnostic_text(tmp_path: Path) -> None:
    ir = tmp_path / "kernel_with_warning.mlir"
    ir.write_text(
        "warning: overriding the module attributes in frontend dump\n"
        "module {\n"
        "  func.func @kernel() { return }\n"
        "}\n",
        encoding="utf-8",
    )
    selected = {
        "strategy": {
            "strategy_id": "candidate_warning",
            "tile_m": 16,
            "tile_n": 16,
            "tile_k": 64,
            "sync_policy": "inject",
        }
    }
    args = argparse.Namespace(
        enable_ir_rewrite=True,
        rewrite_mode="annotation",
        rewrite_safety="conservative",
        kernel=str(ir),
        bound_report=None,
        counterfactual=None,
        vtriton_bindings=None,
        vtriton_compile_commands=None,
    )

    emit_strategy_rewrite_outputs(tmp_path, args, selected, [], [])
    annotated = (tmp_path / "optimized.annotated.hivm.mlir").read_text(encoding="utf-8")
    assert "warning: overriding the module attributes" in annotated
    assert "module attributes {hivm.sync" in annotated
    assert "func.func @kernel() attributes" in annotated
