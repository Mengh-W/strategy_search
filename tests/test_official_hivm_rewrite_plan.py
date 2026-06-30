# -*- coding: utf-8 -*-
import json
from pathlib import Path

from strategy_search.hivm_official_rewrite_plan import (
    OFFICIAL_HIVM_OP_SCHEMA,
    build_four_plan_rewrite_plan,
    build_hivm_inventory,
)

ROOT = Path(__file__).resolve().parents[1]


def test_official_schema_contains_four_plan_core_ops():
    for op in [
        "hivm.hir.load",
        "hivm.hir.store",
        "hivm.hir.nd2nz",
        "hivm.hir.mmad",
        "hivm.hir.set_flag",
        "hivm.hir.wait_flag",
        "hivm.hir.pipe_barrier",
    ]:
        assert op in OFFICIAL_HIVM_OP_SCHEMA
        assert OFFICIAL_HIVM_OP_SCHEMA[op]["roles"]


def test_inventory_reads_fa_best_core_hivm_ops():
    text = (ROOT / "sample_input" / "fa_best.hivm.mlir").read_text(encoding="utf-8")
    inv = build_hivm_inventory(text, "fa_best.hivm.mlir")
    counts = inv["summary"]["op_counts"]
    assert counts.get("hivm.hir.load", 0) >= 1
    assert counts.get("hivm.hir.store", 0) >= 1
    assert counts.get("hivm.hir.mmad", 0) >= 1
    assert inv["summary"]["by_category"]["buffers"] >= 1
    assert inv["summary"]["by_category"]["loops"] >= 1


def test_four_plan_rewrite_plan_has_all_requests():
    text = (ROOT / "sample_input" / "fa_best.hivm.mlir").read_text(encoding="utf-8")
    selected_plan = json.loads((ROOT / "artifacts" / "latest_smoke_run" / "selected_plan.json").read_text(encoding="utf-8"))
    inv = build_hivm_inventory(text, "fa_best.hivm.mlir")
    plan = build_four_plan_rewrite_plan(selected_plan, inv)
    names = [r["plan"] for r in plan["requests"]]
    assert names == ["SyncPlan", "MultiBufferPlan", "CVPipelinePlan", "TilingPlan"]
    for req in plan["requests"]:
        assert req["rewrite_actions"]
        assert req["minimum_gates"]
        assert "status" in req
