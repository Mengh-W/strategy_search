# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from strategy_search.multibuffer_stage_boundary import analyze_multibuffer_stage_boundaries, build_stage_mutation_plan
from strategy_search.multibuffer_true_rewrite import (
    apply_multibuffer_true_rewrite,
    build_true_rewrite_actions,
    validate_multibuffer_true_rewrite,
    write_multibuffer_true_rewrite_outputs,
)


def _plan():
    return {"multibuffer_plan": {"controllable_knobs": {"double_buffer": True}}}


def _ir():
    return """
module {
  scf.for %i = %c0 to %c8 step %c1 {
    %buf = hivm.hir.pointer_cast(%base, %off) : memref<64xfloat16, #hivm.address_space<ub>> to memref<64xfloat16, #hivm.address_space<ub>>
    annotation.mark %buf {hivm.multi_buffer = 2 : i32} : memref<64xfloat16, #hivm.address_space<ub>>
    hivm.hir.load outs(%buf : memref<64xfloat16, #hivm.address_space<ub>>)
    hivm.hir.pipe_barrier[<PIPE_MTE2>]
    hivm.hir.vadd ins(%buf : memref<64xfloat16, #hivm.address_space<ub>>) outs(%out : memref<64xfloat16, #hivm.address_space<ub>>)
  }
}
"""


def test_build_true_rewrite_actions_from_stage_plan():
    stage = analyze_multibuffer_stage_boundaries(_ir(), _plan(), max_candidates=10)
    plan = build_stage_mutation_plan(stage)
    actions = build_true_rewrite_actions(plan, max_actions=2)
    assert actions
    a = actions[0]
    assert a["mutation_kind"] == "restricted_additive_pingpong_buffer_rewrite"
    assert a["slot_symbols"]["ping"].endswith("_ping")
    assert a["slot_symbols"]["pong"].endswith("_pong")


def test_apply_multibuffer_true_rewrite_changes_ir_and_replaces_uses():
    stage = analyze_multibuffer_stage_boundaries(_ir(), _plan(), max_candidates=10)
    plan = build_stage_mutation_plan(stage)
    actions = build_true_rewrite_actions(plan, max_actions=1)
    rewritten, report = apply_multibuffer_true_rewrite(_ir(), actions)
    assert report["mutation_performed"] is True
    assert report["rewritten_action_count"] == 1
    assert report["replacement_count"] >= 2
    assert "HIVM V5.0 MultiBufferPlan true rewrite" in rewritten
    assert "_ping" in rewritten and "_pong" in rewritten
    assert "hivm.multi_buffer_slot" in rewritten
    validation = validate_multibuffer_true_rewrite(_ir(), rewritten, report)
    assert validation["passed"] is True


def test_write_multibuffer_true_rewrite_outputs(tmp_path: Path):
    ir_path = tmp_path / "x.mlir"
    plan_path = tmp_path / "selected_plan.json"
    out = tmp_path / "out"
    ir_path.write_text(_ir(), encoding="utf-8")
    plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
    result = write_multibuffer_true_rewrite_outputs(ir_path, plan_path, out, max_candidates=10, max_actions=1)
    assert Path(result["optimized_ir_path"]).exists()
    assert Path(result["rewrite_report_path"]).exists()
    assert Path(result["validation_path"]).exists()
    assert Path(result["diff_path"]).exists()
    summary = result["summary"]
    assert summary["semantic_mutation_performed"] is True
    assert summary["passed_portable_validation"] is True
    assert summary["rewritten_action_count"] == 1
