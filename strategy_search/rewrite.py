# -*- coding: utf-8 -*-
"""Strategy-to-IR annotation, safe structural hint rewrite, and vTriton sidecar bundle emission."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .plans import RESOURCE_SCOPES, SPACE_ALIAS
from .structural_rewrite import (
    apply_structural_rewrite,
    build_backend_execution_plan,
    build_structural_rewrite_report,
    try_run_external_strategy_rewriter,
    try_run_external_vtriton_hivm_crud,
    try_run_tritonsim_validation,
    validate_python_structural_result,
    build_structural_validation_summary,
    build_vtriton_adapter_manifest,
    build_phase2_closure_report,
)
from .structural_legality import build_structural_legality_report
from .structural_edit_schema import structural_edit_schema, validate_structural_edit_script
from .phase3_analysis import (
    emit_phase3a_analysis_outputs,
    emit_phase3b_analysis_outputs,
    emit_phase3c_analysis_outputs,
    emit_phase3d_analysis_outputs,
    emit_phase3e_validation_outputs,
    emit_phase3f_closure_outputs,
)
from .phase4_analysis import emit_phase4a_outputs, emit_phase4b_outputs, emit_phase4c_outputs, emit_phase4d_outputs, emit_phase4e_outputs
from .phase5_analysis import emit_phase5a_outputs, emit_phase5b_outputs, emit_phase5c_outputs, emit_phase5d_outputs, emit_phase5e_outputs, emit_phase5f_outputs
from .phase6_analysis import emit_phase6a_outputs, emit_phase6b_outputs, emit_phase6c_outputs, emit_phase6d_outputs, emit_phase6e_outputs, emit_phase6f_outputs


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

def _num(x: Any, default: float = 0.0) -> float:
    """Best-effort numeric conversion used by rewrite-side guards.

    The rewrite module intentionally stays text-level and conservative. This
    helper prevents malformed optional profile fields from crashing sidecar
    generation; invalid values are treated as the supplied default.
    """
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def _norm_space(space: Any) -> str:
    """Normalize common HIVM/Ascend memory-space aliases.

    Examples: CBUF -> l1, CC -> l0c, HBM -> gm. Unknown spaces are returned
    lower-cased so the caller can safely decide whether to act on them.
    """
    text = str(space).lower()
    return SPACE_ALIAS.get(text, text)


def _looks_like_diagnostic_prefix(ir_text: str, pos: int) -> bool:
    """Return True if a matched 'module attributes' appears in diagnostic text.

    Some dumped NPUIR files contain lines such as
    'warning: overriding the module attributes ...' before the real IR. A blind
    regex replacement would corrupt that diagnostic line.
    """
    line_start = ir_text.rfind("\n", 0, pos) + 1
    prefix = ir_text[line_start:pos].strip().lower()
    return prefix.startswith(("warning:", "error:", "note:", "remark:"))


def _find_real_module_attrs(ir_text: str) -> Optional[re.Match[str]]:
    """Find the first real MLIR 'module attributes { ... }' block.

    The match is line-anchored so it avoids most diagnostic prose.
    """
    pat = re.compile(r"(?m)^(?P<indent>\s*)module\s+attributes\s*\{(?P<body>[^}]*)\}", re.S)
    for m in pat.finditer(ir_text):
        if not _looks_like_diagnostic_prefix(ir_text, m.start()):
            return m
    return None


def _find_real_module_keyword(ir_text: str) -> Optional[re.Match[str]]:
    """Find a real MLIR module keyword that can safely receive attributes."""
    pat = re.compile(r"(?m)^\s*module\b(?!\s+attributes)")
    for m in pat.finditer(ir_text):
        if not _looks_like_diagnostic_prefix(ir_text, m.start()):
            return m
    return None




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
    """Safely update real module attributes.

    If the input does not contain a trustworthy top-level module anchor, we do
    not force a syntactic rewrite. Step-1 annotation must never break IR. In
    that fallback case, module-level strategy data remains available in the
    sidecar JSON files and a header comment is emitted only for human audit.
    """
    changes: List[Dict[str, Any]] = []
    m = _find_real_module_attrs(ir_text)
    if m:
        before = m.group("body")
        after = _merge_attr_body(before, updates)
        for k, v in updates.items():
            changes.append({"type": "module_attr", "key": k, "after": v})
        return ir_text[:m.start("body")] + after + ir_text[m.end("body"):], changes

    m2 = _find_real_module_keyword(ir_text)
    if m2:
        attr = ", ".join(f"{k} = {_mlir_literal(v)}" for k, v in updates.items())
        for k, v in updates.items():
            changes.append({"type": "module_attr", "key": k, "after": v, "insertion": "created_attributes_block"})
        return ir_text[:m2.end()] + f" attributes {{{attr}}}" + ir_text[m2.end():], changes

    header = "\n".join(f"// [auto_strategy module_attr_fallback] {k} = {v}" for k, v in updates.items()) + "\n"
    for k, v in updates.items():
        changes.append({"type": "module_attr_fallback_comment", "key": k, "after": v, "reason": "no_safe_module_anchor_found"})
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
    """Return whether a buffer name is safe to receive a multi-buffer hint.

    Step-2 deliberately avoids accumulator/output/persistent buffers because
    adding ping-pong style hints there can imply a different live range or
    reduction semantics.
    """
    lname = name.lower()
    if any(k in lname for k in ["acc", "persist", "l0c", "out", "dst", "sum"]):
        return False
    return True


def _stream_like_buffer_name(name: str) -> bool:
    """Heuristic used only outside conservative mode.

    Balanced/aggressive Step-2 can expose more visible local hints for common
    FlashAttention-style stream buffers. Conservative mode never relies on this
    heuristic; it requires explicit per-buffer nbuf>=2 evidence.
    """
    lname = name.lower()
    return any(tok in lname for tok in ["q_", "k_", "v_", "q.", "k.", "v.", "q$", "k$", "v$", "query", "key", "value"])


def _parse_buffer_multipliers(strategy: Dict[str, Any]) -> Dict[str, int]:
    """Parse selected strategy buffer multipliers into normalized integers."""
    raw = strategy.get("buffer_multipliers_json", "{}") or "{}"
    try:
        obj = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except Exception:
        obj = {}
    out: Dict[str, int] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out[str(k)] = max(1, int(_num(v, 1)))
    return out


def _extract_alloc_inventory(ir_text: str) -> List[Dict[str, Any]]:
    """Collect single-line memref.alloc inventory for Step-2 capability/audit.

    The demo rewrite remains text-level and conservative. It acts only on
    single-line allocs whose HIVM address space is visible on that same line.
    """
    inv: List[Dict[str, Any]] = []
    for lineno, line in enumerate(ir_text.splitlines(), 1):
        m = re.search(r"%([\w.$-]+)\s*=\s*memref\.alloc", line)
        sm = re.search(r"#hivm\.address_space<([\w]+)>", line)
        if not (m and sm):
            continue
        name = m.group(1)
        scope = _norm_space(sm.group(1))
        inv.append({
            "line": lineno,
            "name": name,
            "scope": scope,
            "eligible_name": _eligible_multibuffer_name(name),
            "stream_like_name": _stream_like_buffer_name(name),
            "already_has_multibuffer": ("multi_buffer" in line or "hivm.nbuf" in line),
            "text": line.strip(),
        })
    return inv


def _tile_attr_updates(strategy: Dict[str, Any]) -> Dict[str, Any]:
    """Return tile attributes that Step-2 is allowed to replace if anchors exist."""
    keys = ["tile_m", "tile_n", "tile_k", "block_dim"]
    out: Dict[str, Any] = {}
    for k in keys:
        if k in strategy and strategy.get(k) is not None:
            out[k] = strategy.get(k)
    return out


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


def _apply_safe_multibuffer_rewrite(ir_text: str, strategy: Dict[str, Any], safety: str = "conservative") -> Tuple[str, List[Dict[str, Any]]]:
    """Step-2: conservatively add alloc-level multi-buffer hints.

    This function does NOT create ping/pong buffers, move load/store ops, or
    change execution order. It only attaches machine-readable hints to existing
    UB/L1 ``memref.alloc`` anchors.

    Safety modes:
    - conservative: require explicit ``buffer_multipliers_json[name] >= 2``;
    - balanced: also allow common q/k/v stream-like UB/L1 buffers when
      ``double_buffer=true``;
    - aggressive: also allow any eligible UB/L1 buffer when ``double_buffer`` or
      global UB/L1 multiplier suggests multi-buffering. Still no op motion.
    """
    changes: List[Dict[str, Any]] = []
    if not strategy.get("double_buffer"):
        return ir_text, changes

    safety = str(safety or "conservative").lower()
    per_buf = _parse_buffer_multipliers(strategy)
    explicit_two = {name: mult for name, mult in per_buf.items() if mult >= 2}

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
            global_mult = int(_num(strategy.get("ub_multiplier", 1) if scope == "ub" else strategy.get("l1_multiplier", 1) if scope == "l1" else 1, 1))
            nbuf = explicit_two.get(name, 1)
            reason = None
            if scope in {"ub", "l1"} and _eligible_multibuffer_name(name) and "multi_buffer" not in line and "hivm.nbuf" not in line:
                if nbuf >= 2:
                    reason = "explicit_buffer_multipliers_json"
                elif global_mult >= 2 and role in {"stream", "cv"}:
                    nbuf = max(2, global_mult)
                    reason = "role_and_global_multiplier"
                elif safety in {"balanced", "aggressive"} and strategy.get("double_buffer") and _stream_like_buffer_name(name):
                    nbuf = 2
                    reason = f"{safety}_stream_name_heuristic"
                elif safety == "aggressive" and (strategy.get("double_buffer") or global_mult >= 2):
                    nbuf = max(2, global_mult)
                    reason = "aggressive_eligible_buffer_heuristic"
            if reason:
                n = max(2, int(nbuf))
                new_line = _add_alloc_attr_to_line(line, {"multi_buffer": n, "hivm.nbuf": n})
                changes.append({
                    "type": "buffer_attr",
                    "buffer": name,
                    "scope": scope,
                    "change": f"add multi_buffer={n}, hivm.nbuf={n}",
                    "reason": reason,
                    "safety": safety,
                })
        lines.append(new_line)
    return "\n".join(lines) + ("\n" if ir_text.endswith("\n") else ""), changes


def _apply_existing_tile_attr_rewrite(ir_text: str, strategy: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    """Step-2: replace existing tile attributes only when clear anchors exist.

    This is intentionally not a loop-nest rewrite. If the IR lacks tile anchors,
    the function leaves it unchanged and the capability report explains the
    fallback.
    """
    updates = _tile_attr_updates(strategy)
    changes: List[Dict[str, Any]] = []
    if not updates:
        return ir_text, changes

    def replace_key(text: str, key: str, val: Any) -> str:
        lit = _mlir_literal(val)
        patterns = [
            # Existing tile anchors only. Function-level hivm.strategy.* attrs
            # are Step-1 annotations and should not be counted as Step-2 tile
            # structural anchors.
            rf"(?P<prefix>\b(?:hivm\.)?{re.escape(key)}\s*=\s*)(?P<old>[^,}}\n]+)",
        ]
        out = text
        for pat in patterns:
            def repl(m: re.Match[str]) -> str:
                old = m.group('old').strip()
                if old != lit:
                    changes.append({"type": "tile_attr", "key": key, "before": old, "after": val, "anchor": m.group(0).split('=')[0].strip()})
                return m.group('prefix') + lit
            out = re.sub(pat, repl, out)
        return out

    out = ir_text
    for key, val in updates.items():
        out = replace_key(out, key, val)
    return out, changes



def _safe_barrier_notes(ir_text: str, strategy: Dict[str, Any], safety: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Step-2 sync handling: annotate only, never rewrite barriers/events.

    Real GraphSyncSolver rewrite is intentionally outside Step-2 because moving
    or deleting sync ops requires a dependency graph and deadlock/data-race
    proof. Even aggressive Step-2 keeps the original barrier line.
    """
    changes: List[Dict[str, Any]] = []
    if strategy.get("sync_policy") != "graph_sync_solver":
        return ir_text, changes
    lines: List[str] = []
    for line in ir_text.splitlines():
        is_barrier = ("pipe_barrier" in line) or ("hivm.hir.barrier" in line) or ("hivm.barrier" in line)
        if is_barrier:
            lines.append("      // [auto_strategy sync_hint] GraphSyncSolver candidate; Step-2 does not remove/move barriers without dependency legality proof")
            lines.append(line)
            changes.append({"type": "sync_hint", "change": "annotate barrier only", "safety": safety, "structural_rewrite": False})
        else:
            lines.append(line)
    return "\n".join(lines) + ("\n" if ir_text.endswith("\n") else ""), changes



