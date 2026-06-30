# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from strategy_search.multibuffer_rewrite_readiness import (
    analyze_multibuffer_readiness,
    annotate_multibuffer_candidates,
    build_multibuffer_mutation_plan,
    write_multibuffer_outputs,
)


def test_multibuffer_readiness_detects_pointer_cast_candidates():
    ir = """
func.func @k() {
  %0 = hivm.hir.pointer_cast(%c0_i64) : memref<2x4x16x16xbf16, #hivm.address_space<cbuf>>
  %1 = memref.subview %0[%i, %j, %c0, %c0] [1, 1, 16, 16] [1, 1, 1, 1] : memref<2x4x16x16xbf16, #hivm.address_space<cbuf>> to memref<?x?x16x16xbf16, #hivm.address_space<cbuf>>
  hivm.hir.nd2nz ins(%arg0 : memref<?xbf16, #hivm.address_space<gm>>) outs(%1 : memref<?x?x16x16xbf16, #hivm.address_space<cbuf>>) init_out_buffer = false
}
"""
    selected = {"multibuffer_plan": {"controllable_knobs": {"double_buffer": True}}}
    report = analyze_multibuffer_readiness(ir, selected, max_candidates=10)
    assert report["anchor_count"] >= 2
    assert report["selected_candidate_count"] >= 1
    assert any(c["kind"] == "hivm_pointer_cast" for c in report["selected_candidates"])


def test_multibuffer_mutation_plan_is_non_mutating_and_migratable():
    ir = """
  %0 = hivm.hir.pointer_cast(%c0_i64) : memref<2x4x16x16xbf16, #hivm.address_space<cbuf>>
  hivm.hir.nd2nz ins(%arg0 : memref<?xbf16, #hivm.address_space<gm>>) outs(%0 : memref<2x4x16x16xbf16, #hivm.address_space<cbuf>>) init_out_buffer = false
"""
    selected = {"multibuffer_plan": {"controllable_knobs": {"double_buffer": True}}}
    readiness = analyze_multibuffer_readiness(ir, selected)
    plan = build_multibuffer_mutation_plan(readiness)
    assert plan["production_rewrite_claim_allowed"] is False
    assert plan["action_count"] >= 1
    assert plan["actions"][0]["status"] == "PLANNED_NOT_MUTATED"
    assert "replace_uses_in_stage_region" in plan["actions"][0]["hivmopseditor_migration"]["required_capabilities"]


def test_multibuffer_annotation_does_not_change_operations():
    ir = "%0 = hivm.hir.pointer_cast(%c0_i64) : memref<2x4x16x16xbf16, #hivm.address_space<cbuf>>\n"
    selected = {"multibuffer_plan": {"controllable_knobs": {"double_buffer": True}}}
    readiness = analyze_multibuffer_readiness(ir, selected)
    plan = build_multibuffer_mutation_plan(readiness)
    annotated, report = annotate_multibuffer_candidates(ir, plan)
    assert report["semantic_mutation_performed"] is False
    assert annotated.count("hivm.hir.pointer_cast") == ir.count("hivm.hir.pointer_cast")


def test_write_multibuffer_outputs(tmp_path: Path):
    ir_path = tmp_path / "x.mlir"
    plan_path = tmp_path / "selected_plan.json"
    out = tmp_path / "out"
    ir_path.write_text("%0 = hivm.hir.pointer_cast(%c0_i64) : memref<2x4x16x16xbf16, #hivm.address_space<cbuf>>\nhivm.hir.nd2nz outs(%0 : memref<2x4x16x16xbf16, #hivm.address_space<cbuf>>)\n", encoding="utf-8")
    plan_path.write_text(json.dumps({"multibuffer_plan": {"controllable_knobs": {"double_buffer": True}}}), encoding="utf-8")
    result = write_multibuffer_outputs(ir_path, plan_path, out)
    assert Path(result["readiness_path"]).exists()
    assert Path(result["mutation_plan_path"]).exists()
    assert result["summary"]["semantic_mutation_performed"] is False
