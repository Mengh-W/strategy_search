# -*- coding: utf-8 -*-
"""Acceptance/reporting layer for the unified four-plan rewrite controller.

V4.12 turns the JSON-heavy V4.11 controller output into human-readable
acceptance artifacts.  It does not add new semantic rewrite mutations.  Its
job is to make the current state auditable: what ran, what passed, what is only
planned, what artifacts were produced, and what remains blocked by the lack of a
real HivmOpsEditor/MLIR verifier environment.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ACCEPTANCE_REPORT_VERSION = "hivm_controller_acceptance_report_v1"
PROJECT_VERSION = "V4.12-controller-acceptance-report"


def _read_json(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_text(path: str | Path, text: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return str(p)


def _write_json(path: str | Path, obj: Any) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _bool_symbol(value: Any) -> str:
    return "✅" if bool(value) else "❌"


def _rel(path: Any, base_dir: str | Path) -> str:
    if not path:
        return ""
    try:
        p = Path(str(path))
        b = Path(base_dir)
        return str(p.relative_to(b))
    except Exception:
        return str(path)


def _stage_row(stage_name: str, stage: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "stage": stage_name,
        "status": stage.get("stage_status") or stage.get("readiness") or "UNKNOWN",
        "semantic_mutation_performed": bool(stage.get("semantic_mutation_performed")),
        "production_rewrite_claim_allowed": bool(stage.get("production_rewrite_claim_allowed")),
        "key_counts": {
            "rewritten_action_count": stage.get("rewritten_action_count"),
            "selected_candidate_count": stage.get("selected_candidate_count"),
            "stage_mutation_plan_action_count": stage.get("stage_mutation_plan_action_count"),
            "pipeline_window_count": stage.get("pipeline_window_count"),
            "cvpipeline_rewrite_plan_action_count": stage.get("cvpipeline_rewrite_plan_action_count"),
            "loop_anchor_count": stage.get("loop_anchor_count"),
        },
        "artifacts": stage.get("artifacts", {}),
    }


def build_acceptance_model(controller_report: Dict[str, Any], controller_summary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    controller_summary = controller_summary or {}
    stage_summaries = controller_report.get("stage_summaries", {})
    stages = [
        _stage_row("SyncPlan", stage_summaries.get("syncplan", {})),
        _stage_row("MultiBufferPlan readiness", stage_summaries.get("multibuffer_readiness", {})),
        _stage_row("MultiBufferPlan stage-boundary", stage_summaries.get("multibuffer_stage_boundary", {})),
        _stage_row("CVPipelinePlan staged planner", stage_summaries.get("cvpipeline_stage_planner", {})),
        _stage_row("TilingPlan feasibility", stage_summaries.get("tiling_feasibility", {})),
    ]
    sync = stage_summaries.get("syncplan", {})
    mb_stage = stage_summaries.get("multibuffer_stage_boundary", {})
    cv = stage_summaries.get("cvpipeline_stage_planner", {})
    tiling = stage_summaries.get("tiling_feasibility", {})
    acceptance_items = [
        {
            "item": "SyncPlan audited portable rewrite closure",
            "passed": bool(sync.get("stage_status") == "PASSED" and sync.get("mutation_performed") and sync.get("passed_portable_validation") and sync.get("passed_portable_liveness_after")),
            "evidence": [
                f"rewritten_action_count={sync.get('rewritten_action_count')}",
                f"audit_decision={sync.get('audit_decision')}",
                f"diff_lines={sync.get('num_sync_related_diff_lines')}",
            ],
        },
        {
            "item": "MultiBufferPlan rewrite readiness scaffold",
            "passed": _as_int(mb_stage.get("stage_mutation_plan_action_count")) > 0,
            "evidence": [
                f"ready_for_pingpong={mb_stage.get('stage_boundary_status_counts', {}).get('READY_FOR_PINGPONG_PLAN')}",
                f"stage_plan_actions={mb_stage.get('stage_mutation_plan_action_count')}",
            ],
        },
        {
            "item": "CVPipelinePlan staged rewrite planner scaffold",
            "passed": _as_int(cv.get("cvpipeline_rewrite_plan_action_count")) > 0,
            "evidence": [
                f"pipeline_windows={cv.get('pipeline_window_count')}",
                f"ready_windows={cv.get('pipeline_window_status_counts', {}).get('READY_FOR_CVPIPELINE_PLAN')}",
            ],
        },
        {
            "item": "TilingPlan feasibility scan",
            "passed": bool(tiling.get("readiness") and not str(tiling.get("readiness")).startswith("BLOCKED")),
            "evidence": [
                f"readiness={tiling.get('readiness')}",
                f"loop_anchors={tiling.get('loop_anchor_count')}",
                f"compute_anchors={tiling.get('compute_anchor_count')}",
            ],
        },
        {
            "item": "Production rewrite claim remains blocked until real verifier",
            "passed": controller_report.get("production_rewrite_claim_allowed") is False,
            "evidence": [controller_report.get("claim_boundary", "")],
        },
    ]
    passed_count = sum(1 for x in acceptance_items if x["passed"])
    total_count = len(acceptance_items)
    if passed_count == total_count:
        acceptance_decision = "ACCEPTED_AS_PORTABLE_CONTROLLER_DEMO_NOT_PRODUCTION"
    elif passed_count >= max(1, total_count - 1):
        acceptance_decision = "ACCEPTED_WITH_REVIEW_ITEMS_NOT_PRODUCTION"
    else:
        acceptance_decision = "REVIEW_REQUIRED_BEFORE_DEMO_ACCEPTANCE"
    return {
        "schema_version": ACCEPTANCE_REPORT_VERSION,
        "version": PROJECT_VERSION,
        "input_ir": controller_report.get("input_ir") or controller_summary.get("input_ir"),
        "selected_plan": controller_report.get("selected_plan") or controller_summary.get("selected_plan"),
        "overall_decision": controller_report.get("overall_decision") or controller_summary.get("overall_decision"),
        "acceptance_decision": acceptance_decision,
        "acceptance_passed_count": passed_count,
        "acceptance_total_count": total_count,
        "claim_boundary": controller_report.get("claim_boundary"),
        "stage_table": stages,
        "acceptance_items": acceptance_items,
        "hivmopseditor_migration_queue": controller_report.get("hivmopseditor_migration_queue", []),
        "execution_order_policy": controller_report.get("execution_order_policy", []),
        "production_rewrite_claim_allowed": False,
    }


def render_markdown(model: Dict[str, Any], output_dir: str | Path) -> str:
    out = Path(output_dir)
    lines: List[str] = []
    lines.append("# HIVM Four-Plan Rewrite Acceptance Report")
    lines.append("")
    lines.append(f"版本：`{model.get('version')}`")
    lines.append("")
    lines.append("## 1. 总体结论")
    lines.append("")
    lines.append(f"- Controller decision: `{model.get('overall_decision')}`")
    lines.append(f"- Acceptance decision: `{model.get('acceptance_decision')}`")
    lines.append(f"- Acceptance checks: `{model.get('acceptance_passed_count')}/{model.get('acceptance_total_count')}`")
    lines.append(f"- Production rewrite claim allowed: `{model.get('production_rewrite_claim_allowed')}`")
    lines.append("")
    lines.append("> 当前验收口径：可以验收为 portable/controller demo；不能宣称 production-level HivmOpsEditor rewrite 已完成。")
    lines.append("")
    lines.append("## 2. Claim boundary")
    lines.append("")
    lines.append(str(model.get("claim_boundary") or ""))
    lines.append("")
    lines.append("## 3. Stage summary")
    lines.append("")
    lines.append("| Stage | Status | Semantic mutation | Production claim | Key counts |")
    lines.append("|---|---:|---:|---:|---|")
    for row in model.get("stage_table", []):
        key_counts = ", ".join(f"{k}={v}" for k, v in row.get("key_counts", {}).items() if v not in (None, {}, []))
        lines.append(f"| {row.get('stage')} | `{row.get('status')}` | {_bool_symbol(row.get('semantic_mutation_performed'))} | {_bool_symbol(row.get('production_rewrite_claim_allowed'))} | {key_counts} |")
    lines.append("")
    lines.append("## 4. Acceptance checks")
    lines.append("")
    lines.append("| Check | Result | Evidence |")
    lines.append("|---|---:|---|")
    for item in model.get("acceptance_items", []):
        evidence = "<br>".join(str(x) for x in item.get("evidence", []) if x)
        lines.append(f"| {item.get('item')} | {_bool_symbol(item.get('passed'))} | {evidence} |")
    lines.append("")
    lines.append("## 5. HivmOpsEditor migration queue")
    lines.append("")
    queue = model.get("hivmopseditor_migration_queue", [])
    if not queue:
        lines.append("暂无 migration queue。")
    else:
        lines.append("| Priority | Plan | Action count | Status | Required operation-level API |")
        lines.append("|---:|---|---:|---|---|")
        for q in queue:
            api = ", ".join(q.get("operation_level_api", []))
            lines.append(f"| {q.get('priority')} | {q.get('plan')} | {q.get('action_count')} | `{q.get('status')}` | {api} |")
    lines.append("")
    lines.append("## 6. 推荐执行顺序")
    lines.append("")
    for rule in model.get("execution_order_policy", []):
        lines.append(f"- {rule}")
    lines.append("")
    lines.append("## 7. 后续验收门槛")
    lines.append("")
    lines.extend([
        "1. 编译真实 vTriton/BiShengIR 环境，确认 `hivm-crud` 或 `hivm-operation-backend` 可运行。",
        "2. 用 HivmOpsEditor 执行 SyncPlan mutation，并通过 MLIR verifier。",
        "3. 对 before/after HIVM 跑 DES/trace，对比同步结构和执行图。",
        "4. 上真机用 msprof 对比性能和正确性。",
        "5. MultiBuffer/CVPipeline/Tiling 只能在 operation-level verifier 可用后进入 semantic mutation。",
    ])
    lines.append("")
    return "\n".join(lines)


def render_html(markdown_text: str, model: Dict[str, Any]) -> str:
    # Lightweight HTML without external dependency; keep markdown as preformatted
    # plus a small header so Windows users can open it directly.
    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
<meta charset=\"utf-8\">
<title>HIVM Four-Plan Rewrite Acceptance Report</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 28px; line-height: 1.5; color: #222; }}
pre {{ white-space: pre-wrap; background: #f7f7f7; padding: 18px; border-radius: 8px; }}
.badge {{ display: inline-block; padding: 4px 8px; border-radius: 999px; background: #eee; margin-right: 8px; }}
</style>
</head>
<body>
<h1>HIVM Four-Plan Rewrite Acceptance Report</h1>
<p><span class=\"badge\">{html.escape(str(model.get('acceptance_decision')))}</span><span class=\"badge\">production=false</span></p>
<pre>{html.escape(markdown_text)}</pre>
</body>
</html>
"""


