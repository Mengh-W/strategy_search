# -*- coding: utf-8 -*-
"""Markdown and HTML report generation for strategy search results."""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from .plans import KernelFeatures, RESOURCE_SCOPES


def _size_item_to_bytes(item: Dict[str, Any]) -> int:
    if not isinstance(item, dict):
        return 0
    if "size_kb" in item:
        return int(float(item["size_kb"]) * 1024)
    if "size_mb" in item:
        return int(float(item["size_mb"]) * 1024 * 1024)
    if "size_gb" in item:
        return int(float(item["size_gb"]) * 1024 * 1024 * 1024)
    return 0


def memory_cap_bytes(hw: Dict[str, Any], space: str) -> int:
    ms = hw.get("memory_spaces", {})
    key = {"cbuf": "l1", "cc": "l0c", "hbm": "gm", "gm": "hbm"}.get(space, space)
    if space in {"gm_ws", "workspace", "gm_workspace"}:
        for k in ("gm_workspace", "workspace", "gm_ws"):
            cap = _size_item_to_bytes(ms.get(k, {}))
            if cap:
                return cap
        hbm_cap = _size_item_to_bytes(ms.get("hbm", {})) or _size_item_to_bytes(ms.get("gm", {}))
        frac = float(hw.get("workspace_model", {}).get("workspace_budget_fraction", 0.0625))
        default_cap = int(hw.get("workspace_model", {}).get("default_workspace_bytes", 2 * 1024**3))
        return min(default_cap, int(hbm_cap * frac)) if hbm_cap else default_cap
    return _size_item_to_bytes(ms.get(key, {}))


def load_json(path: str) -> Dict[str, Any]:
    """Read a JSON file. Kept local to avoid report -> core coupling."""
    return json.loads(Path(path).read_text(encoding="utf-8"))

HTML_REPORT_CSS = """
:root{--bg:#0f1419;--card:#182230;--card2:#111923;--ink:#e6edf3;--mut:#9aa7b4;--line:#2b3648;--acc:#58a6ff;--ok:#3fb950;--warn:#d29922;--bad:#f85149;}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;}
.wrap{max-width:1180px;margin:0 auto;padding:30px 24px 60px} h1{margin:0;font-size:26px} h2{font-size:18px;margin:28px 0 12px;padding-bottom:7px;border-bottom:1px solid var(--line)} h3{font-size:15px;margin:16px 0 8px;color:var(--acc)}
.sub{color:var(--mut);margin:6px 0 18px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}.kpi .v{font-size:24px;font-weight:750}.kpi .l{color:var(--mut);font-size:12px}.good{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}.mut{color:var(--mut)}
table{width:100%;border-collapse:collapse;font-size:13px;background:var(--card)} th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top} th{background:#121b27;color:var(--mut);font-weight:650} .r{text-align:right;font-variant-numeric:tabular-nums}.c{text-align:center} code{background:#101823;border:1px solid var(--line);border-radius:5px;padding:1px 5px;color:#d6e2ee} pre{white-space:pre-wrap;background:#0b1017;border:1px solid var(--line);border-radius:10px;padding:12px;overflow:auto}
.tag{display:inline-block;border:1px solid var(--line);border-radius:20px;padding:1px 8px;font-size:12px}.tag.ok{color:var(--ok);border-color:#245d35;background:#13251a}.tag.warn{color:var(--warn);border-color:#5a4a1f;background:#2a2413}.tag.bad{color:var(--bad);border-color:#5a2730;background:#2a151a}.bartrk{height:12px;background:#121b27;border-radius:8px;overflow:hidden}.bar{height:12px;background:linear-gradient(90deg,var(--acc),#7ee0ff)}.note{color:var(--mut);border-left:3px solid var(--line);padding:4px 0 4px 12px;margin:12px 0}.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}.vizrow{display:grid;grid-template-columns:180px 1fr 110px;gap:10px;align-items:center;margin:8px 0}.vizlabel{color:var(--mut)}.bar2trk{height:18px;background:#101823;border:1px solid var(--line);border-radius:10px;overflow:hidden;position:relative}.bar2{height:100%;background:linear-gradient(90deg,var(--acc),#7ee0ff);border-radius:10px}.bar2.best{background:linear-gradient(90deg,var(--ok),#85e89d)}.delta.good{color:var(--ok)}.delta.bad{color:var(--bad)}.twocol{display:grid;grid-template-columns:1fr 1fr;gap:12px}.small{font-size:12px;color:var(--mut)}
@media(max-width:850px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.twocol{grid-template-columns:1fr}.vizrow{grid-template-columns:1fr}}
"""


def _fmt_num(x: Any, nd: int = 2) -> str:
    """格式化数值，便于 Markdown/HTML 报告显示。"""
    try:
        if isinstance(x, int):
            return f"{x:,}"
        return f"{float(x):,.{nd}f}"
    except Exception:
        return str(x)


def _html_page(title: str, body: str) -> str:
    """包裹 HTML body，生成完整可打开的报告页面。"""
    return "<!doctype html><html lang='zh'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>" + f"<title>{html.escape(title)}</title><style>{HTML_REPORT_CSS}</style></head><body><div class='wrap'>{body}</div></body></html>"