# ---------------------------------------------------------------------------
# Step-2C: CVPipeline safe op-anchor rewrite
# ---------------------------------------------------------------------------
# This is deliberately a hint rewrite, not a true pipeline lowering pass.  It
# marks existing cube/fixpipe/vector/store anchors with machine-readable
# hivm.cv.* attributes and emits a report.  It never reorders operations,
# inserts/removes event/wait ops, or duplicates buffers.

_CV_CUBE_OPS = {
    "mmad", "mmadL1", "matmul", "matmul_l1", "cube", "conv", "mad",
}
_CV_FIXPIPE_OPS = {"fixpipe", "fix_pipe", "fixpipe2ub"}
_CV_VECTOR_PREFIXES = ("v",)
_CV_VECTOR_OPS = {
    "vadd", "vsub", "vmul", "vdiv", "vexp", "vreduce", "vmax", "vmin",
    "vrec", "vsqrt", "cast", "softmax", "relu", "gelu", "elewise",
}
_CV_STORE_OPS = {"store", "nz2nd"}
_CV_LOAD_OPS = {"load", "nd2nz", "dma_load"}
_CV_SYNC_OPS = {"set_flag", "wait_flag", "pipe_barrier", "barrier"}


def _classify_hivm_op(op_name: str) -> str:
    """Classify a HIVM op into a CV pipeline role."""
    name = op_name.split(".")[-1]
    if name in _CV_CUBE_OPS or "mmad" in name.lower():
        return "cube"
    if name in _CV_FIXPIPE_OPS or "fixpipe" in name.lower():
        return "fixpipe"
    if name in _CV_STORE_OPS:
        return "store"
    if name in _CV_LOAD_OPS:
        return "load"
    if name in _CV_SYNC_OPS:
        return "sync"
    if name in _CV_VECTOR_OPS or (name.startswith(_CV_VECTOR_PREFIXES) and name not in {"view"}):
        return "vector"
    return "other"


def _extract_cv_op_inventory(ir_text: str) -> List[Dict[str, Any]]:
    """Collect line-level HIVM op anchors that may participate in CV pipeline.

    The text-level demo only rewrites single-line operation anchors such as
    ``hivm.hir.mmad ins(...)`` or ``hivm.hir.vadd ins(...)``.  Multi-line operand
    lists are still anchored by the first op line, which is enough for an op
    attribute hint but not enough for real scheduling.
    """
    inv: List[Dict[str, Any]] = []
    pat = re.compile(r"^(?P<indent>\s*)(?P<op>hivm\.(?:hir\.)?[A-Za-z_][\w.]*)\b(?P<rest>.*)$")
    for lineno, line in enumerate(ir_text.splitlines(), 1):
        m = pat.match(line)
        if not m:
            continue
        op = m.group("op")
        role = _classify_hivm_op(op)
        if role == "other":
            continue
        inv.append({
            "line": lineno,
            "op": op,
            "role": role,
            "already_has_cv_hint": "hivm.cv." in line,
            "text": line.strip(),
        })
    return inv


def _cv_pipeline_enabled(strategy: Dict[str, Any]) -> bool:
    """Return whether selected strategy asks for CV pipelining hints."""
    try:
        return int(strategy.get("cv_pipeline_stage", 1) or 1) > 1
    except Exception:
        return False


def _add_cv_attr_to_op_line(line: str, attrs: Dict[str, Any]) -> str:
    """Attach a flat attr dictionary immediately after a HIVM op name.

    Example:
      hivm.hir.mmad ins(...) -> hivm.hir.mmad {hivm.cv.role = "cube"} ins(...)

    If an op already has a leading attr dictionary, merge into it.  This is a
    local anchor hint only; it does not alter op ordering or operands.
    """
    m = re.match(r"^(?P<indent>\s*)(?P<op>hivm\.(?:hir\.)?[A-Za-z_][\w.]*)(?P<after>.*)$", line)
    if not m:
        return line
    indent, op, after = m.group("indent"), m.group("op"), m.group("after")
    # Existing leading op attrs: ``op { ... } rest``.
    m_attr = re.match(r"^\s*\{(?P<body>[^}]*)\}(?P<tail>.*)$", after)
    if m_attr:
        body = _merge_attr_body(m_attr.group("body"), attrs)
        return f"{indent}{op} {{{body}}}{m_attr.group('tail')}"
    attr_text = ", ".join(f"{k} = {_mlir_literal(v)}" for k, v in attrs.items())
    return f"{indent}{op} {{{attr_text}}}{after}"


def _apply_safe_cv_pipeline_rewrite(ir_text: str, strategy: Dict[str, Any], safety: str = "conservative") -> Tuple[str, List[Dict[str, Any]]]:
    """Step-2C: add CVPipeline op-level hints to existing op anchors.

    Safety contract:
    - no op reorder;
    - no cube/vector overlap schedule is materialized;
    - no event/wait insertion, deletion, or reuse;
    - no buffer duplication;
    - stage>=4 is marked as requested stage but still only emits hints.

    Conservative mode marks only cube/fixpipe/vector ops.  Balanced/aggressive
    also mark load/store anchors so the downstream pass can understand stage
    boundaries more easily.
    """
    changes: List[Dict[str, Any]] = []
    if not _cv_pipeline_enabled(strategy):
        return ir_text, changes

    safety = str(safety or "conservative").lower()
    stage = max(2, int(_num(strategy.get("cv_pipeline_stage", 2), 2)))
    template = strategy.get("cv_pipeline_template", "auto")
    pc_distance = int(_num(strategy.get("producer_consumer_distance", 1), 1))
    cube_loop = int(_num(strategy.get("tile_mix_cube_loop", 1), 1))
    vector_loop = int(_num(strategy.get("tile_mix_vector_loop", 1), 1))
    mixed = bool(strategy.get("enable_mixed_cv", False))
    auto_balance = bool(strategy.get("auto_cv_balance", False))

    allowed_roles = {"cube", "fixpipe", "vector"}
    if safety in {"balanced", "aggressive"}:
        allowed_roles |= {"load", "store"}

    lines: List[str] = []
    role_counts: Dict[str, int] = {}
    for line in ir_text.splitlines():
        m = re.match(r"^(?P<indent>\s*)(?P<op>hivm\.(?:hir\.)?[A-Za-z_][\w.]*)\b(?P<rest>.*)$", line)
        if not m:
            lines.append(line)
            continue
        op = m.group("op")
        role = _classify_hivm_op(op)
        if role not in allowed_roles or "hivm.cv." in line:
            lines.append(line)
            continue
        role_counts[role] = role_counts.get(role, 0) + 1
        local_index = role_counts[role] - 1
        attrs = {
            "hivm.cv.pipeline_hint": True,
            "hivm.cv.role": role,
            "hivm.cv.stage": stage,
            "hivm.cv.template": template,
            "hivm.cv.producer_consumer_distance": pc_distance,
            "hivm.cv.cube_loop": cube_loop,
            "hivm.cv.vector_loop": vector_loop,
            "hivm.cv.enable_mixed_cv": mixed,
            "hivm.cv.auto_balance": auto_balance,
            "hivm.cv.anchor_index": local_index,
        }
        new_line = _add_cv_attr_to_op_line(line, attrs)
        changes.append({
            "type": "cv_op_attr",
            "op": op,
            "role": role,
            "line_hint_index": local_index,
            "change": "add hivm.cv.* pipeline hint attrs",
            "stage": stage,
            "template": template,
            "safety": safety,
            "structural_reorder": False,
        })
        lines.append(new_line)
    return "\n".join(lines) + ("\n" if ir_text.endswith("\n") else ""), changes