def write_acceptance_outputs(
    controller_report_path: str | Path,
    output_dir: str | Path,
    controller_summary_path: str | Path | None = None,
) -> Dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    controller_report = _read_json(controller_report_path)
    controller_summary = _read_json(controller_summary_path) if controller_summary_path and Path(controller_summary_path).exists() else {}
    model = build_acceptance_model(controller_report, controller_summary)
    model_path = _write_json(out / "controller_acceptance_model.json", model)
    md_text = render_markdown(model, out)
    md_path = _write_text(out / "controller_acceptance_report.md", md_text)
    html_path = _write_text(out / "controller_acceptance_report.html", render_html(md_text, model))
    summary = {
        "schema_version": "hivm_controller_acceptance_summary_v1",
        "version": PROJECT_VERSION,
        "acceptance_decision": model.get("acceptance_decision"),
        "acceptance_checks": f"{model.get('acceptance_passed_count')}/{model.get('acceptance_total_count')}",
        "overall_decision": model.get("overall_decision"),
        "production_rewrite_claim_allowed": False,
        "markdown_report": md_path,
        "html_report": html_path,
        "model": model_path,
    }
    summary_path = _write_json(out / "controller_acceptance_summary.json", summary)
    return {"summary": summary, "model": model, "summary_path": summary_path}


__all__ = [
    "ACCEPTANCE_REPORT_VERSION",
    "PROJECT_VERSION",
    "build_acceptance_model",
    "render_markdown",
    "render_html",
    "write_acceptance_outputs",
]