def _scope_rows(max_live: Dict[str, int], hw: Dict[str, Any]) -> str:
    """生成各 address space 容量占用表格行。"""
    rows: List[str] = []
    for scope in RESOURCE_SCOPES:
        cap = memory_cap_bytes(hw, scope)
        used = int(max_live.get(scope, 0) or 0)
        util = used / cap if cap else 0.0
        tag = "ok" if util <= 0.80 else ("warn" if util <= 1.0 else "bad")
        rows.append(
            f"<tr><td><code>{scope.upper()}</code></td><td class='r'>{used/1024:.2f} KB</td><td class='r'>{cap/1024:.2f} KB</td>"
            f"<td class='r'>{util*100:.1f}%</td><td><div class='bartrk'><div class='bar' style='width:{min(100, util*100):.1f}%'></div></div></td>"
            f"<td class='c'><span class='tag {tag}'>{'OK' if util<=1 else 'overflow'}</span></td></tr>"
        )
    return "".join(rows)


def _strategy_diff_rows(base: Dict[str, Any], best: Dict[str, Any]) -> str:
    """生成 best strategy 与 current IR 估计策略的参数差异表格行。"""
    keys = ["tile_m", "tile_n", "tile_k", "block_dim", "double_buffer", "cv_pipeline_stage", "sync_policy", "loop_order", "tail_strategy", "reduce_tile_policy", "layout_aware_tile", "multibuffer_template", "cv_pipeline_template", "sync_template", "stage_buffer_policy", "ub_multiplier", "l1_multiplier"]
    rows: List[str] = []
    bs, ss = base.get("strategy", {}), best.get("strategy", {})
    for k in keys:
        if k not in ss and k not in bs:
            continue
        a, b = bs.get(k, "-"), ss.get(k, "-")
        chg = a != b
        rows.append(f"<tr><td><code>{html.escape(k)}</code></td><td class='c'>{html.escape(str(a))}</td><td class='c'>{html.escape(str(b))}</td><td class='c'><span class='tag {'ok' if chg else ''}'>{'变化' if chg else '不变'}</span></td></tr>")
    return "".join(rows)


def _cost_rows(cost: Dict[str, Any]) -> str:
    """生成 cost breakdown 表格行。"""
    b = cost.get("cost_breakdown", {}) if isinstance(cost, dict) else {}
    items = [
        ("parallelized_tile_cycles", "并行化后的 tile cycles"),
        ("per_tile_load_exposed", "每 tile 暴露 load cost"),
        ("per_tile_cube_vector_pipeline", "每 tile Cube/Vector pipeline cost"),
        ("per_tile_store_exposed", "每 tile 暴露 store cost"),
        ("per_tile_workspace_exposed", "每 tile 暴露 GM workspace cost"),
        ("gm_workspace_bytes", "GM workspace live bytes"),
        ("gm_workspace_bytes_per_tile_total", "GM workspace traffic / tile"),
        ("warmup_drain", "流水线 warmup / drain"),
        ("sync_cost", "同步 cost"),
        ("memory_pressure_penalty", "Memory pressure penalty"),
        ("shape_regularization_penalty", "Shape regularization penalty"),
        ("tail_efficiency", "Tail efficiency"),
    ]
    rows=[]
    for key, label in items:
        val = b.get(key, cost.get(key))
        if val is None:
            continue
        rows.append(f"<tr><td>{html.escape(label)}</td><td class='r'>{_fmt_num(val, 4 if key.endswith('efficiency') else 2)}</td></tr>")
    return "".join(rows)



def _num_from_cost(obj: Dict[str, Any], key: str, default: float = 0.0) -> float:
    """从 cost 字典中安全读取数值字段。"""
    c = obj.get("cost", {}) if isinstance(obj, dict) else {}
    b = c.get("cost_breakdown", {}) if isinstance(c, dict) else {}
    v = c.get(key, b.get(key, default))
    try:
        return float(v)
    except Exception:
        return float(default)


def _bar_width(value: float, max_value: float) -> float:
    """把数值归一化为 HTML 条形图宽度百分比。"""
    if max_value <= 0:
        return 0.0
    return max(1.5, min(100.0, value / max_value * 100.0))


def _before_after_metric_rows(base: Dict[str, Any], best: Dict[str, Any]) -> str:
    """生成优化前后关键指标对比表格行。"""
    metrics = [
        ("predicted_cycles", "Predicted cycles", "lower"),
        ("n_tiles", "Tile 数量", "lower"),
        ("tile_time", "Tile time", "lower"),
        ("sync_cost", "同步 cost", "lower"),
        ("per_tile_workspace_exposed", "GM workspace 暴露 cost", "lower"),
        ("gm_workspace_bytes", "GM workspace live bytes", "lower"),
        ("memory_pressure_penalty", "资源压力惩罚", "lower"),
        ("shape_regularization_penalty", "Shape 规则化惩罚", "lower"),
        ("effective_parallelism", "有效并行度", "higher"),
        ("tail_efficiency", "Tail efficiency", "higher"),
    ]
    rows: List[str] = []
    for key, label, direction in metrics:
        a = _num_from_cost(base, key, 0.0)
        b = _num_from_cost(best, key, 0.0)
        if a == 0 and b == 0 and key not in ("sync_cost", "per_tile_workspace_exposed", "gm_workspace_bytes", "memory_pressure_penalty", "shape_regularization_penalty"):
            continue
        diff = b - a
        good = diff < 0 if direction == "lower" else diff > 0
        if abs(diff) < 1e-12:
            cls = ""
        else:
            cls = "good" if good else "bad"
        pct = "—" if abs(a) < 1e-12 else f"{(b / a - 1.0) * 100:+.1f}%"
        rows.append(
            f"<tr><td>{html.escape(label)}</td><td class='r'>{_fmt_num(a, 4 if key.endswith('efficiency') else 2)}</td>"
            f"<td class='r'>{_fmt_num(b, 4 if key.endswith('efficiency') else 2)}</td>"
            f"<td class='r delta {cls}'>{_fmt_num(diff, 4 if key.endswith('efficiency') else 2)}</td><td class='r'>{pct}</td></tr>"
        )
    return "".join(rows)


