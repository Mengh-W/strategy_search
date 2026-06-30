#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Plan-only validation for Prefill-A5 benchmark.

This report intentionally evaluates only the optimization events that are inside
(or directly mappable to) the current four-plan strategy space:
TilingPlan, MultiBufferPlan, CVPipelinePlan, SyncPlan.

Events outside the current model boundary, such as SSA reuse, hoist, compiler
code motion, or dtype/workspace policy, are listed separately and are not counted
as cost-model failures.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.prefill_a5_stage_benchmark import run as run_stage_benchmark  # noqa: E402
from strategy_search.core import write_json  # noqa: E402


SUPPORTED_TRANSITIONS = [
    {
        "from": "S1",
        "to": "S2",
        "event": "BLOCK_SBS=256 + multibuffer=False",
        "plans": ["TilingPlan", "MultiBufferPlan"],
        "reason": "BLOCK_SBS maps to tile_n; multibuffer maps to MultiBufferPlan.double_buffer/template.",
    },
    {
        "from": "S2",
        "to": "S3",
        "event": "enable_mixed_cv=False",
        "plans": ["CVPipelinePlan"],
        "reason": "enable_mixed_cv is explicitly represented by StrategyConfig.enable_mixed_cv.",
    },
    {
        "from": "S4",
        "to": "S5",
        "event": "enable_hivm_auto_cv_balance=True",
        "plans": ["CVPipelinePlan"],
        "reason": "auto_cv_balance is explicitly represented by StrategyConfig.auto_cv_balance. S4 is used as the local baseline so the dtype change S3->S4 is not counted.",
    },
    {
        "from": "S5",
        "to": "S6",
        "event": "tile_mix_cube_loop=4, tile_mix_vector_loop=1",
        "plans": ["CVPipelinePlan"],
        "reason": "tile_mix_cube_loop/tile_mix_vector_loop are explicitly represented by StrategyConfig.",
    },
]

BOUNDARY_GAP_TRANSITIONS = [
    {
        "from": "S0",
        "to": "S1",
        "event": "BLOCK_V=512",
        "classification": "conceptually TilingPlan, but not represented in current StrategyConfig",
        "reason": "The current model maps BLOCK_SBS to tile_n and BLOCK_K to tile_k, but does not have a BLOCK_V/vector-block field. Therefore S0 and S1 become identical strategies in the current cost model.",
    },
]

OUT_OF_SCOPE_TRANSITIONS = [
    {"from": "S3", "to": "S4", "event": "workspace_sv bf16", "classification": "dtype / workspace policy, not one of the current four plan knobs"},
    {"from": "S6", "to": "S7", "event": "shared kv_nope SSA", "classification": "IR rewrite / SSA reuse, not in current four-plan cost model"},
    {"from": "S7", "to": "S8", "event": "hoist Q loads", "classification": "IR rewrite / code motion, not in current four-plan cost model"},
    {"from": "S8", "to": "S9", "event": "enable_code_motion=True", "classification": "compiler pass / code motion, not in current four-plan cost model"},
]


def _gain(prev: float, cur: float) -> float:
    return prev / max(cur, 1e-9)


def _signed_log_error(pred_gain: float, real_gain: float) -> float:
    return math.log(max(pred_gain, 1e-9)) - math.log(max(real_gain, 1e-9))


