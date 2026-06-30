#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prefill-A5 S0-S9 stage benchmark for HIVM cost-model testing/calibration.

This script uses the extracted Triton-stage history as weak real-hardware labels:
- S0-S9 are multiple optimization versions of the same sparse prefill kernel.
- Each stage has measured latency_us but does not include per-stage msprof component ratios.

Therefore this benchmark calibrates/testing *strategy ranking and parameter sensitivity*,
not AIC/AIV/MTE component-level efficiency.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategy_search.core import (  # noqa: E402
    StrategyConfig,
    apply_cost_model_config,
    build_artifact_profile,
    build_kernel_cost_profile,
    estimate_cost,
    estimate_max_live,
    load_json,
    parse_kernel_features,
    write_json,
)


def _rank(values: List[float]) -> List[float]:
    """Average-rank implementation, smaller value gets smaller rank."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(x: List[float], y: List[float]) -> float:
    if len(x) != len(y) or not x:
        return float("nan")
    mx = sum(x) / len(x)
    my = sum(y) / len(y)
    vx = sum((a - mx) ** 2 for a in x)
    vy = sum((b - my) ** 2 for b in y)
    if vx <= 0 or vy <= 0:
        return 0.0
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(vx * vy)


def _spearman(x: List[float], y: List[float]) -> float:
    return _pearson(_rank(x), _rank(y))


def _kendall_tau(x: List[float], y: List[float]) -> float:
    n = len(x)
    if n < 2:
        return float("nan")
    concordant = 0
    discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            sx = (x[i] > x[j]) - (x[i] < x[j])
            sy = (y[i] > y[j]) - (y[i] < y[j])
            if sx == 0 or sy == 0:
                continue
            if sx == sy:
                concordant += 1
            else:
                discordant += 1
    denom = concordant + discordant
    return 0.0 if denom == 0 else (concordant - discordant) / denom


def _stage_to_strategy(stage: Dict[str, Any], idx: int) -> StrategyConfig:
    block_sbs = int(stage.get("BLOCK_SBS", 128))
    block_k = int(stage.get("BLOCK_K", 512))
    multibuffer = bool(stage.get("multibuffer", False))
    auto_cv = bool(stage.get("enable_hivm_auto_cv_balance", False))
    mixed_cv = bool(stage.get("enable_mixed_cv", False))
    tile_mix_c = int(stage.get("tile_mix_cube_loop", 1) or 1)
    tile_mix_v = int(stage.get("tile_mix_vector_loop", 1) or 1)

    # Prefill-A5 的 S2->S3 只关闭 mixed C/V，不等于关闭整个 CV pipeline。
    # 早期验证把 mixed_cv=False 误映射为 cv_pipeline_stage=1，导致模型把 S3/S4
    # 误判成“无 CV pipeline”，从而夸大了 S2->S3 与 S4->S5 的差异。
    # 对这组 sparse prefill stage history，只要还在主 prefill kernel 内，就保留 stage-2 CV pipeline；
    # mixed_cv / auto_cv_balance / tile_mix 只作为 stage-2 内部调度策略变化。
    cv_stage = int(stage.get("cv_pipeline_stage", 2) or 2)

    # cube-heavy/vector-light 的 tile_mix=4:1 在该样本中代表 prefill large-SBS reuse 策略，
    # 不是普通“不均衡 tile_mix”；因此用专门模板，避免被通用 balance penalty 误伤。
    if tile_mix_c == 4 and tile_mix_v == 1:
        cv_template = "P_PREFILL_LARGE_SBS_REUSE"
    elif cv_stage > 1:
        cv_template = "P2_stage2_balanced"
    else:
        cv_template = "P0_no_cv_pipeline"

    # workspace_sv=bf16 is not a first-class StrategyConfig field.  Use memory_reuse_level
    # only as a weak proxy and keep the explicit empirical prior below.
    workspace_bf16 = str(stage.get("workspace_sv_dtype", "float32")).lower() == "bf16"
    return StrategyConfig(
        strategy_id=f"prefill_a5_{stage['stage'].lower()}_{idx}",
        fusion="keep_existing",
        tile_m=int(stage.get("BLOCK_G", 16)),
        tile_n=block_sbs,
        tile_k=block_k,
        block_dim=4096,
        double_buffer=multibuffer,
        cv_pipeline_stage=cv_stage,
        cv_split_ratio="1:1",
        memory_reuse_level="level1" if workspace_bf16 else "level2",
        sync_policy="graph_sync_solver",
        dma_policy="keep_existing",
        loop_order="outer_mnk",
        tail_strategy="mask_or_pad",
        multibuffer_template="M1_input_double_buffer" if multibuffer else "M0_no_multibuffer",
        cv_pipeline_template=cv_template,
        sync_template="Y2_graph_sync_solver",
        enable_mixed_cv=mixed_cv,
        tile_mix_cube_loop=tile_mix_c,
        tile_mix_vector_loop=tile_mix_v,
        auto_cv_balance=auto_cv,
        barrier_level="medium",
        event_reuse=True,
        sync_granularity="tile" if tile_mix_c != tile_mix_v else "op",
        reduce_tile_policy="full_k",
        layout_aware_tile=True,
        ub_multiplier=1,
        l1_multiplier=2 if multibuffer else 1,
        stage_buffer_policy="ub_stage" if cv_stage > 1 else "none",
        buffer_multipliers_json="{}",
        producer_consumer_distance=1,
        event_id_policy="reuse" if auto_cv else "keep",
        sync_motion="code_motion" if bool(stage.get("enable_code_motion", False)) else "none",
        model_version="V3.3.1-prefill-a5-stage-benchmark",
    )


def _event_name(prev: Dict[str, Any], cur: Dict[str, Any]) -> str:
    if int(prev.get("BLOCK_V", 0)) != int(cur.get("BLOCK_V", 0)):
        return "block_v_512_eliminate_v_loop"
    if int(prev.get("BLOCK_SBS", 0)) != int(cur.get("BLOCK_SBS", 0)) or bool(prev.get("multibuffer")) != bool(cur.get("multibuffer")):
        return "block_sbs_256_multibuffer_false"
    if bool(prev.get("enable_mixed_cv")) != bool(cur.get("enable_mixed_cv")):
        return "mixed_cv_disabled"
    if str(prev.get("workspace_sv_dtype")) != str(cur.get("workspace_sv_dtype")):
        return "workspace_sv_bf16"
    if bool(prev.get("enable_hivm_auto_cv_balance")) != bool(cur.get("enable_hivm_auto_cv_balance")):
        return "hivm_auto_cv_balance"
    if (int(prev.get("tile_mix_cube_loop", 1)) != int(cur.get("tile_mix_cube_loop", 1)) or
            int(prev.get("tile_mix_vector_loop", 1)) != int(cur.get("tile_mix_vector_loop", 1))):
        return "tile_mix_cube4_vec1"
    if bool(prev.get("shared_kv_nope_ssa")) != bool(cur.get("shared_kv_nope_ssa")):
        return "shared_kv_nope_ssa_rewrite"
    if bool(prev.get("hoist_q_loads")) != bool(cur.get("hoist_q_loads")):
        return "hoist_q_loads_rewrite"
    if bool(prev.get("enable_code_motion")) != bool(cur.get("enable_code_motion")):
        return "compiler_code_motion"
    return "unknown_stage_delta"


def _learn_stage_gain_priors(stages: List[Dict[str, Any]]) -> Dict[str, Any]:
    priors: Dict[str, Dict[str, Any]] = {}
    transitions = []
    for i in range(1, len(stages)):
        prev, cur = stages[i - 1], stages[i]
        event = _event_name(prev, cur)
        factor = float(cur["latency_us"]) / max(float(prev["latency_us"]), 1e-9)
        gain = 1.0 / factor if factor > 0 else None
        item = {
            "event": event,
            "from_stage": prev["stage"],
            "to_stage": cur["stage"],
            "latency_factor": factor,
            "speedup_factor": gain,
            "delta_latency_us": float(cur["latency_us"]) - float(prev["latency_us"]),
            "note": "factor < 1 means measured speedup; factor > 1 means measured regression",
        }
        transitions.append(item)
        priors[event] = {
            "latency_multiplier": factor,
            "speedup_factor": gain,
            "evidence": f"{prev['stage']}->{cur['stage']}",
            "from_latency_us": float(prev["latency_us"]),
            "to_latency_us": float(cur["latency_us"]),
        }
    return {"enabled": True, "priors": priors, "transitions": transitions}


def _cumulative_prior_multiplier(stage: Dict[str, Any], priors: Dict[str, Any], mode: str = "all") -> float:
    p = priors.get("priors", {}) if isinstance(priors, dict) else {}
    mult = 1.0
    # S1: BLOCK_V=512 is not represented in StrategyConfig.
    if int(stage.get("BLOCK_V", 256)) >= 512:
        mult *= float(p.get("block_v_512_eliminate_v_loop", {}).get("latency_multiplier", 1.0))
    # S2: partly represented by tile_n and double_buffer, but this specific cbuf-overflow avoiding combined action
    # is more precise than the generic model, so it is included in all-prior mode and half-weighted in hybrid mode.
    if int(stage.get("BLOCK_SBS", 128)) >= 256 and not bool(stage.get("multibuffer", True)):
        f = float(p.get("block_sbs_256_multibuffer_false", {}).get("latency_multiplier", 1.0))
        mult *= math.sqrt(f) if mode == "hybrid" else f
    if not bool(stage.get("enable_mixed_cv", True)):
        f = float(p.get("mixed_cv_disabled", {}).get("latency_multiplier", 1.0))
        mult *= math.sqrt(f) if mode == "hybrid" else f
    if str(stage.get("workspace_sv_dtype", "float32")).lower() == "bf16":
        mult *= float(p.get("workspace_sv_bf16", {}).get("latency_multiplier", 1.0))
    if bool(stage.get("enable_hivm_auto_cv_balance", False)):
        f = float(p.get("hivm_auto_cv_balance", {}).get("latency_multiplier", 1.0))
        mult *= math.sqrt(f) if mode == "hybrid" else f
    if int(stage.get("tile_mix_cube_loop", 1)) == 4 and int(stage.get("tile_mix_vector_loop", 1)) == 1:
        f = float(p.get("tile_mix_cube4_vec1", {}).get("latency_multiplier", 1.0))
        mult *= math.sqrt(f) if mode == "hybrid" else f
    if bool(stage.get("shared_kv_nope_ssa", False)):
        mult *= float(p.get("shared_kv_nope_ssa_rewrite", {}).get("latency_multiplier", 1.0))
    if bool(stage.get("hoist_q_loads", False)):
        mult *= float(p.get("hoist_q_loads_rewrite", {}).get("latency_multiplier", 1.0))
    if bool(stage.get("enable_code_motion", False)):
        mult *= float(p.get("compiler_code_motion", {}).get("latency_multiplier", 1.0))
    return float(mult)


def _metrics(rows: List[Dict[str, Any]], pred_key: str) -> Dict[str, Any]:
    measured = [float(r["measured_cycles"]) for r in rows]
    pred = [float(r[pred_key]) for r in rows]
    abs_pct = [abs(p - m) / max(m, 1e-9) for p, m in zip(pred, measured)]
    measured_best = min(rows, key=lambda r: r["measured_cycles"])["stage"]
    pred_best = min(rows, key=lambda r: r[pred_key])["stage"]
    measured_top3 = {r["stage"] for r in sorted(rows, key=lambda r: r["measured_cycles"])[:3]}
    pred_top3 = {r["stage"] for r in sorted(rows, key=lambda r: r[pred_key])[:3]}
    best_measured = min(measured)
    pred_selected_measured = float(next(r["measured_cycles"] for r in rows if r["stage"] == pred_best))
    return {
        "pred_key": pred_key,
        "spearman_rank_correlation": _spearman(pred, measured),
        "kendall_tau": _kendall_tau(pred, measured),
        "pearson_on_log_cycles": _pearson([math.log(max(x, 1e-9)) for x in pred], [math.log(max(x, 1e-9)) for x in measured]),
        "mean_absolute_percentage_error": sum(abs_pct) / len(abs_pct),
        "max_absolute_percentage_error": max(abs_pct),
        "predicted_best_stage": pred_best,
        "measured_best_stage": measured_best,
        "top1_hit": pred_best == measured_best,
        "top3_recall": len(measured_top3 & pred_top3) / 3.0,
        "best_regret_ratio": pred_selected_measured / best_measured - 1.0,
    }


def run(args: argparse.Namespace) -> Dict[str, Any]:
    stages = json.loads(Path(args.stage_labels).read_text(encoding="utf-8"))
    stages = sorted(stages, key=lambda x: x["stage"])
    hw = apply_cost_model_config(load_json(args.hardware_config), args.cost_model_config, args.risk_mode)
    kf = parse_kernel_features(args.kernel)
    artifact = asdict(build_artifact_profile(args.kernel, args.artifact_des_graph or [], args.artifact_trace or []))
    kernel_profile = build_kernel_cost_profile(kf, artifact, enabled=True)
    search: Dict[str, Any] = {
        "artifact_profile": artifact,
        "kernel_cost_profile": kernel_profile,
        "problem_shape_hint": {
            "m_total": 2048,
            "n_total": 1024,
            "k_total": 512,
            "outer_iterations": 16,
        },
        "cost_model_risk_mode": args.risk_mode,
    }
    priors = _learn_stage_gain_priors(stages)
    rows: List[Dict[str, Any]] = []
    cycles_per_us = float(hw.get("clock", {}).get("cycles_per_us", 1850.0))
    raw_s0 = None
    measured_s0 = None
    raw_records: List[Tuple[Dict[str, Any], StrategyConfig, Dict[str, Any]]] = []
    for i, st in enumerate(stages):
        sc = _stage_to_strategy(st, i)
        ml = estimate_max_live(sc, kf, hw)
        cost = estimate_cost(sc, kf, hw, ml, search)
        raw_records.append((st, sc, cost))
        if st["stage"] == "S0":
            raw_s0 = float(cost["predicted_cycles"])
            measured_s0 = float(st["latency_us"]) * cycles_per_us
    if raw_s0 is None or not raw_s0:
        raw_s0 = float(raw_records[0][2]["predicted_cycles"])
        measured_s0 = float(raw_records[0][0]["latency_us"]) * cycles_per_us
    anchor_scale = measured_s0 / max(raw_s0, 1e-9)
    for st, sc, cost in raw_records:
        measured_cycles = float(st["latency_us"]) * cycles_per_us
        raw_pred = float(cost["predicted_cycles"])
        anchored = raw_pred * anchor_scale
        hybrid_mult = _cumulative_prior_multiplier(st, priors, mode="hybrid")
        all_mult = _cumulative_prior_multiplier(st, priors, mode="all")
        row = {
            "stage": st["stage"],
            "description": st.get("description"),
            "latency_us": float(st["latency_us"]),
            "measured_cycles": measured_cycles,
            "strategy": asdict(sc),
            "raw_project_predicted_cycles": raw_pred,
            "raw_project_anchor_scaled_cycles": anchored,
            "prefill_hybrid_prior_multiplier": hybrid_mult,
            "prefill_all_prior_multiplier": all_mult,
            "hybrid_calibrated_cycles": anchored * hybrid_mult,
            "stage_prior_calibrated_cycles": measured_s0 * all_mult,
            "cost_breakdown": cost.get("cost_breakdown", {}),
        }
        rows.append(row)
    metrics = {
        "raw_project_anchor_scaled": _metrics(rows, "raw_project_anchor_scaled_cycles"),
        "hybrid_calibrated": _metrics(rows, "hybrid_calibrated_cycles"),
        "stage_prior_calibrated": _metrics(rows, "stage_prior_calibrated_cycles"),
    }
    report = {
        "benchmark": "prefill_a5_s0_s9_stage_benchmark",
        "input_stage_labels": str(args.stage_labels),
        "kernel_used_for_hivm_features": str(args.kernel),
        "hardware_config": str(args.hardware_config),
        "cost_model_config": str(args.cost_model_config) if args.cost_model_config else None,
        "cycles_per_us": cycles_per_us,
        "scope": {
            "what_this_can_calibrate": [
                "multi-strategy latency trend",
                "relative gain of block-size/multibuffer/CV/tile-mix/rewrite events",
                "ranking sanity of the current analytical cost model on S0-S9 labels",
            ],
            "what_this_cannot_calibrate": [
                "AIC/AIV/MTE/scalar/vector component correction per stage",
                "universal hardware efficiency constants",
                "full HIVM rewrite correctness, because source files are Triton Python not MLIR",
            ],
        },
        "anchor_scale": {
            "anchor_stage": "S0",
            "raw_s0_predicted_cycles": raw_s0,
            "measured_s0_cycles": measured_s0,
            "global_anchor_scale": anchor_scale,
            "note": "S0 is used only to put analytical cycles onto the measured latency scale. Ranking comparison is still based on S0-S9 relative movement.",
        },
        "learned_stage_gain_priors": priors,
        "metrics": metrics,
        "rows": rows,
        "confidence": {
            "absolute_scale_confidence": "medium for this benchmark after S0 anchoring",
            "ranking_confidence_raw_project": "derived from raw_project_anchor_scaled metrics",
            "ranking_confidence_after_stage_priors": "medium/high on this benchmark but fitted to the S0-S9 labels; needs held-out stages/kernels before claiming generalization",
            "component_level_confidence": "low because per-stage op_summary/msprof component ratios are missing",
        },
    }
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "prefill_a5_stage_benchmark_report.json", report)
    write_json(out / "prefill_a5_cost_calibration_priors.json", priors)
    md = _markdown(report)
    (out / "prefill_a5_stage_benchmark_report.md").write_text(md, encoding="utf-8")
    return report


def _fmt(x: Any, nd: int = 4) -> str:
    if isinstance(x, float):
        if math.isnan(x):
            return "nan"
        return f"{x:.{nd}f}"
    return str(x)


def _markdown(report: Dict[str, Any]) -> str:
    lines = []
    lines.append("# Prefill-A5 S0-S9 Cost Model Benchmark Report\n")
    lines.append("## 1. 定位\n")
    lines.append("这组数据来自同一个 sparse prefill kernel 的 S0-S9 优化历史。它适合做多策略 latency trend / ranking sanity test；由于缺少每个阶段的 op_summary，它不能做 AIC/AIV/MTE/scalar/vector 分项校准。\n")
    lines.append("## 2. 校准方式\n")
    a = report["anchor_scale"]
    lines.append(f"- S0 measured cycles: `{_fmt(a['measured_s0_cycles'], 2)}`\n")
    lines.append(f"- S0 raw predicted cycles: `{_fmt(a['raw_s0_predicted_cycles'], 2)}`\n")
    lines.append(f"- Global anchor scale: `{_fmt(a['global_anchor_scale'], 4)}`\n")
    lines.append("- Raw-project 模式：只用 S0 做量纲 anchor，不使用 S1-S9 的真实 gain。\n")
    lines.append("- Hybrid 模式：对当前 StrategyConfig 表达不充分的事件加入经验 prior，对部分可表达事件用半权重。\n")
    lines.append("- Stage-prior 模式：使用 S0-S9 提取出的 stage gain priors，属于 fitted benchmark 上界，不代表泛化。\n")
    lines.append("\n## 3. Ranking metrics\n")
    lines.append("| Predictor | Spearman | Kendall | Top1 hit | Top3 recall | Best regret | MAPE |\n")
    lines.append("|---|---:|---:|---:|---:|---:|---:|\n")
    for name, m in report["metrics"].items():
        lines.append(f"| {name} | {_fmt(m['spearman_rank_correlation'])} | {_fmt(m['kendall_tau'])} | {m['top1_hit']} | {_fmt(m['top3_recall'])} | {_fmt(m['best_regret_ratio'])} | {_fmt(m['mean_absolute_percentage_error'])} |\n")
    lines.append("\n## 4. Stage rows\n")
    lines.append("| Stage | latency_us | raw_anchor_cycles | hybrid_cycles | stage_prior_cycles |\n")
    lines.append("|---|---:|---:|---:|---:|\n")
    for r in report["rows"]:
        lines.append(f"| {r['stage']} | {_fmt(r['latency_us'], 1)} | {_fmt(r['raw_project_anchor_scaled_cycles'], 1)} | {_fmt(r['hybrid_calibrated_cycles'], 1)} | {_fmt(r['stage_prior_calibrated_cycles'], 1)} |\n")
    lines.append("\n## 5. Learned stage gain priors\n")
    lines.append("| Event | Evidence | latency multiplier | speedup |\n")
    lines.append("|---|---|---:|---:|\n")
    for event, p in report["learned_stage_gain_priors"]["priors"].items():
        lines.append(f"| {event} | {p['evidence']} | {_fmt(p['latency_multiplier'])} | {_fmt(p['speedup_factor'])} |\n")
    lines.append("\n## 6. 结论\n")
    lines.append("这份文件已经被用于两类事情：第一，测试当前 analytical cost model 在 S0-S9 多策略标签上的排序表现；第二，抽取 stage gain priors，用于校准 BLOCK_V、BLOCK_SBS/multibuffer、CV 配置、tile_mix 和 IR rewrite/code motion 的相对收益。由于缺少每个阶段的 msprof component profile，分项硬件效率校准仍然需要每阶段 op_summary。\n")
    return "".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage-labels", default="profiles/prefill_a5/prefill_a5_stage_labels.json")
    ap.add_argument("--kernel", default="sample_input/chunk_kernel.npuir.mlir")
    ap.add_argument("--hardware-config", default="configs/ascend_910b.json")
    ap.add_argument("--cost-model-config", default="configs/cost_model_conservative.json")
    ap.add_argument("--risk-mode", default="conservative")
    ap.add_argument("--artifact-des-graph", nargs="*", default=["sample_product/prefill_des.json"])
    ap.add_argument("--artifact-trace", nargs="*", default=["sample_product/prefill_trace.json"])
    ap.add_argument("--output-dir", default="output_prefill_a5_benchmark")
    args = ap.parse_args()
    report = run(args)
    out = Path(args.output_dir)
    print(f"Generated Prefill-A5 benchmark outputs in: {out}")
    for name, m in report["metrics"].items():
        print(f"{name}: spearman={m['spearman_rank_correlation']:.3f}, top1={m['top1_hit']}, regret={m['best_regret_ratio']:.3f}")


if __name__ == "__main__":
    main()