def _before_after_cycle_bars(base: Dict[str, Any], best: Dict[str, Any]) -> str:
    """生成优化前后 cycles 条形对比图。"""
    base_cost = _num_from_cost(base, "predicted_cycles", 0.0)
    best_cost = _num_from_cost(best, "predicted_cycles", 0.0)
    maxv = max(base_cost, best_cost, 1.0)
    saved = base_cost - best_cost
    saved_pct = 0.0 if base_cost <= 0 else saved / base_cost * 100.0
    return (
        "<div class='card'><h3>优化前后 predicted cycles 对比</h3>"
        f"<div class='vizrow'><div class='vizlabel'>当前 IR 估计</div><div class='bar2trk'><div class='bar2' style='width:{_bar_width(base_cost,maxv):.1f}%'></div></div><div class='r'>{_fmt_num(base_cost)}</div></div>"
        f"<div class='vizrow'><div class='vizlabel'>最优候选</div><div class='bar2trk'><div class='bar2 best' style='width:{_bar_width(best_cost,maxv):.1f}%'></div></div><div class='r'>{_fmt_num(best_cost)}</div></div>"
        f"<p class='note'>解析模型下，最优候选相对当前 IR 估计减少 <b>{_fmt_num(saved)}</b> cycles，下降约 <b>{saved_pct:.1f}%</b>。这表示相对输入 IR 当前状态的解析估计改进，不代表真机实测加速。</p></div>"
    )


def _scope_compare_rows(base_ml: Dict[str, int], best_ml: Dict[str, int], hw: Dict[str, Any]) -> str:
    """生成优化前后各层级内存占用对比表格行。"""
    rows: List[str] = []
    for scope in RESOURCE_SCOPES:
        cap = memory_cap_bytes(hw, scope)
        a = int(base_ml.get(scope, 0) or 0)
        b = int(best_ml.get(scope, 0) or 0)
        au = a / cap if cap else 0.0
        bu = b / cap if cap else 0.0
        tag = "ok" if bu <= 0.80 else ("warn" if bu <= 1.0 else "bad")
        rows.append(
            f"<tr><td><code>{scope.upper()}</code></td><td class='r'>{a/1024:.2f} KB<br><span class='small'>{au*100:.1f}%</span></td>"
            f"<td class='r'>{b/1024:.2f} KB<br><span class='small'>{bu*100:.1f}%</span></td>"
            f"<td><div class='bartrk'><div class='bar' style='width:{min(100, au*100):.1f}%'></div></div><div class='bartrk' style='margin-top:5px'><div class='bar' style='width:{min(100, bu*100):.1f}%'></div></div></td>"
            f"<td class='r'>{cap/1024:.2f} KB</td><td class='c'><span class='tag {tag}'>{'OK' if bu<=1 else 'overflow'}</span></td></tr>"
        )
    return "".join(rows)


def _cost_breakdown_compare_rows(base: Dict[str, Any], best: Dict[str, Any]) -> str:
    """生成优化前后 cost breakdown 对比表格行。"""
    items = [
        ("parallelized_tile_cycles", "并行化 tile cycles"),
        ("per_tile_load_exposed", "每 tile 暴露 load"),
        ("per_tile_cube_vector_pipeline", "Cube/Vector pipeline"),
        ("per_tile_store_exposed", "每 tile 暴露 store"),
        ("warmup_drain", "warmup / drain"),
        ("sync_cost", "同步 cost"),
        ("memory_pressure_penalty", "资源压力惩罚"),
        ("shape_regularization_penalty", "shape 惩罚"),
    ]
    rows: List[str] = []
    for key, label in items:
        a = _num_from_cost(base, key, 0.0)
        b = _num_from_cost(best, key, 0.0)
        if a == 0 and b == 0 and key not in ("sync_cost", "per_tile_workspace_exposed", "gm_workspace_bytes", "memory_pressure_penalty", "shape_regularization_penalty"):
            continue
        diff = b - a
        cls = "good" if diff < 0 else ("bad" if diff > 0 else "")
        rows.append(f"<tr><td>{html.escape(label)}</td><td class='r'>{_fmt_num(a)}</td><td class='r'>{_fmt_num(b)}</td><td class='r delta {cls}'>{_fmt_num(diff)}</td></tr>")
    return "".join(rows)


def _top_candidate_bars(top: List[Dict[str, Any]], n: int = 10) -> str:
    """生成 Top-K 候选 predicted_cycles 的 HTML 条形图。"""
    rows: List[str] = []
    vals = [float(item.get("cost", {}).get("predicted_cycles", 0.0) or 0.0) for item in top[:n]]
    maxv = max(vals + [1.0])
    for i, item in enumerate(top[:n], 1):
        s = item.get("strategy", {})
        cyc = float(item.get("cost", {}).get("predicted_cycles", 0.0) or 0.0)
        label = f"#{i} ({s.get('tile_m')},{s.get('tile_n')},{s.get('tile_k')}) / CV{s.get('cv_pipeline_stage')}"
        rows.append(
            f"<div class='vizrow'><div class='vizlabel'>{html.escape(label)}</div>"
            f"<div class='bar2trk'><div class='bar2 {'best' if i==1 else ''}' style='width:{_bar_width(cyc,maxv):.1f}%'></div></div>"
            f"<div class='r'>{_fmt_num(cyc)}</div></div>"
        )
    return "<div class='card'><h3>Top 候选 predicted cycles 分布</h3>" + "".join(rows) + "<p class='note'>柱越短表示 predicted cycles 越低。该图用于观察 Top-K 候选之间的相对差距。</p></div>"


