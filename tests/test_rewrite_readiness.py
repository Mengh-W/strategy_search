# -*- coding: utf-8 -*-
import json
from pathlib import Path

from strategy_search.hivm_official_rewrite_plan import build_hivm_inventory
from strategy_search.rewrite_readiness import build_rewrite_readiness_bundle, build_readiness_reports

ROOT = Path(__file__).resolve().parents[1]


def _load_inputs():
    ir_text = (ROOT / "sample_input" / "fa_best.hivm.mlir").read_text(encoding="utf-8")
    selected_plan = json.loads((ROOT / "artifacts" / "latest_smoke_run" / "selected_plan.json").read_text(encoding="utf-8"))
    return selected_plan, build_hivm_inventory(ir_text, "fa_best.hivm.mlir")


def test_readiness_bundle_contains_four_plan_reports():
    selected_plan, inventory = _load_inputs()
    bundle = build_rewrite_readiness_bundle(selected_plan, inventory)
    assert bundle["schema_version"] == "four_plan_rewrite_readiness_v1"
    reports = bundle["reports"]
    assert set(reports) == {
        "sync_plan_readiness",
        "multibuffer_plan_readiness",
        "cv_pipeline_plan_readiness",
        "tiling_plan_readiness",
    }
    for report in reports.values():
        assert report["selected_knobs"] is not None
        assert report["backend_mutation_request_template"]["mutation_kind"]
        assert report["must_prove_before_mutate"]
        assert report["status"]


def test_readiness_detects_real_fa_best_anchors():
    selected_plan, inventory = _load_inputs()
    bundle = build_rewrite_readiness_bundle(selected_plan, inventory)
    sync = bundle["reports"]["sync_plan_readiness"]
    mb = bundle["reports"]["multibuffer_plan_readiness"]
    cv = bundle["reports"]["cv_pipeline_plan_readiness"]
    tiling = bundle["reports"]["tiling_plan_readiness"]
    assert len(sync["anchors"]["sync_ops"]) >= 1
    assert mb["anchors"]["num_local_buffers"] >= 1
    assert len(cv["anchors"]["stage_sequence_by_line"]) >= 5
    assert len(tiling["anchors"]["loop_ops"]) >= 1


def test_build_readiness_reports_writes_expected_files(tmp_path):
    paths = build_readiness_reports(
        ROOT / "sample_input" / "fa_best.hivm.mlir",
        ROOT / "artifacts" / "latest_smoke_run" / "selected_plan.json",
        tmp_path,
    )
    expected = {"inventory", "rewrite_plan", "readiness_bundle", "sync", "multibuffer", "cv_pipeline", "tiling"}
    assert set(paths) == expected
    for path in paths.values():
        assert path.exists()
        assert json.loads(path.read_text(encoding="utf-8"))