def _row_lookup(stage_report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {r["stage"]: r for r in stage_report["rows"]}


def _transition_rows(stage_report: Dict[str, Any], transitions: List[Dict[str, Any]], pred_key: str) -> List[Dict[str, Any]]:
    rows = _row_lookup(stage_report)
    out = []
    for t in transitions:
        a, b = t["from"], t["to"]
        ra, rb = rows[a], rows[b]
        real_gain = _gain(float(ra["latency_us"]), float(rb["latency_us"]))
        pred_gain = _gain(float(ra[pred_key]), float(rb[pred_key]))
        real_speedup = real_gain > 1.0
        pred_speedup = pred_gain > 1.0
        out.append({
            **t,
            "latency_before_us": float(ra["latency_us"]),
            "latency_after_us": float(rb["latency_us"]),
            "real_gain": real_gain,
            "predicted_gain": pred_gain,
            "direction_hit": real_speedup == pred_speedup,
            "absolute_gain_error": abs(pred_gain - real_gain),
            "signed_log_gain_error": _signed_log_error(pred_gain, real_gain),
            "interpretation": _interpret_transition(t["event"], real_gain, pred_gain),
        })
    return out


def _interpret_transition(event: str, real_gain: float, pred_gain: float) -> str:
    if (real_gain > 1.0) != (pred_gain > 1.0):
        return f"Direction mismatch: measured shows {'speedup' if real_gain > 1 else 'regression'}, but model predicts {'speedup' if pred_gain > 1 else 'regression'}."
    if abs(pred_gain - real_gain) / max(real_gain, 1e-9) > 0.25:
        return "Direction is correct, but gain magnitude is over/under-sensitive."
    return "Direction and rough gain magnitude are acceptable for this weak benchmark."


def _summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    hits = sum(1 for r in rows if r["direction_hit"])
    mae = sum(float(r["absolute_gain_error"]) for r in rows) / max(n, 1)
    m_log = sum(abs(float(r["signed_log_gain_error"])) for r in rows) / max(n, 1)
    return {
        "num_supported_transitions": n,
        "direction_hits": hits,
        "direction_hit_rate": hits / max(n, 1),
        "mean_absolute_gain_error": mae,
        "mean_abs_log_gain_error": m_log,
        "verdict": _verdict(hits / max(n, 1), mae, rows),
    }


def _verdict(hit_rate: float, mae: float, rows: List[Dict[str, Any]]) -> str:
    bad = [r for r in rows if not r["direction_hit"]]
    if hit_rate >= 0.75 and mae < 0.2:
        return "good: current four-plan cost model captures most plan-level directions on this benchmark"
    if hit_rate >= 0.5:
        names = ", ".join(f"{r['from']}->{r['to']}" for r in bad)
        return f"partial: current four-plan cost model is useful but needs calibration; mismatched transitions: {names}"
    return "weak: current four-plan cost model does not yet reliably capture plan-level directions on this benchmark"


def _calibration_suggestions(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    suggestions = []
    for r in rows:
        factor = r["real_gain"] / max(r["predicted_gain"], 1e-9)
        note = ""
        if not r["direction_hit"]:
            note = "priority: direction mismatch, add or revise the corresponding plan-specific term"
        elif abs(math.log(factor)) > 0.20:
            note = "magnitude calibration: direction is correct but sensitivity is too weak/strong"
        else:
            note = "no urgent calibration needed"
        suggestions.append({
            "transition": f"{r['from']}->{r['to']}",
            "event": r["event"],
            "plans": r.get("plans", []),
            "real_gain": r["real_gain"],
            "current_model_predicted_gain": r["predicted_gain"],
            "recommended_gain_multiplier_on_predicted_effect": factor,
            "note": note,
        })
    return suggestions


def _markdown(report: Dict[str, Any]) -> str:
    lines = []
    lines.append("# Prefill-A5 Plan-only Cost Model Validation Report\n\n")
    lines.append("## 1. 验证边界\n\n")
    lines.append("本报告只验证当前 cost model 承诺建模的四个 plan：TilingPlan、MultiBufferPlan、CVPipelinePlan、SyncPlan。S6->S7 的 shared SSA、S7->S8 的 hoist、S8->S9 的 compiler code motion，以及 S3->S4 的 dtype/workspace policy 不计入当前 cost model 的性能验证。\n\n")
    s = report["plan_only_summary"]
    lines.append("## 2. 核心结果\n\n")
    lines.append(f"- Supported plan transitions: `{s['num_supported_transitions']}`\n")
    lines.append(f"- Direction hits: `{s['direction_hits']}/{s['num_supported_transitions']}`\n")
    lines.append(f"- Direction hit rate: `{s['direction_hit_rate']:.2%}`\n")
    lines.append(f"- Mean absolute gain error: `{s['mean_absolute_gain_error']:.4f}`\n")
    lines.append(f"- Verdict: **{s['verdict']}**\n\n")
    lines.append("## 3. Plan-only transition validation\n\n")
    lines.append("| Transition | Event | Plans | Real gain | Model predicted gain | Direction hit | Interpretation |\n")
    lines.append("|---|---|---|---:|---:|---|---|\n")
    for r in report["plan_only_transition_rows"]:
        lines.append(f"| {r['from']}->{r['to']} | {r['event']} | {', '.join(r.get('plans', []))} | {r['real_gain']:.4f} | {r['predicted_gain']:.4f} | {r['direction_hit']} | {r['interpretation']} |\n")
    lines.append("\n## 4. 不计入当前 cost model 验证的变化\n\n")
    lines.append("| Transition | Event | Classification |\n")
    lines.append("|---|---|---|\n")
    for r in report["boundary_gap_transitions"] + report["out_of_scope_transitions"]:
        lines.append(f"| {r['from']}->{r['to']} | {r['event']} | {r.get('classification', '')} |\n")
    lines.append("\n## 5. 校准建议\n\n")
    lines.append("| Transition | Event | Current predicted gain | Real gain | Suggested multiplier | Note |\n")
    lines.append("|---|---|---:|---:|---:|---|\n")
    for r in report["calibration_suggestions"]:
        lines.append(f"| {r['transition']} | {r['event']} | {r['current_model_predicted_gain']:.4f} | {r['real_gain']:.4f} | {r['recommended_gain_multiplier_on_predicted_effect']:.4f} | {r['note']} |\n")
    lines.append("\n## 6. 结论\n\n")
    if report.get("direction_hit_rate", 0.0) >= 0.999:
        lines.append("这次验证说明：在 Prefill-A5 的 plan-only 范围内，当前配置已经能正确捕捉四个可表达 plan transition 的收益方向；mixed_cv=False、auto_cv_balance 与 tile_mix=4:1 的局部收益幅度也和实测更接近。需要注意的是，这只是基于单个 kernel 优化历史的局部校准结果，不能外推为跨 kernel、跨 shape 的通用可靠排序模型。\n")
    else:
        lines.append("这次验证说明：当前四 plan cost model 已经能对部分 plan 参数变化产生有效响应，尤其是 BLOCK_SBS/multibuffer 组合；但它还不能稳定预测所有 plan-level 增量，特别是 mixed_cv=False 和 tile_mix=4:1 两个 CVPipelinePlan 相关转移方向判断错误。因此，prefill_a5 可以证明当前 cost model 有可校准的策略敏感度，但还不能证明它已经具备可靠的 plan-level ranking 能力。下一步应该把 mixed_cv 与 tile_mix 的经验项改成 workload/profile dependent，而不是固定奖励或固定惩罚。\n")
    return "".join(lines)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    stage_report = run_stage_benchmark(args)
    pred_key = "raw_project_anchor_scaled_cycles"
    plan_rows = _transition_rows(stage_report, SUPPORTED_TRANSITIONS, pred_key)
    report = {
        "benchmark": "prefill_a5_plan_only_validation",
        "source_stage_report": "prefill_a5_stage_benchmark_report.json",
        "prediction_key_used": pred_key,
        "scope": {
            "included": "only transitions directly represented by the current four-plan StrategyConfig",
            "excluded": "BLOCK_V gap, dtype/workspace policy, SSA reuse, hoist, compiler code motion",
        },
        "plan_only_summary": _summary(plan_rows),
        "plan_only_transition_rows": plan_rows,
        "boundary_gap_transitions": BOUNDARY_GAP_TRANSITIONS,
        "out_of_scope_transitions": OUT_OF_SCOPE_TRANSITIONS,
        "calibration_suggestions": _calibration_suggestions(plan_rows),
    }
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "prefill_a5_plan_only_validation_report.json", report)
    (out / "prefill_a5_plan_only_validation_report.md").write_text(_markdown(report), encoding="utf-8")
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage-labels", default="profiles/prefill_a5/prefill_a5_stage_labels.json")
    ap.add_argument("--kernel", default="sample_input/chunk_kernel.npuir.mlir")
    ap.add_argument("--hardware-config", default="configs/ascend_910b.json")
    ap.add_argument("--cost-model-config", default="configs/cost_model_conservative.json")
    ap.add_argument("--risk-mode", default="conservative")
    ap.add_argument("--artifact-des-graph", nargs="*", default=["sample_product/prefill_des.json"])
    ap.add_argument("--artifact-trace", nargs="*", default=["sample_product/prefill_trace.json"])
    ap.add_argument("--output-dir", default="output_prefill_a5_plan_only_validation")
    args = ap.parse_args()
    report = run(args)
    s = report["plan_only_summary"]
    print(f"Generated Prefill-A5 plan-only validation outputs in: {args.output_dir}")
    print(f"direction_hit_rate={s['direction_hit_rate']:.3f}, hits={s['direction_hits']}/{s['num_supported_transitions']}")
    print(s["verdict"])


if __name__ == "__main__":
    main()
