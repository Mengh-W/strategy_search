# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from strategy_search.multibuffer_stage_boundary import (
    analyze_multibuffer_stage_boundaries,
    build_stage_mutation_plan,
    write_multibuffer_stage_outputs,
)


def _plan():
    return {"multibuffer_plan": {"controllable_knobs": {"double_buffer": True}}}


def test_stage_boundary_detects_producer_consumer_pair():
    ir = """
module {
  scf.for %i = %c0 to %c16 step %c1 {
    %buf = hivm.hir.pointer_cast(%base, %off) : memref<128xfloat16, #hivm.address_space<ub>> to memref<128xfloat16, #hivm.address_space<ub>>
    hivm.hir.load outs(%buf : memref<128xfloat16, #hivm.address_space<ub>>)
    hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_V>, %e0]
    hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_V>, %e0]
    hivm.hir.vadd ins(%buf : memref<128xfloat16, #hivm.address_space<ub>>) outs(%out : memref<128xfloat16, #hivm.address_space<ub>>)
  }
}
"""
    report = analyze_multibuffer_stage_boundaries(ir, _plan(), max_candidates=10)
    assert report["analyzed_candidate_count"] >= 1
    c = report["stage_boundary_candidates"][0]
    assert c["symbol"] == "%buf"
    assert c["nearest_stage_pair"]["has_pair"] is True
    assert c["producer_candidates"]
    assert c["consumer_candidates"]
    assert c["loop_context_lines"]
    assert c["sync_context"]
    assert c["stage_boundary_status"] in {"READY_FOR_PINGPONG_PLAN", "REVIEW_REQUIRED"}


def test_stage_mutation_plan_is_non_semantic_scaffold():
    ir = """
module {
  scf.for %i = %c0 to %c8 step %c1 {
    %buf = hivm.hir.pointer_cast(%base, %off) : memref<64xfloat16, #hivm.address_space<ub>> to memref<64xfloat16, #hivm.address_space<ub>>
    hivm.hir.load outs(%buf : memref<64xfloat16, #hivm.address_space<ub>>)
    hivm.hir.vmul ins(%buf : memref<64xfloat16, #hivm.address_space<ub>>) outs(%out : memref<64xfloat16, #hivm.address_space<ub>>)
  }
}
"""
    report = analyze_multibuffer_stage_boundaries(ir, _plan(), max_candidates=10)
    plan = build_stage_mutation_plan(report)
    assert plan["semantic_mutation_performed"] is False
    assert plan["production_rewrite_claim_allowed"] is False
    assert plan["action_count"] >= 1
    a = plan["actions"][0]
    assert a["mutation_kind"] == "double_buffer_stage_boundary_plan"
    assert "producer_slot_expr" in a["proposed_pingpong_rewrite"]


def test_write_multibuffer_stage_outputs(tmp_path: Path):
    ir_path = tmp_path / "x.mlir"
    plan_path = tmp_path / "selected_plan.json"
    out = tmp_path / "out"
    ir_path.write_text(
        """
module {
  scf.for %i = %c0 to %c8 step %c1 {
    %buf = hivm.hir.pointer_cast(%base, %off) : memref<64xfloat16, #hivm.address_space<ub>> to memref<64xfloat16, #hivm.address_space<ub>>
    hivm.hir.load outs(%buf : memref<64xfloat16, #hivm.address_space<ub>>)
    hivm.hir.pipe_barrier[<PIPE_MTE2>]
    hivm.hir.vadd ins(%buf : memref<64xfloat16, #hivm.address_space<ub>>) outs(%out : memref<64xfloat16, #hivm.address_space<ub>>)
  }
}
""",
        encoding="utf-8",
    )
    plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
    result = write_multibuffer_stage_outputs(ir_path, plan_path, out, max_candidates=10, max_annotations=5)
    assert Path(result["stage_report_path"]).exists()
    assert Path(result["stage_plan_path"]).exists()
    assert Path(result["annotated_ir_path"]).exists()
    summary = result["summary"]
    assert summary["semantic_mutation_performed"] is False
    assert summary["stage_mutation_plan_action_count"] >= 1
