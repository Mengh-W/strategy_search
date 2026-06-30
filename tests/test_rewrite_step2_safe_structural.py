# -*- coding: utf-8 -*-
"""Step-2 safe structural hint rewrite regression tests."""
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


def _selected(buffer_json: str = '{"k_ub":2,"v_l1":2}', **extra):
    strategy = {
        "strategy_id": "candidate_step2",
        "tile_m": 32,
        "tile_n": 64,
        "tile_k": 256,
        "block_dim": 16,
        "double_buffer": True,
        "ub_multiplier": 1,
        "l1_multiplier": 1,
        "buffer_multipliers_json": buffer_json,
        "sync_policy": "graph_sync_solver",
        "event_reuse": True,
        "cv_pipeline_stage": 2,
    }
    strategy.update(extra)
    return {
        "strategy": strategy,
        "max_live_bytes": {"ub": 4096, "l1": 8192},
        "cost": {"predicted_cycles": 100.0},
    }


def test_step2_conservative_adds_only_explicit_alloc_hints_and_tile_attrs(tmp_path: Path) -> None:
    ir = tmp_path / "kernel.mlir"
    ir.write_text(
        "module {\n"
        "  func.func @kernel() attributes {tile_m = 8 : i64, hivm.tile_n = 16 : i64} {\n"
        "    %q_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>\n"
        "    %k_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>\n"
        "    %acc_ub = memref.alloc() : memref<64x128xf32, #hivm.address_space<ub>>\n"
        "    %v_l1 = memref.alloc() : memref<64x128xf16, #hivm.address_space<cbuf>>\n"
        "    hivm.hir.barrier {mode = \"ALL\"}\n"
        "    return\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )

    emit_strategy_rewrite_outputs(tmp_path, _args(ir, "conservative"), _selected(), [], [])

    structural = (tmp_path / "optimized.safe_structural.hivm.mlir").read_text(encoding="utf-8")
    assert "%k_ub = memref.alloc() {multi_buffer = 2 : i64, hivm.nbuf = 2 : i64}" in structural
    assert "%v_l1 = memref.alloc() {multi_buffer = 2 : i64, hivm.nbuf = 2 : i64}" in structural
    assert "%q_ub = memref.alloc() :" in structural  # no explicit nbuf target under conservative mode
    assert "%acc_ub = memref.alloc() :" in structural  # accumulator guard
    assert "tile_m = 32 : i64" in structural
    assert "hivm.tile_n = 64 : i64" in structural
    assert "hivm.hir.barrier" in structural  # Step-2 never removes sync ops
    assert "Step-2 does not remove/move barriers" in structural

    cap = json.loads((tmp_path / "rewrite_capability_report.json").read_text(encoding="utf-8"))
    assert cap["schema_version"] == "hivm_rewrite_capability_v1"
    assert cap["capabilities"]["alloc_level_multibuffer_hint"] is True
    assert cap["capabilities"]["sync_barrier_or_event_rewrite"] is False
    assert cap["applied_changes_summary"]["buffer_hints_added"] == 2
    assert set(cap["applied_changes_summary"]["buffers_rewritten"]) == {"k_ub", "v_l1"}
    assert cap["anchors"]["tile_attr_anchor_found"] is True


def test_step2_balanced_can_use_stream_name_heuristic_but_never_outputs(tmp_path: Path) -> None:
    ir = tmp_path / "kernel_balanced.mlir"
    ir.write_text(
        "module {\n"
        "  func.func @kernel() {\n"
        "    %q_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>\n"
        "    %k_l1 = memref.alloc() : memref<64x128xf16, #hivm.address_space<cbuf>>\n"
        "    %o_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>\n"
        "    return\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )

    emit_strategy_rewrite_outputs(tmp_path, _args(ir, "balanced"), _selected(buffer_json="{}"), [], [])

    structural = (tmp_path / "optimized.safe_structural.hivm.mlir").read_text(encoding="utf-8")
    assert "%q_ub = memref.alloc() {multi_buffer = 2 : i64, hivm.nbuf = 2 : i64}" in structural
    assert "%k_l1 = memref.alloc() {multi_buffer = 2 : i64, hivm.nbuf = 2 : i64}" in structural
    assert "%o_ub = memref.alloc() :" in structural

    diff = json.loads((tmp_path / "rewrite_diff_report.json").read_text(encoding="utf-8"))
    reasons = {c.get("buffer"): c.get("reason") for c in diff["changes"] if c.get("type") == "buffer_attr"}
    assert reasons["q_ub"] == "balanced_stream_name_heuristic"
    assert reasons["k_l1"] == "balanced_stream_name_heuristic"