def build_cv_pipeline_rewrite_report(
    ir_text: str,
    strategy: Dict[str, Any],
    safety: str,
    cv_changes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build a dedicated report for CVPipeline hint rewrite."""
    cv_changes = cv_changes or []
    inv = _extract_cv_op_inventory(ir_text)
    counts: Dict[str, int] = {}
    for item in inv:
        counts[item["role"]] = counts.get(item["role"], 0) + 1
    changed_counts: Dict[str, int] = {}
    for c in cv_changes:
        role = str(c.get("role"))
        changed_counts[role] = changed_counts.get(role, 0) + 1
    has_cube = counts.get("cube", 0) > 0
    has_vector = counts.get("vector", 0) > 0
    has_fixpipe = counts.get("fixpipe", 0) > 0
    enabled = _cv_pipeline_enabled(strategy)
    return {
        "schema_version": "hivm_cv_pipeline_rewrite_report_v1",
        "producer": "strategy_search_demo_v3.3.1_step2c_cv_hint_rewrite",
        "rewrite_stage": "step2c_cv_pipeline_hint_rewrite",
        "rewrite_safety": safety,
        "strategy_id": strategy.get("strategy_id"),
        "selected_cv_plan": {
            "cv_pipeline_stage": strategy.get("cv_pipeline_stage"),
            "cv_pipeline_template": strategy.get("cv_pipeline_template"),
            "enable_mixed_cv": strategy.get("enable_mixed_cv"),
            "tile_mix_cube_loop": strategy.get("tile_mix_cube_loop"),
            "tile_mix_vector_loop": strategy.get("tile_mix_vector_loop"),
            "auto_cv_balance": strategy.get("auto_cv_balance"),
            "producer_consumer_distance": strategy.get("producer_consumer_distance"),
            "stage_buffer_policy": strategy.get("stage_buffer_policy"),
        },
        "op_inventory": {
            "total_cv_related_ops": len(inv),
            "role_counts": counts,
            "has_cube_anchor": has_cube,
            "has_fixpipe_anchor": has_fixpipe,
            "has_vector_anchor": has_vector,
            "has_cv_pipeline_opportunity": bool(has_cube and (has_vector or has_fixpipe)),
        },
        "applied_changes_summary": {
            "cv_op_hints_added": len(cv_changes),
            "changed_role_counts": changed_counts,
            "changed_ops": [
                {"op": c.get("op"), "role": c.get("role"), "stage": c.get("stage"), "template": c.get("template")}
                for c in cv_changes
            ],
        },
        "capabilities": {
            "cv_plan_func_annotation": True,
            "cv_plan_sidecar_config": True,
            "cv_op_level_hint_attrs": bool(enabled and cv_changes),
            "cv_load_store_boundary_hints": any(c.get("role") in {"load", "store"} for c in cv_changes),
            "cv_pipeline_structural_reorder": False,
            "event_wait_insertion_for_cv_overlap": False,
            "buffer_duplication_for_cv_stage": False,
        },
        "fallback_reasons": {
            "cv_not_enabled": None if enabled else "selected cv_pipeline_stage <= 1",
            "no_cube_vector_pattern": None if (has_cube and (has_vector or has_fixpipe)) else "missing cube+vector/fixpipe anchors; kept function-level and sidecar hints only",
            "structural_reorder": "not implemented in safe hint rewrite; requires dependency graph, live-range analysis, event/wait legality, and output correctness validation",
        },
        "safety_contract": [
            "CVPipeline rewrite here only adds machine-readable hivm.cv.* hint attributes to existing op anchors.",
            "It does not move cube/vector/fixpipe/store ops.",
            "It does not insert/delete/reuse set_flag/wait_flag/barrier events.",
            "It does not duplicate buffers or materialize ping-pong/stage buffers.",
            "A real vTriton/compiler CV pipeline pass must consume these hints and re-verify correctness before claiming realized speedup.",
        ],
    }


def build_rewrite_capability_report(
    ir_text: str,
    strategy: Dict[str, Any],
    safety: str,
    structural_changes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build Step-2 capability/fallback report.

    The report makes the boundary explicit: Step-2 may emit safe local hints,
    but it refuses to lower loops, duplicate buffers, move ops, or rewrite sync.
    """
    structural_changes = structural_changes or []
    allocs = _extract_alloc_inventory(ir_text)
    per_buf = _parse_buffer_multipliers(strategy)
    explicit_targets = {k: v for k, v in per_buf.items() if v >= 2}
    tile_updates = _tile_attr_updates(strategy)

    tile_anchor_patterns = []
    for k in tile_updates:
        tile_anchor_patterns.extend([f"{k}", f"hivm.{k}", f"hivm.strategy.{k}"])
    tile_anchor_found = any(re.search(rf"\b{re.escape(anchor)}\s*=", ir_text) for anchor in tile_anchor_patterns)

    rewritten_buffers = [c.get("buffer") for c in structural_changes if c.get("type") == "buffer_attr"]
    rewritten_tile_attrs = [c.get("key") for c in structural_changes if c.get("type") == "tile_attr"]
    cv_op_hints = [c for c in structural_changes if c.get("type") == "cv_op_attr"]
    cv_inventory = _extract_cv_op_inventory(ir_text)
    skipped_buffers: List[Dict[str, Any]] = []
    for a in allocs:
        name = a["name"]
        reason = None
        if a["scope"] not in {"ub", "l1"}:
            reason = "not_ub_or_l1_scope"
        elif not a["eligible_name"]:
            reason = "accumulator_output_or_persistent_name_guard"
        elif a["already_has_multibuffer"]:
            reason = "already_has_multibuffer_hint"
        elif name in rewritten_buffers:
            reason = None
        elif safety == "conservative" and explicit_targets:
            reason = "not_listed_with_multiplier_ge_2"
        elif safety == "conservative" and strategy.get("double_buffer"):
            reason = "no_explicit_per_buffer_multiplier_ge_2_under_conservative_safety"
        elif safety in {"balanced", "aggressive"} and not a["stream_like_name"]:
            reason = "not_stream_like_under_name_heuristic"
        if reason:
            skipped_buffers.append({"name": name, "scope": a["scope"], "reason": reason})

    can_multibuffer_hint = bool(rewritten_buffers) or bool(explicit_targets) or (str(safety).lower() in {"balanced", "aggressive"} and bool(strategy.get("double_buffer")))
    return {
        "schema_version": "hivm_rewrite_capability_v1",
        "producer": "strategy_search_demo_v3.3.1_step2_safe_structural",
        "rewrite_stage": "step2_safe_structural_hint_rewrite",
        "rewrite_safety": safety,
        "strategy_id": strategy.get("strategy_id"),
        "capabilities": {
            "func_and_module_annotation": True,
            "alloc_level_multibuffer_hint": can_multibuffer_hint,
            "existing_tile_attr_replacement": bool(tile_updates) and tile_anchor_found,
            "tiling_loop_nest_generation": False,
            "real_pingpong_buffer_duplication": False,
            "load_store_op_motion": False,
            "cv_pipeline_op_level_hint_attrs": bool(cv_op_hints),
            "cv_pipeline_structural_reorder": False,
            "sync_barrier_or_event_rewrite": False,
        },
        "anchors": {
            "alloc_count": len(allocs),
            "ub_l1_alloc_count": sum(1 for a in allocs if a["scope"] in {"ub", "l1"}),
            "tile_attr_anchor_found": tile_anchor_found,
            "explicit_buffer_multiplier_targets": explicit_targets,
            "cv_related_op_count": len(cv_inventory),
            "cv_cube_anchor_count": sum(1 for x in cv_inventory if x.get("role") == "cube"),
            "cv_vector_anchor_count": sum(1 for x in cv_inventory if x.get("role") == "vector"),
            "cv_fixpipe_anchor_count": sum(1 for x in cv_inventory if x.get("role") == "fixpipe"),
        },
        "applied_changes_summary": {
            "buffer_hints_added": len(rewritten_buffers),
            "buffers_rewritten": rewritten_buffers,
            "tile_attrs_replaced": rewritten_tile_attrs,
            "cv_op_hints_added": len(cv_op_hints),
            "cv_roles_rewritten": sorted({str(c.get("role")) for c in cv_op_hints}),
            "sync_rewrites_performed": 0,
        },
        "fallback_reasons": {
            "tile_loop_rewrite": "not_in_step2; requires index remapping, tail masks, reduction accumulation, and legality checks",
            "real_multibuffer_pingpong": "not_in_step2; requires buffer duplication, producer-consumer live-range analysis, and event/wait insertion",
            "cv_pipeline_rewrite": None if cv_op_hints else "no op-level CVPipeline hint emitted; structural reorder still requires cube/vector/fixpipe/store dependency graph",
            "cv_pipeline_structural_reorder": "not_in_step2; requires cube/vector/fixpipe/store dependency graph, live-range analysis, and event/wait legality",
            "sync_rewrite": "not_in_step2; requires proven dependency graph and deadlock/data-race validation",
            "tile_attr_replacement": None if tile_anchor_found else "no_existing_tile_attribute_anchor_found; kept function-level strategy annotation only",
            "conservative_multibuffer": None if rewritten_buffers else "no concrete safe alloc-level multi-buffer rewrite was emitted under current safety mode",
        },
        "skipped_buffers": skipped_buffers[:50],
        "safety_contract": [
            "Step-2 may add attributes to existing func/module/alloc/tile anchors.",
            "Step-2 must not create new buffers or duplicate existing buffers.",
            "Step-2 must not move load/store/compute operations.",
            "Step-2 must not remove or move barriers/events.",
            "Step-2 output still requires vTriton/compiler-pass validation before claiming realized speedup.",
        ],
    }


def build_strategy_attrs(strategy: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """从 selected strategy 中构建 module/func 属性。"""
    module_attrs = {
        "hivm.sync": "graph_sync_solver" if strategy.get("sync_policy") == "graph_sync_solver" else strategy.get("sync_policy", "inject"),
        "hivm.strategy.source": "auto_strategy_search_v3",
        "hivm.strategy.version": "V3.3.1-step2-safe-structural",
    }
    # Step-1 full annotation: preserve every plan-level strategy parameter
    # currently emitted by the search space. Unknown future keys are still
    # carried by sidecar JSON; this list controls only compact IR attrs.
    keys = [
        "strategy_id", "model_version",
        # TilingPlan
        "tile_m", "tile_n", "tile_k", "block_dim", "loop_order",
        "tail_strategy", "reduce_tile_policy", "layout_aware_tile",
        # MultiBufferPlan
        "double_buffer", "ub_multiplier", "l1_multiplier",
        "buffer_multipliers_json", "multibuffer_template",
        "stage_buffer_policy", "memory_reuse_level", "dma_policy",
        # CVPipelinePlan
        "cv_pipeline_stage", "cv_pipeline_template", "cv_split_ratio",
        "enable_mixed_cv", "tile_mix_cube_loop", "tile_mix_vector_loop",
        "auto_cv_balance", "producer_consumer_distance", "fusion",
        # SyncPlan
        "sync_policy", "sync_template", "barrier_level", "event_reuse",
        "sync_granularity", "event_id_policy", "sync_motion",
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
        "producer": "strategy_search_demo_v3.3.1_step2_safe_structural",
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
    if _cv_pipeline_enabled(strategy):
        edits.append({
            "type": "mark_cv_pipeline_ops",
            "match": {"dialect": "hivm", "roles": ["cube", "fixpipe", "vector"] + (["load", "store"] if str(safety).lower() in {"balanced", "aggressive"} else [])},
            "attrs": {
                "hivm.cv.pipeline_hint": True,
                "hivm.cv.stage": int(_num(strategy.get("cv_pipeline_stage", 2), 2)),
                "hivm.cv.template": strategy.get("cv_pipeline_template"),
                "hivm.cv.producer_consumer_distance": int(_num(strategy.get("producer_consumer_distance", 1), 1)),
                "hivm.cv.cube_loop": int(_num(strategy.get("tile_mix_cube_loop", 1), 1)),
                "hivm.cv.vector_loop": int(_num(strategy.get("tile_mix_vector_loop", 1), 1)),
                "hivm.cv.enable_mixed_cv": bool(strategy.get("enable_mixed_cv", False)),
                "hivm.cv.auto_balance": bool(strategy.get("auto_cv_balance", False)),
            },
            "structural_reorder": False,
        })
    if strategy.get("sync_policy") == "graph_sync_solver":
        edits.append({"type": "sync_hint", "action": "prefer_graph_sync_solver", "remove_barrier_all": False})
    return {
        "schema_version": "hivm_strategy_edit_v1",
        "producer": "strategy_search_demo_v3.3.1_step2_safe_structural",
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
    for fname in ["selected_strategy.json", "selected_plan.json", "pass_pipeline_config.json", "strategy_edit_script.json", "rewrite_audit.md", "rewrite_diff_report.json", "rewrite_capability_report.json", "cv_pipeline_rewrite_report.json"]:
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
        "producer": "strategy_search_demo_v3.3.1_step2_safe_structural",
        "strategy_id": strategy.get("strategy_id"),
        "original_ir": str(Path(original_ir_path).resolve()),
        "annotated_ir": str(Path(annotated_path).resolve()) if annotated_path else None,
        "safe_structural_ir": str(Path(structural_path).resolve()) if structural_path else None,
        "selected_strategy_json": str((out / "selected_strategy.json").resolve()),
        "pass_pipeline_config_json": str((out / "pass_pipeline_config.json").resolve()) if (out / "pass_pipeline_config.json").exists() else None,
        "strategy_edit_script_json": str((out / "strategy_edit_script.json").resolve()) if (out / "strategy_edit_script.json").exists() else None,
        "rewrite_capability_report_json": str((out / "rewrite_capability_report.json").resolve()) if (out / "rewrite_capability_report.json").exists() else None,
        "cv_pipeline_rewrite_report_json": str((out / "cv_pipeline_rewrite_report.json").resolve()) if (out / "cv_pipeline_rewrite_report.json").exists() else None,
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
        "// >>> auto_strategy_search V3.3.1 Step-1 annotated HIVM/NPUIR\n"
        "// This file carries strategy hints. It is not proof that backend compiler passes were executed.\n"
    )
    annotated = annotated_header + annotated
    annotated_path = out / "optimized.annotated.hivm.mlir"
    annotated_path.write_text(annotated, encoding="utf-8")

    structural_path: Optional[Path] = None
    structural_changes: List[Dict[str, Any]] = []
    cv_changes: List[Dict[str, Any]] = []
    cv_report: Optional[Dict[str, Any]] = None
    capability_report: Optional[Dict[str, Any]] = None
    formal_structural_path: Optional[Path] = None
    formal_structural_changes: List[Dict[str, Any]] = []
    formal_structural_report: Optional[Dict[str, Any]] = None
    phase3a_summary: Optional[Dict[str, Any]] = None
    phase3b_summary: Optional[Dict[str, Any]] = None
    phase3c_summary: Optional[Dict[str, Any]] = None
    phase3d_summary: Optional[Dict[str, Any]] = None
    phase3e_summary: Optional[Dict[str, Any]] = None
    phase3f_summary: Optional[Dict[str, Any]] = None
    phase4a_summary: Optional[Dict[str, Any]] = None
    phase4b_summary: Optional[Dict[str, Any]] = None
    phase5a_summary: Optional[Dict[str, Any]] = None
    phase5b_summary: Optional[Dict[str, Any]] = None
    if mode in {"safe_structural", "both"}:
        structural = annotated
        structural, ch = _apply_existing_tile_attr_rewrite(structural, strategy)
        structural_changes.extend(ch)
        structural, ch = _apply_safe_multibuffer_rewrite(structural, strategy, safety)
        structural_changes.extend(ch)
        structural, ch = _apply_safe_cv_pipeline_rewrite(structural, strategy, safety)
        cv_changes.extend(ch)
        structural_changes.extend(ch)
        structural, ch = _safe_barrier_notes(structural, strategy, safety)
        structural_changes.extend(ch)
        structural_header = (
            "// >>> auto_strategy_search V3.3.1 Step-2 safe structural HIVM/NPUIR\n"
            "// Safe local hint rewrite only: existing tile attrs + alloc-level multi_buffer/hivm.nbuf hints + CV op-level hints.\n"
            "// No loop generation, no buffer duplication, no op motion/reordering, no barrier/event rewrite.\n"
            "// vTriton/real compiler verification is required before claiming realized speedup.\n"
        )
        structural = structural_header + structural
        structural_path = out / "optimized.safe_structural.hivm.mlir"
        structural_path.write_text(structural, encoding="utf-8")
        cv_report = build_cv_pipeline_rewrite_report(ir_text, strategy, safety, cv_changes)
        write_json(out / "cv_pipeline_rewrite_report.json", cv_report)
        capability_report = build_rewrite_capability_report(ir_text, strategy, safety, structural_changes)
        write_json(out / "rewrite_capability_report.json", capability_report)

    # Phase-2A: formal operation-sequence structural rewrite backend boundary.
    # This is separate from Step-2 hints. The production target follows the MLIR
    # rewrite model: operation-level mutation via vTriton/HivmOpsEditor or a
    # PatternRewriter-style pass. Python fallback remains for audit/demo only.
    if getattr(args, "enable_structural_rewrite", False):
        structural_input = structural_path if structural_path else annotated_path
        base_text = Path(structural_input).read_text(encoding="utf-8")
        structural_backend = getattr(args, "structural_rewrite_backend", "auto")
        backend_plan = build_backend_execution_plan(
            structural_backend,
            getattr(args, "vtriton_strategy_rewriter", None),
            getattr(args, "vtriton_hivm_crud", None),
            getattr(args, "tritonsim_hivm", None),
        )
        write_json(out / "structural_backend_execution_plan.json", backend_plan)

        result = apply_structural_rewrite(base_text, strategy, getattr(args, "structural_rewrite_safety", safety))
        adapter_manifest = build_vtriton_adapter_manifest(
            backend_plan=backend_plan,
            edit_script=result.edit_script,
            strategy_rewriter_binary=getattr(args, "vtriton_strategy_rewriter", None),
            hivm_crud_binary=getattr(args, "vtriton_hivm_crud", None),
            tritonsim_hivm=getattr(args, "tritonsim_hivm", None),
            strategy=strategy,
        )
        write_json(out / "vtriton_adapter_manifest.json", adapter_manifest)
        # Preferred Phase-4 naming: this is a generic HIVM bridge manifest.
        # Keep vtriton_adapter_manifest.json as a backward-compatible alias for old tests/scripts.
        bridge_manifest = dict(adapter_manifest)
        bridge_manifest["preferred_name"] = "HIVM Rewrite Bridge Manifest"
        bridge_manifest["preferred_manifest_file"] = "hivm_bridge_manifest.json"
        bridge_manifest["legacy_alias_file"] = "vtriton_adapter_manifest.json"
        bridge_manifest["scope_clarification"] = "Current backend is a standalone HIVM bridge compatible with future vTriton/HivmOpsEditor integration; it is not a fully vTriton-backed production pass yet."
        write_json(out / "hivm_bridge_manifest.json", bridge_manifest)
        write_json(out / "structural_edit_script.json", result.edit_script)
        write_json(out / "structural_edit_schema.json", structural_edit_schema())
        schema_ok, schema_errors = validate_structural_edit_script(result.edit_script)
        write_json(out / "structural_edit_validation_report.json", {"passed": schema_ok, "errors": schema_errors, "schema_version": result.edit_script.get("schema_version")})
        structural_legality_report = build_structural_legality_report(
            base_text,
            result.edit_script,
            getattr(args, "structural_rewrite_safety", safety),
        )
        write_json(out / "structural_legality_report.json", structural_legality_report)

        header = (
            "// >>> auto_strategy_search V3.3.2 Step-3 FORMAL structural / Phase-2C backend bridge HIVM/NPUIR rewrite\n"
            "// Production target: vTriton/HivmOpsEditor or MLIR PatternRewriter operation-level mutation; Phase-2C can call a standalone C++ strict bridge for barrier rewrite.\n"
            "// Python fallback output is auditable prototype IR; validate with tritonsim-hivm / target compiler before using for performance claims.\n"
        )
        fallback_path = out / "optimized.structural.python_fallback.hivm.mlir"
        fallback_path.write_text(header + result.text, encoding="utf-8")
        python_validation = validate_python_structural_result(base_text, result.text, result)
        write_json(out / "structural_python_fallback_validation_report.json", python_validation)

        selected_backend = backend_plan.get("selected_backend")
        formal_structural_path = out / "optimized.structural.hivm.mlir"

        external_report_path: Optional[Path] = None
        if selected_backend == "dry_run":
            formal_structural_path.write_text(base_text, encoding="utf-8")
            backend_status = {"mode": "dry_run", "mutated_ir_written": False, "reason": "edit script/schema/backend plan emitted only"}
        elif selected_backend == "vtriton_strategy_rewriter":
            external_report_path = out / "structural_rewrite.external_vtriton_report.json"
            backend_status = try_run_external_strategy_rewriter(
                input_path=Path(structural_input),
                edit_script_path=out / "structural_edit_script.json",
                output_path=formal_structural_path,
                report_path=external_report_path,
                rewriter_binary=getattr(args, "vtriton_strategy_rewriter", None),
            )
            if not (backend_status.get("vtriton_strategy_rewriter_used") and formal_structural_path.exists()):
                formal_structural_path.write_text(header + result.text, encoding="utf-8")
                backend_status["fallback_used_after_external_failure"] = True
                backend_status["fallback_output"] = str(fallback_path)
        elif selected_backend == "vtriton_hivm_crud":
            backend_status = try_run_external_vtriton_hivm_crud(
                input_path=Path(structural_input),
                output_path=out / "optimized.structural.external_vtriton_crud.hivm.mlir",
                crud_binary=getattr(args, "vtriton_hivm_crud", None),
                mode=getattr(args, "vtriton_crud_mode", "roundtrip"),
                remove_gm_trips=int(getattr(args, "vtriton_remove_gm_trips", 0) or 0),
            )
            formal_structural_path.write_text(header + result.text, encoding="utf-8")
            backend_status["python_fallback_output_used_as_formal_output"] = True
        elif selected_backend == "dry_run_failed_no_backend":
            formal_structural_path.write_text(base_text, encoding="utf-8")
            backend_status = {"mode": "vtriton_requested_but_unavailable", "mutated_ir_written": False, "reason": backend_plan.get("reason")}
        else:
            formal_structural_path.write_text(header + result.text, encoding="utf-8")
            backend_status = {"mode": "python_fallback", "vtriton_binary_used": False, "reason": backend_plan.get("reason")}

        formal_structural_changes = result.changes
        formal_structural_report = build_structural_rewrite_report(strategy, result, backend_status)
        # When an external backend succeeds, the formal output is produced by that backend,
        # not by the Python fallback.  Keep the fallback changes for audit, but make the
        # effective formal-output changes reflect the external backend report.
        if external_report_path and external_report_path.exists() and backend_status.get("vtriton_strategy_rewriter_used"):
            try:
                external_report = json.loads(external_report_path.read_text(encoding="utf-8"))
                ext_changes = external_report.get("changes", []) if isinstance(external_report, dict) else []
                ext_counts: Dict[str, int] = {}
                for ch in ext_changes:
                    typ = str(ch.get("type", "unknown")) if isinstance(ch, dict) else "unknown"
                    ext_counts[typ] = ext_counts.get(typ, 0) + 1
                formal_structural_report["changes_summary_source"] = "external_vtriton_strategy_rewriter"
                formal_structural_report["python_fallback_planned_changes_summary"] = formal_structural_report.get("changes_summary", {})
                formal_structural_report["python_fallback_planned_changes"] = formal_structural_report.get("changes", [])
                formal_structural_report["changes_summary"] = {"total_changes": len(ext_changes), "change_counts": ext_counts}
                formal_structural_report["changes"] = ext_changes
                formal_structural_report["external_backend_report"] = str(external_report_path)
                formal_structural_report["structural_rewrite_performed"] = bool(ext_changes)
            except Exception as exc:
                formal_structural_report["external_backend_report_parse_error"] = str(exc)
        formal_structural_report["input_ir"] = str(structural_input)
        formal_structural_report["output_ir"] = str(formal_structural_path)
        formal_structural_report["python_fallback_output"] = str(fallback_path)
        formal_structural_report["backend_execution_plan"] = backend_plan
        formal_structural_report["hivm_bridge_manifest"] = str(out / "hivm_bridge_manifest.json")
        formal_structural_report["vtriton_adapter_manifest"] = str(out / "vtriton_adapter_manifest.json")  # legacy compatibility alias
        formal_structural_report["python_fallback_validation"] = python_validation
        formal_structural_report["structural_legality_report"] = str(out / "structural_legality_report.json")
        formal_structural_report["local_legality_summary"] = structural_legality_report.get("summary", {})
        write_json(out / "structural_rewrite_report.json", formal_structural_report)

        validation_report = None
        if getattr(args, "run_vtriton_validation", False):
            validation_dir = out / "vtriton_validation"
            validation_report = {
                "schema_version": "hivm_vtriton_validation_report_v1",
                "phase": "Phase-3E",
                "input_ir": try_run_tritonsim_validation(
                    Path(structural_input),
                    getattr(args, "tritonsim_hivm", None),
                    validation_dir,
                    "input",
                    des_graph_file=validation_dir / "original_des_graph.json",
                    perfetto_trace_file=validation_dir / "original_perfetto_trace.json",
                ),
                "optimized_structural_ir": try_run_tritonsim_validation(
                    formal_structural_path,
                    getattr(args, "tritonsim_hivm", None),
                    validation_dir,
                    "optimized",
                    des_graph_file=validation_dir / "optimized_des_graph.json",
                    perfetto_trace_file=validation_dir / "optimized_perfetto_trace.json",
                ),
                "note": "Phase-3E wrapper captures tritonsim-hivm stdout/stderr and requests DES graph + Perfetto trace artifacts when the local build supports these flags.",
            }
            write_json(out / "vtriton_validation_report.json", validation_report)

        # Phase-2F: parser-independent validation summary for the actual formal
        # structural output. This compares op-family counts before/after and
        # checks whether claimed edits are reflected by the emitted IR. It is an
        # audit gate, not a replacement for target MLIR/vTriton parsing.
        optimized_text_for_validation = formal_structural_path.read_text(encoding="utf-8") if formal_structural_path.exists() else ""
        structural_validation_summary = build_structural_validation_summary(
            original_ir_text=base_text,
            optimized_ir_text=optimized_text_for_validation,
            rewrite_report=formal_structural_report,
            legality_report=structural_legality_report,
            tritonsim_validation_report=validation_report,
        )
        write_json(out / "structural_validation_summary.json", structural_validation_summary)

        # Phase-2H: close the second-stage operation-level rewrite bridge and
        # hand off to Phase 3.  This is a status/roadmap artifact, not another
        # mutation pass.
        phase2_closure_report = build_phase2_closure_report(
            edit_script=result.edit_script,
            backend_plan=backend_plan,
            adapter_manifest=adapter_manifest,
            legality_report=structural_legality_report,
            rewrite_report=formal_structural_report,
            validation_summary=structural_validation_summary,
        )
        write_json(out / "phase2_closure_report.json", phase2_closure_report)

        # Phase-3A: correctness-analysis foundation.  This does not authorize
        # additional mutations; it emits op inventory, conservative dependency
        # graph, and event liveness reports for the actual formal structural IR.
        phase3_input_text = formal_structural_path.read_text(encoding="utf-8") if formal_structural_path.exists() else base_text
        phase3a_summary = emit_phase3a_analysis_outputs(out, phase3_input_text)
        # Phase-3B: memory-correctness evidence for future GM deletion, Q-load hoist,
        # double-buffer and CV-overlap rewrites.  This emits liveness/alias/capacity
        # reports only; it still does not unlock dangerous mutations.
        phase3b_summary = emit_phase3b_analysis_outputs(out, phase3_input_text)
        # Phase-3C: GM MemorySSA-like reaching-definition and deletion decision gates.
        # This still does not force GM deletion; it determines whether deletion can be proven safe.
        phase3c_summary = emit_phase3c_analysis_outputs(out, phase3_input_text)
        # Phase-3D: loop-invariant load hoist proof gate. This nominates candidates
        # and explains why production mutation remains deferred without target parser proof.
        phase3d_summary = emit_phase3d_analysis_outputs(out, phase3_input_text)
        # Phase-3E: vTriton/tritonsim-hivm DES + Perfetto trace validation wrapper.
        # This does not claim speedup; it records whether external validation was
        # run and whether DES/trace artifacts were generated for original/optimized IR.
        phase3e_summary = emit_phase3e_validation_outputs(
            out=out,
            original_ir_text=base_text,
            optimized_ir_text=phase3_input_text,
            tritonsim_validation_report=validation_report,
            structural_validation_summary=structural_validation_summary,
        )
        # Phase-3F: close Phase 3 and hand off to Phase 4. This is a report-only
        # stage: it consolidates evidence and keeps dangerous mutations locked
        # unless all local/target/external gates are satisfied.
        phase3f_summary = emit_phase3f_closure_outputs(
            out=out,
            phase3a_summary=phase3a_summary,
            phase3b_summary=phase3b_summary,
            phase3c_summary=phase3c_summary,
            phase3d_summary=phase3d_summary,
            phase3e_summary=phase3e_summary,
            structural_validation_summary=structural_validation_summary,
            vtriton_adapter_manifest=adapter_manifest,
        )
        # Phase-4A: bridge hardening / target-parser readiness audit.
        # This still does not unlock risky mutations.  It records whether the current
        # HIVM Rewrite Bridge can handshake with an external backend and whether a
        # target parser / tritonsim-hivm validation path is actually connected.
        phase4a_summary = emit_phase4a_outputs(
            out=out,
            original_ir_text=base_text,
            optimized_ir_text=phase3_input_text,
            edit_script=result.edit_script,
            bridge_manifest=bridge_manifest,
            backend_plan=backend_plan,
            strategy_rewriter_binary=getattr(args, "vtriton_strategy_rewriter", None),
            hivm_crud_binary=getattr(args, "vtriton_hivm_crud", None),
            tritonsim_hivm=getattr(args, "tritonsim_hivm", None),
            tritonsim_validation_report=validation_report,
        )
        # Phase-4B: DES/trace execution gate. Phase-3E introduced a wrapper;
        # Phase-4B makes the gate explicit and emits command templates/failure
        # diagnostics for connecting a real tritonsim-hivm build.
        phase4b_summary = emit_phase4b_outputs(
            out=out,
            tritonsim_validation_report=validation_report,
            phase4a_summary=phase4a_summary,
            tritonsim_hivm=getattr(args, "tritonsim_hivm", None),
            original_ir_path=str(Path(args.kernel)),
            optimized_ir_path=str(formal_structural_path),
        )
        # Phase-4C: guarded Q-load hoist prototype gate.  This does not perform
        # unsafe text-level region motion.  It emits a backend dry-run worklist
        # only when Phase-3D local proof and Phase-4A/B external gates are clean.
        phase4c_summary = emit_phase4c_outputs(
            out=out,
            phase4a_summary=phase4a_summary,
            phase4b_summary=phase4b_summary,
        )
        # Phase-4D: official-docs-aligned Operation-level dry-run contract.
        # This stage does not mutate IR.  It translates the guarded Phase-4C
        # worklist into a future HivmOpsEditor/MLIR backend plan and records the
        # official rewrite/legality/dominance gates that must pass first.
        phase4d_summary = emit_phase4d_outputs(
            out=out,
            phase4a_summary=phase4a_summary,
            phase4b_summary=phase4b_summary,
            phase4c_summary=phase4c_summary,
        )
        # Phase-4E: close Phase 4 and hand off to Phase 5.
        # This is a closure/reporting stage only: it summarizes official-docs-aligned
        # gates and keeps production mutations locked until a real Operation-level
        # backend, verifier, DES/trace and msprof validation are connected.
        phase4e_summary = emit_phase4e_outputs(
            out=out,
            phase4a_summary=phase4a_summary,
            phase4b_summary=phase4b_summary,
            phase4c_summary=phase4c_summary,
            phase4d_summary=phase4d_summary,
        )
        # Phase-5A: Operation-level backend readiness and inventory alignment.
        # This is still report-only: it does not perform production mutation.
        # It records whether a real HivmOpsEditor/MLIR Operation backend is
        # connected and emits a local inventory baseline for future backend comparison.
        phase5a_summary = emit_phase5a_outputs(
            out=out,
            original_ir_text=base_text,
            optimized_ir_text=phase3_input_text,
            operation_backend_binary=getattr(args, "hivm_operation_backend", None),
            hivm_strategy_rewriter_binary=getattr(args, "vtriton_strategy_rewriter", None),
            hivm_crud_binary=getattr(args, "vtriton_hivm_crud", None),
            mlir_opt_binary=getattr(args, "mlir_opt", None),
        )
        # Phase-5B: no-op roundtrip / verifier gate.
        # This stage still performs no production mutation. It validates whether a
        # future Operation-level backend can parse, re-emit and verify original and
        # optimized IR before any real transformation is attempted.
        phase5b_summary = emit_phase5b_outputs(
            out=out,
            original_ir_text=base_text,
            optimized_ir_text=phase3_input_text,
            operation_backend_binary=getattr(args, "hivm_operation_backend", None),
            mlir_opt_binary=getattr(args, "mlir_opt", None),
        )
        # Phase-5C: Operation-level dry-run execution gate.
        # The backend consumes the Phase-4D dry-run plan and attempts to locate
        # candidate Operations and target insertion points.  It still performs
        # no production mutation.
        phase5c_summary = emit_phase5c_outputs(
            out=out,
            optimized_ir_text=phase3_input_text,
            operation_backend_binary=getattr(args, "hivm_operation_backend", None),
        )
        # Phase-5D: guarded Operation-level mutation execution gate.
        # This defines the backend mutation contract and invokes it when supplied,
        # but rejects fake/non-MLIR backends as non-production.
        phase5d_summary = emit_phase5d_outputs(
            out=out,
            optimized_ir_text=phase3_input_text,
            operation_backend_binary=getattr(args, "hivm_operation_backend", None),
        )
        # Phase-5E: limited GM round-trip deletion guarded gate.
        # This prepares a strict Operation-level deletion contract but refuses
        # text-level GM traffic deletion or fake backend evidence.
        phase5e_summary = emit_phase5e_outputs(
            out=out,
            optimized_ir_text=phase3_input_text,
            operation_backend_binary=getattr(args, "hivm_operation_backend", None),
        )
        # Phase-5F: closure and Phase-6 handoff.
        # This does not expand mutation scope; it summarizes which contracts are
        # ready and which production mutations remain locked until a real
        # Operation-level backend/verifier/DES/msprof chain exists.
        phase5f_summary = emit_phase5f_outputs(out=out)
        # Phase-6A: real Operation-backend integration readiness.
        # This is the first Phase-6 step and remains conservative: it does not
        # perform production mutation. It checks whether the user supplied a
        # genuine MLIR/HivmOpsEditor backend, vTriton/source context, and real
        # tritonsim-hivm needed for positive-case validation.
        phase6a_summary = emit_phase6a_outputs(
            out=out,
            operation_backend_binary=getattr(args, "hivm_operation_backend", None),
            vtriton_source_root=getattr(args, "vtriton_source_root", None),
            tritonsim_hivm=getattr(args, "tritonsim_hivm", None),
            mlir_opt_binary=getattr(args, "mlir_opt", None),
        )
        # Phase-6B: ingest real user-provided HIVM/NPUIR fixtures and build the
        # vTriton/HivmOpsEditor positive-case validation harness. This still
        # refuses production mutation unless a real Operation backend and real
        # tritonsim-hivm are connected.
        phase6b_fixture_arg = getattr(args, "phase6_positive_fixtures", None)
        phase6b_fixture_paths = _split_paths(phase6b_fixture_arg)
        phase6b_summary = emit_phase6b_outputs(
            out=out,
            fixture_paths=phase6b_fixture_paths,
            operation_backend_binary=getattr(args, "hivm_operation_backend", None),
            tritonsim_hivm=getattr(args, "tritonsim_hivm", None),
            vtriton_source_root=getattr(args, "vtriton_source_root", None),
        )
        # Phase-6C: restricted true rewrite positive-case execution.
        # This is the first stage that performs real file-level IR mutation for
        # explicitly marked tiny positive fixtures. It is intentionally not
        # claimed as production MLIR/HivmOpsEditor rewriting, and it does not
        # touch complex user kernels.
        phase6c_summary = emit_phase6c_outputs(
            out=out,
            fixture_paths=phase6b_fixture_paths,
        )
        # Phase-6D: consume the supplied vTriton source tree and generate a
        # source-aware HivmOpsEditor backend adapter skeleton. This is the first
        # stage that inspects the real vTriton HivmOpsEditor API rather than
        # relying only on a previously assumed contract.
        phase6d_summary = emit_phase6d_outputs(
            out=out,
            vtriton_source_root=getattr(args, "vtriton_source_root", None),
        )
        # Phase-6E: local vTriton integration/build pack.
        # This stage creates concrete install/build/smoke-test scripts for the
        # HivmOpsEditor adapter and accepts a compiled backend only after it
        # proves real MLIR/HivmOpsEditor identity. It still does not claim broad
        # production mutation in this sandbox.
        phase6e_summary = emit_phase6e_outputs(
            out=out,
            vtriton_source_root=getattr(args, "vtriton_source_root", None),
            operation_backend_binary=getattr(args, "hivm_operation_backend", None),
            tritonsim_hivm=getattr(args, "tritonsim_hivm", None),
        )
        # Phase-6F: compiled backend acceptance + Phase-6 closure.
        # This stage is binary-facing: it accepts a real compiled
        # HivmOpsEditor/MLIR backend only after capability, inventory,
        # roundtrip and verify smoke tests pass on a fixture.
        phase6f_summary = emit_phase6f_outputs(
            out=out,
            fixture_paths=phase6b_fixture_paths,
            operation_backend_binary=getattr(args, "hivm_operation_backend", None),
            tritonsim_hivm=getattr(args, "tritonsim_hivm", None),
        )
    pass_cfg = build_pass_pipeline_config(strategy, selected)
    write_json(out / "pass_pipeline_config.json", pass_cfg)
    edit_script = build_strategy_edit_script(strategy, selected, mode, safety)
    write_json(out / "strategy_edit_script.json", edit_script)

    diff = {
        "schema_version": "hivm_rewrite_diff_v1",
        "producer": "strategy_search_demo_v3.3.1_step2_safe_structural",
        "strategy_id": strategy.get("strategy_id"),
        "rewrite_mode": mode,
        "rewrite_safety": safety,
        "annotated_ir": str(annotated_path),
        "safe_structural_ir": str(structural_path) if structural_path else None,
        "formal_structural_ir": str(formal_structural_path) if formal_structural_path else None,
        "structural_rewrite_report": str(out / "structural_rewrite_report.json") if formal_structural_report else None,
        "structural_legality_report": str(out / "structural_legality_report.json") if formal_structural_report else None,
        "structural_validation_summary": str(out / "structural_validation_summary.json") if formal_structural_report else None,
        "hivm_bridge_manifest": str(out / "hivm_bridge_manifest.json") if formal_structural_report else None,
        "vtriton_adapter_manifest": str(out / "vtriton_adapter_manifest.json") if formal_structural_report else None,  # legacy compatibility alias
        "phase2_closure_report": str(out / "phase2_closure_report.json") if formal_structural_report else None,
        "phase3a_analysis_summary": str(out / "phase3a_analysis_summary.json") if phase3a_summary else None,
        "phase3b_analysis_summary": str(out / "phase3b_analysis_summary.json") if phase3b_summary else None,
        "buffer_liveness_report": str(out / "buffer_liveness_report.json") if phase3b_summary else None,
        "capacity_recheck_report": str(out / "capacity_recheck_report.json") if phase3b_summary else None,
        "gm_alias_report": str(out / "gm_alias_report.json") if phase3b_summary else None,
        "phase3c_analysis_summary": str(out / "phase3c_analysis_summary.json") if phase3c_summary else None,
        "phase3d_analysis_summary": str(out / "phase3d_analysis_summary.json") if phase3d_summary else None,
        "phase3e_analysis_summary": str(out / "phase3e_analysis_summary.json") if phase3e_summary else None,
        "vtriton_des_trace_validation_report": str(out / "vtriton_des_trace_validation_report.json") if phase3e_summary else None,
        "trace_comparison_report_html": str(out / "trace_comparison_report.html") if phase3e_summary else None,
        "phase3_closure_report": str(out / "phase3_closure_report.json") if phase3f_summary else None,
        "phase3f_analysis_summary": str(out / "phase3f_analysis_summary.json") if phase3f_summary else None,
        "phase5a_analysis_summary": str(out / "phase5a_analysis_summary.json") if phase5a_summary else None,
        "phase5b_analysis_summary": str(out / "phase5b_analysis_summary.json") if phase5b_summary else None,
        "phase5b_roundtrip_verifier_gate_report": str(out / "phase5b_roundtrip_verifier_gate_report.json") if phase5b_summary else None,
        "phase5c_analysis_summary": str(out / "phase5c_analysis_summary.json") if 'phase5c_summary' in locals() and phase5c_summary else None,
        "phase6e_analysis_summary": str(out / "phase6e_analysis_summary.json") if 'phase6e_summary' in locals() and phase6e_summary else None,
        "phase6e_vtriton_local_integration_report": str(out / "phase6e_vtriton_local_integration_report.json") if 'phase6e_summary' in locals() and phase6e_summary else None,
        "phase6e_backend_build_plan": str(out / "phase6e_backend_build_plan.json") if 'phase6e_summary' in locals() and phase6e_summary else None,
        "phase6f_analysis_summary": str(out / "phase6f_analysis_summary.json") if 'phase6f_summary' in locals() and phase6f_summary else None,
        "phase6f_backend_acceptance_report": str(out / "phase6f_backend_acceptance_report.json") if 'phase6f_summary' in locals() and phase6f_summary else None,
        "phase6_closure_report": str(out / "phase6_closure_report.json") if 'phase6f_summary' in locals() and phase6f_summary else None,
        "phase5c_operation_level_dry_run_report": str(out / "phase5c_operation_level_dry_run_report.json") if 'phase5c_summary' in locals() and phase5c_summary else None,
        "phase5d_analysis_summary": str(out / "phase5d_analysis_summary.json") if 'phase5d_summary' in locals() and phase5d_summary else None,
        "phase5d_guarded_mutation_execution_report": str(out / "phase5d_guarded_mutation_execution_report.json") if 'phase5d_summary' in locals() and phase5d_summary else None,
        "phase5d_mutation_safety_report": str(out / "phase5d_mutation_safety_report.json") if 'phase5d_summary' in locals() and phase5d_summary else None,
        "phase5e_analysis_summary": str(out / "phase5e_analysis_summary.json") if 'phase5e_summary' in locals() and phase5e_summary else None,
        "phase5e_limited_gm_roundtrip_deletion_report": str(out / "phase5e_limited_gm_roundtrip_deletion_report.json") if 'phase5e_summary' in locals() and phase5e_summary else None,
        "phase5e_gm_deletion_safety_report": str(out / "phase5e_gm_deletion_safety_report.json") if 'phase5e_summary' in locals() and phase5e_summary else None,
        "phase5_closure_report": str(out / "phase5_closure_report.json") if 'phase5f_summary' in locals() and phase5f_summary else None,
        "phase5f_analysis_summary": str(out / "phase5f_analysis_summary.json") if 'phase5f_summary' in locals() and phase5f_summary else None,
        "phase5f_leadership_summary": str(out / "phase5f_leadership_summary.json") if 'phase5f_summary' in locals() and phase5f_summary else None,
        "phase6a_analysis_summary": str(out / "phase6a_analysis_summary.json") if 'phase6a_summary' in locals() and phase6a_summary else None,
        "phase6b_analysis_summary": str(out / "phase6b_analysis_summary.json") if 'phase6b_summary' in locals() and phase6b_summary else None,
        "phase6c_analysis_summary": str(out / "phase6c_analysis_summary.json") if 'phase6c_summary' in locals() and phase6c_summary else None,
        "phase6d_analysis_summary": str(out / "phase6d_analysis_summary.json") if 'phase6d_summary' in locals() and phase6d_summary else None,
        "phase6d_vtriton_source_integration_report": str(out / "phase6d_vtriton_source_integration_report.json") if 'phase6d_summary' in locals() and phase6d_summary else None,
        "phase6d_backend_files_manifest": str(out / "phase6d_generated_backend_files_manifest.json") if 'phase6d_summary' in locals() and phase6d_summary else None,
        "target_parser_validation_report": str(out / "target_parser_validation_report.json") if phase4a_summary else None,
        "phase4a_analysis_summary": str(out / "phase4a_analysis_summary.json") if phase4a_summary else None,
        "phase4b_des_trace_execution_report": str(out / "phase4b_des_trace_execution_report.json") if phase4b_summary else None,
        "phase4b_analysis_summary": str(out / "phase4b_analysis_summary.json") if phase4b_summary else None,
        "phase4b_validation_commands": str(out / "phase4b_validation_commands.sh") if phase4b_summary else None,
        "phase4c_q_load_hoist_prototype_report": str(out / "phase4c_q_load_hoist_prototype_report.json") if formal_structural_report else None,
        "phase4c_q_load_hoist_candidate_script": str(out / "phase4c_q_load_hoist_candidate_script.json") if formal_structural_report else None,
        "phase4c_analysis_summary": str(out / "phase4c_analysis_summary.json") if formal_structural_report else None,
        "phase4d_operation_rewrite_dry_run_report": str(out / "phase4d_operation_rewrite_dry_run_report.json") if formal_structural_report else None,
        "phase4d_hivmopseditor_dry_run_plan": str(out / "phase4d_hivmopseditor_dry_run_plan.json") if formal_structural_report else None,
        "phase4d_official_mlir_compliance_report": str(out / "phase4d_official_mlir_compliance_report.json") if formal_structural_report else None,
        "phase4d_analysis_summary": str(out / "phase4d_analysis_summary.json") if formal_structural_report else None,
        "phase4_closure_report": str(out / "phase4_closure_report.json") if formal_structural_report else None,
        "phase4e_analysis_summary": str(out / "phase4e_analysis_summary.json") if formal_structural_report else None,
        "loop_invariant_load_hoist_report": str(out / "loop_invariant_load_hoist_report.json") if phase3d_summary else None,
        "q_load_hoist_decision": str(out / "q_load_hoist_decision.json") if phase3d_summary else None,
        "gm_memory_ssa_report": str(out / "gm_memory_ssa_report.json") if phase3c_summary else None,
        "gm_roundtrip_deletion_decision": str(out / "gm_roundtrip_deletion_decision.json") if phase3c_summary else None,
        "rewrite_legality_gate_report": str(out / "rewrite_legality_gate_report.json") if phase3c_summary else None,
        "dependency_graph_report": str(out / "dependency_graph_report.json") if phase3a_summary else None,
        "event_liveness_report": str(out / "event_liveness_report.json") if phase3a_summary else None,
        "hivm_ir_inventory": str(out / "hivm_ir_inventory.json") if phase3a_summary else None,
        "rewrite_capability_report": str(out / "rewrite_capability_report.json") if capability_report else None,
        "cv_pipeline_rewrite_report": str(out / "cv_pipeline_rewrite_report.json") if cv_report else None,
        "changes": all_changes + structural_changes + formal_structural_changes,
        "structural_change": bool(structural_changes or formal_structural_changes),
        "formal_operation_sequence_change": bool(formal_structural_changes),
        "limitations": [
            "Step-2 may replace existing tile attributes, but it does not generate a new tiling loop nest.",
            "Step-2 may add alloc-level multi_buffer/hivm.nbuf hints, but it does not duplicate buffers or implement ping-pong scheduling.",
            "CVPipeline op-level hivm.cv.* hints may be emitted in Step-2, but cube/vector/fixpipe/store operations are not reordered.",
            "Sync barrier/event deletion, motion, and reuse are not structurally rewritten in Step-2.",
            "Compiler-pass-level optimized IR must be produced/validated by vTriton or a real AscendNPU compiler pass pipeline.",
        ],
    }
    write_json(out / "rewrite_diff_report.json", diff)
    audit = []
    audit.append("# V3.3.1 Step-1 Strategy-to-HIVM Annotation Rewrite Audit\n")
    audit.append(f"- Strategy: `{strategy.get('strategy_id')}`\n")
    audit.append(f"- Rewrite mode: `{mode}`\n")
    audit.append(f"- Safety: `{safety}`\n")
    audit.append(f"- Annotated IR: `{annotated_path.name}`\n")
    if structural_path:
        audit.append(f"- Safe structural IR: `{structural_path.name}`\n")
    if formal_structural_path:
        audit.append(f"- Formal structural IR: `{formal_structural_path.name}`\n")
        audit.append("- Structural rewrite report: `structural_rewrite_report.json`\n")
        audit.append("- Structural validation summary: `structural_validation_summary.json`\n")
        audit.append("- HIVM bridge manifest: `hivm_bridge_manifest.json`（兼容保留 `vtriton_adapter_manifest.json`）\n")
        audit.append("- Phase-2 closure report: `phase2_closure_report.json`\n")
        if phase3a_summary:
            audit.append("- Phase-3A op inventory: `hivm_ir_inventory.json`\n")
            audit.append("- Phase-3A dependency graph: `dependency_graph_report.json`\n")
            audit.append("- Phase-3A event liveness: `event_liveness_report.json`\n")
            audit.append("- Phase-3A summary: `phase3a_analysis_summary.json`\n")
        if phase3b_summary:
            audit.append("- Phase-3B buffer liveness: `buffer_liveness_report.json`\n")
            audit.append("- Phase-3B capacity recheck: `capacity_recheck_report.json`\n")
            audit.append("- Phase-3B GM alias report: `gm_alias_report.json`\n")
            audit.append("- Phase-3B summary: `phase3b_analysis_summary.json`\n")
        if phase3c_summary:
            audit.append("- Phase-3C GM MemorySSA report: `gm_memory_ssa_report.json`\n")
            audit.append("- Phase-3C GM deletion decision: `gm_roundtrip_deletion_decision.json`\n")
            audit.append("- Phase-3C rewrite legality gate: `rewrite_legality_gate_report.json`\n")
            audit.append("- Phase-3C summary: `phase3c_analysis_summary.json`\n")
        if phase3d_summary:
            audit.append("- Phase-3D load-hoist proof: `loop_invariant_load_hoist_report.json`\n")
            audit.append("- Phase-3D Q-load hoist decision: `q_load_hoist_decision.json`\n")
            audit.append("- Phase-3D summary: `phase3d_analysis_summary.json`\n")
        if phase3e_summary:
            audit.append("- Phase-3E DES/trace validation wrapper: `vtriton_des_trace_validation_report.json`\n")
            audit.append("- Phase-3E trace comparison HTML: `trace_comparison_report.html`\n")
            audit.append("- Phase-3E summary: `phase3e_analysis_summary.json`\n")
        if phase3f_summary:
            audit.append("- Phase-3F closure report: `phase3_closure_report.json`\n")
            audit.append("- Phase-3F summary: `phase3f_analysis_summary.json`\n")
        if phase4a_summary:
            audit.append("- Phase-4A target parser / bridge hardening report: `target_parser_validation_report.json`\n")
            audit.append("- Phase-4A summary: `phase4a_analysis_summary.json`\n")
        if 'phase4d_summary' in locals() and phase4d_summary:
            audit.append("- Phase-4D Operation-level dry-run contract: `phase4d_operation_rewrite_dry_run_report.json`\n")
            audit.append("- Phase-4D official MLIR compliance report: `phase4d_official_mlir_compliance_report.json`\n")
            audit.append("- Phase-4D summary: `phase4d_analysis_summary.json`\n")
        if 'phase4e_summary' in locals() and phase4e_summary:
            audit.append("- Phase-4E closure report: `phase4_closure_report.json`\n")
            audit.append("- Phase-4E summary: `phase4e_analysis_summary.json`\n")
    if capability_report:
        audit.append("- Capability report: `rewrite_capability_report.json`\n")
    if cv_report:
        audit.append("- CVPipeline rewrite report: `cv_pipeline_rewrite_report.json`\n")
    audit.append("\n## What was changed\n")
    for c in diff["changes"]:
        audit.append(f"- `{c.get('type')}`: {c}\n")
    if cv_report:
        audit.append("\n## Step-2C CVPipeline hint summary\n")
        audit.append(f"- cv_op_hints_added: `{cv_report.get('applied_changes_summary', {}).get('cv_op_hints_added')}`\n")
        audit.append(f"- role_counts: `{cv_report.get('op_inventory', {}).get('role_counts')}`\n")
        audit.append(f"- structural_reorder: `{cv_report.get('capabilities', {}).get('cv_pipeline_structural_reorder')}`\n")
    if formal_structural_report:
        audit.append("\n## Step-3 formal structural rewrite summary\n")
        audit.append(f"- structural_rewrite_performed: `{formal_structural_report.get('structural_rewrite_performed')}`\n")
        audit.append(f"- change_counts: `{formal_structural_report.get('changes_summary', {}).get('change_counts')}`\n")
        audit.append(f"- backend: `{formal_structural_report.get('backend')}`\n")
    if phase3a_summary:
        audit.append("\n## Phase-3A dependency-analysis foundation\n")
        inv = phase3a_summary.get("inventory", {})
        dep = phase3a_summary.get("dependency_graph", {})
        ev = phase3a_summary.get("event_liveness", {})
        audit.append(f"- op_count: `{inv.get('op_count')}`; unknown_op_count: `{inv.get('unknown_op_count')}`\n")
        audit.append(f"- dependency_edges: `{dep.get('edge_count')}`; edge_counts: `{dep.get('edge_counts')}`\n")
        audit.append(f"- event_count: `{ev.get('event_count')}`; local_event_liveness: `{ev.get('passed_local_event_liveness')}`\n")
        audit.append("- Note: Phase-3A emits evidence only. It does not unlock GM deletion, event reuse, real double-buffer, full CV overlap, or tiling lowering.\n")
    if phase3b_summary:
        audit.append("\n## Phase-3B buffer-liveness and GM-alias foundation\n")
        bl = phase3b_summary.get("buffer_liveness", {})
        gm = phase3b_summary.get("gm_alias", {})
        cap = bl.get("capacity_recheck", {})
        audit.append(f"- buffer_count: `{bl.get('buffer_count')}`; local_buffer_count: `{bl.get('local_buffer_count')}`; gm_buffer_count: `{bl.get('gm_buffer_count')}`\n")
        audit.append(f"- capacity_passed: `{cap.get('passed_conservative_capacity_recheck')}`; peak_by_space: `{cap.get('peak_by_space')}`\n")
        audit.append(f"- gm_access_count: `{gm.get('gm_access_count')}`; gm_roundtrip_candidates: `{gm.get('gm_roundtrip_candidate_count')}`; deletion_unlocked: `{gm.get('deletion_unlocked')}`\n")
        audit.append("- Note: Phase-3B emits memory evidence only. GM deletion, Q-load hoist, real double-buffer and full CV overlap remain locked.\n")
    if phase4a_summary:
        audit.append("\n## Phase-4A bridge hardening / target-parser readiness\n")
        audit.append(f"- target_parser_status: `{phase4a_summary.get('target_parser_status')}`\n")
        audit.append(f"- blocker_count: `{phase4a_summary.get('blocker_count')}`; blockers: `{phase4a_summary.get('phase4a_blockers')}`\n")
        audit.append("- Note: Phase-4A is a readiness audit only. It does not enable GM deletion, Q-load production hoist, double-buffer, CV overlap, or tiling lowering.\n")
    if 'phase4b_summary' in locals() and phase4b_summary:
        audit.append("\n## Phase-4B DES/trace execution gate\n")
        audit.append(f"- status: `{phase4b_summary.get('status')}`; passed_external_des_trace_gate: `{phase4b_summary.get('passed_external_des_trace_gate')}`\n")
        audit.append(f"- reasons: `{phase4b_summary.get('reasons')}`\n")
        audit.append("- Note: Phase-4B is an external validation gate. Passing it is necessary but not sufficient for risky production mutations.\n")
    if 'phase4c_summary' in locals() and phase4c_summary:
        audit.append("\n## Phase-4C guarded Q-load hoist prototype gate\n")
        audit.append(f"- candidates: `{phase4c_summary.get('candidate_count')}`; backend_dry_run_ready: `{phase4c_summary.get('backend_dry_run_ready_count')}`; production_allowed: `{phase4c_summary.get('production_mutation_allowed_count')}`\n")
        audit.append(f"- blockers: `{phase4c_summary.get('blockers')}`\n")
        audit.append("- Note: Phase-4C emits a backend dry-run worklist only; it does not perform unsafe text-level region motion.\n")
    if 'phase5d_summary' in locals() and phase5d_summary:
        audit.append("\n## Phase-5D guarded Operation-level mutation execution gate\n")
        audit.append(f"- status: `{phase5d_summary.get('status')}`; mutation_performed: `{phase5d_summary.get('mutation_performed')}`; production_allowed: `{phase5d_summary.get('production_mutation_allowed')}`\n")
        audit.append(f"- blockers: `{phase5d_summary.get('blockers')}`\n")
        audit.append("- Note: Phase-5D may call a backend mutation contract, but fake/non-MLIR backends are explicitly rejected as non-production. No Python text-level region motion is performed.\n")
    if 'phase5e_summary' in locals() and phase5e_summary:
        audit.append("\n## Phase-5E limited GM round-trip deletion gate\n")
        audit.append(f"- status: `{phase5e_summary.get('status')}`; candidates: `{phase5e_summary.get('candidate_count_total')}`; executable: `{phase5e_summary.get('executable_action_count')}`; deleted_pairs: `{phase5e_summary.get('deleted_pair_count')}`; production_allowed: `{phase5e_summary.get('production_mutation_allowed')}`\n")
        audit.append(f"- blockers: `{phase5e_summary.get('blockers')}`\n")
        audit.append("- Note: Phase-5E prepares a GM deletion backend contract only. It does not text-delete GM traffic; fake/non-MLIR backends and deferred Phase-3C candidates are rejected.\n")

    if 'phase4d_summary' in locals() and phase4d_summary:
        audit.append("\n## Phase-4D official-docs-aligned Operation-level dry-run contract\n")
        audit.append(f"- dry_run_actions: `{phase4d_summary.get('dry_run_action_count')}`; production_allowed: `{phase4d_summary.get('production_mutation_allowed_count')}`\n")
        audit.append(f"- blockers: `{phase4d_summary.get('blockers')}`\n")
        audit.append("- Note: Phase-4D follows official MLIR rewrite discipline: no text-level region motion, no production mutation, and future movement must go through an Operation-level backend with legality/dominance/verifier gates.\n")
    if 'phase4e_summary' in locals() and phase4e_summary:
        audit.append("\n## Phase-4E closure and Phase-5 handoff\n")
        audit.append(f"- phase4_status: `{phase4e_summary.get('phase4_status')}`; remaining_blockers: `{phase4e_summary.get('remaining_blocker_count')}`\n")
        audit.append(f"- production_mutations_unlocked: `{phase4e_summary.get('production_mutations_unlocked')}`\n")
        audit.append("- Note: Phase-4E closes the bridge/dry-run phase. It does not unlock risky mutations; Phase 5 must connect a real Operation-level backend and verifier first.\n")
    if phase3c_summary:
        audit.append("\n## Phase-3C GM MemorySSA and rewrite legality gate\n")
        gmssa = phase3c_summary.get("gm_memory_ssa", {})
        dec = phase3c_summary.get("gm_roundtrip_deletion_decision", {})
        gates = phase3c_summary.get("rewrite_gates_unlocked", {})
        audit.append(f"- gm_access_count: `{gmssa.get('gm_access_count')}`; memory_events: `{gmssa.get('memory_event_count')}`; candidates: `{gmssa.get('candidate_count')}`\n")
        audit.append(f"- gm_delete_allowed: `{dec.get('delete_allowed_count')}`; deferred: `{dec.get('deferred_count')}`; deletion_unlocked: `{dec.get('deletion_unlocked')}`\n")
        audit.append(f"- rewrite_gates: `{gates}`\n")
        audit.append("- Note: Phase-3C adds GM MemorySSA-like decision gates. It only allows deletion when all gates pass; otherwise deletion remains deferred.\n")
    if phase3d_summary:
        audit.append("\n## Phase-3D loop-invariant load-hoist proof gate\n")
        hc = phase3d_summary.get("hoist_candidates", {})
        audit.append(f"- hoist_candidates: `{hc.get('candidate_count')}`; local_proof_passed: `{hc.get('local_proof_passed_count')}`; hoist_allowed: `{hc.get('hoist_allowed_count')}`; hoist_unlocked: `{hc.get('hoist_unlocked')}`\n")
        audit.append("- Note: Phase-3D nominates candidates only. Production mutation remains locked without target parser region-motion proof.\n")
    if phase3e_summary:
        audit.append("\n## Phase-3E external DES/trace validation wrapper\n")
        audit.append(f"- validation_status: `{phase3e_summary.get('validation_status')}`; tritonsim_ran_both: `{phase3e_summary.get('external_tritonsim_ran_both')}`; artifacts_available: `{phase3e_summary.get('des_trace_artifacts_available')}`\n")
        audit.append("- Note: Phase-3E is a validation wrapper. It does not prove numerical correctness or real msprof speedup.\n")
    if phase3f_summary:
        audit.append("\n## Phase-3F closure and Phase-4 handoff\n")
        audit.append(f"- phase3_status: `{phase3f_summary.get('phase3_status')}`; remaining_blockers: `{phase3f_summary.get('remaining_blocker_count')}`\n")
        audit.append(f"- phase4_candidate_status: `{phase3f_summary.get('phase4_candidate_status')}`\n")
        audit.append("- Note: Phase-3F closes the analysis foundation. It does not default-enable GM deletion, real double-buffer, full CV overlap, or tiling lowering.\n")
    if capability_report:
        audit.append("\n## Step-2 capability summary\n")
        cap = capability_report.get("capabilities", {})
        for k in sorted(cap):
            audit.append(f"- {k}: `{cap[k]}`\n")
        audit.append("\n## Step-2 fallback reasons\n")
        for k, v in capability_report.get("fallback_reasons", {}).items():
            if v:
                audit.append(f"- {k}: {v}\n")
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
        structural_path=str(formal_structural_path or structural_path) if (formal_structural_path or structural_path) else None,
        strategy=strategy,
        selected=selected,
        des_paths=des_paths,
        trace_paths=trace_paths,
    )
    write_json(out / "vtriton_integration_report.json", {
        "schema_version": "vtriton_integration_report_v1",
        "producer": "strategy_search_demo_v3.3.1_step2_safe_structural",
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

