# -*- coding: utf-8 -*-
"""Strategy-to-IR annotation and vTriton sidecar bundle emission."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def write_json(path: Path, data: Any) -> None:
    """Write JSON with stable UTF-8 formatting."""
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _split_paths(value: Optional[str]) -> List[str]:
    """解析 CLI 中逗号分隔的可选文件路径参数。"""
    if not value:
        return []
    parts: List[str] = []
    for chunk in str(value).split(","):
        chunk = chunk.strip()
        if chunk:
            parts.append(chunk)
    return parts




# ---------------------------------------------------------------------------
# V3.0: vTriton 嫁接与 Strategy-to-HIVM rewrite
# ---------------------------------------------------------------------------
# 设计目标：
#   1) 把 selected_strategy 从 JSON 建议，映射回 HIVM/NPUIR MLIR；
#   2) 生成 vTriton 可消费的 candidate bundle；
#   3) 保持 rewrite 保守可审计：默认 annotation-level，safe_structural 只做局部安全属性改写；
#   4) 不冒充真实 compiler lowering：真正 compile/verify/delta 交给 vTriton counterfactual harness。


def _mlir_literal(v: Any) -> str:
    """把 Python 值转换成 MLIR attribute 字面量。"""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return f"{v} : i64"
    if isinstance(v, float):
        return f"{v:.6g} : f64"
    text = str(v).replace('"', '\\"')
    return f'"{text}"'


def _split_mlir_attrs(attr_body: str) -> List[str]:
    """按逗号粗分 MLIR attribute；只用于本 demo 的简单 flat attribute 块。"""
    parts: List[str] = []
    cur: List[str] = []
    depth = 0
    in_str = False
    esc = False
    for ch in attr_body:
        if in_str:
            cur.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            cur.append(ch)
            continue
        if ch in "[{(<":
            depth += 1
        elif ch in "]})>":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            item = "".join(cur).strip()
            if item:
                parts.append(item)
            cur = []
        else:
            cur.append(ch)
    item = "".join(cur).strip()
    if item:
        parts.append(item)
    return parts


def _merge_attr_body(attr_body: str, updates: Dict[str, Any]) -> str:
    """在 flat MLIR attribute body 中更新/追加 key=value。"""
    seen = set()
    out: List[str] = []
    for part in _split_mlir_attrs(attr_body):
        key = part.split("=", 1)[0].strip() if "=" in part else part.strip()
        if key in updates:
            out.append(f"{key} = {_mlir_literal(updates[key])}")
            seen.add(key)
        else:
            out.append(part)
    for key, val in updates.items():
        if key not in seen:
            out.append(f"{key} = {_mlir_literal(val)}")
    return ", ".join(out)


def _update_or_add_module_attrs(ir_text: str, updates: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    """更新 module attributes；不存在时创建一个 attributes 块。"""
    changes: List[Dict[str, Any]] = []
    m = re.search(r"module\s+attributes\s*\{([^}]*)\}", ir_text, flags=re.S)
    if m:
        before = m.group(1)
        after = _merge_attr_body(before, updates)
        for k, v in updates.items():
            changes.append({"type": "module_attr", "key": k, "after": v})
        return ir_text[:m.start(1)] + after + ir_text[m.end(1):], changes
    m2 = re.search(r"\bmodule\b", ir_text)
    if m2:
        attr = ", ".join(f"{k} = {_mlir_literal(v)}" for k, v in updates.items())
        for k, v in updates.items():
            changes.append({"type": "module_attr", "key": k, "after": v})
        return ir_text[:m2.end()] + f" attributes {{{attr}}}" + ir_text[m2.end():], changes
    # 极少数测试文本可能没有 module；保守地在头部写注释，不改变语法主体。
    header = "\n".join(f"// [auto_strategy module_attr] {k} = {v}" for k, v in updates.items()) + "\n"
    for k, v in updates.items():
        changes.append({"type": "module_attr_comment", "key": k, "after": v})
    return header + ir_text, changes


def _inject_func_strategy_attrs(ir_text: str, updates: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    """给第一个 func.func 的 attributes 块注入 hivm.strategy.*；没有 attributes 时采用保守注释。"""
    changes: List[Dict[str, Any]] = []
    # 常见形态：func.func @name(...) attributes { ... } {
    pat = re.compile(r"(func\.func\s+@\w+[\s\S]*?\)\s*attributes\s*\{)([^}]*)\}", re.S)
    m = pat.search(ir_text)
    if m:
        before = m.group(2)
        after = _merge_attr_body(before, updates)
        for k, v in updates.items():
            changes.append({"type": "func_attr", "key": k, "after": v})
        return ir_text[:m.start(2)] + after + ir_text[m.end(2):], changes
    # 常见形态：func.func @name(多行参数) {，没有 attributes。插入 attributes { ... }。
    pat_no_attr = re.compile(r"(func\.func\s+@\w+[\s\S]*?\)\s*)\{", re.S)
    m2 = pat_no_attr.search(ir_text)
    if m2:
        body = ", ".join(f"{k} = {_mlir_literal(v)}" for k, v in updates.items())
        for k, v in updates.items():
            changes.append({"type": "func_attr", "key": k, "after": v, "insertion": "created_attributes_block"})
        return ir_text[:m2.end(1)] + f"attributes {{{body}}} " + ir_text[m2.end(1):], changes
    # 极端退化处理：把策略作为函数前注释，保证不破坏语法。
    m3 = re.search(r"func\.func\s+@\w+", ir_text)
    comment = "\n".join(f"  // [auto_strategy func_attr] {k} = {v}" for k, v in updates.items()) + "\n"
    for k, v in updates.items():
        changes.append({"type": "func_attr_comment", "key": k, "after": v})
    if m3:
        return ir_text[:m3.start()] + comment + ir_text[m3.start():], changes
    return comment + ir_text, changes


def _eligible_multibuffer_name(name: str) -> bool:
    lname = name.lower()
    if any(k in lname for k in ["acc", "persist", "l0c", "out", "dst", "sum"]):
        return False
    return True


def _add_alloc_attr_to_line(line: str, attrs: Dict[str, Any]) -> str:
    """给 memref.alloc 行添加/合并属性，保持单行文本级改写。"""
    if "memref.alloc" not in line:
        return line
    attr_text = ", ".join(f"{k} = {_mlir_literal(v)}" for k, v in attrs.items())
    # 已有 alloc() { ... } :
    m = re.search(r"(memref\.alloc\([^)]*\)\s*)\{([^}]*)\}", line)
    if m:
        body = _merge_attr_body(m.group(2), attrs)
        return line[:m.start(2)] + body + line[m.end(2):]
    # 没有 attr，插入到冒号前
    idx = line.find(":")
    if idx >= 0:
        return line[:idx].rstrip() + f" {{{attr_text}}} " + line[idx:]
    return line.rstrip() + f" {{{attr_text}}}"


def _apply_safe_multibuffer_rewrite(ir_text: str, strategy: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    """保守地给可识别 UB/L1 stream buffer 增加 multi_buffer hint。"""
    changes: List[Dict[str, Any]] = []
    if not strategy.get("double_buffer"):
        return ir_text, changes
    try:
        per_buf = json.loads(strategy.get("buffer_multipliers_json", "{}") or "{}")
    except Exception:
        per_buf = {}
    # 如果搜索结果没有显式 nbuf=2，就只保留全局 hint，不强行改 buffer，避免假优化。
    explicit_two = {str(k): int(v) for k, v in per_buf.items() if int(_num(v, 1)) >= 2}
    lines: List[str] = []
    for line in ir_text.splitlines():
        new_line = line
        m = re.search(r"%([\w.$-]+)\s*=\s*memref\.alloc", line)
        sm = re.search(r"#hivm\.address_space<([\w]+)>", line)
        role = None
        rm = re.search(r'hivm\.role\s*=\s*"(\w+)"', line)
        if rm:
            role = rm.group(1).lower()
        if m and sm:
            name = m.group(1)
            scope = _norm_space(sm.group(1))
            nbuf = explicit_two.get(name, 1)
            # 只做显式 per-buffer nbuf=2，或者 role=stream/cv 且全局 ub/l1 multiplier>1。
            global_mult = int(strategy.get("ub_multiplier", 1) if scope == "ub" else strategy.get("l1_multiplier", 1) if scope == "l1" else 1)
            should = (
                scope in {"ub", "l1"}
                and _eligible_multibuffer_name(name)
                and (nbuf >= 2 or (global_mult >= 2 and role in {"stream", "cv"}))
            )
            if should and "multi_buffer" not in line and "hivm.nbuf" not in line:
                n = max(2, nbuf, global_mult)
                new_line = _add_alloc_attr_to_line(line, {"multi_buffer": n, "hivm.nbuf": n})
                changes.append({"type": "buffer_attr", "buffer": name, "scope": scope, "change": f"add multi_buffer={n}"})
        lines.append(new_line)
    return "\n".join(lines) + ("\n" if ir_text.endswith("\n") else ""), changes


def _safe_barrier_notes(ir_text: str, strategy: Dict[str, Any], safety: str) -> Tuple[str, List[Dict[str, Any]]]:
    """默认只标注 barrier；aggressive 才删除 pipe_barrier。"""
    changes: List[Dict[str, Any]] = []
    if strategy.get("sync_policy") != "graph_sync_solver":
        return ir_text, changes
    lines: List[str] = []
    for line in ir_text.splitlines():
        is_barrier = ("pipe_barrier" in line) or ("hivm.hir.barrier" in line) or ("hivm.barrier" in line)
        if is_barrier and safety == "aggressive":
            lines.append("      // [auto_strategy removed] barrier removed under graph_sync_solver aggressive mode")
            changes.append({"type": "sync_rewrite", "change": "remove barrier", "safety": safety})
        elif is_barrier:
            lines.append("      // [auto_strategy hint] GraphSyncSolver may remove or move this barrier after dependency legality check")
            lines.append(line)
            changes.append({"type": "sync_hint", "change": "annotate barrier", "safety": safety})
        else:
            lines.append(line)
    return "\n".join(lines) + ("\n" if ir_text.endswith("\n") else ""), changes


def build_strategy_attrs(strategy: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """从 selected strategy 中构建 module/func 属性。"""
    module_attrs = {
        "hivm.sync": "graph_sync_solver" if strategy.get("sync_policy") == "graph_sync_solver" else strategy.get("sync_policy", "inject"),
        "hivm.strategy.source": "auto_strategy_search_v3",
        "hivm.strategy.version": "V3.3-artifact-kernel-profile",
    }
    keys = [
        "strategy_id", "tile_m", "tile_n", "tile_k", "block_dim", "double_buffer",
        "cv_pipeline_stage", "stage_buffer_policy", "sync_policy", "reduce_tile_policy",
        "loop_order", "tail_strategy", "layout_aware_tile", "ub_multiplier", "l1_multiplier",
        "producer_consumer_distance", "event_id_policy", "sync_motion", "buffer_multipliers_json",
    ]
    func_attrs = {f"hivm.strategy.{k}": strategy.get(k) for k in keys if k in strategy}
    return module_attrs, func_attrs


def build_pass_pipeline_config(strategy: Dict[str, Any], selected: Dict[str, Any]) -> Dict[str, Any]:
    """生成给 vTriton/真实 compiler pass 的策略配置，不直接声称已执行 pass。"""
    try:
        per_buf = json.loads(strategy.get("buffer_multipliers_json", "{}") or "{}")
    except Exception:
        per_buf = {}
    return {
        "schema_version": "hivm_pass_pipeline_config_v1",
        "producer": "strategy_search_demo_v3.0",
        "strategy_id": strategy.get("strategy_id"),
        "note": "This is a requested pass configuration / hint bundle. It is not proof that compiler passes were executed.",
        "passes": [
            {
                "name": "TileLoop",
                "enabled": True,
                "options": {
                    "tile_m": strategy.get("tile_m"),
                    "tile_n": strategy.get("tile_n"),
                    "tile_k": strategy.get("tile_k"),
                    "block_dim": strategy.get("block_dim"),
                    "loop_order": strategy.get("loop_order"),
                    "tail_strategy": strategy.get("tail_strategy"),
                    "reduce_tile_policy": strategy.get("reduce_tile_policy"),
                    "layout_aware_tile": strategy.get("layout_aware_tile"),
                },
                "execution_status": "not_executed_by_demo",
            },
            {
                "name": "MarkMultiBuffer",
                "enabled": bool(strategy.get("double_buffer")),
                "options": {
                    "double_buffer": strategy.get("double_buffer"),
                    "ub_multiplier": strategy.get("ub_multiplier"),
                    "l1_multiplier": strategy.get("l1_multiplier"),
                    "buffer_multipliers": per_buf,
                },
                "execution_status": "not_executed_by_demo",
            },
            {
                "name": "CVPipelining",
                "enabled": int(strategy.get("cv_pipeline_stage", 1) or 1) > 1,
                "options": {
                    "stage": strategy.get("cv_pipeline_stage"),
                    "template": strategy.get("cv_pipeline_template"),
                    "stage_buffer_policy": strategy.get("stage_buffer_policy"),
                    "producer_consumer_distance": strategy.get("producer_consumer_distance"),
                    "enable_mixed_cv": strategy.get("enable_mixed_cv"),
                },
                "execution_status": "not_executed_by_demo",
            },
            {
                "name": "GraphSyncSolver",
                "enabled": strategy.get("sync_policy") == "graph_sync_solver",
                "options": {
                    "sync_policy": strategy.get("sync_policy"),
                    "event_reuse": strategy.get("event_reuse"),
                    "event_id_policy": strategy.get("event_id_policy"),
                    "sync_granularity": strategy.get("sync_granularity"),
                    "sync_motion": strategy.get("sync_motion"),
                    "barrier_level": strategy.get("barrier_level"),
                },
                "execution_status": "not_executed_by_demo",
            },
            {
                "name": "PlanMemory",
                "enabled": True,
                "options": {
                    "check_spaces": RESOURCE_SCOPES,
                    "selected_max_live_bytes": selected.get("max_live_bytes", {}),
                    "gm_workspace_policy": strategy.get("stage_buffer_policy"),
                },
                "execution_status": "analytically_checked_by_demo",
            },
        ],
    }


def build_strategy_edit_script(strategy: Dict[str, Any], selected: Dict[str, Any], mode: str, safety: str) -> Dict[str, Any]:
    """生成 vTriton edit primitives 可借鉴的 edit script。"""
    module_attrs, func_attrs = build_strategy_attrs(strategy)
    edits: List[Dict[str, Any]] = []
    for k, v in module_attrs.items():
        edits.append({"type": "set_module_attr", "key": k, "value": v})
    for k, v in func_attrs.items():
        edits.append({"type": "set_func_attr", "target": "first_func", "key": k, "value": v})
    try:
        per_buf = json.loads(strategy.get("buffer_multipliers_json", "{}") or "{}")
    except Exception:
        per_buf = {}
    for name, mult in per_buf.items():
        if int(_num(mult, 1)) >= 2:
            edits.append({"type": "add_buffer_attr", "match": {"name": name, "address_space": ["ub", "l1"]}, "attrs": {"multi_buffer": int(mult), "hivm.nbuf": int(mult)}})
    if strategy.get("sync_policy") == "graph_sync_solver":
        edits.append({"type": "sync_hint", "action": "prefer_graph_sync_solver", "remove_barrier_all": safety == "aggressive"})
    return {
        "schema_version": "hivm_strategy_edit_v1",
        "producer": "strategy_search_demo_v3.0",
        "strategy_id": strategy.get("strategy_id"),
        "rewrite_mode": mode,
        "rewrite_safety": safety,
        "edits": edits,
        "guards": [
            {"type": "reparse_check", "required": True},
            {"type": "extract_reversibility_check", "required": True},
            {"type": "max_live_check", "spaces": RESOURCE_SCOPES, "selected_max_live_bytes": selected.get("max_live_bytes", {})},
            {"type": "des_after_check", "tool": "tritonsim-hivm", "required_for_verified_speedup": True},
            {"type": "output_correctness_check", "required_for_aggressive_rewrite": True},
        ],
    }


def build_vtriton_candidate_bundle(
    out: Path,
    args: argparse.Namespace,
    original_ir_path: str,
    annotated_path: Optional[str],
    structural_path: Optional[str],
    strategy: Dict[str, Any],
    selected: Dict[str, Any],
    des_paths: List[str],
    trace_paths: List[str],
) -> Dict[str, Any]:
    """生成 vTriton 可回放/验证的 candidate bundle 清单和建议命令。"""
    candidate_dir = out / "vtriton_candidate_bundle"
    candidate_dir.mkdir(exist_ok=True)
    # 复制关键 sidecars，方便独立交给 vTriton。
    for fname in ["selected_strategy.json", "selected_plan.json", "pass_pipeline_config.json", "strategy_edit_script.json", "rewrite_audit.md", "rewrite_diff_report.json"]:
        src = out / fname
        if src.exists():
            (candidate_dir / fname).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    target_ir = structural_path or annotated_path or original_ir_path
    cmd_after = None
    if target_ir:
        cmd_after = (
            "tritonsim-hivm --npuir-file " + str(target_ir) +
            " --scheduler des --des-graph-file " + str(candidate_dir / "des_after.json") +
            " --perfetto-trace-file " + str(candidate_dir / "trace_after.json")
        )
    bundle = {
        "schema_version": "vtriton_strategy_candidate_bundle_v1",
        "producer": "strategy_search_demo_v3.0",
        "strategy_id": strategy.get("strategy_id"),
        "original_ir": str(Path(original_ir_path).resolve()),
        "annotated_ir": str(Path(annotated_path).resolve()) if annotated_path else None,
        "safe_structural_ir": str(Path(structural_path).resolve()) if structural_path else None,
        "selected_strategy_json": str((out / "selected_strategy.json").resolve()),
        "pass_pipeline_config_json": str((out / "pass_pipeline_config.json").resolve()) if (out / "pass_pipeline_config.json").exists() else None,
        "strategy_edit_script_json": str((out / "strategy_edit_script.json").resolve()) if (out / "strategy_edit_script.json").exists() else None,
        "vtriton_inputs_consumed": {
            "des_graph_files": des_paths,
            "trace_files": trace_paths,
            "bound_report": _split_paths(getattr(args, "bound_report", None)),
            "counterfactual": _split_paths(getattr(args, "counterfactual", None)),
            "bindings_jsonl": _split_paths(getattr(args, "vtriton_bindings", None)),
            "compile_commands_jsonl": _split_paths(getattr(args, "vtriton_compile_commands", None)),
        },
        "suggested_vtriton_commands": {
            "analyze_after_ir": cmd_after,
            "note": "Run this command inside a vTriton build/runtime where tritonsim-hivm is available. Hardware compile/profile validation is outside this demo container.",
        },
        "expected_delta": {
            "predicted_cycles_after": selected.get("cost", {}).get("predicted_cycles"),
            "predicted_speedup_vs_current_ir_estimated": selected.get("predicted_speedup_vs_current_ir_estimated"),
        },
        "verification_status": "not_run_in_demo",
    }
    write_json(out / "vtriton_candidate_bundle.json", bundle)
    write_json(candidate_dir / "bundle_manifest.json", bundle)
    return bundle


def emit_strategy_rewrite_outputs(
    out: Path,
    args: argparse.Namespace,
    selected: Dict[str, Any],
    des_paths: List[str],
    trace_paths: List[str],
) -> None:
    """根据 selected_strategy 生成 annotated/safe_structural HIVM、pass config、edit script 和 vTriton bundle。"""
    if not getattr(args, "enable_ir_rewrite", False):
        return
    strategy = selected.get("strategy", {})
    if not strategy:
        return
    ir_text = Path(args.kernel).read_text(encoding="utf-8")
    mode = getattr(args, "rewrite_mode", "annotation")
    safety = getattr(args, "rewrite_safety", "conservative")
    all_changes: List[Dict[str, Any]] = []

    module_attrs, func_attrs = build_strategy_attrs(strategy)
    annotated, ch = _update_or_add_module_attrs(ir_text, module_attrs)
    all_changes.extend(ch)
    annotated, ch = _inject_func_strategy_attrs(annotated, func_attrs)
    all_changes.extend(ch)
    annotated_header = (
        "// >>> auto_strategy_search V3.0 annotated HIVM/NPUIR\n"
        "// This file carries strategy hints. It is not proof that backend compiler passes were executed.\n"
    )
    annotated = annotated_header + annotated
    annotated_path = out / "optimized.annotated.hivm.mlir"
    annotated_path.write_text(annotated, encoding="utf-8")

    structural_path: Optional[Path] = None
    structural_changes: List[Dict[str, Any]] = []
    if mode in {"safe_structural", "both"}:
        structural = annotated
        structural, ch = _apply_safe_multibuffer_rewrite(structural, strategy)
        structural_changes.extend(ch)
        structural, ch = _safe_barrier_notes(structural, strategy, safety)
        structural_changes.extend(ch)
        structural_header = (
            "// >>> auto_strategy_search V3.0 safe structural HIVM/NPUIR\n"
            "// Conservative local rewrite only: module sync attrs + explicit safe buffer hints.\n"
            "// Not full tiling/CV lowering; vTriton/real compiler verification is required.\n"
        )
        structural = structural_header + structural
        structural_path = out / "optimized.safe_structural.hivm.mlir"
        structural_path.write_text(structural, encoding="utf-8")

    pass_cfg = build_pass_pipeline_config(strategy, selected)
    write_json(out / "pass_pipeline_config.json", pass_cfg)
    edit_script = build_strategy_edit_script(strategy, selected, mode, safety)
    write_json(out / "strategy_edit_script.json", edit_script)

    diff = {
        "schema_version": "hivm_rewrite_diff_v1",
        "producer": "strategy_search_demo_v3.0",
        "strategy_id": strategy.get("strategy_id"),
        "rewrite_mode": mode,
        "rewrite_safety": safety,
        "annotated_ir": str(annotated_path),
        "safe_structural_ir": str(structural_path) if structural_path else None,
        "changes": all_changes + structural_changes,
        "structural_change": bool(structural_changes),
        "limitations": [
            "Tiling loop nest is not structurally rewritten in V3.0.",
            "CVPipeline cube_loop/vector_loop is not structurally rewritten unless future pattern pass is added.",
            "GM workspace alloc/load/store spill lowering is not generated by this demo.",
            "Compiler-pass-level optimized IR must be produced/validated by vTriton or a real AscendNPU compiler pass pipeline.",
        ],
    }
    write_json(out / "rewrite_diff_report.json", diff)
    audit = []
    audit.append("# V3.0 Strategy-to-HIVM Rewrite Audit\n")
    audit.append(f"- Strategy: `{strategy.get('strategy_id')}`\n")
    audit.append(f"- Rewrite mode: `{mode}`\n")
    audit.append(f"- Safety: `{safety}`\n")
    audit.append(f"- Annotated IR: `{annotated_path.name}`\n")
    if structural_path:
        audit.append(f"- Safe structural IR: `{structural_path.name}`\n")
    audit.append("\n## What was changed\n")
    for c in diff["changes"]:
        audit.append(f"- `{c.get('type')}`: {c}\n")
    audit.append("\n## What was intentionally not changed\n")
    for x in diff["limitations"]:
        audit.append(f"- {x}\n")
    audit.append("\n## vTriton validation expectation\n")
    audit.append("Run `tritonsim-hivm` on the emitted IR to generate DES/trace-after, then use vTriton counterfactual/compile/verify/delta harness for authoritative validation.\n")
    (out / "rewrite_audit.md").write_text("".join(audit), encoding="utf-8")

    bundle = build_vtriton_candidate_bundle(
        out=out,
        args=args,
        original_ir_path=args.kernel,
        annotated_path=str(annotated_path),
        structural_path=str(structural_path) if structural_path else None,
        strategy=strategy,
        selected=selected,
        des_paths=des_paths,
        trace_paths=trace_paths,
    )
    write_json(out / "vtriton_integration_report.json", {
        "schema_version": "vtriton_integration_report_v1",
        "producer": "strategy_search_demo_v3.0",
        "status": "bridge_outputs_emitted",
        "vtriton_can_provide": [
            "NPUIR/HIVM dump from Triton DSL or existing MLIR",
            "DES graph with pipe/dependency evidence",
            "Perfetto trace timeline",
            "bound report and attribution",
            "counterfactual edit/compile/verify/delta when configured with a working vTriton build and target hardware",
        ],
        "demo_currently_consumed_inputs": {
            "des_graph_files": des_paths,
            "trace_files": trace_paths,
            "bound_report_files": _split_paths(getattr(args, "bound_report", None)),
            "counterfactual_files": _split_paths(getattr(args, "counterfactual", None)),
        },
        "bundle": bundle,
    })

