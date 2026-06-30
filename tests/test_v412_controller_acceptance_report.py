# -*- coding: utf-8 -*-
from pathlib import Path

from strategy_search.controller_acceptance_report import build_acceptance_model, render_markdown, write_acceptance_outputs


def _fake_report():
    return {
        "overall_decision": "PORTABLE_SYNC_REWRITE_PLUS_MULTI_PLAN_SCAFFOLD_READY",
        "claim_boundary": "Only SyncPlan has audited portable/text-level semantic rewrite.",
        "production_rewrite_claim_allowed": False,
        "stage_summaries": {
            "syncplan": {
                "stage_status": "PASSED",
                "mutation_performed": True,
                "rewritten_action_count": 2,
                "passed_portable_validation": True,
                "passed_portable_liveness_after": True,
                "num_sync_related_diff_lines": 9,
                "audit_decision": "PORTABLE_REWRITE_AUDITED_NOT_PRODUCTION",
                "semantic_mutation_performed": True,
                "production_rewrite_claim_allowed": False,
            },
            "multibuffer_stage_boundary": {
                "stage_status": "PASSED",
                "stage_boundary_status_counts": {"READY_FOR_PINGPONG_PLAN": 1},
                "stage_mutation_plan_action_count": 1,
                "semantic_mutation_performed": False,
                "production_rewrite_claim_allowed": False,
            },
            "cvpipeline_stage_planner": {
                "stage_status": "PASSED",
                "pipeline_window_count": 2,
                "pipeline_window_status_counts": {"READY_FOR_CVPIPELINE_PLAN": 1},
                "cvpipeline_rewrite_plan_action_count": 2,
                "semantic_mutation_performed": False,
                "production_rewrite_claim_allowed": False,
            },
            "tiling_feasibility": {
                "stage_status": "REVIEW_REQUIRED",
                "readiness": "READY_FOR_TILING_PLAN_SCAFFOLD",
                "loop_anchor_count": 3,
                "compute_anchor_count": 4,
                "semantic_mutation_performed": False,
                "production_rewrite_claim_allowed": False,
            },
        },
        "hivmopseditor_migration_queue": [
            {"priority": 1, "plan": "SyncPlan", "action_count": 2, "status": "portable", "operation_level_api": ["addSetFlagWaitFlagBefore"]}
        ],
        "execution_order_policy": ["1. Sync first"],
    }


def test_acceptance_model_has_boundary():
    model = build_acceptance_model(_fake_report())
    assert model["production_rewrite_claim_allowed"] is False
    assert model["acceptance_decision"] == "ACCEPTED_AS_PORTABLE_CONTROLLER_DEMO_NOT_PRODUCTION"
    assert model["acceptance_passed_count"] == model["acceptance_total_count"]


def test_render_markdown_mentions_not_production():
    model = build_acceptance_model(_fake_report())
    md = render_markdown(model, Path("."))
    assert "portable/controller demo" in md
    assert "不能宣称 production-level" in md
    assert "HivmOpsEditor migration queue" in md


def test_write_acceptance_outputs(tmp_path: Path):
    report_path = tmp_path / "controller.json"
    import json
    report_path.write_text(json.dumps(_fake_report(), ensure_ascii=False), encoding="utf-8")
    result = write_acceptance_outputs(report_path, tmp_path / "out")
    summary = result["summary"]
    assert Path(summary["markdown_report"]).exists()
    assert Path(summary["html_report"]).exists()
    assert summary["production_rewrite_claim_allowed"] is False