def write_html_report(out: Path, args: argparse.Namespace, kf: KernelFeatures, search_stats: Dict[str, Any], legal: List[Dict[str, Any]], rejected: List[Dict[str, Any]], relaxed: List[Dict[str, Any]], selected: Dict[str, Any], baseline: Dict[str, Any], speedup: float, top: List[Dict[str, Any]], hw: Dict[str, Any]) -> None:
    """生成 HTML 可视化报告，展示 before/after、四 Plan、cost 和硬件边界。"""
    best = top[0]
    best_cost = float(best["cost"].get("predicted_cycles", 0.0))
    base_cost = float(baseline["cost"].get("predicted_cycles", 0.0))
    hcs = search_stats.get("hardware_constraints_summary", {})
    scope_table = _scope_rows(best.get("max_live_bytes", {}), hw)
    scope_compare_table = _scope_compare_rows(baseline.get("max_live_bytes", {}), best.get("max_live_bytes", {}), hw)
    cost_table = _cost_rows(best.get("cost", {}))
    cost_compare_table = _cost_breakdown_compare_rows(baseline, best)
    metric_compare_table = _before_after_metric_rows(baseline, best)
    diff_table = _strategy_diff_rows(baseline, best)
    cycle_bars = _before_after_cycle_bars(baseline, best)
    top_bars = _top_candidate_bars(top, 10)
    top_rows: List[str] = []
    for i, item in enumerate(top[:12], 1):
        s = item.get("strategy", {})
        c = item.get("cost", {})
        ml = item.get("max_live_bytes", {})
        top_rows.append(
            f"<tr><td class='r'>{i}</td><td><code>{html.escape(str(s.get('strategy_id','')))}</code></td>"
            f"<td class='r'>{_fmt_num(c.get('predicted_cycles', 0))}</td><td class='c'>{html.escape(str(c.get('risk_level', c.get('risk_assessment', {}).get('risk_level', 'N/A'))))}</td><td class='c'>({s.get('tile_m')},{s.get('tile_n')},{s.get('tile_k')})</td>"
            f"<td class='c'>{s.get('block_dim')}</td><td class='c'>{s.get('double_buffer')}</td><td class='c'>{s.get('cv_pipeline_stage')}</td>"
            f"<td class='c'>{html.escape(str(s.get('sync_policy')))}</td><td class='r'>{float(ml.get('ub',0))/1024:.2f}</td></tr>"
        )
    reason_items = "".join(f"<li>{html.escape(str(r))}</li>" for r in selected.get("reason", [])[:10])
    notes = [
        "本报告与 CLI/JSON 输出来自同一批寻优结果，只是重新组织为更适合展示的中文页面。",
        "当前版本不执行 IR rewrite；输出结果是 strategy-level recommendation，而不是 optimized HIVM 文件。",
        "predicted cycles 是解析 cost model 下的估计值，不等价于真机实测延迟；speedup 使用 current-IR estimated cost 作为参考。",
        "当前报告启用 risk-aware cost model：UNKNOWN sync legality 与 PASS_ESTIMATED CVPipeline 会根据 cost-risk-mode 被显式降权/惩罚。",
        "当前报告不包含瓶颈诊断和 discrete memory access 分析，这两项不属于本版本 scope。",
    ]
    if not baseline.get("feasible", True):
        notes.append("当前输入 IR 在本解析硬件 gate 下被判定为不可行，因此 speedup 显示为 N/A；cost 对照仅用于诊断资源压力/策略差异。")
    note_list = "".join(f"<li>{html.escape(x)}</li>" for x in notes)
    body = f"""
    <h1>HIVM 四类 Plan 参数寻优报告</h1>
    <p class='sub'>Kernel <code>{html.escape(os.path.basename(args.kernel))}</code> · 硬件配置 <code>{html.escape(os.path.basename(args.hardware_config))}</code> · 搜索模式 <code>{html.escape(str(search_stats.get('search_mode')))}</code></p>
    <div class='grid kpi'>
      <div class='card'><div class='v'>{_fmt_num(base_cost)}</div><div class='l'>当前输入 IR 估计 predicted cycles</div></div>
      <div class='card'><div class='v good'>{_fmt_num(best_cost)}</div><div class='l'>最优候选 predicted cycles</div></div>
      <div class='card'><div class='v good'>{('N/A' if speedup is None else f'{speedup:.3f}×')}</div><div class='l'>相对当前 IR 估计的预测加速比</div></div>
      <div class='card'><div class='v'>{len(legal):,}</div><div class='l'>Relax 后合法候选数</div></div>
    </div>

    <h2>1. 输入 Kernel 静态特征</h2>
    <div class='card'>
      <table><tr><th>特征</th><th class='r'>取值</th></tr>
      <tr><td>函数数量</td><td class='r'>{kf.num_functions}</td></tr>
      <tr><td>AIC / AIV 证据</td><td class='r'>{kf.has_aic} / {kf.has_aiv}</td></tr>
      <tr><td>同步操作</td><td class='r'>barrier={kf.num_pipe_barrier}, set={kf.num_set_flag}, wait={kf.num_wait_flag}, block_set={kf.num_sync_block_set}, block_wait={kf.num_sync_block_wait}</td></tr>
      <tr><td>计算 / 搬运操作</td><td class='r'>nd2nz={kf.num_nd2nz}, mma={kf.num_mmad}, fixpipe={kf.num_fixpipe}, load={kf.num_load}, store={kf.num_store}, vector={sum(kf.vector_op_counts.values())}</td></tr>
      <tr><td>推断的问题规模</td><td class='r'><code>{html.escape(json.dumps(kf.inferred_problem_shape, ensure_ascii=False))}</code></td></tr>
      </table>
    </div>

    <h2>2. 搜索空间与算法摘要</h2>
    <div class='card'>
      <table><tr><th>项目</th><th class='r'>取值</th></tr>
      <tr><td>候选生成方式</td><td class='r'>{html.escape(str(hcs.get('block_dim_generation', 'unknown')))}</td></tr>
      <tr><td>Layer-1 保留 / 拒绝</td><td class='r'>{search_stats.get('layer1_kept')} / {search_stats.get('layer1_rejected_count')}</td></tr>
      <tr><td>Layer-2 allocation 数</td><td class='r'>{search_stats.get('layer2_allocations')}</td></tr>
      <tr><td>Layer-3 候选数</td><td class='r'>{search_stats.get('layer3_candidates')}</td></tr>
      <tr><td>Stage2b L1 保留策略</td><td class='r'>{html.escape(str((search_stats.get('layer1_stability_audit') or {}).get('policy', 'n/a')))}</td></tr>
      <tr><td>Stage2b pinned standard L1</td><td class='r'>{(search_stats.get('layer1_stability_audit') or {}).get('pinned_standard_after_topw_and_diversity', (search_stats.get('layer1_stability_audit') or {}).get('pinned_standard_after_topw', 0))}</td></tr>
      <tr><td>Stage2b diversity 新增 L1</td><td class='r'>{(search_stats.get('layer1_stability_audit') or {}).get('diversity_added_after_topw', 0)}</td></tr>
      <tr><td>Stage2b fallback 新增 L1</td><td class='r'>{(search_stats.get('layer1_stability_audit') or {}).get('fallback_added_after_topw_diversity_and_pins', 0)}</td></tr>
      <tr><td>搜索质量审计</td><td class='r'>{'enabled' if (search_stats.get('search_quality_audit') or {}).get('enabled') else 'disabled'}</td></tr>
      <tr><td>Beam vs 小空间穷举 gap</td><td class='r'>{_fmt_num(((search_stats.get('search_quality_audit') or {}).get('beam_vs_small_exhaustive_gap_ratio') or 0.0) * 100, 2) + '%' if (search_stats.get('search_quality_audit') or {}).get('enabled') and (search_stats.get('search_quality_audit') or {}).get('beam_vs_small_exhaustive_gap_ratio') is not None else 'N/A'}</td></tr>
      <tr><td>Beam 相对随机基线优势</td><td class='r'>{_fmt_num(((search_stats.get('search_quality_audit') or {}).get('beam_advantage_over_random_ratio') or 0.0) * 100, 2) + '%' if (search_stats.get('search_quality_audit') or {}).get('enabled') and (search_stats.get('search_quality_audit') or {}).get('beam_advantage_over_random_ratio') is not None else 'N/A'}</td></tr>
      <tr><td>候选去重删除数</td><td class='r'>{(search_stats.get('candidate_dedup_audit') or {}).get('dedup_removed', 0)}</td></tr>
      <tr><td>Relax 后仍被拒绝</td><td class='r'>{len(rejected):,}</td></tr>
      <tr><td>通过 relax 变为可行</td><td class='r'>{len(relaxed):,}</td></tr>
      </table>
      <p class='note'>当前激活的寻优维度为 TilingPlan、MultiBufferPlan、CVPipelinePlan 和 SyncPlan。Fusion、DMA policy 和 memory reuse 在本版本中保持固定。</p>
    </div>

    <h2>3. 优化前后核心对比</h2>
    {cycle_bars}
    {"<div class='card'><p class='note'>当前输入 IR 在解析硬件 gate 下不可行，预测加速比不作为有效指标；下表仅用于展示 current-IR estimated cost 与最优候选之间的模型差异。</p></div>" if not baseline.get("feasible", True) else ""}
    <div class='card'><table><tr><th>指标</th><th class='r'>当前 IR 估计</th><th class='r'>最优候选</th><th class='r'>变化量</th><th class='r'>变化比例</th></tr>{metric_compare_table}</table>
    <p class='note'>“优化前”指根据输入 IR 当前已有特征恢复出的 current-IR estimated strategy；“优化后”指搜索得到的 selected best strategy。当前版本不改写 IR，因此这里比较的是解析模型下的策略层结果。</p></div>

    <h2>4. 最优候选策略</h2>
    <div class='card'><table><tr><th>参数</th><th class='c'>当前 IR 估计</th><th class='c'>最优候选</th><th class='c'>是否变化</th></tr>{diff_table}</table></div>
    <div class='card'><h3>模型选择该策略的主要原因</h3><ul>{reason_items}</ul></div>

    <h2>5. 硬件边界检查与资源占用对比</h2>
    <div class='card'><table><tr><th>Scope</th><th class='r'>当前 IR 估计</th><th class='r'>最优候选</th><th>双条对比<br><span class='small'>上：当前 IR；下：最优</span></th><th class='r'>容量上限</th><th class='c'>最优状态</th></tr>{scope_compare_table}</table>
    <p class='note'>这里是 PlanMemory-style 的解析估计，用于过滤明显非法候选；它不是 compiler dry-run，也不能替代真实编译合法性验证。</p></div>

    <h2>6. Cost Breakdown 对比</h2>
    <div class='card'><table><tr><th>组成项</th><th class='r'>当前 IR 估计</th><th class='r'>最优候选</th><th class='r'>变化量</th></tr>{cost_compare_table}</table>
    <p class='note'>部分 cost 项经过 overlap、max 和 penalty 计算后得到，不应被理解为严格可加的真机耗时分解。</p></div>

    <h2>7. Top 候选排行与可视化</h2>
    {top_bars}
    <div class='card'><table><tr><th class='r'>#</th><th>Strategy ID</th><th class='r'>Predicted cycles</th><th class='c'>Risk</th><th class='c'>Tile</th><th class='c'>BlockDim</th><th class='c'>DB</th><th class='c'>CV</th><th class='c'>Sync</th><th class='r'>UB KB</th></tr>{''.join(top_rows)}</table></div>

    <h2>8. Scope 与结果解释</h2>
    <div class='card'><ul>{note_list}</ul></div>
    """
    (out / "strategy_search_report.html").write_text(_html_page("HIVM 四类 Plan 参数寻优报告", body), encoding="utf-8")


def write_markdown_report(out: Path, args: argparse.Namespace, kf: KernelFeatures, search_stats: Dict[str, Any], legal: List[Dict[str, Any]], rejected: List[Dict[str, Any]], relaxed: List[Dict[str, Any]], selected: Dict[str, Any], baseline: Dict[str, Any], speedup: float, top: List[Dict[str, Any]]) -> None:
    """生成中文 Markdown 报告，汇总 best strategy、当前 IR 对比、硬件约束和 cost breakdown。"""
    best = top[0]
    md: List[str] = []
    md.append("# HIVM 四类 Plan 参数寻优报告\n\n")
    md.append("本报告由 `auto_strategy_search.py` 生成。当前版本聚焦于 strategy-level 参数寻优：在 `TilingPlan`、`MultiBufferPlan`、`CVPipelinePlan` 和 `SyncPlan` 四类 Plan 上进行组合搜索，并在解析式硬件约束与 cost model 下选择 predicted cycles 最低的合法候选。\n\n")
    md.append("> 说明：本版本不执行 IR rewrite，不包含瓶颈诊断，也不扩展 discrete memory access 分析。报告中的 predicted cycles 是解析模型下的相对排序信号，不等价于真机实测耗时。\n\n")
    md.append("## 1. 输入信息\n")
    md.append(f"- Kernel：`{os.path.basename(args.kernel)}`\n")
    md.append(f"- 硬件配置：`{os.path.basename(args.hardware_config)}`\n")
    md.append(f"- 搜索空间：`{os.path.basename(args.search_space) if args.search_space else 'AUTO_GENERATED'}`\n")
    md.append(f"- 搜索模式：`{search_stats['search_mode']}`\n")
    md.append(f"- Cost risk mode：`{getattr(args, 'cost_risk_mode', 'conservative')}`\n")
    if getattr(args, "cost_model_config", None):
        md.append(f"- Cost model config：`{os.path.basename(args.cost_model_config)}`\n")
    if getattr(args, "guided_mode", "off") != "off":
        md.append(f"- Guided mode：`{args.guided_mode}`\n")
    md.append("\n")

    md.append("## 2. Kernel 静态特征\n")
    md.append(f"- 函数数量：{kf.num_functions}，AIC={kf.has_aic}，AIV={kf.has_aiv}\n")
    md.append(f"- 同步操作：pipe_barrier={kf.num_pipe_barrier}, set_flag={kf.num_set_flag}, wait_flag={kf.num_wait_flag}, sync_block_set={kf.num_sync_block_set}, sync_block_wait={kf.num_sync_block_wait}\n")
    md.append(f"- 计算/搬运操作：nd2nz={kf.num_nd2nz}, mma={kf.num_mmad}, fixpipe={kf.num_fixpipe}, load={kf.num_load}, store={kf.num_store}, vector_ops={sum(kf.vector_op_counts.values())}\n")
    md.append(f"- 解析出的 local buffer 数量：{len(kf.buffers)}\n")
    md.append(f"- 静态 max-live 近似：{ {k: round(v/1024, 2) for k, v in kf.static_max_live_bytes.items()} } KB\n")
    md.append(f"- 推断的问题规模：`{json.dumps(kf.inferred_problem_shape, ensure_ascii=False)}`\n\n")

    hcs = search_stats.get("hardware_constraints_summary", {})
    md.append("## 3. 候选生成与搜索摘要\n")
    if hcs:
        md.append(f"- 候选生成方式：`{hcs.get('block_dim_generation', 'unknown')}`\n")
        md.append(f"- block_dim 使用的最大可用 core 数：{hcs.get('max_available_cores')}\n")
        md.append(f"- 全局 block_dim 候选：`{hcs.get('global_block_dim_candidates')}`\n")
        if 'full_core_candidate_present' in hcs:
            md.append(f"- 是否存在 full-core 候选：`{hcs.get('full_core_candidate_present')}`\n")
        md.append(f"- 规则说明：{hcs.get('rule')}\n")
    md.append(f"- Layer-1 保留 cases：{search_stats['layer1_kept']}\n")
    md.append(f"- Layer-1 因 alignment/single-buffer capacity 被拒绝：{search_stats['layer1_rejected_count']}\n")
    md.append(f"- Layer-2 overlap allocations：{search_stats['layer2_allocations']}\n")
    md.append(f"- Layer-3 生成候选数：{search_stats['layer3_candidates']}\n")
    l1_audit = search_stats.get("layer1_stability_audit", {}) or {}
    dedup_audit = search_stats.get("candidate_dedup_audit", {}) or {}
    if l1_audit:
        md.append(f"- Stage2b L1 保留策略：`{l1_audit.get('policy')}`\n")
        md.append(f"- Stage2b pinned standard L1 survivors：{l1_audit.get('pinned_standard_after_topw_and_diversity', l1_audit.get('pinned_standard_after_topw', 0))}\n")
        md.append(f"- Stage2b diversity 新增 L1 cases：{l1_audit.get('diversity_added_after_topw', 0)}\n")
        md.append(f"- Stage2b fallback 新增 L1 cases：{l1_audit.get('fallback_added_after_topw_diversity_and_pins', 0)}\n")
    if dedup_audit:
        md.append(f"- Stage2b exact candidate 去重删除数：{dedup_audit.get('dedup_removed', 0)}\n")
    qa = search_stats.get("search_quality_audit", {}) or {}
    if qa.get("enabled"):
        gap = qa.get("beam_vs_small_exhaustive_gap_ratio")
        adv = qa.get("beam_advantage_over_random_ratio")
        md.append(f"- 搜索质量审计：enabled；Beam vs 小空间穷举 gap：{'N/A' if gap is None else f'{gap*100:.2f}%'}；Beam 相对随机基线优势：{'N/A' if adv is None else f'{adv*100:.2f}%'}\n")
    else:
        md.append("- 搜索质量审计：disabled（可用 `--enable-search-quality-audit` 开启小空间穷举/随机基线对照）\n")
    md.append(f"- Relax 后合法候选数：{len(legal)}\n")
    md.append(f"- Relax 后仍拒绝候选数：{len(rejected)}\n")
    md.append(f"- 通过 relax 变为可行的候选数：{len(relaxed)}\n\n")

    md.append("## 4. 寻优结果与优化前后对比\n")
    md.append(f"- 当前输入 IR 估计 predicted cycles：{baseline['cost']['predicted_cycles']:.2f}\n")
    md.append(f"- 最优候选 predicted cycles：{best['cost']['predicted_cycles']:.2f}\n")
    md.append(f"- 相对当前输入 IR 估计的预测加速比：{'N/A' if speedup is None else f'{speedup:.3f}x'}\n")
    md.append(f"- 最优候选风险等级：`{best['cost'].get('risk_level', best['cost'].get('risk_assessment', {}).get('risk_level', 'N/A'))}`，风险模式：`{best['cost'].get('cost_risk_mode', getattr(args, 'cost_risk_mode', 'conservative'))}`\n")
    saved = baseline['cost']['predicted_cycles'] - best['cost']['predicted_cycles']
    saved_pct = 0.0 if baseline['cost']['predicted_cycles'] == 0 else saved / baseline['cost']['predicted_cycles'] * 100.0
    if not baseline.get("feasible", True):
        md.append("- 注意：当前输入 IR 在解析硬件 gate 下不可行，因此 speedup 不作为有效指标；下方仅保留 cost 对照用于诊断。\n\n")
    else:
        md.append(f"- 解析模型下 predicted cycles 减少：{saved:.2f}，下降约 {saved_pct:.1f}%\n\n")
    md.append("### 4.1 核心指标对比\n")
    md.append("| 指标 | 当前 IR 估计 | 最优候选 | 变化量 |\n")
    md.append("|---|---:|---:|---:|\n")
    for key, label in [("predicted_cycles", "Predicted cycles"), ("n_tiles", "Tile 数量"), ("tile_time", "Tile time"), ("sync_cost", "同步 cost"), ("memory_pressure_penalty", "资源压力惩罚"), ("shape_regularization_penalty", "Shape 惩罚"), ("legality_risk_penalty", "合法性风险惩罚"), ("effective_parallelism", "有效并行度"), ("tail_efficiency", "Tail efficiency")]:
        a = _num_from_cost(baseline, key, 0.0)
        b = _num_from_cost(best, key, 0.0)
        if a == 0 and b == 0 and key not in ("sync_cost", "per_tile_workspace_exposed", "gm_workspace_bytes", "memory_pressure_penalty", "shape_regularization_penalty"):
            continue
        md.append(f"| {label} | {a:.4f} | {b:.4f} | {b-a:+.4f} |\n")
    md.append("\n> 说明：这里的“优化前”是 current-IR estimated strategy，“优化后”是 selected best strategy；当前版本不执行 IR rewrite。\n\n")

    md.append("### 4.2 最优候选策略\n")
    for k, v in best["strategy"].items():
        md.append(f"- `{k}`：`{v}`\n")
    md.append("\n### 4.2 模型选择该策略的原因\n")
    for r in selected["reason"]:
        md.append(f"- {r}\n")

    risk = best["cost"].get("risk_assessment", {})
    md.append("\n### 4.3 风险评估与收益来源归因\n")
    md.append(f"- Risk level：`{risk.get('risk_level', 'N/A')}`，Risk score：`{risk.get('risk_score', 'N/A')}`，Risk mode：`{risk.get('risk_mode', best['cost'].get('cost_risk_mode', 'N/A'))}`\n")
    for rr in risk.get("risk_reasons", [])[:8]:
        md.append(f"  - {rr}\n")
    attrib = best["cost"].get("improvement_attribution", {})
    pos = attrib.get("positive_cost_components_cycles", {}) if isinstance(attrib, dict) else {}
    adj = attrib.get("risk_adjustments_cycles", {}) if isinstance(attrib, dict) else {}
    if pos:
        md.append("\n| Cost / Risk 组成项 | cycles |\n")
        md.append("|---|---:|\n")
        for k, v in pos.items():
            md.append(f"| {k} | {float(v):.2f} |\n")
    if adj:
        md.append("\n| 风险调整项 | cycles |\n")
        md.append("|---|---:|\n")
        for k, v in adj.items():
            md.append(f"| {k} | {float(v):.2f} |\n")

    md.append("\n## 5. 分层算法覆盖范围\n")
    md.append("- L1 搜索 `TilingPlan`：在 alignment 与 single-buffer capacity 检查下搜索 tile shape。\n")
    md.append("- L2 搜索 `MultiBufferPlan` 与 template-bundled `CVPipelinePlan`：在估计容量压力下评估 double buffer / pipeline stage 等组合。\n")
    md.append("- L3 搜索 `SyncPlan`：在 keep-existing 与 GraphSyncSolver-style policy 之间做策略级选择。\n")
    md.append("- `selected_plan.json` 和 `top_plans.json` 保存四类 Plan 的可控参数、派生成本特征与合法性状态。\n")
    md.append("- `estimate_max_live()` 是当前 memory-capacity 模型：基于解析出的 local-buffer lifetimes 和 strategy-dependent tile/stage buffers 估计 PlanMemory-style max-live pressure。\n\n")

    md.append("## 6. 资源占用与 Cost Breakdown 对比\n")
    md.append("### 6.1 硬件资源占用对比\n")
    md.append("| Scope | 当前 IR 估计 KB | 最优候选 KB | 容量上限 KB |\n")
    md.append("|---|---:|---:|---:|\n")
    hw_local = load_json(args.hardware_config)
    for scope in RESOURCE_SCOPES:
        cap = memory_cap_bytes(hw_local, scope) / 1024
        a = baseline.get("max_live_bytes", {}).get(scope, 0) / 1024
        b = best.get("max_live_bytes", {}).get(scope, 0) / 1024
        md.append(f"| {scope.upper()} | {a:.2f} | {b:.2f} | {cap:.2f} |\n")
    md.append("\n### 6.2 Cost Breakdown 对比\n")
    md.append("| 组成项 | 当前 IR 估计 | 最优候选 | 变化量 |\n")
    md.append("|---|---:|---:|---:|\n")
    for key, label in [("parallelized_tile_cycles", "并行化 tile cycles"), ("per_tile_load_exposed", "每 tile 暴露 load"), ("per_tile_cube_vector_pipeline", "Cube/Vector pipeline"), ("per_tile_store_exposed", "每 tile 暴露 store"), ("per_tile_workspace_exposed", "每 tile 暴露 GM workspace"), ("gm_workspace_bytes", "GM workspace live bytes"), ("warmup_drain", "warmup / drain"), ("sync_cost", "同步 cost"), ("memory_pressure_penalty", "资源压力惩罚"), ("shape_regularization_penalty", "shape 惩罚"), ("legality_risk_penalty", "合法性风险惩罚")]:
        a = _num_from_cost(baseline, key, 0.0)
        b = _num_from_cost(best, key, 0.0)
        if a == 0 and b == 0 and key not in ("sync_cost", "per_tile_workspace_exposed", "gm_workspace_bytes", "memory_pressure_penalty", "shape_regularization_penalty"):
            continue
        md.append(f"| {label} | {a:.2f} | {b:.2f} | {b-a:+.2f} |\n")
    md.append("\n## 7. Top 候选排行\n")
    md.append("| Rank | Strategy ID | Predicted cycles | Risk | Tile | DB | CV stage | Sync | DMA | Reuse | maxLive UB KB |\n")
    md.append("|---:|---|---:|---|---|---|---:|---|---|---|---:|\n")
    for i, item in enumerate(top[:10], 1):
        s = item["strategy"]
        md.append(f"| {i} | {s['strategy_id']} | {item['cost']['predicted_cycles']:.2f} | {item['cost'].get('risk_level', item['cost'].get('risk_assessment', {}).get('risk_level', 'N/A'))} | ({s['tile_m']},{s['tile_n']},{s['tile_k']}) | {s['double_buffer']} | {s['cv_pipeline_stage']} | {s['sync_policy']} | {s['dma_policy']} | {s['memory_reuse_level']} | {item['max_live_bytes']['ub']/1024:.2f} |\n")

    md.append("\n## 8. Scope 与解释边界\n")
    md.append("- 当前版本是参数搜索实现：它把 HIVM 行为抽象为四类可搜索 Plan，并在合法候选上最小化解析 cost model。\n")
    md.append("- 当前独立仓库通过 IR parsing 与硬件规则解析得到 Plan 字段；真实 compiler pass dumps 不是运行必需项，但如果可获得，将是更强的数据来源。\n")
    md.append("- 当前 estimated capacity / alignment / tiling / pipeline gate 覆盖了主要硬件边界；SyncPlan 只提供策略级同步建模，不提供形式化 deadlock proof。\n")
    md.append("- 第一阶段 risk-aware 改造后，UNKNOWN GraphSyncSolver 和 PASS_ESTIMATED CVPipeline 不再默认拿满收益；报告同时输出 risk_level 和 legality_risk_penalty。\n")
    md.append("- 本版本不做 IR rewrite；如需证明策略可以真实落地，还需要后续接入 IR rewrite、compiler dry-run 与真机 profiling。\n")
    (out / "strategy_search_report.md").write_text("".join(md), encoding="utf-8")


# ------------------------------ main run ------------------------------

