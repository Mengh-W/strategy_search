"""
HIVM / AscendNPU-IR 四类 Plan 参数寻优 demo。

本文件是整个项目的主程序，核心流程可以概括为：

1. 读取输入 HIVM/NPUIR MLIR 与硬件配置 JSON；
2. 从 MLIR 中抽取 kernel 静态结构，例如 memref、address space、mmad、vector op、sync op；
3. 自动生成四类候选 plan：TilingPlan、MultiBufferPlan、CVPipelinePlan、SyncPlan；
4. 对候选做硬件边界检查，过滤 UB/L1/L0A/L0B/L0C/GM workspace 超限的策略；
5. 使用 analytical cost model 给每个合法策略估算 predicted_cycles；
6. 从输入 IR 当前可见特征恢复 current_ir_estimated_strategy，作为“当前输入 IR 估计状态”；
7. 输出 best strategy、current-IR 对比、Top-K 候选、硬件边界、cost breakdown 和中文报告。

重要边界：
- 这里的 cost 是解析式估计值，不是真机实测 cycles；
- V3.0 可选输出 annotation-level / safe structural HIVM rewrite bundle；
- current_ir_estimated_strategy 是从输入 IR 恢复出的策略近似；V3.0 rewrite 不是完整 compiler lowering，需由 vTriton/真实编译器验证。
"""
from __future__ import annotations

import argparse
import copy
import itertools
import json
import math
import os
import random
import re
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


from .plans import (
    DTYPE_BYTES,
    SPACE_ALIAS,
    LOCAL_SPACES,
    RESOURCE_SCOPES,
    StrategyConfig,
    BufferInfo,
    KernelFeatures,
    Layer1Case,
    TilingPlan,
    MultiBufferPlan,
    CVPipelinePlan,
    SyncPlan,
    FourPlanBundle,
    DesGraphProfile,
    ArtifactProfile,
    DiagnosisHints,
    strategy_signature,
    layer1_signature,
    tile_signature_from_dict,
)

# ---------------------------------------------------------------------------
# 通用工具函数
# ---------------------------------------------------------------------------
# 这一组函数负责 dtype 字节数、对齐、JSON 读写和 memref 大小解析等基础操作。
# 它们不包含具体优化逻辑，只为后面的解析器、搜索器和 cost model 提供工具。
# ------------------------------ 通用工具 ------------------------------

def _prod(xs: Iterable[int]) -> int:
    """计算一组整数的乘积，用于 memref 维度展开和元素数量估算。"""
    p = 1
    for x in xs:
        p *= int(x)
    return p


def _align(x: float, align: int) -> int:
    """将数值向上对齐到指定粒度，保证 tile、buffer 和地址满足硬件对齐要求。"""
    if align <= 0:
        align = 1
    return int(math.ceil(float(x) / align) * align)


def _norm_space(space: str) -> str:
    """统一 address space 的命名，把 cbuf/cc/hbm 等别名映射到 l1/l0c/gm。"""
    return SPACE_ALIAS.get(space.lower(), space.lower())


def _parse_memref_size(memref_body: str) -> Optional[int]:
    """解析静态 memref 形状，并返回其字节大小；遇到动态维度或未知 dtype 时返回 None。"""
    body0 = memref_body.split(",")[0].strip()
    if "?" in body0:
        return None
    parts = [p.strip() for p in body0.split("x") if p.strip()]
    if len(parts) < 2:
        return None
    dtype = parts[-1]
    dims: List[int] = []
    for d in parts[:-1]:
        if not d.isdigit():
            return None
        dims.append(int(d))
    if dtype not in DTYPE_BYTES:
        return None
    return _prod(dims) * DTYPE_BYTES[dtype]


def load_json(path: str) -> Dict[str, Any]:
    """读取 JSON 文件并返回字典结构，所有配置和辅助 profile 都通过该函数加载。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    """将 Python 对象以中文友好的 JSON 格式写入文件。"""
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def apply_cost_model_config(hw: Dict[str, Any], config_path: Optional[str], risk_mode: str) -> Dict[str, Any]:
    """把可选 cost-model JSON 配置和命令行 risk mode 合并进硬件配置。

    这样第一阶段不需要修改硬件 JSON 本体，就能切换 conservative/balanced/aggressive。
    """
    hw = copy.deepcopy(hw)
    hw.setdefault("calibration", {})
    if config_path:
        cfg = load_json(config_path)
        if not isinstance(cfg, dict):
            raise ValueError(f"cost-model config must be a JSON object: {config_path}")
        cal = hw.setdefault("calibration", {})
        if isinstance(cfg.get("cost_model_safety"), dict):
            cal["cost_model_safety"] = _deep_update_dict(cal.get("cost_model_safety", {}), cfg["cost_model_safety"])
        if isinstance(cfg.get("cost_model_risk_modes"), dict):
            cal["cost_model_risk_modes"] = _deep_update_dict(cal.get("cost_model_risk_modes", {}), cfg["cost_model_risk_modes"])
        if isinstance(cfg.get("cost_model_strategy_effects"), dict):
            cal["cost_model_strategy_effects"] = _deep_update_dict(cal.get("cost_model_strategy_effects", {}), cfg["cost_model_strategy_effects"])
        if isinstance(cfg.get("cost_model_calibration"), dict):
            cal["cost_model_calibration"] = _deep_update_dict(cal.get("cost_model_calibration", {}), cfg["cost_model_calibration"])
        if isinstance(cfg.get("metadata"), dict):
            cal["cost_model_config_metadata"] = cfg["metadata"]
    hw["calibration"]["cost_risk_mode"] = risk_mode
    return hw


def count_hivm_ops(text: str, names: Iterable[str]) -> Dict[str, int]:
    """统计 HIVM/HIVM-HIR 中指定算子族的出现次数，并兼容裸 hivm 与 hivm.hir 两种写法。"""
    counts: Dict[str, int] = {}
    for name in names:
        if name == "pipe_barrier":
            pattern = r"(?:hivm\.hir\.(?:pipe_barrier|barrier)|hivm\.pipe_barrier)\b"
        else:
            pattern = rf"(?:hivm\.hir\.{re.escape(name)}|hivm\.{re.escape(name)})\b"
        counts[name] = len(re.findall(pattern, text))
    return counts


# ------------------------------ 外部分析与诊断引导 ------------------------------

def _flatten_json_fields(obj: Any, prefix: str = "") -> List[str]:
    """递归展开 JSON 字段路径，用于审计输入 profile 的字段覆盖情况。"""
    fields: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            fields.append(path)
            fields.extend(_flatten_json_fields(v, path))
    elif isinstance(obj, list):
        if obj:
            fields.extend(_flatten_json_fields(obj[0], f"{prefix}[]" if prefix else "[]"))
    return fields


def _num(x: Any, default: float = 0.0) -> float:
    """把任意输入安全转换为有限浮点数，转换失败或出现 NaN/Inf 时返回默认值。"""
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def _norm_pipe(pipe: str) -> str:
    """统一 DES/profile 中的 pipe 名称，将不同写法归并到 mte2、mte3、cube、vector、sync 等类别。"""
    p = str(pipe or "").lower()
    if "mte2" in p or p in {"load", "pipe_mte2"}:
        return "mte2"
    if "mte3" in p or "store" in p:
        return "mte3"
    if "mte_ub" in p or "fix" in p:
        return "fix"
    if "cube" in p or p in {"m", "pipe_m"}:
        return "cube"
    if "vector" in p or p in {"v", "pipe_v"}:
        return "vector"
    if "sync" in p or "barrier" in p:
        return "sync"
    return p or "unknown"


def _bump(d: Dict[str, float], key: str, factor: float) -> None:
    """按乘法因子更新 bias 字典中的某个权重，用于诊断信息对搜索优先级的软引导。"""
    d[key] = round(float(d.get(key, 1.0)) * factor, 4)


def _add_signal(hints: DiagnosisHints, source: str, signal_type: str, message: str, variables: List[str], evidence: Any = None, severity: float = 1.0) -> None:
    """向 DiagnosisHints 添加一条诊断信号，并根据严重程度提升相关搜索变量的权重。"""
    hints.signals.append({
        "source": source,
        "signal_type": signal_type,
        "message": message,
        "search_variables": variables,
        "severity": severity,
        "evidence": evidence,
    })
    for v in variables:
        _bump(hints.variable_bias, v, 1.0 + 0.12 * max(0.0, min(severity, 3.0)))


def load_desgraph_profile(paths: List[str]) -> Optional[DesGraphProfile]:
    """读取可选 DES graph JSON，汇总 pipe 耗时、字节数、FLOPs、同步数量和关键算子。"""
    ops_all: List[Dict[str, Any]] = []
    fields: List[str] = []
    used: List[str] = []
    for path in paths:
        if not path:
            continue
        p = Path(path)
        if not p.exists():
            continue
        data = load_json(str(p))
        used.append(str(p))
        fields.extend(_flatten_json_fields(data))
        ops = data.get("operations", []) if isinstance(data, dict) else []
        if isinstance(ops, list):
            ops_all.extend([op for op in ops if isinstance(op, dict)])
    if not used:
        return None
    pipe_duration: Dict[str, float] = {}
    pipe_bytes: Dict[str, float] = {}
    pipe_flops: Dict[str, float] = {}
    sync_ops = barrier_ops = dependency_edges = 0
    for op in ops_all:
        name = str(op.get("name", "")).lower()
        pipe = _norm_pipe(str(op.get("pipe", "")))
        duration = _num(op.get("duration", 0.0)) * _num(op.get("loop_multiplier", 1.0), 1.0)
        pipe_duration[pipe] = pipe_duration.get(pipe, 0.0) + duration
        pipe_bytes[pipe] = pipe_bytes.get(pipe, 0.0) + _num(op.get("bytes", 0.0))
        pipe_flops[pipe] = pipe_flops.get(pipe, 0.0) + _num(op.get("flops", 0.0))
        if op.get("is_sync") or "flag" in name or "barrier" in name or pipe == "sync":
            sync_ops += 1
        if op.get("is_barrier") or "barrier" in name:
            barrier_ops += 1
        deps = op.get("depends_on", [])
        if isinstance(deps, list):
            dependency_edges += len(deps)
    top_ops = sorted(ops_all, key=lambda op: _num(op.get("duration", 0.0)) * _num(op.get("loop_multiplier", 1.0), 1.0), reverse=True)[:20]
    top_ops_simple = [{"id": op.get("id"), "name": op.get("name"), "pipe": op.get("pipe"), "duration": op.get("duration"), "bytes": op.get("bytes"), "flops": op.get("flops")} for op in top_ops]
    return DesGraphProfile(used, len(ops_all), pipe_duration, pipe_bytes, pipe_flops, sync_ops, barrier_ops, dependency_edges, top_ops_simple, sorted(set(fields)))


def _classify_action_text(text: str) -> List[Tuple[str, List[str], float]]:
    """根据文本中的关键词把诊断建议归类为计算、访存、同步、流水或布局相关信号。"""
    t = str(text or "").lower()
    out: List[Tuple[str, List[str], float]] = []
    if any(k in t for k in ["simd", "repeat", "mask", "vector", "intra-unit"]):
        out.append(("ComputeBound-Vector", ["f", "t", "r"], 1.4))
    if any(k in t for k in ["cube", "mmad", "matrix"]):
        out.append(("ComputeBound-Cube", ["t", "B", "r"], 1.4))
    if any(k in t for k in ["coalesc", "memory", "bandwidth", "load", "mte2", "hbm"]):
        out.append(("MemoryBound-Load", ["d", "m", "t", "ℓ"], 1.4))
    if any(k in t for k in ["store", "mte3"]):
        out.append(("MemoryBound-Store", ["d", "m", "t"], 1.2))
    if any(k in t for k in ["sync", "wait", "barrier", "event"]):
        out.append(("SyncBound", ["y", "m", "s", "t"], 1.5))
    if any(k in t for k in ["serial", "overlap", "pipeline", "idle"]):
        out.append(("PipelineImbalance", ["m", "s", "r", "y"], 1.4))
    if any(k in t for k in ["occupancy", "load balance", "grid partition", "active core"]):
        out.append(("ParallelismLow", ["B", "t"], 1.5))
    if any(k in t for k in ["nd2nz", "layout", "format"]):
        out.append(("LayoutOverhead", ["d", "t", "ℓ"], 1.3))
    return out




def _split_csv_paths(x: Optional[str]) -> List[str]:
    """把逗号分隔的路径参数拆成路径列表，并自动忽略空字符串。"""
    if not x:
        return []
    return [p.strip() for p in str(x).split(",") if p.strip()]


def _read_text_if_exists(path: str) -> str:
    """在文件存在时读取文本内容；文件缺失时返回空字符串，避免主流程报错。"""
    if not path or not Path(path).exists():
        return ""
    return Path(path).read_text(encoding="utf-8", errors="ignore")



def _parse_memref_shape_dtype(memref_body: str) -> Tuple[List[int], str, Optional[int]]:
    """解析 memref 的静态形状、dtype 和字节大小，作为 MLIR 结构抽取的基础。"""
    body0 = memref_body.split(",")[0].strip()
    parts = [p.strip() for p in body0.split("x") if p.strip()]
    if len(parts) < 2:
        return [], "unknown", None
    dtype = parts[-1]
    dims: List[int] = []
    for d in parts[:-1]:
        if not d.isdigit():
            return [], dtype, None
        dims.append(int(d))
    if dtype not in DTYPE_BYTES:
        return dims, dtype, None
    return dims, dtype, _prod(dims) * DTYPE_BYTES[dtype]


def _extract_named_memrefs(text: str) -> List[Dict[str, Any]]:
    """从 HIVM MLIR 中抽取带 SSA 名字的 memref 使用和分配记录。"""
    out: List[Dict[str, Any]] = []
    seen = set()
    lines = text.splitlines()
    ref_re = re.compile(r"%([A-Za-z0-9_]+)\s*(?:=\s*memref\.alloc\(\)\s*)?:\s*memref<([^>]+?)#hivm\.address_space<([a-zA-Z0-9_]+)>[^>]*>")
    for i, line in enumerate(lines):
        for m in ref_re.finditer(line):
            name, body, space = m.group(1), m.group(2), _norm_space(m.group(3))
            dims, dtype, size = _parse_memref_shape_dtype(body)
            item = {
                "name": name,
                "space": space,
                "dims": dims,
                "dtype": dtype,
                "size_bytes_static": size,
                "line": i,
                "is_alloc": "memref.alloc" in line and line.strip().startswith(f"%{name}"),
            }
            key = (item["name"], item["space"], tuple(item["dims"]), item["dtype"], item["line"], item["is_alloc"])
            if key not in seen:
                seen.add(key)
                out.append(item)
    return out


def _extract_cube_shape_evidence(text: str) -> List[Dict[str, Any]]:
    """从 mmad 类 Cube 算子行中抽取输入输出形状，并尽量推断 tile_m/tile_n/tile_k。"""
    out: List[Dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines()):
        if "hivm.hir.mmad" not in line:
            continue
        shapes = []
        for body in re.findall(r"memref<([^>]+?)#hivm\.address_space<([a-zA-Z0-9_]+)>[^>]*>", line):
            dims, dtype, size = _parse_memref_shape_dtype(body[0])
            if dims:
                shapes.append({"dims": dims, "dtype": dtype, "space": _norm_space(body[1]), "size_bytes": size})
        inferred = {}
        if len(shapes) >= 3:
            a, b, c = shapes[0], shapes[1], shapes[-1]
            if len(c["dims"]) >= 2:
                inferred["tile_m"] = c["dims"][0]
                inferred["tile_n"] = c["dims"][1]
            # 常见 Cube 约定会把 K/reduce 维放在 A 或 B 的第二维。
            if len(a["dims"]) >= 2:
                inferred["tile_k"] = a["dims"][1]
            elif len(b["dims"]) >= 2:
                inferred["tile_k"] = b["dims"][1]
        out.append({"line": line_no, "shapes": shapes, "inferred_tile": inferred})
    return out


def _infer_generic_hivm_structure(text: str, named_memrefs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """基于 memref、Cube 形状和命名习惯推断输入 IR 的通用 HIVM 结构证据。"""
    by_name: Dict[str, Dict[str, Any]] = {}
    for m in named_memrefs:
        if m.get("dims") and m["name"] not in by_name:
            by_name[m["name"]] = m

    by_space: Dict[str, List[Dict[str, Any]]] = {}
    for m in named_memrefs:
        by_space.setdefault(str(m.get("space", "unknown")), []).append({
            "name": m.get("name"), "dims": m.get("dims"), "dtype": m.get("dtype"),
            "is_alloc": m.get("is_alloc", False), "size_bytes_static": m.get("size_bytes_static"),
        })

    cube_shapes = _extract_cube_shape_evidence(text)
    candidate_tiles = []
    for e in cube_shapes:
        t = e.get("inferred_tile") or {}
        if t.get("tile_m") and t.get("tile_n") and t.get("tile_k"):
            candidate_tiles.append(t)

    conventional = {}
    def dims(name: str) -> List[int]:
        """从已解析的命名 memref 表中安全读取指定张量的维度。"""
        return list(by_name.get(name, {}).get("dims", []) or [])
    q, k, v, o = dims("Q_gm"), dims("K_gm"), dims("V_gm"), dims("O_gm")
    if len(q) >= 2 or len(k) >= 2 or len(v) >= 2:
        conventional = {
            "detected": True,
            "Q_gm": q, "K_gm": k, "V_gm": v, "O_gm": o,
            "note": "name-based conventional tensor signature; used as evidence only, not a hard-coded kernel family",
        }
    else:
        conventional = {"detected": False}

    loop_trip = None
    trip_m = re.search(r"@trip\s*=\s*(\d+)", text)
    if trip_m:
        loop_trip = int(trip_m.group(1))

    primary_tile = candidate_tiles[0] if candidate_tiles else {}
    return {
        "detected": bool(named_memrefs or cube_shapes),
        "logical_axes": ["axis_m", "axis_n", "axis_k"],
        "candidate_tiles_from_cube_ops": candidate_tiles,
        "primary_tile_candidate": primary_tile,
        "cube_shape_evidence": cube_shapes[:20],
        "memrefs_by_space_detail": {k: v[:80] for k, v in by_space.items()},
        "conventional_tensor_signature": conventional,
        "loop_trip_annotation": loop_trip,
    }

def _detect_ping_pong_buffers(named_memrefs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """识别 *_ping/*_pong 命名的局部 buffer 对，作为 double buffer/multibuffer 的静态证据。"""
    allocs = [m for m in named_memrefs if m.get("is_alloc")]
    by_base: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for m in allocs:
        name = str(m.get("name", ""))
        mm = re.match(r"(.+?)_(ping|pong)$", name)
        if not mm:
            continue
        base, role = mm.group(1), mm.group(2)
        by_base.setdefault(base, {})[role] = m
    pairs: List[Dict[str, Any]] = []
    for base, d in by_base.items():
        if "ping" in d and "pong" in d:
            a, b = d["ping"], d["pong"]
            same = (a.get("space") == b.get("space") and a.get("dims") == b.get("dims") and a.get("dtype") == b.get("dtype"))
            pairs.append({
                "base": base,
                "ping": a.get("name"),
                "pong": b.get("name"),
                "space": a.get("space"),
                "dims": a.get("dims"),
                "dtype": a.get("dtype"),
                "size_bytes_each": a.get("size_bytes_static"),
                "total_pair_bytes": (a.get("size_bytes_static") or 0) + (b.get("size_bytes_static") or 0),
                "same_shape_scope": same,
                "evidence": "*_ping/*_pong named local buffers",
            })
    return pairs


def _extract_event_sync_pairs(text: str) -> List[Dict[str, Any]]:
    """解析 wait_flag/set_flag 的 event id 和 pipe 信息，构造同步事件配对证据。"""
    waits: Dict[str, List[Dict[str, Any]]] = {}
    sets: Dict[str, List[Dict[str, Any]]] = {}
    pat = re.compile(r"hivm\.hir\.(wait_flag|set_flag)\s*\{([^}]*)\}")
    for m in pat.finditer(text):
        kind, attrs = m.group(1), m.group(2)
        pipe_m = re.search(r"pipe\s*=\s*\"?([A-Za-z0-9_]+)\"?", attrs)
        event_m = re.search(r"event\s*=\s*\"?([A-Za-z0-9_]+)\"?", attrs)
        item = {"kind": kind, "pipe": pipe_m.group(1) if pipe_m else None, "event_id": event_m.group(1) if event_m else None}
        if not item["event_id"]:
            continue
        (waits if kind == "wait_flag" else sets).setdefault(item["event_id"], []).append(item)
    pairs: List[Dict[str, Any]] = []
    for eid in sorted(set(waits) | set(sets)):
        for w in waits.get(eid, []) or [None]:
            for s in sets.get(eid, []) or [None]:
                pairs.append({
                    "event_id": eid,
                    "wait_pipe": w.get("pipe") if isinstance(w, dict) else None,
                    "set_pipe": s.get("pipe") if isinstance(s, dict) else None,
                    "has_wait": isinstance(w, dict),
                    "has_set": isinstance(s, dict),
                })
    return pairs


def _detect_cv_op_sequence(text: str) -> Dict[str, Any]:
    """分析 HIVM-HIR 算子序列，判断是否存在 Cube-Vector 交替流水的候选结构。"""
    ops = re.findall(r"hivm\.hir\.([A-Za-z0-9_]+)\b", text)
    cube_ops = [op for op in ops if op in {"mmad", "mmadL1"}]
    vector_ops = [op for op in ops if op.startswith("v") or op in {"vreduce", "vsub", "vexp", "vdiv", "vcmp", "vsel"}]
    fix_ops = [op for op in ops if op == "fixpipe"]
    layout_ops = [op for op in ops if op in {"nd2nz", "nz2nd", "copy"}]
    # 检测通用 HIVM C/V 序列：cube/fix -> vector 算子 -> layout -> cube/fix。
    seq_str = " ".join(ops)
    cube_vector_layout_cube = bool(re.search(r"mmad\s+fixpipe.*v(reduce|sub|exp|div|mul|add).*nd2nz.*mmad\s+fixpipe", seq_str))
    return {
        "num_ops": len(ops),
        "cube_ops": cube_ops,
        "vector_ops": vector_ops,
        "fixpipe_ops": fix_ops,
        "layout_ops": layout_ops,
        "cv_pipeline_candidate": bool(cube_ops and vector_ops),
        "cube_vector_layout_cube_sequence": cube_vector_layout_cube,
        "separability_status": "estimated_from_op_sequence" if cube_ops and vector_ops else "not_applicable",
        "op_sequence_prefix": ops[:80],
    }


def _extract_scalar_family_counts(text: str) -> Dict[str, int]:
    """统计 MLIR 中 scalar/control/address 类操作。只基于 IR 文本，不使用实机 profiling。"""
    return {
        "arith_scalar": len(re.findall(r"\barith\.(?:addi|subi|muli|divsi|remsi|cmpi|andi|ori|xori|shli|shrsi|shrui)\b", text)),
        "index_cast": len(re.findall(r"\b(?:arith\.)?index_cast\b", text)),
        "reinterpret_cast": len(re.findall(r"\breinterpret_cast\b", text)),
        "pointer_cast": len(re.findall(r"(?:hivm\.hir\.|hivm\.)pointer_cast\b", text)),
        "apply": len(re.findall(r"\b(?:affine\.)?apply\b|(?:hivm\.hir\.|hivm\.)apply\b", text)),
        "scalar_load": len(re.findall(r"\bmemref\.load\b|(?:hivm\.hir\.|hivm\.)load\b", text)),
        "scf_for": len(re.findall(r"\bscf\.for\b", text)),
        "scf_if": len(re.findall(r"\bscf\.if\b", text)),
        "get_block_idx": len(re.findall(r"(?:hivm\.hir\.|hivm\.)get_block_idx\b", text)),
        "set_mask_norm": len(re.findall(r"(?:hivm\.hir\.|hivm\.)set_mask_norm\b", text)),
        "set_ffts_base_addr": len(re.findall(r"(?:hivm\.hir\.|hivm\.)set_ffts_base_addr\b", text)),
    }


def _line_op_category(line: str) -> Optional[str]:
    """把 MLIR 行粗分类为 compute/memory/vector/scalar/sync，用于 loop-weighted 统计。"""
    l = line.lower()
    if any(k in l for k in ["set_flag", "wait_flag", "pipe_barrier", "sync_block"]):
        return "sync"
    if any(k in l for k in ["mmad", "mmadl1"]):
        return "compute"
    if any(k in l for k in ["copy", "nd2nz", "nz2nd", "fixpipe", "memref.store"]):
        return "memory"
    if re.search(r"hivm\.hir\.v[a-z0-9_]+\b", l):
        return "vector"
    if any(k in l for k in ["arith.", "index_cast", "reinterpret_cast", "pointer_cast", "affine.apply", "memref.load", "get_block_idx", "set_mask_norm"]):
        return "scalar"
    return None


def _extract_loop_weighted_features(text: str) -> Dict[str, Any]:
    """提取 loop-depth 加权 op 计数。内层循环中的 op 对 cost 更敏感，因此比 flat count 更有价值。"""
    weighted = {"compute": 0.0, "memory": 0.0, "vector": 0.0, "scalar": 0.0, "sync": 0.0}
    flat = {k: 0 for k in weighted}
    inner_loop_counts = {k: 0 for k in weighted}
    depth = 0
    max_depth = 0
    for line in text.splitlines():
        close_before = line.count("}")
        depth = max(0, depth - close_before)
        cat = _line_op_category(line)
        if cat:
            flat[cat] += 1
            w = 1.0 + min(depth, 5) * 0.65
            weighted[cat] += w
            if depth >= 1:
                inner_loop_counts[cat] += 1
        if "scf.for" in line or "scf.if" in line:
            # scf 控制本身也是 scalar/control 开销。
            weighted["scalar"] += 1.0 + min(depth, 5) * 0.70
            flat["scalar"] += 1
        depth += line.count("{")
        max_depth = max(max_depth, depth)
    total_weighted = sum(weighted.values()) or 1.0
    return {
        "max_loop_depth": int(max_depth),
        "flat_counts_by_component": flat,
        "loop_weighted_counts_by_component": {k: round(v, 4) for k, v in weighted.items()},
        "inner_loop_counts_by_component": inner_loop_counts,
        "loop_weighted_ratios": {k: round(v / total_weighted, 6) for k, v in weighted.items()},
        "inner_loop_sync_count": int(inner_loop_counts.get("sync", 0)),
        "inner_loop_scalar_count": int(inner_loop_counts.get("scalar", 0)),
    }


def _extract_memory_path_features(text: str) -> Dict[str, Any]:
    """从含 memref 类型的行中估计空间路径 traffic，不使用任何实测耗时。"""
    path_counts: Dict[str, int] = {}
    path_bytes: Dict[str, float] = {}
    op_bytes = {"copy": 0.0, "nd2nz": 0.0, "fixpipe": 0.0, "load_store": 0.0}
    for line in text.splitlines():
        if not any(k in line for k in ["copy", "nd2nz", "fixpipe", "load", "store", "memref.load", "memref.store"]):
            continue
        items = []
        for body, space in re.findall(r"memref<([^>]+?)#hivm\.address_space<([a-zA-Z0-9_]+)>[^>]*>", line):
            dims, dtype, size = _parse_memref_shape_dtype(body)
            items.append((_norm_space(space), int(size or 0)))
        if len(items) >= 2:
            src, dst = items[0][0], items[-1][0]
            b = max(x[1] for x in items) if any(x[1] for x in items) else 0
            key = f"{src}->{dst}"
            path_counts[key] = path_counts.get(key, 0) + 1
            path_bytes[key] = path_bytes.get(key, 0.0) + float(b)
        lname = line.lower()
        bline = max([x[1] for x in items], default=0)
        if "nd2nz" in lname:
            op_bytes["nd2nz"] += bline
        elif "fixpipe" in lname:
            op_bytes["fixpipe"] += bline
        elif "copy" in lname:
            op_bytes["copy"] += bline
        elif "load" in lname or "store" in lname:
            op_bytes["load_store"] += bline
    total = sum(path_bytes.values())
    return {
        "path_counts": path_counts,
        "path_bytes": {k: int(v) for k, v in path_bytes.items()},
        "op_bytes": {k: int(v) for k, v in op_bytes.items()},
        "total_path_bytes": int(total),
        "gm_related_bytes": int(sum(v for k, v in path_bytes.items() if "gm" in k)),
        "l0_l1_related_bytes": int(sum(v for k, v in path_bytes.items() if "l0" in k or "l1" in k)),
    }


def _extract_buffer_lifetime_features(buffers: List[BufferInfo]) -> Dict[str, Any]:
    """基于静态 buffer gen/kill 估计 live range、reuse pressure 和 per-buffer multibuffer 价值。"""
    by_space: Dict[str, Dict[str, float]] = {}
    candidates = []
    for b in buffers:
        span = max(1, int(b.kill) - int(b.gen) + 1)
        d = by_space.setdefault(b.space, {"count": 0, "bytes": 0, "span_sum": 0, "byte_span_sum": 0, "max_span": 0})
        d["count"] += 1
        d["bytes"] += int(b.size_bytes)
        d["span_sum"] += span
        d["byte_span_sum"] += int(b.size_bytes) * span
        d["max_span"] = max(d["max_span"], span)
        if b.space in {"ub", "l1"} and b.size_bytes > 0:
            benefit = math.log1p(span) * math.log1p(b.size_bytes / 1024.0)
            candidates.append({"name": b.name, "space": b.space, "size_bytes": int(b.size_bytes), "live_span": int(span), "double_buffer_benefit_proxy": round(float(benefit), 4)})
    for d in by_space.values():
        d["avg_span"] = float(d["span_sum"] / max(1, d["count"]))
    candidates = sorted(candidates, key=lambda x: x["double_buffer_benefit_proxy"], reverse=True)[:20]
    return {"by_space": by_space, "top_double_buffer_candidates": candidates, "num_candidate_buffers": len(candidates)}


def _extract_sync_criticality_features(text: str, event_pairs: List[Dict[str, Any]], loop_weighted: Dict[str, Any]) -> Dict[str, Any]:
    """估计同步是否可能落在高频/内层/跨 pipe 路径上。"""
    pair_count = len(event_pairs or [])
    missing_pairs = sum(1 for p in event_pairs if not (p.get("has_wait") and p.get("has_set"))) if event_pairs else 0
    cross_pipe_pairs = sum(1 for p in event_pairs if p.get("wait_pipe") and p.get("set_pipe") and p.get("wait_pipe") != p.get("set_pipe")) if event_pairs else 0
    sync_counts = count_hivm_ops(text, ["set_flag", "wait_flag", "pipe_barrier", "sync_block_set", "sync_block_wait"])
    total_sync = sum(sync_counts.values())
    inner_sync = int((loop_weighted or {}).get("inner_loop_sync_count", 0) or 0)
    criticality = 0.0
    if total_sync:
        criticality += min(1.0, inner_sync / max(1.0, total_sync)) * 0.45
        criticality += min(1.0, cross_pipe_pairs / max(1.0, pair_count)) * 0.35 if pair_count else 0.0
        criticality += min(1.0, missing_pairs / max(1.0, pair_count)) * 0.20 if pair_count else 0.0
    return {
        "sync_counts": sync_counts,
        "total_sync_ops": int(total_sync),
        "inner_loop_sync_count": int(inner_sync),
        "event_pair_count": int(pair_count),
        "missing_set_or_wait_pairs": int(missing_pairs),
        "cross_pipe_event_pairs": int(cross_pipe_pairs),
        "sync_criticality_proxy": round(float(min(1.0, criticality)), 6),
    }


def _extract_alignment_tail_features(text: str, named_memrefs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """估计 shape 对齐、tail/mask 和潜在 bank conflict proxy。"""
    dim_total = 0
    dim_bad16 = 0
    for m in named_memrefs:
        for d in m.get("dims", []) or []:
            if isinstance(d, int) and d > 1:
                dim_total += 1
                if d % 16 != 0:
                    dim_bad16 += 1
    masks = len(re.findall(r"\bmask\b|set_mask_norm|vcmp|vsel", text))
    storage_aligned = len(re.findall(r"hivm\.storage_aligned", text))
    offsets = [int(x) for x in re.findall(r"(?:offset|byte_offset|base_offset)\s*=\s*(-?\d+)", text) if x.lstrip("-").isdigit()]
    bad_offsets = sum(1 for x in offsets if x % 32 != 0)
    return {
        "dim_total": int(dim_total),
        "dim_not_multiple_of_16": int(dim_bad16),
        "dim_misalignment_ratio": round(dim_bad16 / max(1, dim_total), 6),
        "mask_or_tail_ops": int(masks),
        "storage_aligned_annotations": int(storage_aligned),
        "offset_count": int(len(offsets)),
        "offset_not_32B_aligned": int(bad_offsets),
        "offset_misalignment_ratio": round(bad_offsets / max(1, len(offsets)), 6),
    }


def _extract_sequence_pattern_features(text: str) -> Dict[str, Any]:
    """提取 copy/layout/cube/vector/sync 的序列 pattern，用于 CVPipeline 与 layout cost 判断。"""
    ops = re.findall(r"(?:hivm\.hir\.|hivm\.)([A-Za-z0-9_]+)\b", text)
    seq = " ".join(ops)
    patterns = {
        "copy_nd2nz_mmad": len(re.findall(r"copy(?:\s+\w+){0,8}\s+nd2nz(?:\s+\w+){0,8}\s+mmadL?1?", seq)),
        "mmad_fixpipe_vector": len(re.findall(r"mmadL?1?(?:\s+\w+){0,8}\s+fixpipe(?:\s+\w+){0,12}\s+v\w+", seq)),
        "vector_to_store": len(re.findall(r"v\w+(?:\s+\w+){0,10}\s+(?:copy|store)", seq)),
        "sync_dense_pair": len(re.findall(r"set_flag\s+wait_flag|wait_flag\s+set_flag|pipe_barrier\s+pipe_barrier", seq)),
    }
    cv_opportunity = 0.0
    if patterns["copy_nd2nz_mmad"]:
        cv_opportunity += 0.25
    if patterns["mmad_fixpipe_vector"]:
        cv_opportunity += 0.35
    if patterns["vector_to_store"]:
        cv_opportunity += 0.20
    if patterns["sync_dense_pair"]:
        cv_opportunity -= 0.15
    return {"patterns": patterns, "cv_pipeline_opportunity_proxy": round(max(0.0, min(1.0, cv_opportunity)), 6), "op_sequence_len": len(ops)}

def extract_source_meta(paths: List[str]) -> Dict[str, Any]:
    """从可选 Python/Triton 源文件中抽取 BLOCK、pipeline、sync、multibuffer 等元参数。"""
    meta: Dict[str, Any] = {"files": [], "assignments": {}, "block_params": {}, "pipeline_params": {}, "sync_params": {}, "multibuffer_params": {}}
    for path in paths:
        text = _read_text_if_exists(path)
        if not text:
            continue
        meta["files"].append(str(Path(path)))
        assign_re = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^#\n]+)", re.MULTILINE)
        for name, raw in assign_re.findall(text):
            val_raw = raw.strip().rstrip(",")
            val: Any = val_raw
            if val_raw in {"True", "False"}:
                val = (val_raw == "True")
            else:
                m = re.match(r"[-+]?\d+", val_raw)
                if m and m.group(0) == val_raw:
                    val = int(val_raw)
            # 避免用后续的关键字转发表达式（如 BLOCK_G=BLOCK_G）覆盖已经解析到的具体赋值（如 BLOCK_G=16）。
            if not (isinstance(val, str) and val == name and name in meta["assignments"]):
                meta["assignments"][name] = val
            else:
                val = meta["assignments"].get(name, val)
            lname = name.lower()
            if name.startswith("BLOCK_"):
                meta["block_params"][name] = val
            if "tile_mix" in lname or "cv" in lname or "pipeline" in lname:
                meta["pipeline_params"][name] = val
            if "sync" in lname or "barrier" in lname or "event" in lname:
                meta["sync_params"][name] = val
            if "multibuffer" in lname or "double_buffer" in lname:
                meta["multibuffer_params"][name] = val
        for key in ["BLOCK_G", "BLOCK_SBS", "BLOCK_K", "BLOCK_V", "tile_mix_cube_loop", "tile_mix_vector_loop", "enable_mixed_cv", "enable_hivm_auto_cv_balance", "multibuffer", "inject_barrier_all"]:
            if key in text and key not in meta["assignments"]:
                meta.setdefault("mentioned_keys", []).append(key)
    return meta


def extract_mlir_evidence(path: str) -> Dict[str, Any]:
    """从输入 MLIR 中抽取候选空间生成、硬件边界检查和报告展示所需的结构证据。"""
    text = _read_text_if_exists(path)
    if not text:
        return {"available": False}
    memrefs: List[Dict[str, Any]] = []
    for m in re.finditer(r"memref<([^>]+?)#hivm\.address_space<([a-zA-Z0-9_]+)>[^>]*>", text):
        body, space = m.group(1), _norm_space(m.group(2))
        dims, dtype, size = _parse_memref_shape_dtype(body)
        memrefs.append({"shape_body": body.strip(), "space": space, "dims": dims, "dtype": dtype, "size_bytes_static": size})
    named_memrefs = _extract_named_memrefs(text)
    alloc_memrefs = [m for m in named_memrefs if m.get("is_alloc")]
    unique_alloc_bytes_by_space: Dict[str, int] = {}
    unique_alloc_count_by_space: Dict[str, int] = {}
    for m in alloc_memrefs:
        sp = str(m.get("space", ""))
        unique_alloc_count_by_space[sp] = unique_alloc_count_by_space.get(sp, 0) + 1
        unique_alloc_bytes_by_space[sp] = unique_alloc_bytes_by_space.get(sp, 0) + int(m.get("size_bytes_static") or 0)

    op_counts = count_hivm_ops(text, ["set_flag", "wait_flag", "pipe_barrier", "sync_block_set", "sync_block_wait", "nd2nz", "mmadL1", "mmad", "fixpipe", "load", "store", "copy", "vreduce", "vsub", "vexp", "vdiv"])
    # 结构性 scalar/control 证据：只来自 MLIR 文本，不使用任何实测 profiling target。
    # 这类操作往往不会出现在 hivm.hir.* 计数里，但对 chunk/prefill 这类 kernel 的
    # 地址计算、循环控制和同步开销非常关键。
    scalar_family_counts = _extract_scalar_family_counts(text)
    offset_values = [int(x) for x in re.findall(r"(?:offset|byte_offset|base_offset)\s*=\s*(-?\d+)", text) if x.lstrip("-").isdigit()]
    buffers = _parse_static_buffers(text)
    static_max_live = _static_max_live(buffers)
    generic_structure = _infer_generic_hivm_structure(text, named_memrefs)
    ping_pong_pairs = _detect_ping_pong_buffers(named_memrefs)
    event_pairs = _extract_event_sync_pairs(text)
    cv_sequence = _detect_cv_op_sequence(text)
    loop_weighted_features = _extract_loop_weighted_features(text)
    memory_path_features = _extract_memory_path_features(text)
    buffer_lifetime_features = _extract_buffer_lifetime_features(buffers)
    sync_criticality_features = _extract_sync_criticality_features(text, event_pairs, loop_weighted_features)
    alignment_tail_features = _extract_alignment_tail_features(text, named_memrefs)
    sequence_pattern_features = _extract_sequence_pattern_features(text)
    advanced_mlir_features = {
        "loop_weighted": loop_weighted_features,
        "memory_path": memory_path_features,
        "buffer_lifetime": buffer_lifetime_features,
        "sync_criticality": sync_criticality_features,
        "alignment_tail": alignment_tail_features,
        "sequence_patterns": sequence_pattern_features,
    }
    return {
        "available": True,
        "file": str(Path(path)),
        "num_lines": len(text.splitlines()),
        "op_counts": op_counts,
        "scalar_family_counts": scalar_family_counts,
        "hivm_multi_buffer_annotations": len(re.findall(r"hivm\.multi_buffer\s*=\s*\d+", text)),
        "hivm_part_of_mix": len(re.findall(r"hivm\.part_of_mix", text)),
        "hivm_storage_aligned": len(re.findall(r"hivm\.storage_aligned", text)),
        "memrefs_by_space": {sp: sum(1 for x in memrefs if x["space"] == sp) for sp in sorted({x["space"] for x in memrefs})},
        "static_memref_bytes_by_space": {sp: sum((x.get("size_bytes_static") or 0) for x in memrefs if x["space"] == sp) for sp in sorted({x["space"] for x in memrefs})},
        "unique_alloc_count_by_space": unique_alloc_count_by_space,
        "unique_alloc_bytes_by_space": unique_alloc_bytes_by_space,
        "static_max_live_bytes_by_space": static_max_live,
        "sample_memrefs": memrefs[:30],
        "sample_named_memrefs": named_memrefs[:60],
        "max_pointer_offset_hint": max(offset_values) if offset_values else None,
        "has_cube_ops": (op_counts.get("mmadL1", 0) + op_counts.get("mmad", 0)) > 0,
        "has_vector_or_fix_ops": bool(re.search(r"hivm\.hir\.(v[a-zA-Z0-9_]+|fixpipe)", text)),
        "generic_hivm_structure": generic_structure,
        "ping_pong_pairs": ping_pong_pairs,
        "event_sync_pairs": event_pairs,
        "cv_op_sequence": cv_sequence,
        "advanced_mlir_features": advanced_mlir_features,
    }

def extract_des_evidence(paths: List[str]) -> Dict[str, Any]:
    """从可选 DES JSON 中抽取 pipe、DMA、同步和 multibuffer 统计，用于 cost audit。"""
    prof = load_desgraph_profile(paths)
    if not prof:
        return {"available": False}
    total_duration = sum(prof.pipe_duration.values()) or 1.0
    pipe_fraction = {k: v / total_duration for k, v in prof.pipe_duration.items()}
    critical_pipe = max(prof.pipe_duration.items(), key=lambda kv: kv[1])[0] if prof.pipe_duration else None
    sync_counts: Dict[str, int] = {}
    space_bytes: Dict[str, float] = {}
    multibuffer_slots: Dict[str, int] = {}
    for file in prof.source_files:
        data = load_json(file)
        for op in data.get("operations", []) if isinstance(data, dict) else []:
            if not isinstance(op, dict):
                continue
            name = str(op.get("name", ""))
            lname = name.lower()
            if any(k in lname for k in ["set_flag", "wait_flag", "pipe_barrier", "sync_block_set", "sync_block_wait"]):
                sync_counts[name] = sync_counts.get(name, 0) + 1
            src, dst = str(op.get("src_space", "") or ""), str(op.get("dst_space", "") or "")
            b = _num(op.get("bytes", 0.0)) * _num(op.get("loop_multiplier", 1.0), 1.0)
            if b and (src or dst):
                key = f"{_norm_space(src) if src else 'unknown'}->{_norm_space(dst) if dst else 'unknown'}"
                space_bytes[key] = space_bytes.get(key, 0.0) + b
            slots = int(_num(op.get("multi_buffer_slots", 1), 1))
            multibuffer_slots[str(slots)] = multibuffer_slots.get(str(slots), 0) + 1
    return {
        "available": True,
        "files": prof.source_files,
        "num_operations": prof.num_operations,
        "pipe_duration": prof.pipe_duration,
        "pipe_fraction": pipe_fraction,
        "critical_pipe": critical_pipe,
        "pipe_bytes": prof.pipe_bytes,
        "pipe_flops": prof.pipe_flops,
        "sync_ops": prof.sync_ops,
        "barrier_ops": prof.barrier_ops,
        "sync_counts_by_name": sync_counts,
        "dma_bytes_by_space_path": space_bytes,
        "multi_buffer_slots_histogram": multibuffer_slots,
        "dependency_edges": prof.dependency_edges,
        "top_ops_by_duration": prof.top_ops_by_duration,
        "schema_fields": prof.schema_fields,
    }


def extract_trace_evidence(paths: List[str]) -> Dict[str, Any]:
    """从可选 trace JSON 中抽取运行阶段、事件数量和耗时摘要，用于辅助审计。"""
    events = 0
    named: Dict[str, int] = {}
    files: List[str] = []
    for path in paths:
        if not path or not Path(path).exists():
            continue
        files.append(str(Path(path)))
        try:
            data = load_json(path)
        except Exception:
            continue
        arr = data.get("traceEvents", []) if isinstance(data, dict) else data
        if isinstance(arr, list):
            events += len(arr)
            for ev in arr[:50000]:
                if isinstance(ev, dict):
                    name = str(ev.get("name", ""))[:80]
                    if name:
                        named[name] = named.get(name, 0) + 1
    return {"available": bool(files), "files": files, "num_events": events, "top_event_names": sorted(named.items(), key=lambda kv: kv[1], reverse=True)[:20]}


def build_artifact_profile(kernel_path: str, des_paths: List[str], trace_paths: List[str], deprecated_source_paths: Optional[List[str]] = None) -> ArtifactProfile:
    """合并 MLIR、DES、trace 和源代码元信息，形成统一的 artifact profile。"""
    """Build optional artifact evidence for V3.3.

    V3.3 keeps JSON artifacts as the only structured optional
    inputs. Python/Triton kernel source files are not parsed as inputs because
    source code is not a stable schema; optimization ideas from known source
    examples are captured as built-in, documented templates instead.
    """
    source_meta: Dict[str, Any] = {
        "files": [],
        "deprecated_ignored_source_files": [str(Path(x)) for x in (deprecated_source_paths or []) if x],
        "note": "Python/Triton source files are not parsed in V3.3. Use --artifact-des-graph/--artifact-trace JSON inputs; source-derived ideas are built into templates manually.",
    }
    mlir = extract_mlir_evidence(kernel_path)
    des = extract_des_evidence(des_paths)
    trace = extract_trace_evidence(trace_paths)
    files: List[str] = []
    for group in [[kernel_path] if kernel_path else [], des.get("files", []), trace.get("files", [])]:
        files.extend([str(x) for x in group if x])
    coverage = {
        "has_source_meta": False,
        "has_mlir": bool(mlir.get("available")),
        "has_des": bool(des.get("available")),
        "has_trace": bool(trace.get("available")),
        "parameter_space_evidence": ["mlir" if mlir.get("available") else None, "des" if des.get("available") else None, "trace" if trace.get("available") else None],
        "hardware_boundary_evidence": ["mlir_address_space" if mlir.get("available") else None, "des_dma_paths" if des.get("available") else None],
        "cost_model_evidence": ["des_pipe_duration" if des.get("available") else None, "des_sync_counts" if des.get("available") else None, "trace_events" if trace.get("available") else None],
        "source_input_policy": "Python/Triton source is not accepted as structured input; deprecated --source is ignored.",
    }
    for k in list(coverage.keys()):
        if isinstance(coverage[k], list):
            coverage[k] = [x for x in coverage[k] if x]
    return ArtifactProfile(sorted(set(files)), source_meta, mlir, des, trace, coverage)



def _safe_ratio_dict(scores: Dict[str, float]) -> Dict[str, float]:
    """把非负 score 字典归一化为比例；全 0 时返回均匀的保守比例。"""
    clean = {str(k): max(0.0, float(v or 0.0)) for k, v in scores.items()}
    total = sum(clean.values())
    if total <= 1e-9:
        keys = list(clean.keys()) or ["compute", "memory", "vector", "scalar", "sync"]
        return {k: 1.0 / len(keys) for k in keys}
    return {k: v / total for k, v in clean.items()}


def build_kernel_cost_profile(kf: KernelFeatures, artifact: Dict[str, Any], *, enabled: bool = True) -> Dict[str, Any]:
    """基于 MLIR 与编译产物 JSON 构造 kernel-aware cost profile。

    重要边界：这个 profile 不使用 DES makespan、端到端耗时或 msprof 目标，
    只使用输入 IR 与产物文件中的结构证据，例如 op counts、pipe mix、trace event
    name count、DMA path 和同步计数。它的作用是让 analytical cost model 的分项权重
    随 kernel 结构变化，而不是做 profiling target calibration。
    """
    if not enabled:
        return {"enabled": False, "reason": "artifact kernel cost profile disabled"}
    artifact = artifact if isinstance(artifact, dict) else {}
    mlir = artifact.get("mlir_evidence", {}) if isinstance(artifact.get("mlir_evidence", {}), dict) else {}
    des = artifact.get("des_evidence", {}) if isinstance(artifact.get("des_evidence", {}), dict) else {}
    trace = artifact.get("trace_evidence", {}) if isinstance(artifact.get("trace_evidence", {}), dict) else {}

    op = mlir.get("op_counts", {}) if isinstance(mlir.get("op_counts", {}), dict) else {}
    scalar_counts = mlir.get("scalar_family_counts", {}) if isinstance(mlir.get("scalar_family_counts", {}), dict) else {}
    advanced = mlir.get("advanced_mlir_features", {}) if isinstance(mlir.get("advanced_mlir_features", {}), dict) else {}
    loop_weighted = advanced.get("loop_weighted", {}) if isinstance(advanced.get("loop_weighted", {}), dict) else {}
    loop_counts = loop_weighted.get("loop_weighted_counts_by_component", {}) if isinstance(loop_weighted.get("loop_weighted_counts_by_component", {}), dict) else {}
    memory_path = advanced.get("memory_path", {}) if isinstance(advanced.get("memory_path", {}), dict) else {}
    sync_criticality = advanced.get("sync_criticality", {}) if isinstance(advanced.get("sync_criticality", {}), dict) else {}
    alignment_tail = advanced.get("alignment_tail", {}) if isinstance(advanced.get("alignment_tail", {}), dict) else {}
    buffer_lifetime = advanced.get("buffer_lifetime", {}) if isinstance(advanced.get("buffer_lifetime", {}), dict) else {}
    seq_patterns = advanced.get("sequence_patterns", {}) if isinstance(advanced.get("sequence_patterns", {}), dict) else {}
    trace_top = dict(trace.get("top_event_names", []) or []) if isinstance(trace.get("top_event_names", []), list) else {}

    compute_score = 18.0 * float(op.get("mmadL1", 0) or 0) + 14.0 * float(op.get("mmad", 0) or 0)
    compute_score += 2.5 * float(loop_counts.get("compute", 0.0) or 0.0)
    memory_score = (
        7.0 * float(op.get("copy", 0) or 0)
        + 8.0 * float(op.get("nd2nz", 0) or 0)
        + 5.0 * float(op.get("fixpipe", 0) or 0)
        + 2.0 * float(op.get("load", 0) or 0)
        + 2.0 * float(op.get("store", 0) or 0)
    )
    memory_score += 0.0025 * min(float(memory_path.get("total_path_bytes", 0) or 0), 2_000_000.0)
    memory_score += 2.2 * float(loop_counts.get("memory", 0.0) or 0.0)
    vector_score = 3.0 * float(sum((kf.vector_op_counts or {}).values())) + 1.8 * float(loop_counts.get("vector", 0.0) or 0.0)
    scalar_score = (
        1.0 * float(scalar_counts.get("arith_scalar", 0) or 0)
        + 1.0 * float(scalar_counts.get("index_cast", 0) or 0)
        + 1.2 * float(scalar_counts.get("reinterpret_cast", 0) or 0)
        + 1.6 * float(scalar_counts.get("pointer_cast", 0) or 0)
        + 1.3 * float(scalar_counts.get("apply", 0) or 0)
        + 0.8 * float(scalar_counts.get("scalar_load", 0) or 0)
        + 10.0 * float(scalar_counts.get("scf_for", 0) or 0)
        + 6.0 * float(scalar_counts.get("scf_if", 0) or 0)
        + 3.0 * float(scalar_counts.get("get_block_idx", 0) or 0)
        + 2.0 * float(scalar_counts.get("set_mask_norm", 0) or 0)
        + 2.0 * float(scalar_counts.get("set_ffts_base_addr", 0) or 0)
    )
    scalar_score += 0.55 * float(loop_counts.get("scalar", 0.0) or 0.0)
    scalar_score += 12.0 * float(loop_weighted.get("max_loop_depth", 0) or 0)
    scalar_score += 4.0 * float(alignment_tail.get("mask_or_tail_ops", 0) or 0)
    sync_score = (
        3.0 * float(kf.num_pipe_barrier)
        + 1.3 * float(kf.num_set_flag + kf.num_wait_flag)
        + 4.0 * float(kf.num_sync_block_set + kf.num_sync_block_wait)
    )
    sync_score += 0.95 * float(loop_counts.get("sync", 0.0) or 0.0)
    sync_score *= (1.0 + 0.65 * float(sync_criticality.get("sync_criticality_proxy", 0.0) or 0.0))
    # trace event 名称只作为产物结构证据：不读取耗时 target，只按 event name 数量提示 scalar/sync 密度。
    trace_scalar_hint = 0.0
    trace_sync_hint = 0.0
    for name, cnt in trace_top.items():
        lname = str(name).lower()
        c = float(cnt or 0)
        if any(k in lname for k in ["index_cast", "cmpi", "addi", "muli", "extui", "load", "apply"]):
            trace_scalar_hint += min(c, 5000.0) * 0.02
        if any(k in lname for k in ["barrier", "set_flag", "wait_flag", "sync"]):
            trace_sync_hint += min(c, 5000.0) * 0.04
    scalar_score += trace_scalar_hint
    sync_score += trace_sync_hint

    static_ratios = _safe_ratio_dict({
        "compute": compute_score,
        "memory": memory_score,
        "vector": vector_score,
        "scalar": scalar_score,
        "sync": sync_score,
    })

    pipe_frac = des.get("pipe_fraction", {}) if isinstance(des.get("pipe_fraction", {}), dict) else {}
    product_ratios = None
    if pipe_frac:
        raw = {
            "compute": float(pipe_frac.get("cube", 0.0) or 0.0),
            "memory": float(pipe_frac.get("mte", 0.0) or 0.0) + float(pipe_frac.get("mte2", 0.0) or 0.0) + float(pipe_frac.get("mte3", 0.0) or 0.0) + float(pipe_frac.get("fix", 0.0) or 0.0),
            "vector": float(pipe_frac.get("vector", 0.0) or 0.0),
            "scalar": float(pipe_frac.get("pipe_s", 0.0) or 0.0) + float(pipe_frac.get("scalar", 0.0) or 0.0) + float(pipe_frac.get("s", 0.0) or 0.0),
            "sync": float(pipe_frac.get("sync", 0.0) or 0.0),
        }
        # 如果 DES 产物没有把 barrier 归到 sync pipe，用 sync_ops/barrier_ops 的密度补一个轻量比例。
        n_ops = max(1.0, float(des.get("num_operations", 0) or 0))
        raw["sync"] += min(0.25, float(des.get("sync_ops", 0) or 0) / n_ops * 3.0 + float(des.get("barrier_ops", 0) or 0) / n_ops * 4.0)
        # 产物里的 DMA space path bytes 是结构流量证据，不是实测耗时；用于增强 memory ratio。
        dma_paths = des.get("dma_bytes_by_space_path", {}) if isinstance(des.get("dma_bytes_by_space_path", {}), dict) else {}
        dma_total = sum(float(v or 0.0) for v in dma_paths.values())
        if dma_total > 0:
            raw["memory"] += min(0.35, math.log1p(dma_total / 65536.0) * 0.035)
        product_ratios = _safe_ratio_dict(raw)

    if product_ratios:
        # 产物文件是当前编译链路的结构产物，比纯 MLIR op count 更接近 lowering 后的形态；
        # 但它仍不是 profiling target。为避免 DES pipe fraction 过度主导，这里采用
        # MLIR 静态证据 60% + 产物结构证据 40% 的保守融合。
        alpha_static = 0.60
        ratios = {k: alpha_static * static_ratios.get(k, 0.0) + (1.0 - alpha_static) * product_ratios.get(k, 0.0) for k in static_ratios}
        ratios = _safe_ratio_dict(ratios)
        source = "mlir_plus_product_artifacts"
    else:
        ratios = static_ratios
        source = "mlir_only"

    dominant = max(ratios.items(), key=lambda kv: kv[1])[0]
    scalar_ratio = ratios.get("scalar", 0.0)
    sync_ratio = ratios.get("sync", 0.0)
    memory_ratio = ratios.get("memory", 0.0)
    compute_ratio = ratios.get("compute", 0.0)
    vector_ratio = ratios.get("vector", 0.0)

    sync_crit = float(sync_criticality.get("sync_criticality_proxy", 0.0) or 0.0)
    loop_scalar_ratio = float((loop_weighted.get("loop_weighted_ratios", {}) or {}).get("scalar", 0.0) or 0.0)
    memory_bytes = float(memory_path.get("total_path_bytes", 0) or 0.0)
    memory_path_strength = min(1.0, math.log1p(memory_bytes / 32768.0) / 5.0) if memory_bytes > 0 else 0.0
    buffer_pressure = 0.0
    for d in (buffer_lifetime.get("by_space", {}) or {}).values():
        if isinstance(d, dict):
            buffer_pressure += float(d.get("byte_span_sum", 0.0) or 0.0)
    buffer_pressure_strength = min(1.0, math.log1p(buffer_pressure / 1_000_000.0) / 8.0) if buffer_pressure > 0 else 0.0
    alignment_penalty_strength = min(1.0, float(alignment_tail.get("dim_misalignment_ratio", 0.0) or 0.0) + 0.5 * float(alignment_tail.get("offset_misalignment_ratio", 0.0) or 0.0) + min(0.25, float(alignment_tail.get("mask_or_tail_ops", 0) or 0) / 300.0))
    cv_opportunity = float(seq_patterns.get("cv_pipeline_opportunity_proxy", 0.0) or 0.0)
    # V3.3.1: structure-aware cycle correction。
    # 这些 factor 的语义是“修正对应分项 cycles 的基础估计误差”，不是额外 ranking score。
    # 每类结构证据只进入少数对应分项：memory->load/store/workspace，scalar->scalar/control，
    # sync->sync cost，alignment->vector/fix。overlap 只保留窄范围 confidence，避免重复惩罚。
    weights = {
        "compute_cycle_correction": max(0.90, min(1.25, 0.98 + 0.12 * compute_ratio + 0.08 * max(0.0, 1.0 - cv_opportunity))),
        "memory_cycle_correction": max(0.85, min(1.45, 0.95 + 0.45 * memory_ratio + 0.22 * memory_path_strength + 0.12 * buffer_pressure_strength)),
        "vector_cycle_correction": max(0.90, min(1.35, 0.98 + 0.25 * vector_ratio + 0.20 * alignment_penalty_strength)),
        "scalar_cycle_correction": max(0.90, min(2.00, 1.00 + 0.95 * scalar_ratio + 0.30 * loop_scalar_ratio + 0.12 * alignment_penalty_strength)),
        "sync_cycle_correction": max(0.90, min(1.80, 1.00 + 0.85 * sync_ratio + 0.35 * sync_crit)),
        "small_tile_fragmentation_correction": max(0.90, min(1.60, 1.00 + 0.45 * loop_scalar_ratio + 0.15 * alignment_penalty_strength)),
        "memory_path_cycle_correction": max(0.95, min(1.25, 1.0 + 0.20 * memory_path_strength)),
        "alignment_cycle_correction": max(0.95, min(1.30, 1.0 + 0.25 * alignment_penalty_strength)),
        "workspace_pressure_correction": max(0.95, min(1.35, 1.0 + 0.30 * buffer_pressure_strength)),
        "overlap_confidence": max(0.75, min(1.05, 1.00 - 0.18 * scalar_ratio - 0.12 * sync_ratio + 0.08 * memory_ratio + 0.06 * cv_opportunity)),
        "cv_overlap_confidence": max(0.75, min(1.05, 1.00 - 0.12 * scalar_ratio - 0.15 * sync_ratio + 0.08 * min(vector_ratio, compute_ratio) + 0.10 * cv_opportunity)),
        "cv_pattern_opportunity_correction": max(0.90, min(1.15, 1.0 + 0.15 * cv_opportunity - 0.08 * sync_crit)),
        # Backward-compatible aliases for old tests/reports. New code should read the *_cycle_correction names.
        "compute_multiplier": max(0.90, min(1.25, 0.98 + 0.12 * compute_ratio + 0.08 * max(0.0, 1.0 - cv_opportunity))),
        "memory_multiplier": max(0.85, min(1.45, 0.95 + 0.45 * memory_ratio + 0.22 * memory_path_strength + 0.12 * buffer_pressure_strength)),
        "vector_multiplier": max(0.90, min(1.35, 0.98 + 0.25 * vector_ratio + 0.20 * alignment_penalty_strength)),
        "scalar_control_multiplier": max(0.90, min(2.00, 1.00 + 0.95 * scalar_ratio + 0.30 * loop_scalar_ratio + 0.12 * alignment_penalty_strength)),
        "sync_multiplier": max(0.90, min(1.80, 1.00 + 0.85 * sync_ratio + 0.35 * sync_crit)),
        "small_tile_scalar_penalty_scale": max(0.90, min(1.60, 1.00 + 0.45 * loop_scalar_ratio + 0.15 * alignment_penalty_strength)),
        "memory_path_multiplier": max(0.95, min(1.25, 1.0 + 0.20 * memory_path_strength)),
        "alignment_penalty_scale": max(0.95, min(1.30, 1.0 + 0.25 * alignment_penalty_strength)),
        "buffer_pressure_scale": max(0.95, min(1.35, 1.0 + 0.30 * buffer_pressure_strength)),
        "overlap_reward_scale": max(0.75, min(1.05, 1.00 - 0.18 * scalar_ratio - 0.12 * sync_ratio + 0.08 * memory_ratio + 0.06 * cv_opportunity)),
        "cv_reward_scale": max(0.75, min(1.05, 1.00 - 0.12 * scalar_ratio - 0.15 * sync_ratio + 0.08 * min(vector_ratio, compute_ratio) + 0.10 * cv_opportunity)),
        "cube_reward_scale": 1.0,
        "cv_pattern_opportunity_scale": max(0.90, min(1.15, 1.0 + 0.15 * cv_opportunity - 0.08 * sync_crit)),
        "loop_weighted_scalar_multiplier": max(0.90, min(1.60, 1.00 + 0.45 * loop_scalar_ratio + 0.15 * alignment_penalty_strength)),
    }
    raw_features = {
        "compute_score": compute_score,
        "memory_score": memory_score,
        "vector_score": vector_score,
        "scalar_score": scalar_score,
        "sync_score": sync_score,
        "scalar_family_counts": scalar_counts,
        "trace_scalar_hint": trace_scalar_hint,
        "trace_sync_hint": trace_sync_hint,
        "product_pipe_fraction": pipe_frac,
        "product_critical_pipe": des.get("critical_pipe") if isinstance(des, dict) else None,
        "advanced_mlir_features": advanced,
        "feature_strengths": {
            "sync_criticality": sync_crit,
            "loop_scalar_ratio": loop_scalar_ratio,
            "memory_path_strength": memory_path_strength,
            "buffer_pressure_strength": buffer_pressure_strength,
            "alignment_penalty_strength": alignment_penalty_strength,
            "cv_pipeline_opportunity_proxy": cv_opportunity,
        },
    }
    if dominant == "scalar":
        kernel_type = "scalar_control_heavy"
    elif dominant == "memory":
        kernel_type = "memory_or_layout_heavy"
    elif dominant == "compute":
        kernel_type = "cube_compute_heavy"
    elif dominant == "vector":
        kernel_type = "vector_heavy"
    elif dominant == "sync":
        kernel_type = "sync_heavy"
    else:
        kernel_type = "mixed"
    return {
        "enabled": True,
        "source": source,
        "uses_profiling_target": False,
        "kernel_type": kernel_type,
        "dominant_component": dominant,
        "ratios": ratios,
        "static_ratios": static_ratios,
        "product_ratios": product_ratios or {},
        "weights": weights,
        "raw_features": raw_features,
        "note": "Kernel-specific correction factors are derived only from MLIR and compiler product artifacts; no measured/profiling target or DES makespan is used. They correct component cycle estimates rather than adding a separate ranking score.",
    }


def kernel_profile_enabled(args: argparse.Namespace) -> bool:
    """命令行开关：默认开启 artifact-kernel-profile，可显式关闭。"""
    return str(getattr(args, "artifact_kernel_profile", "on")) != "off"


def get_artifact(search: Dict[str, Any]) -> Dict[str, Any]:
    """返回缓存的 artifact profile；若未构建则返回空 profile。"""
    return search.get("artifact_profile", {}) if isinstance(search.get("artifact_profile"), dict) else {}


def write_artifact_audits(out: Path, artifact: Dict[str, Any], hw: Dict[str, Any]) -> None:
    """把参数空间、硬件边界和 cost model 的审计信息写成 JSON 文件。"""
    if not artifact:
        artifact = asdict(ArtifactProfile([], {}, {"available": False}, {"available": False}, {"available": False}, {}))
    mlir = artifact.get("mlir_evidence", {}) or {}
    des = artifact.get("des_evidence", {}) or {}
    src = artifact.get("source_meta", {}) or {}
    parameter_audit = {
        "question": "How close is the parameter space to HIVM?",
        "answer": "The search space is four-plan based. V3.3 accepts optional DES/trace JSON as structured profile inputs. Python/Triton source files are not parsed as inputs; source-derived ideas are manually distilled into built-in templates.",
        "source_input_policy": src.get("note", "Python/Triton source input is disabled in V3.3."),
        "ignored_source_files": src.get("deprecated_ignored_source_files", []),
        "mlir_op_counts": mlir.get("op_counts", {}),
        "hivm_annotations": {
            "multi_buffer": mlir.get("hivm_multi_buffer_annotations"),
            "part_of_mix": mlir.get("hivm_part_of_mix"),
            "storage_aligned": mlir.get("hivm_storage_aligned"),
        },
        "generic_hivm_structure": mlir.get("generic_hivm_structure", {}),
        "ping_pong_pairs": mlir.get("ping_pong_pairs", []),
        "cv_op_sequence": mlir.get("cv_op_sequence", {}),
        "event_sync_pairs": mlir.get("event_sync_pairs", []),
        "des_pipe_available": bool(des.get("available")),
        "conclusion": "HIVM-artifact-aware parameter schema" if artifact.get("schema_coverage", {}).get("has_mlir") else "analytical parameter schema without artifact evidence",
    }
    caps = {s: memory_cap_bytes(hw, s) for s in ["ub", "l1", "l0a", "l0b", "l0c"]}
    raw_bytes_by_space = mlir.get("static_memref_bytes_by_space", {}) or {}
    unique_alloc_bytes = mlir.get("unique_alloc_bytes_by_space", {}) or {}
    max_live_bytes = mlir.get("static_max_live_bytes_by_space", {}) or {}
    # 主边界信号不能直接使用原始 memref 出现次数累计字节，因为同一个 memref 会在多个 operand 中重复出现。
    # 因此优先使用 static max-live；若不可用则退回 unique allocation bytes；原始累计值只保留作审计诊断。
    boundary_bytes = max_live_bytes or unique_alloc_bytes or raw_bytes_by_space
    util = {s: (boundary_bytes.get(s, 0) / caps[s] if caps.get(s) else None) for s in caps}
    hardware_audit = {
        "question": "Are hardware boundaries reasonably enforced?",
        "answer": "V3.3 uses analytical gates plus artifact evidence when available. Artifact data are not hard-coded; they validate scope, alignment, multibuffer, DMA-path, and sync-resource assumptions for the current input.",
        "hardware_caps_bytes": caps,
        "mlir_raw_memref_occurrence_bytes_by_space": raw_bytes_by_space,
        "mlir_unique_alloc_bytes_by_space": unique_alloc_bytes,
        "mlir_static_max_live_bytes_by_space": max_live_bytes,
        "boundary_bytes_used_for_utilization": boundary_bytes,
        "mlir_static_memref_utilization_by_space": util,
        "memrefs_by_space": mlir.get("memrefs_by_space", {}),
        "unique_alloc_count_by_space": mlir.get("unique_alloc_count_by_space", {}),
        "ping_pong_multibuffer_evidence": mlir.get("ping_pong_pairs", []),
        "alignment_evidence": {"hivm_storage_aligned_count": mlir.get("hivm_storage_aligned")},
        "multibuffer_evidence": {"hivm_multi_buffer_annotations": mlir.get("hivm_multi_buffer_annotations"), "des_multi_buffer_slots_histogram": des.get("multi_buffer_slots_histogram", {})},
        "dma_path_evidence": des.get("dma_bytes_by_space_path", {}),
        "sync_resource_evidence": des.get("sync_counts_by_name", {}),
        "conclusion": "partially artifact-validated hardware boundary" if artifact.get("schema_coverage", {}).get("has_mlir") else "analytical hardware boundary only",
    }
    cost_audit = {
        "question": "Is the cost model reasonable?",
        "answer": "V3.3 keeps the analytical search objective but audits/calibrates it with pipe, DMA, sync, and trace evidence when DES/trace artifacts are provided.",
        "des_available": bool(des.get("available")),
        "num_operations": des.get("num_operations"),
        "pipe_duration": des.get("pipe_duration", {}),
        "pipe_fraction": des.get("pipe_fraction", {}),
        "critical_pipe": des.get("critical_pipe"),
        "pipe_bytes": des.get("pipe_bytes", {}),
        "dma_bytes_by_space_path": des.get("dma_bytes_by_space_path", {}),
        "sync_counts_by_name": des.get("sync_counts_by_name", {}),
        "top_ops_by_duration": des.get("top_ops_by_duration", [])[:10],
        "trace_summary": artifact.get("trace_evidence", {}),
        "conclusion": "DES-assisted pipe/sync/DMA-aware cost audit" if des.get("available") else "analytical cost model without DES audit",
    }
    write_json(out / "parameter_space_audit.json", parameter_audit)
    write_json(out / "hardware_boundary_audit.json", hardware_audit)
    write_json(out / "cost_model_audit.json", cost_audit)

def build_diagnosis_hints(
    desgraph_paths: List[str],
    bound_report_paths: List[str],
    counterfactual_paths: List[str],
    multi_kernel_paths: List[str],
    enabled: bool,
    mode: str = "diagnosis",
) -> DiagnosisHints:
    """基于 DES、边界报告、反事实报告和多 kernel 报告生成软诊断引导信号。"""
    hints = DiagnosisHints(
        enabled=enabled,
        mode=mode if enabled else "off",
        source_files=[],
        signals=[],
        variable_bias={"f": 1.0, "t": 1.0, "B": 1.0, "m": 1.0, "s": 1.0, "r": 1.0, "ℓ": 1.0, "y": 1.0, "d": 1.0},
        value_bias={},
        coverage=[],
        unknown_signals=[],
        des_profile=None,
        bound_reports=[],
        counterfactual_reports=[],
        multi_kernel_reports=[],
    )
    if not enabled:
        return hints

    des = load_desgraph_profile(desgraph_paths)
    if des:
        hints.source_files.extend(des.source_files)
        hints.des_profile = asdict(des)
        total = sum(des.pipe_duration.values()) or 1.0
        for pipe, dur in sorted(des.pipe_duration.items(), key=lambda kv: kv[1], reverse=True):
            frac = dur / total
            if frac < 0.10:
                continue
            if pipe == "vector":
                _add_signal(hints, "desgraph", "ComputeBound-Vector", f"DES graph vector pipe takes {frac:.1%} of modeled duration", ["f", "t", "r"], {"pipe": pipe, "duration_fraction": frac}, frac * 2)
                _bump(hints.value_bias, "fusion:moderate_elementwise_fusion", 1.12)
                _bump(hints.value_bias, "fusion:aggressive_elementwise_fusion", 1.08)
            elif pipe == "cube":
                _add_signal(hints, "desgraph", "ComputeBound-Cube", f"DES graph cube pipe takes {frac:.1%} of modeled duration", ["t", "B", "r"], {"pipe": pipe, "duration_fraction": frac}, frac * 2)
            elif pipe == "mte2":
                _add_signal(hints, "desgraph", "MemoryBound-Load", f"DES graph MTE2/load pipe takes {frac:.1%} of modeled duration", ["d", "m", "t", "ℓ"], {"pipe": pipe, "duration_fraction": frac}, frac * 2)
                _bump(hints.value_bias, "dma_policy:prefer_contiguous", 1.12)
                _bump(hints.value_bias, "dma_policy:prefetch_nd2nz", 1.10)
            elif pipe == "mte3":
                _add_signal(hints, "desgraph", "MemoryBound-Store", f"DES graph MTE3/store pipe takes {frac:.1%} of modeled duration", ["d", "m", "t"], {"pipe": pipe, "duration_fraction": frac}, frac * 2)
            elif pipe in {"sync", "pipe_s"}:
                _add_signal(hints, "desgraph", "SyncBound", f"DES graph sync/scalar pipe takes {frac:.1%} of modeled duration", ["y", "m", "s", "t"], {"pipe": pipe, "duration_fraction": frac}, frac * 2)
        if des.sync_ops >= 8:
            _add_signal(hints, "desgraph", "SyncBound", f"DES graph has {des.sync_ops} sync-like ops", ["y", "m", "s", "t"], {"sync_ops": des.sync_ops}, 1.5)
            _bump(hints.value_bias, "sync_policy:graph_sync_solver", 1.20)
        hints.coverage.append({"source": "desgraph", "files": des.source_files, "covered_fields": des.schema_fields, "status": "covered"})

    for path in bound_report_paths:
        if not path or not Path(path).exists():
            continue
        data = load_json(path)
        hints.source_files.append(str(Path(path)))
        hints.bound_reports.append(data)
        fields = _flatten_json_fields(data)
        bc = str(data.get("binding_component", "")).lower()
        if bc:
            for sig, vars_, sev in _classify_action_text(bc):
                _add_signal(hints, "bound_report", sig, f"binding_component={bc}", vars_, {"binding_component": bc}, sev)
        action = data.get("recommended_action", "")
        if action:
            classified = _classify_action_text(action)
            if classified:
                for sig, vars_, sev in classified:
                    _add_signal(hints, "bound_report", sig, f"recommended_action: {action}", vars_, {"recommended_action": action}, sev)
            else:
                hints.unknown_signals.append({"source": "bound_report", "field": "recommended_action", "value": action, "action": "fallback_default_search"})
        attr = data.get("attribution", {}) if isinstance(data.get("attribution"), dict) else {}
        g2 = _num(attr.get("gap2_coalescing", 0.0))
        g3 = _num(attr.get("gap3_avoidable_serial", 0.0))
        g4 = _num(attr.get("gap4_intra_unit_exec", 0.0))
        if g2 > 0.05:
            _add_signal(hints, "bound_report", "Layout/Coalescing", f"gap2_coalescing={g2:.3f}", ["d", "t", "ℓ"], {"gap2_coalescing": g2}, 1 + g2)
        if g3 > 0.05:
            _add_signal(hints, "bound_report", "PipelineImbalance", f"gap3_avoidable_serial={g3:.3f}", ["m", "s", "r", "y"], {"gap3_avoidable_serial": g3}, 1 + g3)
        if g4 > 0.05:
            _add_signal(hints, "bound_report", "ComputeBound-IntraUnit", f"gap4_intra_unit_exec={g4:.3f}", ["f", "t", "r", "B"], {"gap4_intra_unit_exec": g4}, 1 + g4)
        hints.coverage.append({"source": "bound_report", "file": str(path), "covered_fields": fields, "status": "covered"})

    for path in counterfactual_paths:
        if not path or not Path(path).exists():
            continue
        data = load_json(path)
        hints.source_files.append(str(Path(path)))
        hints.counterfactual_reports.append(data)
        fields = _flatten_json_fields(data)
        text = " ".join(str(data.get(k, "")) for k in ["gap_name", "experiment_kind", "description", "methodology"])
        speed_like = max(_num(data.get("scaling_ratio", 0.0)), _num(data.get("t_before_us", 0.0)) / max(1e-9, _num(data.get("t_after_us", 0.0), 1.0)))
        for sig, vars_, sev in _classify_action_text(text):
            _add_signal(hints, "counterfactual", sig, f"counterfactual text indicates {sig}", vars_, {"text": text[:240]}, max(sev, speed_like))
        if "memory" in text.lower() or "work_scaling" in text.lower():
            _add_signal(hints, "counterfactual", "MemoryBound-Scaling", "counterfactual validates memory/work scaling behavior", ["d", "m", "t", "ℓ"], {"scaling_ratio": data.get("scaling_ratio")}, 1.4)
        hints.coverage.append({"source": "counterfactual", "file": str(path), "covered_fields": fields, "status": "covered"})

    for path in multi_kernel_paths:
        if not path or not Path(path).exists():
            continue
        data = load_json(path)
        hints.source_files.append(str(Path(path)))
        hints.multi_kernel_reports.append(data)
        fields = _flatten_json_fields(data)
        kernels = data.get("kernels", []) if isinstance(data, dict) else []
        if isinstance(kernels, list) and kernels:
            worst = sorted([k for k in kernels if isinstance(k, dict)], key=lambda x: _num(x.get("tightness", 0.0)), reverse=True)[:5]
            hints.signals.append({"source": "multi_kernel", "signal_type": "KernelPrioritization", "message": "multi-kernel report available; use tightness/time to prioritize kernels in future multi-kernel mode", "search_variables": [], "severity": 0.5, "evidence": worst})
        hints.coverage.append({"source": "multi_kernel", "file": str(path), "covered_fields": fields, "status": "covered"})

    # 限制 bias 上界，避免诊断信息变成硬剪枝；诊断只负责调整优先级。
    for k, v in list(hints.variable_bias.items()):
        hints.variable_bias[k] = round(min(max(v, 1.0), 2.5), 4)
    for k, v in list(hints.value_bias.items()):
        hints.value_bias[k] = round(min(max(v, 1.0), 1.8), 4)
    return hints


def strategy_diagnosis_bias(c: StrategyConfig, hints: DiagnosisHints) -> Tuple[float, List[str]]:
    """根据诊断信号给候选策略计算软 bias，只影响排序优先级而不替代 cost model。"""
    if not hints.enabled:
        return 1.0, []
    bias = 1.0
    reasons: List[str] = []
    var_to_enabled = {
        "f": c.fusion != "keep_existing",
        "t": True,
        "B": c.block_dim > 1,
        "m": c.double_buffer,
        "s": c.cv_pipeline_stage > 1,
        "r": c.cv_split_ratio != "1:1",
        "ℓ": c.memory_reuse_level in {"level1", "level0", "inplace"},
        "y": c.sync_policy == "graph_sync_solver",
        "d": c.dma_policy != "keep_existing",
    }
    for var, enabled in var_to_enabled.items():
        if enabled:
            b = float(hints.variable_bias.get(var, 1.0))
            if b > 1.0:
                bias *= min(b, 1.45)
                reasons.append(f"{var} boosted by diagnosis bias {b:.2f}")
    for key in [f"fusion:{c.fusion}", f"sync_policy:{c.sync_policy}", f"dma_policy:{c.dma_policy}"]:
        b = float(hints.value_bias.get(key, 1.0))
        if b > 1.0:
            bias *= min(b, 1.35)
            reasons.append(f"{key} value bias {b:.2f}")
    # 保持软引导：它只能改善搜索优先级，不能压过物理/解析 cost model。
    return min(bias, 3.0), reasons


def get_available_cores(kf: KernelFeatures, hw: Dict[str, Any]) -> int:
    """从硬件配置中读取可用核心数，并兼容不同字段命名。"""
    par = hw.get("calibration", {}).get("parallelism", {})
    num_aiv = int(par.get("num_aiv_cores", 40))
    num_aic = int(par.get("num_aic_cores", num_aiv))
    if kf.has_aiv and not kf.has_aic:
        return max(1, num_aiv)
    if kf.has_aic and not kf.has_aiv:
        return max(1, num_aic)
    return max(1, num_aiv)


def tile_key(tile: Dict[str, Any]) -> str:
    """生成 tile 的去重键，避免同一 tile 组合重复进入候选空间。"""
    return f"{int(tile['m'])}x{int(tile['n'])}x{int(tile['k'])}"


def estimate_num_tiles_for_tile(kf: KernelFeatures, search: Dict[str, Any], tile: Dict[str, Any]) -> int:
    """根据问题规模和 tile 大小估算 M/N/K 三个方向的 tile 数量。"""
    p = problem_shape(search, kf)
    n_tiles = (
        math.ceil(int(p.get("m_total", 1)) / max(1, int(tile["m"])))
        * math.ceil(int(p.get("n_total", 1)) / max(1, int(tile["n"])))
        * math.ceil(int(p.get("k_total", 1)) / max(1, int(tile["k"])))
        * int(p.get("outer_iterations", 1))
    )
    return max(1, int(n_tiles))


def generate_block_dim_candidates_for_tile(n_tiles_total: int, max_cores: int) -> List[int]:
    """根据 tile 数量和核心数自动生成 block_dim 候选，覆盖整除、近满核和保守并行度。"""
    upper = max(1, min(int(max_cores), int(n_tiles_total)))
    base = {1, upper, max(1, upper // 2), max(1, upper // 4)}

    # 常用幂次和工程经验点仍然有价值，但不再作为唯一来源。
    # 它们会被硬件和 kernel 边界裁剪。
    for b in [2, 4, 8, 16, 20, 24, 25, 32, 40, 48, 50, 64]:
        if 1 <= b <= upper:
            base.add(b)

    # 接近满核的选项可以覆盖 50-core 等变体，即使没有为具体设备预置静态列表。
    for ratio in [1.0, 0.96, 0.90, 0.80, 0.75, 0.50]:
        b = int(round(upper * ratio))
        if 1 <= b <= upper:
            base.add(b)

    # n_tiles_total 的约数通常能产生更干净的 wave 调度。
    limit = upper
    for b in range(1, limit + 1):
        if n_tiles_total % b == 0:
            base.add(b)

    return sorted(int(b) for b in base if 1 <= int(b) <= upper)


def select_default_block_dim_for_tile(n_tiles_total: int, max_cores: int) -> int:
    """在 block_dim 候选中选择默认值，优先匹配有效并行度并控制资源压力。"""
    candidates = generate_block_dim_candidates_for_tile(n_tiles_total, max_cores)
    best_b = candidates[0]
    best_score = -1.0
    for b in candidates:
        active = max(1, min(int(b), int(max_cores), int(n_tiles_total)))
        waves = int(math.ceil(float(n_tiles_total) / active))
        tail_eff = float(n_tiles_total) / max(1.0, waves * active)
        eff_parallelism = active * tail_eff
        # 当有效并行度相同，稍微偏好更少 active blocks，因为通常能降低资源和同步压力。
        score = eff_parallelism - 1e-3 * active
        if score > best_score:
            best_score = score
            best_b = int(b)
    return int(best_b)




def _available_tiling_knobs(kf: KernelFeatures) -> Dict[str, List[Any]]:
    """根据候选空间配置返回 TilingPlan 可搜索的 loop、tail、reduce 和 layout 旋钮。"""
    return {
        "loop_order": ["outer_mnk", "outer_mkn", "outer_nmk"],
        "tail_strategy": ["mask_or_pad", "peel", "pad"],
        "reduce_tile_policy": ["full_k", "half_k"],
        "layout_aware_tile": [True, False],
    }


def _available_multibuffer_templates(kf: KernelFeatures) -> List[str]:
    """返回 MultiBufferPlan 可用模板，并根据是否有 ping-pong 证据启用更激进模板。"""
    out = ["M0_no_multibuffer", "M1_input_double_buffer", "M2_input_output_double_buffer"]
    if kf.num_mmad or kf.vector_op_counts:
        out.append("M4_cv_stage_aware_multibuffer")
    # M3 只有在观察到 ping/pong 证据时最有意义；通用抽取器仍可把它作为可搜索模板，最终由容量门控过滤。
    out.append("M3_ping_pong_detected")
    return out


def _available_cv_knobs(kf: KernelFeatures) -> Dict[str, List[Any]]:
    """返回 CVPipelinePlan 的 stage、template、mixed-CV 和 loop-mix 候选值。"""
    has_cv = bool(kf.num_mmad and kf.vector_op_counts)
    if not has_cv:
        return {
            "cv_pipeline_stage": [1],
            "cv_pipeline_template": ["P0_no_cv_pipeline"],
            "enable_mixed_cv": [False],
            "tile_mix_cube_loop": [1],
            "tile_mix_vector_loop": [1],
            "auto_cv_balance": [False],
            "producer_consumer_distance": [1],
            "stage_buffer_policy": ["none"],
        }
    return {
        "cv_pipeline_stage": [1, 2, 4],
        "cv_pipeline_template": ["P0_no_cv_pipeline", "P1_stage2_basic", "P2_stage2_balanced", "P_PREFILL_LARGE_SBS_REUSE", "P3_stage4_aggressive"],
        "enable_mixed_cv": [False, True],
        "tile_mix_cube_loop": [1, 2, 4],
        "tile_mix_vector_loop": [1, 2],
        "auto_cv_balance": [True],
        "producer_consumer_distance": [1],
        "stage_buffer_policy": ["none", "ub_stage", "l1_reuse", "gm_workspace"],
    }


def build_cv_pipeline_plan_candidates(kf: KernelFeatures, search: Dict[str, Any]) -> List[Dict[str, Any]]:
    """组合 CVPipelinePlan 各个旋钮，生成经过兼容性过滤的流水候选。"""
    has_cv = bool(kf.num_mmad and kf.vector_op_counts)
    if not has_cv:
        return [{
            "name": "P0_no_cv_pipeline",
            "cv_pipeline_stage": 1,
            "cv_pipeline_template": "P0_no_cv_pipeline",
            "enable_mixed_cv": False,
            "tile_mix_cube_loop": 1,
            "tile_mix_vector_loop": 1,
            "auto_cv_balance": False,
            "producer_consumer_distance": 1,
            "stage_buffer_policy": "none",
        }]

    allowed_stages = {int(x) for x in search.get("cv_pipeline_stage", [1, 2, 4])}
    allowed_templates = set(search.get("cv_pipeline_template", ["P0_no_cv_pipeline", "P1_stage2_basic", "P2_stage2_balanced", "P_PREFILL_LARGE_SBS_REUSE", "P3_stage4_aggressive"]))
    allowed_mixed = {bool(x) for x in search.get("enable_mixed_cv", [False])}
    allowed_cube = {int(x) for x in search.get("tile_mix_cube_loop", [1, 2])}
    allowed_vector = {int(x) for x in search.get("tile_mix_vector_loop", [1, 2])}
    allowed_balance = {bool(x) for x in search.get("auto_cv_balance", [True])}
    allowed_dist = {int(x) for x in search.get("producer_consumer_distance", [1])}
    allowed_policy = set(search.get("stage_buffer_policy", ["none", "ub_stage", "l1_reuse", "gm_workspace"]))

    def ok(c: Dict[str, Any]) -> bool:
        """判断一个 CVPipelinePlan 候选是否落在当前允许的搜索取值范围内。"""
        return (
            int(c["cv_pipeline_stage"]) in allowed_stages
            and str(c["cv_pipeline_template"]) in allowed_templates
            and bool(c["enable_mixed_cv"]) in allowed_mixed
            and int(c["tile_mix_cube_loop"]) in allowed_cube
            and int(c["tile_mix_vector_loop"]) in allowed_vector
            and bool(c["auto_cv_balance"]) in allowed_balance
            and int(c["producer_consumer_distance"]) in allowed_dist
            and str(c["stage_buffer_policy"]) in allowed_policy
        )

    base = [
        {"name": "P0_no_cv_pipeline", "cv_pipeline_stage": 1, "cv_pipeline_template": "P0_no_cv_pipeline", "enable_mixed_cv": False, "tile_mix_cube_loop": 1, "tile_mix_vector_loop": 1, "auto_cv_balance": False, "producer_consumer_distance": 1, "stage_buffer_policy": "none"},
        {"name": "P1_stage2_basic", "cv_pipeline_stage": 2, "cv_pipeline_template": "P1_stage2_basic", "enable_mixed_cv": False, "tile_mix_cube_loop": 1, "tile_mix_vector_loop": 1, "auto_cv_balance": True, "producer_consumer_distance": 1, "stage_buffer_policy": "none"},
        {"name": "P2_stage2_balanced", "cv_pipeline_stage": 2, "cv_pipeline_template": "P2_stage2_balanced", "enable_mixed_cv": False, "tile_mix_cube_loop": 1, "tile_mix_vector_loop": 1, "auto_cv_balance": True, "producer_consumer_distance": 1, "stage_buffer_policy": "none"},
        {"name": "P2_stage2_balanced_ub_stage", "cv_pipeline_stage": 2, "cv_pipeline_template": "P2_stage2_balanced", "enable_mixed_cv": False, "tile_mix_cube_loop": 1, "tile_mix_vector_loop": 1, "auto_cv_balance": True, "producer_consumer_distance": 1, "stage_buffer_policy": "ub_stage"},
        {"name": "P2_stage2_balanced_gm_workspace", "cv_pipeline_stage": 2, "cv_pipeline_template": "P2_stage2_balanced", "enable_mixed_cv": False, "tile_mix_cube_loop": 1, "tile_mix_vector_loop": 1, "auto_cv_balance": True, "producer_consumer_distance": 1, "stage_buffer_policy": "gm_workspace"},
        # 内置 V2.7 模板来自人工审阅过的 A5 sparse-prefill CV-pipeline 实现。
        # 这里不会把 Python 实现本身作为输入解析，只保留稳定且可文档化的设计规则。
        {"name": "P_PREFILL_LARGE_SBS_REUSE", "cv_pipeline_stage": 2, "cv_pipeline_template": "P_PREFILL_LARGE_SBS_REUSE", "enable_mixed_cv": False, "tile_mix_cube_loop": 4, "tile_mix_vector_loop": 1, "auto_cv_balance": True, "producer_consumer_distance": 1, "stage_buffer_policy": "l1_reuse"},
    ]
    # 只保留一个温和的 mixed/imbalanced 候选，表示 loop-ratio 探索，避免所有模板和 loop mix 全量相乘。
    if True in allowed_mixed:
        base.append({"name": "P2_stage2_mixed_vector_heavy", "cv_pipeline_stage": 2, "cv_pipeline_template": "P2_stage2_balanced", "enable_mixed_cv": True, "tile_mix_cube_loop": 1, "tile_mix_vector_loop": 2, "auto_cv_balance": True, "producer_consumer_distance": 1, "stage_buffer_policy": "none"})
    if 4 in allowed_stages:
        base.append({"name": "P3_stage4_aggressive", "cv_pipeline_stage": 4, "cv_pipeline_template": "P3_stage4_aggressive", "enable_mixed_cv": False, "tile_mix_cube_loop": 2, "tile_mix_vector_loop": 2, "auto_cv_balance": True, "producer_consumer_distance": 1, "stage_buffer_policy": "ub_stage"})
        base.append({"name": "P3_stage4_aggressive_gm_workspace", "cv_pipeline_stage": 4, "cv_pipeline_template": "P3_stage4_aggressive", "enable_mixed_cv": False, "tile_mix_cube_loop": 2, "tile_mix_vector_loop": 2, "auto_cv_balance": True, "producer_consumer_distance": 1, "stage_buffer_policy": "gm_workspace"})

    out = [c for c in base if ok(c) and _cv_template_compatible(int(c["cv_pipeline_stage"]), str(c["cv_pipeline_template"]), bool(c["enable_mixed_cv"]), int(c["tile_mix_cube_loop"]), int(c["tile_mix_vector_loop"]))]
    return out or [base[0]]


def _available_sync_knobs(kf: KernelFeatures) -> Dict[str, List[Any]]:
    """返回 SyncPlan 的 policy、template、barrier、event reuse、granularity 和 sync motion 候选。"""
    has_sync = bool(kf.num_set_flag + kf.num_wait_flag + kf.num_pipe_barrier + kf.num_sync_block_set + kf.num_sync_block_wait)
    if not has_sync:
        return {
            "sync_policy": ["keep_existing"],
            "sync_template": ["Y0_keep_existing"],
            "barrier_level": ["medium"],
            "event_reuse": [False],
            "sync_granularity": ["op"],
            "event_id_policy": ["keep"],
            "sync_motion": ["none"],
        }
    return {
        "sync_policy": ["keep_existing", "graph_sync_solver"],
        "sync_template": ["Y0_keep_existing", "Y1_conservative_barrier", "Y2_graph_sync_solver", "Y3_event_reuse"],
        "barrier_level": ["low", "medium", "high"],
        "event_reuse": [False, True],
        "sync_granularity": ["op", "tile", "stage"],
        "event_id_policy": ["keep", "compact", "reuse"],
        "sync_motion": ["none", "local_move"],
    }


def _sync_template_compatible(policy: str, template: str, event_reuse: bool, event_id_policy: str = "keep") -> bool:
    """判断某个 sync template 与 sync policy、barrier level、event reuse 是否兼容。"""
    if policy == "keep_existing":
        return template in {"Y0_keep_existing", "Y1_conservative_barrier"} and not event_reuse and event_id_policy == "keep"
    if policy == "graph_sync_solver":
        if template not in {"Y2_graph_sync_solver", "Y3_event_reuse"}:
            return False
        if template == "Y3_event_reuse" and event_id_policy == "keep" and not event_reuse:
            return False
        return True
    return False


def _cv_template_compatible(stage: int, template: str, mixed: bool, cube_loop: int, vector_loop: int) -> bool:
    """判断某个 CV template 与 stage、mixed-CV 和 loop-mix 参数是否兼容。"""
    if stage <= 1:
        return template == "P0_no_cv_pipeline" and not mixed and cube_loop == 1 and vector_loop == 1
    if template == "P0_no_cv_pipeline":
        return False
    if stage == 2 and template not in {"P1_stage2_basic", "P2_stage2_balanced", "P_PREFILL_LARGE_SBS_REUSE"}:
        return False
    if template == "P_PREFILL_LARGE_SBS_REUSE":
        return (not mixed) and cube_loop in {2, 4} and vector_loop == 1
    if stage == 4 and template != "P3_stage4_aggressive":
        return False
    return True


def _mb_template_compatible(db: bool, mb_template: str, stage: int) -> bool:
    """判断某个 MultiBuffer template 与 double buffer 和 stage buffer 策略是否兼容。"""
    if not db:
        return mb_template == "M0_no_multibuffer"
    if stage > 1:
        return mb_template in {"M1_input_double_buffer", "M2_input_output_double_buffer", "M3_ping_pong_detected", "M4_cv_stage_aware_multibuffer"}
    return mb_template in {"M1_input_double_buffer", "M2_input_output_double_buffer", "M3_ping_pong_detected"}


def _parse_buffer_multipliers_json(raw: str | Dict[str, Any] | None) -> Dict[str, int]:
    """解析 per-buffer multiplier JSON，并把每个 buffer 的倍数限制在 1 或 2。"""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        obj = raw
    else:
        try:
            obj = json.loads(str(raw)) if str(raw).strip() else {}
        except Exception:
            obj = {}
    out: Dict[str, int] = {}
    for k, v in obj.items():
        try:
            iv = int(v)
        except Exception:
            iv = 1
        out[str(k)] = 2 if iv >= 2 else 1
    return out


def _canonical_buffer_multipliers_json(m: Dict[str, int] | None) -> str:
    """将 per-buffer multiplier 字典排序并序列化，保证策略 ID 和去重稳定。"""
    if not m:
        return "{}"
    clean = {str(k): (2 if int(v) >= 2 else 1) for k, v in m.items()}
    return json.dumps(clean, sort_keys=True, separators=(",", ":"))


def _buffer_role_score(name: str, space: str, size_bytes: int, lifetime: int) -> float:
    """根据 buffer 名称和空间估计其重要性，用于优先选择值得 double buffer 的 buffer。"""
    lname = name.lower()
    score = 0.0
    if space in {"ub", "l1"}:
        score += 3.0
    if any(x in lname for x in ["ping", "pong"]):
        score += 3.0
    if any(x in lname for x in ["q", "k", "v", "input", "load", "stage", "tile"]):
        score += 2.0
    if any(x in lname for x in ["acc", "out", "store", "p_", "s_"]):
        score += 0.8
    score += min(3.0, max(0.0, math.log2(max(2, size_bytes)) - 8.0) / 4.0)
    score += min(2.0, max(0, lifetime) / 128.0)
    return score


def eligible_multibuffer_buffers(kf: KernelFeatures, search: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """从静态 buffer 中筛选可参与 per-buffer multiplier 搜索的局部 buffer。"""
    search = search or {}
    max_buffers = int(search.get("max_per_buffer_multibuffer_buffers", 4))
    min_size = int(search.get("min_per_buffer_size_bytes", 256))
    seen: Dict[str, Dict[str, Any]] = {}
    for b in kf.buffers:
        if b.space not in {"ub", "l1", "l0a", "l0b", "l0c"}:
            continue
        if int(b.size_bytes) < min_size:
            continue
        lifetime = int(b.kill) - int(b.gen)
        if lifetime <= 0:
            continue
        key = str(b.name)
        item = {
            "name": key,
            "space": b.space,
            "size_bytes": int(b.size_bytes),
            "aligned_size_bytes": int(_align(int(b.size_bytes), 512 if b.space.startswith("l0") else 32)),
            "gen": int(b.gen),
            "kill": int(b.kill),
            "lifetime": lifetime,
            "score": _buffer_role_score(key, b.space, int(b.size_bytes), lifetime),
        }
        # 按 SSA 名称去重别名，保留容量最大或生命周期最长的记录。
        old = seen.get(key)
        if old is None or item["score"] > old.get("score", 0):
            seen[key] = item
    arr = sorted(seen.values(), key=lambda x: (-float(x["score"]), -int(x["size_bytes"]), x["name"]))
    return arr[:max_buffers]


def generate_per_buffer_multiplier_candidates(kf: KernelFeatures, search: Dict[str, Any], *, db: bool) -> List[Dict[str, Any]]:
    """为候选局部 buffer 枚举 nbuf_b∈{1,2} 的 per-buffer multiplier 组合。"""
    eligible = eligible_multibuffer_buffers(kf, search)
    search["eligible_multibuffer_buffers"] = eligible
    names = [x["name"] for x in eligible]
    if not names:
        return [{}]
    if not db:
        return [{name: 1 for name in names}]
    max_double = int(search.get("max_buffers_with_multiplier_2", 2))
    max_candidates = int(search.get("max_per_buffer_multiplier_candidates", 3))
    plans: List[Dict[str, int]] = []
    # 按 double buffer 数量从保守到丰富逐层枚举。
    for r in range(0, min(max_double, len(names)) + 1):
        for doubled in itertools.combinations(names, r):
            dset = set(doubled)
            plan = {name: (2 if name in dset else 1) for name in names}
            plans.append(plan)
            if len(plans) >= max_candidates:
                return plans
    return plans


def per_buffer_extra_bytes_by_scope(kf: KernelFeatures, multipliers: Dict[str, int]) -> Dict[str, int]:
    """计算 per-buffer multiplier 相比单 buffer 额外增加的各层级容量占用。"""
    out = {s: 0 for s in LOCAL_SPACES}
    if not multipliers:
        return out
    by_name: Dict[str, BufferInfo] = {}
    for b in kf.buffers:
        by_name.setdefault(b.name, b)
    for name, mult in multipliers.items():
        if int(mult) <= 1:
            continue
        b = by_name.get(name)
        if not b or b.space not in LOCAL_SPACES:
            continue
        aligned = _align(int(b.size_bytes), 512 if b.space.startswith("l0") else 32)
        out[b.space] = out.get(b.space, 0) + aligned * (int(mult) - 1)
    return out


def per_buffer_overlap_bonus(kf: KernelFeatures, multipliers: Dict[str, int]) -> Dict[str, float]:
    """根据被 double 的 buffer 类型估算访存重叠收益，用于 cost model 的 overlap 修正。"""
    by_name: Dict[str, BufferInfo] = {b.name: b for b in kf.buffers}
    load_bonus = 0.0
    store_bonus = 0.0
    stage_bonus = 0.0
    doubled: List[str] = []
    for name, mult in multipliers.items():
        if int(mult) <= 1:
            continue
        b = by_name.get(name)
        if not b:
            continue
        doubled.append(name)
        lname = name.lower()
        if b.space == "l1":
            load_bonus += 0.10
        elif b.space == "ub":
            load_bonus += 0.07
        elif b.space.startswith("l0"):
            load_bonus += 0.03
        if any(x in lname for x in ["out", "store", "p_", "s_", "acc"]):
            store_bonus += 0.04
        if any(x in lname for x in ["stage", "ping", "pong"]):
            stage_bonus += 0.04
    return {
        "load_overlap_bonus": min(0.30, load_bonus + stage_bonus),
        "store_overlap_bonus": min(0.16, store_bonus),
        "num_doubled_buffers": len(doubled),
        "doubled_buffers": doubled,
    }

def apply_v2_focus_space(search: Dict[str, Any], kf: KernelFeatures, hw: Dict[str, Any]) -> Dict[str, Any]:
    """根据 focus preset 收缩或扩展搜索空间，控制 demo 的搜索规模。"""
    out = copy.deepcopy(search)
    max_cores = get_available_cores(kf, hw)
    tile_to_block: Dict[str, List[int]] = {}
    tile_task_counts: Dict[str, int] = {}
    for tile in out.get("tile_candidates", []):
        key = tile_key(tile)
        n_tiles = estimate_num_tiles_for_tile(kf, out, tile)
        tile_task_counts[key] = n_tiles
        tile_to_block[key] = [select_default_block_dim_for_tile(n_tiles, max_cores)]

    out["model_version"] = "V2.8.5-continuous-capped-penalty-model"
    out["candidate_generation"] = "v24_closest_hivm_four_plan_model"
    out["focused_search_parameters"] = [
        "TilingPlan.tile_shape",
        "TilingPlan.loop_order",
        "TilingPlan.tail_strategy",
        "TilingPlan.reduce_tile_policy",
        "TilingPlan.layout_aware_tile",
        "MultiBufferPlan.double_buffer",
        "MultiBufferPlan.multibuffer_template",
        "MultiBufferPlan.buffer_multipliers: per eligible buffer nbuf_b in {1,2}",
        "MultiBufferPlan.ub_multiplier (legacy coarse scope knob retained for compatibility)",
        "MultiBufferPlan.l1_multiplier (legacy coarse scope knob retained for compatibility)",
        "CVPipelinePlan.cv_pipeline_plan_candidates (template-bundled stage/template/loop-mix/balance/stage-buffer patterns)",
        "SyncPlan.policy/template",
        "SyncPlan.barrier_level",
        "SyncPlan.event_reuse",
        "SyncPlan.sync_granularity",
        "SyncPlan.event_id_policy",
        "SyncPlan.sync_motion",
    ]
    out["fixed_or_derived_parameters"] = {
        "fusion": "keep_existing",
        "block_dim": "derived per tile by select_default_block_dim_for_tile(); not searched",
        "memory_reuse_level": "level1",
        "cv_split_ratio": "1:1",
        "dma_policy": "keep_existing",
        "block_dim": "derived per tile by select_default_block_dim_for_tile(); not searched",
    }
    out["fusion_candidates"] = ["keep_existing"]
    out["tile_to_block_dim_candidates"] = tile_to_block
    out["tile_task_counts"] = tile_task_counts
    out["block_dim_candidates"] = sorted({b for xs in tile_to_block.values() for b in xs}) or [1]
    tiling_knobs = _available_tiling_knobs(kf)
    out.update(tiling_knobs)
    out["double_buffer"] = [False, True]
    out["multibuffer_template"] = _available_multibuffer_templates(kf)
    # V2.7 保留粗粒度 scope multiplier，同时加入与文档三一致的 per-buffer nbuf_b∈{1,2}。
    # 真正的 per-buffer 组合在 Layer2 中生成，因为它依赖 DB/template 和 MLIR buffer 证据。
    out["ub_multiplier"] = [1]
    out["l1_multiplier"] = [1]
    out["eligible_multibuffer_buffers"] = eligible_multibuffer_buffers(kf, out)
    out["per_buffer_multiplier_domain"] = {b["name"]: [1, 2] for b in out["eligible_multibuffer_buffers"]}
    out["max_buffers_with_multiplier_2"] = int(out.get("max_buffers_with_multiplier_2", 2))
    out["max_per_buffer_multiplier_candidates"] = int(out.get("max_per_buffer_multiplier_candidates", 3))
    cv_knobs = _available_cv_knobs(kf)
    out.update(cv_knobs)
    out["cv_pipeline_plan_candidates"] = build_cv_pipeline_plan_candidates(kf, out)
    out["cv_pipeline_search_strategy"] = "template_bundled_candidates_not_full_cartesian_product"
    out["cv_split_ratio"] = ["1:1"]
    out["memory_reuse_level"] = ["level1"]
    sync_knobs = _available_sync_knobs(kf)
    out.update(sync_knobs)
    out["dma_policy"] = ["keep_existing"]
    out["layer1_top_w"] = int(out.get("layer1_top_w", 24))
    out["layer2_top_w"] = int(out.get("layer2_top_w", 8))
    out["layer3_top_w"] = int(out.get("layer3_top_w", 12))
    out["layer1_diversity_beam_enabled"] = bool(out.get("layer1_diversity_beam_enabled", True))
    out["layer1_diversity_group_fields"] = list(out.get("layer1_diversity_group_fields", ["tile_m", "tile_n", "tile_k", "block_dim"]))
    out["layer1_diversity_per_group_keep"] = int(out.get("layer1_diversity_per_group_keep", 1))
    out["layer1_diversity_max_extra"] = int(out.get("layer1_diversity_max_extra", 12))
    out["layer1_fallback_keep"] = int(out.get("layer1_fallback_keep", 4))
    out["hardware_constraints_summary"] = {
        "version": "V3.3-artifact-kernel-profile",
        "block_dim_generation": "derived_default_not_searched",
        "max_available_cores": max_cores,
        "num_tile_candidates": len(out.get("tile_candidates", [])),
        "global_block_dim_candidates": out["block_dim_candidates"],
        "rule": "block_dim is derived for each tile: argmax effective_parallelism under 1 <= B <= min(max_available_cores, n_tiles_total(tile))",
        "focused_constraints": "C1/C2/C4 estimated for T,M,P; C3 estimated/UNKNOWN for Y unless real GraphSyncSolver sidecar is provided",
    }
    out["search_space_size_estimate"] = estimate_search_space_size(out)
    return out


def refresh_dynamic_candidate_space(search: Dict[str, Any], kf: KernelFeatures, hw: Dict[str, Any]) -> Dict[str, Any]:
    """基于输入 IR 特征、硬件配置和 artifact 证据动态刷新候选搜索空间。"""
    out = copy.deepcopy(search)
    max_cores = get_available_cores(kf, hw)
    tile_to_block: Dict[str, List[int]] = {}
    tile_task_counts: Dict[str, int] = {}
    global_block_dims = set()

    for tile in out.get("tile_candidates", []):
        key = tile_key(tile)
        n_tiles = estimate_num_tiles_for_tile(kf, out, tile)
        b_candidates = generate_block_dim_candidates_for_tile(n_tiles, max_cores)
        tile_to_block[key] = b_candidates
        tile_task_counts[key] = n_tiles
        global_block_dims.update(b_candidates)

    out["block_dim_candidates"] = sorted(global_block_dims) or [1]
    out["tile_to_block_dim_candidates"] = tile_to_block
    out["tile_task_counts"] = tile_task_counts
    out["hardware_constraints_summary"] = {
        "block_dim_generation": "per_tile_hardware_kernel_aware",
        "max_available_cores": max_cores,
        "num_tile_candidates": len(out.get("tile_candidates", [])),
        "global_block_dim_candidates": out["block_dim_candidates"],
        "full_core_candidate_present": any(max_cores in xs for xs in tile_to_block.values()),
        "rule": "1 <= block_dim <= min(max_available_cores, n_tiles_total(tile)); include divisors and near-full-core candidates",
    }
    out["search_space_size_estimate"] = estimate_search_space_size(out)
    return out


def iter_layer1_raw_candidates(search: Dict[str, Any]):
    """生成 Layer-1 粗筛阶段的原始 tiling/fusion 候选。"""
    tile_to_block = search.get("tile_to_block_dim_candidates", {}) or {}
    for tile in search["tile_candidates"]:
        key = tile_key(tile)
        block_dims = tile_to_block.get(key, search.get("block_dim_candidates", [1]))
        for fusion in search.get("fusion_candidates", ["keep_existing"]):
            for loop_order in search.get("loop_order", ["outer_mnk"]):
                for tail_strategy in search.get("tail_strategy", ["mask_or_pad"]):
                    for reduce_tile_policy in search.get("reduce_tile_policy", ["full_k"]):
                        for layout_aware_tile in search.get("layout_aware_tile", [True]):
                            for block_dim in block_dims:
                                yield tile, fusion, int(block_dim), str(loop_order), str(tail_strategy), str(reduce_tile_policy), bool(layout_aware_tile)


def generate_aligned_dim_values(total: int, align: int, density: str, common: List[int]) -> List[int]:
    """围绕问题规模、对齐粒度和常用工程点生成 tile 维度候选。"""
    total = max(1, int(total))
    align = max(1, int(align))
    aligned_total = max(align, _align(total, align))
    density = (density or "standard").lower()

    if density == "full":
        return list(range(align, aligned_total + 1, align))

    vals = {align, aligned_total}
    for v in common:
        if 1 <= int(v) <= aligned_total:
            vals.add(_align(int(v), align))

    # shape-aware fraction 用于保留与问题规模相关的边界点。
    for div in [2, 3, 4, 6, 8, 16]:
        vals.add(max(align, _align(math.ceil(total / div), align)))

    # 加入总规模约数并按对齐粒度修正；这些点常能产生更整齐的 tile/task wave，也减少手工挑点。
    for d in range(1, int(math.sqrt(total)) + 1):
        if total % d == 0:
            vals.add(max(align, _align(d, align)))
            vals.add(max(align, _align(total // d, align)))

    if density == "expanded":
        # 使用规则对齐网格；步长保证 demo 可运行，同时比标准代表点更密。
        step = max(align, align * 2)
        for v in range(align, aligned_total + 1, step):
            vals.add(v)
        # 近边界点很重要，因为很多最优解靠近“刚好满足内存约束的最大 tile”。
        for back in [1, 2, 3, 4, 6, 8]:
            vals.add(max(align, aligned_total - back * align))

    return sorted({int(v) for v in vals if align <= int(v) <= aligned_total and int(v) % align == 0})


def auto_generate_search_space(kf: KernelFeatures, hw: Dict[str, Any], candidate_space: str = "standard") -> Dict[str, Any]:
    """从 kernel 特征和硬件配置自动生成四类 Plan 的候选取值空间。"""
    cm, cn, ck = cube_tile(hw)
    candidate_space = (candidate_space or "standard").lower()
    p = dict(kf.inferred_problem_shape)
    m_total = max(1, int(p.get("m_total", 512)))
    n_total = max(1, int(p.get("n_total", 512)))
    k_total = max(1, int(p.get("k_total", 512)))

    m_vals = generate_aligned_dim_values(m_total, cm, candidate_space, [16, 32, 64])
    # 在这个 demo kernel 中，M 通常较小；M 保持对齐并由 shape 驱动，而不是写死。
    # full mode 仍会包含所有对齐后的 M 值。
    if candidate_space != "full":
        m_vals = [v for v in m_vals if v <= max(cm, _align(min(m_total, 64), cm))]
    if not m_vals:
        m_vals = [cm]
    # 把保守工程 tile-N 点作为一等候选。
    # 否则扩展网格可能跳过 96/160/192，Layer-1 剪枝时只比较 176/208/256 这类较大的不规则 tile。
    n_vals = generate_aligned_dim_values(n_total, cn, candidate_space, [64, 96, 128, 160, 192, 256, 512])
    k_vals = generate_aligned_dim_values(k_total, ck, candidate_space, [64, 128, 256, 512])

    # V2.7-generic：如果 parser 从当前 HIVM 文件抽取到具体 cube/mmad tile，则保留为一等候选。
    # 这里不会写死任何 sample 数值，而是使用输入 IR 自身暴露的信息。
    for key, vals, align in [("extracted_tile_m", m_vals, cm), ("extracted_tile_n", n_vals, cn), ("extracted_tile_k", k_vals, ck)]:
        v = p.get(key)
        if isinstance(v, int) and v > 0 and v % align == 0 and v not in vals:
            vals.append(int(v))
            vals.sort()

    tiles = []
    seen = set()
    for m in m_vals:
        for n in n_vals:
            for k in k_vals:
                if m % cm == 0 and n % cn == 0 and k % ck == 0:
                    item = {"m": int(m), "n": int(n), "k": int(k)}
                    key = tile_key(item)
                    if key not in seen:
                        seen.add(key)
                        tiles.append(item)

    # Stage2a stability rule: denser spaces must explicitly contain the standard
    # representative tile grid.  This avoids the confusing situation where
    # ``expanded`` regenerates a different tile set and accidentally drops a
    # standard candidate before the beam search ever sees it.
    standard_tile_keys: List[str] = []
    if candidate_space in {"expanded", "full"}:
        m_std = generate_aligned_dim_values(m_total, cm, "standard", [16, 32, 64])
        if candidate_space != "full":
            m_std = [v for v in m_std if v <= max(cm, _align(min(m_total, 64), cm))]
        if not m_std:
            m_std = [cm]
        n_std = generate_aligned_dim_values(n_total, cn, "standard", [64, 96, 128, 160, 192, 256, 512])
        k_std = generate_aligned_dim_values(k_total, ck, "standard", [64, 128, 256, 512])
        for key_name, vals, align in [("extracted_tile_m", m_std, cm), ("extracted_tile_n", n_std, cn), ("extracted_tile_k", k_std, ck)]:
            v = p.get(key_name)
            if isinstance(v, int) and v > 0 and v % align == 0 and v not in vals:
                vals.append(int(v))
                vals.sort()
        for m in m_std:
            for n in n_std:
                for k in k_std:
                    if m % cm == 0 and n % cn == 0 and k % ck == 0:
                        item = {"m": int(m), "n": int(n), "k": int(k)}
                        key = tile_key(item)
                        standard_tile_keys.append(key)
                        if key not in seen:
                            seen.add(key)
                            tiles.append(item)
    else:
        standard_tile_keys = [tile_key(t) for t in tiles]

    search = {
        "problem_shape_hint": p,
        "tile_candidates": tiles,
        "fusion_candidates": ["keep_existing", "moderate_elementwise_fusion", "aggressive_elementwise_fusion"] if kf.vector_op_counts else ["keep_existing"],
        "double_buffer": [False, True],
        "cv_pipeline_stage": [1, 2, 4] if (kf.has_aic and kf.has_aiv and (kf.num_mmad or kf.vector_op_counts)) else [1, 2],
        "cv_split_ratio": ["1:1", "1:2", "2:1"] if (kf.num_mmad and kf.vector_op_counts) else ["1:1"],
        "memory_reuse_level": ["level2", "level1", "level0", "inplace"],
        "sync_policy": ["keep_existing", "graph_sync_solver"] if (kf.num_set_flag + kf.num_wait_flag + kf.num_pipe_barrier) else ["keep_existing"],
        "dma_policy": ["keep_existing", "prefer_contiguous", "prefetch_nd2nz"] if kf.num_nd2nz else ["keep_existing", "prefer_contiguous"],
        "layer1_top_w": 24,
        "layer2_top_w": 8,
        "layer1_diversity_beam_enabled": True,
        "layer1_diversity_group_fields": ["tile_m", "tile_n", "tile_k", "block_dim"],
        "layer1_diversity_per_group_keep": 1,
        "layer1_diversity_max_extra": 12,
        "layer1_fallback_keep": 4,
        "top_k": 10,
        "candidate_generation": "hardware_and_kernel_shape_driven",
        "candidate_space_density": candidate_space,
        "standard_tile_keys": sorted(set(standard_tile_keys)),
        "standard_candidates_included": candidate_space in {"standard", "expanded", "full"},
    }
    return refresh_dynamic_candidate_space(search, kf, hw)


def merge_search_space(auto: Dict[str, Any], override_path: Optional[str]) -> Dict[str, Any]:
    """把自动生成的搜索空间与用户显式配置合并，显式配置优先。"""
    out = copy.deepcopy(auto)
    if override_path:
        ov = load_json(override_path)
        for k, v in ov.items():
            out[k] = v
    return out



def estimate_search_space_size(search: Dict[str, Any]) -> Dict[str, int]:
    """估算四类 Plan 笛卡尔积规模，并给出各维度候选数量。"""
    fusion_n = len(search.get("fusion_candidates", []))
    tiling_subknobs = (
        len(search.get("loop_order", ["outer_mnk"]))
        * len(search.get("tail_strategy", ["mask_or_pad"]))
        * len(search.get("reduce_tile_policy", ["full_k"]))
        * len(search.get("layout_aware_tile", [True]))
    )
    tile_to_block = search.get("tile_to_block_dim_candidates", {}) or {}
    if tile_to_block:
        l1 = fusion_n * tiling_subknobs * sum(len(v) for v in tile_to_block.values())
    else:
        l1 = fusion_n * tiling_subknobs * len(search.get("tile_candidates", [])) * len(search.get("block_dim_candidates", []))
    cv_candidates = search.get("cv_pipeline_plan_candidates")
    cv_n = len(cv_candidates) if isinstance(cv_candidates, list) and cv_candidates else (
        len(search.get("cv_pipeline_stage", []))
        * len(search.get("cv_pipeline_template", ["auto"]))
        * len(search.get("enable_mixed_cv", [False]))
        * len(search.get("tile_mix_cube_loop", [1]))
        * len(search.get("tile_mix_vector_loop", [1]))
        * len(search.get("auto_cv_balance", [True]))
        * len(search.get("producer_consumer_distance", [1]))
        * len(search.get("stage_buffer_policy", ["none"]))
    )
    l2 = (
        len(search.get("double_buffer", []))
        * len(search.get("multibuffer_template", ["auto"]))
        * len(search.get("ub_multiplier", [1]))
        * len(search.get("l1_multiplier", [1]))
        * cv_n
        * len(search.get("cv_split_ratio", []))
    )
    l3 = (
        len(search.get("memory_reuse_level", []))
        * len(search.get("sync_policy", []))
        * len(search.get("sync_template", ["auto"]))
        * len(search.get("barrier_level", ["medium"]))
        * len(search.get("event_reuse", [False]))
        * len(search.get("sync_granularity", ["op"]))
        * len(search.get("event_id_policy", ["keep"]))
        * len(search.get("sync_motion", ["none"]))
        * len(search.get("dma_policy", []))
    )
    return {"raw_l1": l1, "raw_l2_per_l1": l2, "raw_l3_per_l2": l3, "raw_total_cartesian": l1 * l2 * l3}

def _keep_ordered_existing(values: List[Any], preferred: List[Any], fallback_keep: int = 1) -> List[Any]:
    """按原顺序保留候选列表中真实存在的值，用于诊断裁剪后保序。"""
    src = list(values or [])
    out: List[Any] = []
    for v in preferred:
        if v in src and v not in out:
            out.append(v)
    for v in src:
        if len(out) >= max(len(out), fallback_keep) and fallback_keep <= 0:
            break
        if v not in out and len(out) < len(preferred) + fallback_keep:
            out.append(v)
    return out or src[:max(1, fallback_keep)]


def apply_guided_search_adjustments(search: Dict[str, Any], hints: DiagnosisHints, strength: str = "soft") -> Dict[str, Any]:
    """根据诊断模式调整搜索空间和 beam 宽度，但最终选择仍由 predicted_cycles 决定。"""
    out = copy.deepcopy(search)
    if not hints.enabled:
        out["guided_mode"] = "off"
        return out
    vb = hints.variable_bias
    strength = (strength or "soft").lower()

    # 当诊断信息建议某些取值时，确保这些取值存在于候选空间中。
    if vb.get("y", 1.0) > 1.1 and "graph_sync_solver" not in out.get("sync_policy", []):
        out.setdefault("sync_policy", ["keep_existing"]).append("graph_sync_solver")
    if vb.get("d", 1.0) > 1.1:
        out.setdefault("dma_policy", ["keep_existing"])
        for d in ["prefer_contiguous", "prefetch_nd2nz"]:
            if d not in out["dma_policy"]:
                out["dma_policy"].append(d)
    if vb.get("m", 1.0) > 1.1 and True not in out.get("double_buffer", []):
        out.setdefault("double_buffer", [False]).append(True)
    if vb.get("s", 1.0) > 1.1:
        out.setdefault("cv_pipeline_stage", [1])
        for st in [2, 4]:
            if st not in out["cv_pipeline_stage"]:
                out["cv_pipeline_stage"].append(st)

    # 三种诊断模式。无论哪种模式，最终选择始终以 predicted_cycles 最小为准。
    # - soft：较宽的诊断感知搜索；必要时扩大 beam，避免漏掉候选。
    # - balanced：适度缩小 beam 提高效率，同时保留各维度取值。
    # - aggressive：剪掉低优先级取值，但保留少量探索兜底。
    if strength == "soft":
        if max(vb.get("t", 1.0), vb.get("B", 1.0), vb.get("f", 1.0)) > 1.15:
            out["layer1_top_w"] = int(max(int(out.get("layer1_top_w", 24)), 36))
        if max(vb.get("m", 1.0), vb.get("s", 1.0), vb.get("r", 1.0), vb.get("y", 1.0)) > 1.15:
            out["layer2_top_w"] = int(max(int(out.get("layer2_top_w", 8)), 12))
        out["guided_pruning"] = "none_broad_diagnosis_search"

    elif strength == "balanced":
        out["layer1_top_w"] = int(min(int(out.get("layer1_top_w", 24)), 18))
        out["layer2_top_w"] = int(min(int(out.get("layer2_top_w", 8)), 6))
        # 保留所有合法取值维度，只缩小 beam 宽度。
        out["guided_pruning"] = "beam_width_reduction_only"

    elif strength == "aggressive":
        out["layer1_top_w"] = int(min(int(out.get("layer1_top_w", 24)), 12))
        out["layer2_top_w"] = int(min(int(out.get("layer2_top_w", 8)), 4))
        # 取值级剪枝：保留诊断偏好的取值以及兜底取值。
        if vb.get("f", 1.0) > 1.15:
            out["fusion_candidates"] = _keep_ordered_existing(out.get("fusion_candidates", []), ["moderate_elementwise_fusion", "aggressive_elementwise_fusion"], fallback_keep=1)
        if vb.get("m", 1.0) > 1.15:
            out["double_buffer"] = _keep_ordered_existing(out.get("double_buffer", []), [True], fallback_keep=1)
        if vb.get("s", 1.0) > 1.15:
            out["cv_pipeline_stage"] = _keep_ordered_existing(out.get("cv_pipeline_stage", []), [2, 4], fallback_keep=1)
        if vb.get("r", 1.0) > 1.15:
            out["cv_split_ratio"] = _keep_ordered_existing(out.get("cv_split_ratio", []), ["1:1", "1:2", "2:1"], fallback_keep=0)
        if vb.get("ℓ", 1.0) > 1.15:
            out["memory_reuse_level"] = _keep_ordered_existing(out.get("memory_reuse_level", []), ["level2", "level1"], fallback_keep=0)
        if vb.get("y", 1.0) > 1.15:
            out["sync_policy"] = _keep_ordered_existing(out.get("sync_policy", []), ["graph_sync_solver"], fallback_keep=1)
        if vb.get("d", 1.0) > 1.15:
            out["dma_policy"] = _keep_ordered_existing(out.get("dma_policy", []), ["prefer_contiguous", "prefetch_nd2nz"], fallback_keep=1)

        # Tile 剪枝：保留硬件对齐且接近诊断偏好区域的 tile。
        # 对 memory/serial/vector 信号偏好中大型 n/k tile，但仍保留小 tile 兜底。
        tiles = list(out.get("tile_candidates", []))
        if tiles:
            scored_tiles = []
            for tile in tiles:
                n = int(tile.get("n", 0)); k = int(tile.get("k", 0)); m = int(tile.get("m", 0))
                score = 0
                if n >= 128: score += 2
                if k >= 128: score += 2
                if m == 16: score += 1
                if vb.get("t", 1.0) > 1.5: score += int((n + k) / 128)
                scored_tiles.append((score, tile))
            scored_tiles.sort(key=lambda x: (x[0], x[1].get("n", 0), x[1].get("k", 0)), reverse=True)
            keep_n = max(6, min(len(scored_tiles), 8))
            kept = [t for _, t in scored_tiles[:keep_n]]
            # 保留中等 tile 作为探索项，因为很多 CV kernel 偏好仍能允许 double buffering 的中等 tile。
            # 这是软诊断和硬剪枝的关键区别：诊断会缩小空间，但不会退化成“tile 越大越好”的单调区域。
            for t in tiles:
                if int(t.get("n", 0)) == 128 and int(t.get("k", 0)) >= 128 and t not in kept:
                    kept.append(t)
            # 确保保守的小 tile 兜底仍然存在。
            small = sorted(tiles, key=lambda x: (x.get("n", 0) + x.get("k", 0), x.get("m", 0)))[:1]
            for t in small:
                if t not in kept:
                    kept.append(t)
            out["tile_candidates"] = kept
        out["guided_pruning"] = "diagnosis_value_pruning_with_exploration_fallback"
    else:
        out["guided_pruning"] = f"unknown_strength_{strength}_fallback_soft"

    out["guided_strength"] = strength
    out["guided_mode"] = hints.mode
    out["diagnosis_variable_bias"] = hints.variable_bias
    out["diagnosis_value_bias"] = hints.value_bias
    out["search_space_size_estimate"] = estimate_search_space_size(out)
    return out


# ------------------------------ 解析输入 IR ------------------------------

def _parse_static_buffers(text: str) -> List[BufferInfo]:
    """解析 MLIR 中局部 buffer 的分配、空间、大小和粗略生命周期。"""
    lines = text.splitlines()
    buffers: List[BufferInfo] = []
    # 捕获同一行中结果 SSA 名称及其后续 memref<..., #hivm.address_space<space>> 类型。
    def_re = re.compile(r"%([A-Za-z0-9_]+)\s*=.*?memref<([^>]+?)#hivm\.address_space<([a-zA-Z0-9_]+)>[^>]*>")
    for i, line in enumerate(lines):
        m = def_re.search(line)
        if not m:
            continue
        name, body, space = m.group(1), m.group(2), _norm_space(m.group(3))
        if space not in LOCAL_SPACES:
            continue
        size = _parse_memref_size(body)
        if size is None:
            continue
        kill = i
        token = f"%{name}"
        for j in range(i + 1, len(lines)):
            if token in lines[j]:
                kill = j
        buffers.append(BufferInfo(name=name, space=space, size_bytes=size, gen=i, kill=kill))
    return buffers


def _static_max_live(buffers: List[BufferInfo], hw: Dict[str, Any] | None = None) -> Dict[str, int]:
    """根据 buffer 的 gen/kill 生命周期估算每个 address space 的静态 max-live 字节数。"""
    align = {"ub": 32, "l1": 32, "l0a": 512, "l0b": 512, "l0c": 512}
    out = {s: 0 for s in LOCAL_SPACES}
    if not buffers:
        return out
    points = sorted({b.gen for b in buffers} | {b.kill for b in buffers})
    for t in points:
        cur = {s: 0 for s in LOCAL_SPACES}
        for b in buffers:
            if b.gen <= t <= b.kill:
                cur[b.space] = cur.get(b.space, 0) + _align(b.size_bytes, align.get(b.space, 32))
        for s, v in cur.items():
            out[s] = max(out.get(s, 0), v)
    return out


def _extract_memref_footprints(text: str) -> Dict[str, int]:
    """统计 MLIR 中各 address space 的 memref 静态字节 footprint。"""
    footprints = {"ub": 0, "l1": 0, "l0a": 0, "l0b": 0, "l0c": 0, "gm": 0}
    memref_re = re.compile(r"memref<([^>]+?)#hivm\.address_space<([a-zA-Z0-9_]+)>[^>]*>")
    for m in memref_re.finditer(text):
        body, space = m.group(1), _norm_space(m.group(2))
        if space not in footprints:
            continue
        size = _parse_memref_size(body)
        if size is None:
            continue
        footprints[space] = footprints.get(space, 0) + size
    return footprints


def parse_kernel_features(kernel_path: str) -> KernelFeatures:
    """解析输入 IR，抽取 op 计数、buffer footprint、max-live 和问题规模等 kernel 特征。"""
    text = Path(kernel_path).read_text(encoding="utf-8", errors="ignore")
    op_re = re.compile(r"hivm\.hir\.([a-zA-Z0-9_]+)")
    ops = op_re.findall(text)
    op_counts: Dict[str, int] = {}
    for op in ops:
        op_counts[op] = op_counts.get(op, 0) + 1
    # 将裸 HIVM 同步写法归一到同一组计数器。
    # 裸 compute/vector/transfer 算子在本 demo 中不常见，但同步算子经常写成 hivm.set_flag 而不是 hivm.hir.set_flag。
    sync_counts = count_hivm_ops(text, ["set_flag", "wait_flag", "pipe_barrier", "sync_block_set", "sync_block_wait"])
    op_counts.update(sync_counts)
    vector_ops = {k: v for k, v in op_counts.items() if k.startswith("v") or k in {"vreduce", "vcmp", "vsel"}}

    consts = [int(x) for x in re.findall(r"arith\.constant\s+(-?\d+)\s*:", text) if int(x) > 0]
    named_memrefs = _extract_named_memrefs(text)
    generic = _infer_generic_hivm_structure(text, named_memrefs)
    primary_tile = generic.get("primary_tile_candidate", {}) if isinstance(generic, dict) else {}
    conv = generic.get("conventional_tensor_signature", {}) if isinstance(generic, dict) else {}
    q_dims = conv.get("Q_gm") or []
    k_dims = conv.get("K_gm") or conv.get("V_gm") or []

    if conv.get("detected") and len(q_dims) >= 2 and len(k_dims) >= 1:
        # 基于名称的 tensor signature 证据；这是通用可选证据，不是硬编码假设 kernel 一定是 FlashAttention。
        inferred_m = int(q_dims[0])
        inferred_n = int(k_dims[0])
        inferred_k = int(q_dims[1])
        outer_iterations = 1
    elif primary_tile:
        inferred_m = int(primary_tile.get("tile_m") or 16)
        inferred_n = int(max(primary_tile.get("tile_n") or 0, max(consts) if consts else 512))
        inferred_k = int(primary_tile.get("tile_k") or 128)
        outer_iterations = 1
    else:
        inferred_m = 16
        inferred_n = 512 if ("16, 512" in text or "16x512" in text or "c512" in text) else (max(consts) if consts else 512)
        inferred_k = 512 if inferred_n >= 512 else inferred_n
        outer_iterations = 8 if re.search(r"to\s+%c8_i32", text) or "c8_i32" in text else 1

    buffers = _parse_static_buffers(text)
    inferred_shape = {"m_total": inferred_m, "n_total": inferred_n, "k_total": inferred_k, "outer_iterations": outer_iterations}
    if generic.get("detected"):
        inferred_shape.update({
            "kernel_family": "generic_hivm_structure",
            "extracted_tile_m": int(primary_tile.get("tile_m") or inferred_m),
            "extracted_tile_n": int(primary_tile.get("tile_n") or 0),
            "extracted_tile_k": int(primary_tile.get("tile_k") or inferred_k),
            "loop_trip_annotation": int(generic.get("loop_trip_annotation") or 0),
        })
    return KernelFeatures(
        op_counts=op_counts,
        vector_op_counts=vector_ops,
        num_functions=len(re.findall(r"func\.func\s+@", text)),
        has_aic=("func_core_type<AIC>" in text) or ((op_counts.get("mmadL1", 0) + op_counts.get("mmad", 0)) > 0),
        has_aiv=("func_core_type<AIV>" in text) or bool(vector_ops),
        num_pipe_barrier=op_counts.get("pipe_barrier", 0),
        num_set_flag=op_counts.get("set_flag", 0),
        num_wait_flag=op_counts.get("wait_flag", 0),
        num_sync_block_set=op_counts.get("sync_block_set", 0),
        num_sync_block_wait=op_counts.get("sync_block_wait", 0),
        num_nd2nz=op_counts.get("nd2nz", 0),
        num_mmad=op_counts.get("mmadL1", 0) + op_counts.get("mmad", 0),
        num_fixpipe=op_counts.get("fixpipe", 0),
        num_load=op_counts.get("load", 0),
        num_store=op_counts.get("store", 0),
        base_local_footprint_bytes=_extract_memref_footprints(text),
        static_max_live_bytes=_static_max_live(buffers),
        buffers=buffers,
        inferred_problem_shape=inferred_shape,
    )


# ------------------------------ 硬件辅助函数 ------------------------------

def _size_item_to_bytes(item: Dict[str, Any]) -> int:
    """把硬件配置里的 size_kb/size_mb/size_gb 统一换算为 bytes。"""
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
    """读取指定 address space 的容量上限。

    除 UB/L1/L0A/L0B/L0C 外，V2.8.6 新增 gm_ws，用于表示编译策略可使用的
    GM/HBM workspace 预算。优先读取 memory_spaces.gm_workspace / workspace / gm_ws；
    如果配置缺失，则用 hbm 容量乘 workspace_budget_fraction 作为保守兜底。
    """
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
    item = ms.get(key, {})
    return _size_item_to_bytes(item)


def space_alignment(hw: Dict[str, Any], space: str) -> int:
    # 硬件配置通常把对齐信息放在 data_movers 下；缺失时使用文档默认值。
    """读取指定 address space 的对齐粒度；若配置缺失则使用文档默认值。"""
    if space in {"l0a", "l0b", "l0c"}:
        return 512
    if space in {"ub", "l1"}:
        return 32
    return 32


def bandwidth_bytes_per_cycle(hw: Dict[str, Any], mover: str, default: float) -> float:
    """读取或估算指定数据通路的每 cycle 带宽，用于访存 cost。"""
    freq = float(hw.get("clock", {}).get("frequency_ghz", 1.85)) * 1e9
    dm = hw.get("data_movers", {}).get(mover, {})
    gbps = dm.get("bandwidth_gbps")
    if gbps is None:
        return default
    # 在解析式 demo 中，把配置里的 bandwidth_gbps 当作 GB/s 级别模型常量使用。
    return float(gbps) * 1e9 / freq


def cube_flops_per_cycle(hw: Dict[str, Any]) -> float:
    """读取 Cube 单元吞吐，用于矩阵计算 cost 估算。"""
    freq = float(hw.get("clock", {}).get("frequency_ghz", 1.85)) * 1e9
    tflops = hw.get("compute_units", {}).get("cube", {}).get("tflops_fp16", 320)
    return float(tflops) * 1e12 / freq


def vector_elems_per_cycle(hw: Dict[str, Any]) -> float:
    """读取 Vector 单元吞吐，用于向量算子 cost 估算。"""
    return float(hw.get("compute_units", {}).get("vector", {}).get("width_elements", 128))


def cube_tile(hw: Dict[str, Any]) -> Tuple[int, int, int]:
    """读取硬件 Cube 基础 tile 形状，用于对齐和 tile 合法性判断。"""
    cu = hw.get("compute_units", {}).get("cube", {})
    return int(cu.get("tile_m", 16)), int(cu.get("tile_n", 16)), int(cu.get("tile_k", 16))


# ------------------------------ 建模与 cost 估算 ------------------------------

def problem_shape(search: Dict[str, Any], kf: KernelFeatures) -> Dict[str, int]:
    """从 kernel 特征中取得推断问题规模，并提供缺省规模兜底。"""
    hint = search.get("problem_shape_hint") or {}
    base = dict(kf.inferred_problem_shape)
    base.update({k: int(v) for k, v in hint.items() if isinstance(v, (int, float, str)) and str(v).lstrip("-").isdigit()})
    return base


def satisfies_align_tile(tile_m: int, tile_n: int, tile_k: int, hw: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """检查 tile_m/tile_n/tile_k 是否满足硬件 tile 和搬运对齐约束。"""
    cm, cn, ck = cube_tile(hw)
    notes: List[str] = []
    ok = True
    for name, v, a in [("tile_m", tile_m, cm), ("tile_n", tile_n, cn), ("tile_k", tile_k, ck)]:
        if v % a != 0:
            ok = False
            notes.append(f"{name}={v} is not aligned to cube fractal {a}")
    # 基础搬运对齐：bf16 tile 行至少应满足 32B 对齐。
    if (tile_n * 2) % 32 != 0:
        ok = False
        notes.append(f"tile_n bf16 row bytes={tile_n*2} not 32B aligned")
    if (tile_k * 2) % 32 != 0:
        ok = False
        notes.append(f"tile_k bf16 row bytes={tile_k*2} not 32B aligned")
    return ok, notes


def tile_buffers(c: StrategyConfig | Layer1Case, kf: KernelFeatures, hw: Dict[str, Any], *, single_buffer_only: bool = False) -> Dict[str, int]:
    """根据 tile 和 Plan 参数估算 UB/L1/L0A/L0B/L0C 的单 tile buffer 占用。"""
    elem = 2  # bf16/fp16 dominant
    acc = 4   # f32 accumulator / vector temporary
    # Layer1Case 阶段尚未引入 double_buffer/stage/reuse。
    db = False if single_buffer_only else bool(getattr(c, "double_buffer", False))
    stage = 1 if single_buffer_only else int(getattr(c, "cv_pipeline_stage", 1))
    reuse = "level2" if single_buffer_only else str(getattr(c, "memory_reuse_level", "level2"))
    fusion = str(getattr(c, "fusion", "keep_existing"))
    mb_template = str(getattr(c, "multibuffer_template", "M0_no_multibuffer"))
    ub_multiplier = 1 if single_buffer_only else int(getattr(c, "ub_multiplier", 1))
    l1_multiplier = 1 if single_buffer_only else int(getattr(c, "l1_multiplier", 1))
    stage_buffer_policy = "none" if single_buffer_only else str(getattr(c, "stage_buffer_policy", "none"))
    reduce_tile_policy = str(getattr(c, "reduce_tile_policy", "full_k"))

    db_mult = 2 if db else 1
    if mb_template in {"M2_input_output_double_buffer", "M3_ping_pong_detected"}:
        db_mult = max(db_mult, 2)
    # 只有跨 C/V 或 workspace 类 UB 部分应用 stage multiplier，并设置上限以保持 demo 保守。
    stage_mult = max(1, min(stage, 4))
    reuse_factor = {"inplace": 0.65, "level0": 0.75, "level1": 0.88, "level2": 1.00}.get(reuse, 1.0)
    fusion_factor = 0.90 if fusion != "keep_existing" else 1.0

    # Cube 路径。
    l1 = (c.tile_m * c.tile_k + c.tile_k * c.tile_n) * elem * db_mult * max(1, l1_multiplier)
    if reduce_tile_policy == "half_k":
        l1 *= 0.88
    l0a = c.tile_m * c.tile_k * elem
    l0b = c.tile_k * c.tile_n * elem
    l0c = c.tile_m * c.tile_n * acc
    # UB 中的 Vector 路径：输入、mask、临时累加器和输出 staging。
    ub_base = c.tile_m * c.tile_n * (acc * 2 + elem * 2)
    stage_extra = 0.35 * max(0, stage_mult - 1)
    if stage_buffer_policy == "ub_stage":
        stage_extra += 0.22 * max(0, stage_mult - 1)
    elif stage_buffer_policy in {"l1_stage", "l1_reuse"}:
        l1 *= (1.0 + 0.18 * max(0, stage_mult - 1))
    elif stage_buffer_policy == "gm_workspace":
        # CV stage handoff 放到 GM workspace 时，UB 只保留较小的描述符/局部切片代理；
        # 真实中转容量进入 gm_ws 资源项，额外 read/write cost 进入 cost model。
        stage_extra = 0.08 * max(0, stage_mult - 1)
    ub = ub_base * db_mult * max(1, ub_multiplier) * (1.0 + stage_extra) * fusion_factor
    gm_ws = 0
    if stage_buffer_policy == "gm_workspace" and not single_buffer_only:
        gm_ws = int(estimate_workspace_bytes(c, kf, hw, {}).get("workspace_bytes", 0))

    # V2.7 对齐文档三：per-buffer ping-pong/multibuffer 空间。
    # 每个被选中的局部 buffer b 都有独立 nbuf_b∈{1,2}；这里仅加入额外副本，因为单副本已由
    # 静态 max-live 或 tile 工作集代理项表示。
    per_buf = {} if single_buffer_only else _parse_buffer_multipliers_json(getattr(c, "buffer_multipliers_json", "{}"))
    per_buf_extra = per_buffer_extra_bytes_by_scope(kf, per_buf)

    return {
        "ub": int(ub * reuse_factor) + int(per_buf_extra.get("ub", 0)),
        "l1": int(l1 * reuse_factor) + int(per_buf_extra.get("l1", 0)),
        "l0a": int(l0a) + int(per_buf_extra.get("l0a", 0)),
        "l0b": int(l0b) + int(per_buf_extra.get("l0b", 0)),
        "l0c": int(l0c) + int(per_buf_extra.get("l0c", 0)),
        "gm_ws": int(gm_ws),
    }




def workspace_model_config(hw: Dict[str, Any]) -> Dict[str, Any]:
    """读取 GM workspace 建模参数，缺省值按真实编译 fallback 语义保持保守。

    GM workspace 在这里不是“免费扩容 UB”，而是片上 stage buffer 不可行时的
    off-chip spill / handoff 兜底路径。因此默认只允许 fallback、overlap 很低，
    并额外乘以 penalty_factor，避免搜索器把 GM workspace 当作优先优化策略。
    """
    cfg = {
        "handoff_tensor_count": 2,           # S/P 两类 C->V 或 V->C 中转张量代理
        "partial_output_tensor_count": 1,    # partial O / softmax statistics 代理项
        "stage_extra_factor": 1.0,
        "read_write_multiplier": 2.0,        # workspace 通常至少一次写入、一次读回
        "startup_cycles": 350.0,             # off-chip workspace 有更高 setup/排队开销
        "overlap_ratio": 0.10,               # 与主 MTE 通道竞争，默认只允许少量掩盖
        "penalty_factor": 2.0,               # spill/fallback 额外惩罚，需 profiling 标定
        "require_onchip_infeasible": True,   # 片上方案可行时禁止 GM workspace 候选
        "allow_gm_workspace_fallback": True,
        "max_workspace_utilization": 0.25,   # demo 中最多使用预留 workspace 的 25%
    }
    user = hw.get("workspace_model", {}) if isinstance(hw.get("workspace_model"), dict) else {}
    cfg.update(user)
    return cfg


def estimate_workspace_bytes(c: StrategyConfig | Layer1Case, kf: KernelFeatures, hw: Dict[str, Any], search: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """估算 GM workspace 占用与每 tile 读写流量。

    只有当 CVPipelinePlan 显式选择 stage_buffer_policy="gm_workspace" 时才启用。
    容量口径使用 active blocks 上同时存活的 staged handoff tensors；cost 口径使用每 tile
    需要写入/读回的 workspace traffic。这个模型不是生产级 PlanMemory，而是把 GM workspace
    纳入候选合法性和 cost 排序的解析式代理。
    """
    search = search or {}
    stage = 1 if isinstance(c, Layer1Case) else int(getattr(c, "cv_pipeline_stage", 1))
    policy = "none" if isinstance(c, Layer1Case) else str(getattr(c, "stage_buffer_policy", "none"))
    if stage <= 1 or policy != "gm_workspace":
        return {
            "enabled": False, "policy": policy, "workspace_bytes": 0,
            "bytes_per_tile_read": 0, "bytes_per_tile_write": 0, "bytes_per_tile_total": 0,
            "active_blocks": 0, "stage": stage, "handoff_bytes_per_stage": 0,
        }

    cfg = workspace_model_config(hw)
    elem = 2
    acc = 4
    handoff_tensors = float(cfg.get("handoff_tensor_count", 2))
    partial_tensors = float(cfg.get("partial_output_tensor_count", 1))
    # S/P 等中转一般是 fp16/bf16；partial O / stats 更保守按 fp32 代理。
    handoff_bytes = int(c.tile_m * c.tile_n * elem * handoff_tensors + c.tile_m * c.tile_n * acc * partial_tensors * 0.25)
    handoff_bytes = int(handoff_bytes * float(cfg.get("stage_extra_factor", 1.0)))
    pshape_tiles = estimate_num_tiles_for_tile(kf, search, {"m": c.tile_m, "n": c.tile_n, "k": c.tile_k})
    max_cores = get_available_cores(kf, hw)
    active_blocks = max(1, min(int(getattr(c, "block_dim", 1)), int(max_cores), int(math.ceil(pshape_tiles))))
    live_stages = max(1, stage - 1)
    workspace_bytes = _align(handoff_bytes * live_stages * active_blocks, 32)
    rw_mult = float(cfg.get("read_write_multiplier", 2.0))
    bytes_per_tile_total = int(handoff_bytes * live_stages * rw_mult)
    return {
        "enabled": True,
        "policy": policy,
        "workspace_bytes": int(workspace_bytes),
        "bytes_per_tile_read": int(bytes_per_tile_total / 2),
        "bytes_per_tile_write": int(bytes_per_tile_total / 2),
        "bytes_per_tile_total": int(bytes_per_tile_total),
        "active_blocks": int(active_blocks),
        "stage": int(stage),
        "live_stages": int(live_stages),
        "handoff_bytes_per_stage": int(handoff_bytes),
        "cap_bytes": int(memory_cap_bytes(hw, "gm_ws")),
    }


def workspace_transfer_time(c: StrategyConfig, kf: KernelFeatures, hw: Dict[str, Any], search: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """把 GM workspace read/write traffic 转换为每 tile 暴露 cost。

    真实编译里，GM workspace spill/handoff 会和常规 GM->片上、片上->GM 搬运
    竞争 MTE2/MTE3 通道，通常不能像片上 ping-pong 那样充分隐藏。因此这里返回
    一个保守的 exposed cost，并分别保留 read/write cycles 供主 cost model 叠加到
    load/store path，而不是把 workspace 当作独立免费 lane。
    """
    info = estimate_workspace_bytes(c, kf, hw, search)
    if not info.get("enabled"):
        return 0.0, info
    cfg = workspace_model_config(hw)
    bw_r = bandwidth_bytes_per_cycle(hw, "vector_mte2", default=108.0)
    bw_w = bandwidth_bytes_per_cycle(hw, "mte3", default=108.0)
    read_cycles = float(info.get("bytes_per_tile_read", 0)) / max(1.0, bw_r)
    write_cycles = float(info.get("bytes_per_tile_write", 0)) / max(1.0, bw_w)
    raw = read_cycles + write_cycles + float(cfg.get("startup_cycles", 350.0))
    penalty = float(cfg.get("penalty_factor", 2.0))
    exposed = raw * (1.0 - float(cfg.get("overlap_ratio", 0.10))) * penalty
    info = dict(info)
    info.update({
        "workspace_read_cycles": float(read_cycles),
        "workspace_write_cycles": float(write_cycles),
        "raw_workspace_transfer_cycles": float(raw),
        "workspace_penalty_factor": float(penalty),
        "exposed_workspace_transfer_cycles": float(exposed),
    })
    return float(exposed), info

def estimate_max_live(c: StrategyConfig | Layer1Case, kf: KernelFeatures, hw: Dict[str, Any], *, single_buffer_only: bool = False) -> Dict[str, int]:
    """合并 IR 静态 max-live 与当前候选 tile buffer，估算容量边界检查使用的 max-live。"""
    static = kf.static_max_live_bytes or {s: 0 for s in LOCAL_SPACES}
    tb = tile_buffers(c, kf, hw, single_buffer_only=single_buffer_only)
    out: Dict[str, int] = {}
    for s in RESOURCE_SCOPES:
        # 使用一部分 static max-live 作为 kernel 复杂度惩罚。
        # 如果把完整静态 buffer 和合成 tile buffer 直接相加，这个轻量 parser 会对很多 buffer 重复计数。
        static_penalty = 0.08 * static.get(s, 0)
        out[s] = _align(tb.get(s, 0) + static_penalty, space_alignment(hw, s))
    # GM workspace 是策略产生的 off-chip staging 资源，不来自静态 local max-live。
    out["gm_ws"] = _align(tb.get("gm_ws", 0), 32)
    return out


def gm_workspace_fallback_legality(c: StrategyConfig, kf: KernelFeatures, hw: Dict[str, Any], search: Dict[str, Any] | None = None) -> Tuple[bool, str, Dict[str, Any]]:
    """检查 GM workspace 是否符合真实编译 fallback 语义。

    规则：
    1) 只有显式允许 fallback 时才可使用；
    2) GM workspace 使用量不能接近预留上限；
    3) 默认要求 ub_stage / l1_reuse 等片上 stage-buffer 方案均不可行，
       否则 GM workspace 不应作为普通候选参与寻优。
    """
    if str(getattr(c, "stage_buffer_policy", "none")) != "gm_workspace":
        return True, "not_gm_workspace", {}
    cfg = workspace_model_config(hw)
    if not bool(cfg.get("allow_gm_workspace_fallback", True)):
        return False, "GM workspace fallback disabled by hardware config", {}
    info = estimate_workspace_bytes(c, kf, hw, search or {})
    cap = int(info.get("cap_bytes", memory_cap_bytes(hw, "gm_ws")) or 0)
    req = int(info.get("workspace_bytes", 0) or 0)
    max_util = float(cfg.get("max_workspace_utilization", 0.25))
    detail = {"gm_ws_required": req, "gm_ws_cap": cap, "max_workspace_utilization": max_util, "alternatives": []}
    if cap and req > cap * max_util:
        return False, f"GM workspace exceeds conservative utilization limit ({max_util:.0%})", detail
    if not bool(cfg.get("require_onchip_infeasible", True)):
        return True, "gm_workspace_allowed_without_onchip_gate", detail

    # 真实编译器通常先尝试 UB/L1 stage handoff；只有这些合法 lowering 放不下时，
    # 才会考虑 off-chip workspace spill/fallback。
    for policy in ("ub_stage", "l1_reuse", "none"):
        alt = replace(c, stage_buffer_policy=policy)
        alt_ml = estimate_max_live(alt, kf, hw)
        ok, reason, fd = feasibility(alt, alt_ml, hw)
        detail["alternatives"].append({"policy": policy, "ok": bool(ok), "reason": reason, "max_live": fd})
        if ok:
            return False, f"GM workspace rejected: on-chip policy '{policy}' is feasible", detail
    return True, "gm_workspace_allowed_as_fallback", detail


def base_pipe_times(c: StrategyConfig | Layer1Case, kf: KernelFeatures, hw: Dict[str, Any], search: Dict[str, Any]) -> Dict[str, float]:
    """估算 load、compute、vector、store、sync 等基础 pipe 时间，是 cost model 的主体。"""
    elem = 2
    acc = 4
    bytes_load = (c.tile_m * c.tile_k + c.tile_k * c.tile_n + c.tile_m * c.tile_n) * elem
    bytes_store = c.tile_m * c.tile_n * elem
    # V2.7 搜索的 tiling 子旋钮会影响局部性和尾块开销。
    loop_order = getattr(c, "loop_order", "outer_mnk")
    tail_strategy = getattr(c, "tail_strategy", "mask_or_pad")
    reduce_tile_policy = getattr(c, "reduce_tile_policy", "full_k")
    layout_aware_tile = bool(getattr(c, "layout_aware_tile", True))
    if reduce_tile_policy == "half_k":
        # 更多 reduction tile 会降低单 tile 工作集，但会增加循环和 setup 流量。
        bytes_load *= 0.93
    if layout_aware_tile:
        # 偏好对 ND/NZ/Cube 搬运更友好的 shape 和 layout。
        bytes_load *= 0.97
        bytes_store *= 0.98
    if loop_order == "outer_mkn":
        bytes_load *= 0.96  # K 方向局部性略好
    elif loop_order == "outer_nmk":
        bytes_store *= 1.03
    if tail_strategy == "pad":
        bytes_load *= 1.04
        bytes_store *= 1.02
    elif tail_strategy == "peel":
        bytes_load *= 0.99

    if getattr(c, "dma_policy", "keep_existing") == "prefer_contiguous":
        bytes_load *= 0.92
        bytes_store *= 0.96
    if getattr(c, "dma_policy", "keep_existing") == "prefetch_nd2nz":
        bytes_load *= 0.96

    bw_load = bandwidth_bytes_per_cycle(hw, "vector_mte2", default=108.0)
    bw_store = bandwidth_bytes_per_cycle(hw, "mte3", default=108.0)
    starts = hw.get("performance_model", {}).get("startup_costs", {})
    load_time = bytes_load / max(bw_load, 1.0) + starts.get("dma_startup_cycles", 80)
    store_time = bytes_store / max(bw_store, 1.0) + starts.get("dma_startup_cycles", 80)

    flops = 2.0 * c.tile_m * c.tile_n * c.tile_k * max(1, kf.num_mmad)
    cube_time = flops / max(cube_flops_per_cycle(hw), 1.0) + starts.get("cube_startup_cycles", 120)
    vector_elements = c.tile_m * c.tile_n * max(1, sum(kf.vector_op_counts.values()))
    vector_time = vector_elements / max(vector_elems_per_cycle(hw), 1.0) + starts.get("vector_startup_cycles", 35)
    heavy = kf.vector_op_counts.get("vexp", 0) * 3 + kf.vector_op_counts.get("vdiv", 0) * 2 + kf.vector_op_counts.get("vreduce", 0)
    vector_time *= (1.0 + 0.04 * heavy)
    if tail_strategy == "pad":
        vector_time *= 1.04
    elif tail_strategy == "peel":
        vector_time *= 1.02
    if getattr(c, "fusion", "keep_existing") != "keep_existing":
        vector_time *= 0.86

    fix_time = kf.num_fixpipe * (c.tile_m * c.tile_n * acc) / max(bw_store, 1.0) * 0.20
    return {
        "load": float(load_time),
        "store": float(store_time),
        "cube": float(cube_time),
        "vector": float(vector_time),
        "fix": float(fix_time),
    }


def coarse_cost_for_layer1(case: Layer1Case, kf: KernelFeatures, hw: Dict[str, Any], search: Dict[str, Any]) -> float:
    """为 Layer-1 tiling 粗筛计算轻量 cost，用于先保留更可能优秀的 tile。"""
    times = base_pipe_times(case, kf, hw, search)
    p = problem_shape(search, kf)
    n_tiles = max(1.0, math.ceil(p["m_total"] / case.tile_m) * math.ceil(p["n_total"] / case.tile_n) * math.ceil(p["k_total"] / case.tile_k) * p.get("outer_iterations", 1))
    compute = max(times["cube"], times["vector"], times["fix"])
    # Layer-1 剪枝必须使用与最终模型一致的保守先验；
    # 否则在最终 penalty 修正之前，beam 可能只保留“能放下的最大 N tile”。
    fp = case.single_footprint or estimate_max_live(case, kf, hw, single_buffer_only=True)
    util = {sp: (fp.get(sp, 0) / memory_cap_bytes(hw, sp) if memory_cap_bytes(hw, sp) else 0.0) for sp in ["ub", "l1", "l0a", "l0b", "l0c"]}
    pressure_penalty, _ = memory_pressure_penalty(util, hw)
    shape_penalty, _ = shape_regularization_penalty(case, kf, hw, search)
    return n_tiles * (times["load"] + compute + times["store"]) + pressure_penalty + shape_penalty


def select_diverse_layer1_beam(cases: List[Layer1Case], top_w: int, search: Dict[str, Any]) -> Tuple[List[Layer1Case], Dict[str, Any]]:
    """Stage2b Layer-1 beam selector with diversity and fallback retention.

    A pure cost Top-W beam is efficient but can remove whole tile families before
    MultiBuffer/CVPipeline/SyncPlan are evaluated.  This selector keeps the
    original Top-W, then adds representative candidates from important grouping
    dimensions (tile_m/tile_n/tile_k/block_dim), pins standard-space survivors
    from Stage2a, and finally keeps a small deterministic fallback tail.  The
    final frontier is intentionally allowed to exceed top_w by a controlled
    amount because the goal of Stage2b is search stability rather than minimal
    enumeration size.
    """
    sorted_cases = sorted(cases, key=lambda x: x.coarse_cost)
    enabled = bool(search.get("layer1_diversity_beam_enabled", True))
    cost_kept = sorted_cases[:top_w]
    selected_by_sig: Dict[Tuple[Any, ...], Layer1Case] = {layer1_signature(x): x for x in cost_kept}

    diversity_added: List[Layer1Case] = []
    group_counts: Dict[str, Dict[str, int]] = {}
    if enabled:
        group_fields = list(search.get("layer1_diversity_group_fields", ["tile_m", "tile_n", "tile_k", "block_dim"]))
        per_group_keep = max(0, int(search.get("layer1_diversity_per_group_keep", 1)))
        max_diversity_extra = max(0, int(search.get("layer1_diversity_max_extra", 12)))
        diversity_pool: Dict[Tuple[Any, ...], Layer1Case] = {}
        for field in group_fields:
            groups: Dict[Any, List[Layer1Case]] = {}
            for x in sorted_cases:
                groups.setdefault(getattr(x, field, None), []).append(x)
            proposed_for_field = 0
            for _, group in groups.items():
                for x in sorted(group, key=lambda y: y.coarse_cost)[:per_group_keep]:
                    sig = layer1_signature(x)
                    if sig not in selected_by_sig and sig not in diversity_pool:
                        diversity_pool[sig] = x
                        proposed_for_field += 1
            group_counts[str(field)] = {"groups": len(groups), "proposed": proposed_for_field, "per_group_keep": per_group_keep}
        for x in sorted(diversity_pool.values(), key=lambda y: y.coarse_cost)[:max_diversity_extra]:
            selected_by_sig[layer1_signature(x)] = x
            diversity_added.append(x)
    else:
        group_fields = []
        per_group_keep = 0
        max_diversity_extra = 0

    # Stage2a stability rule: in expanded/full mode, standard Layer-1 survivors
    # are pinned into the retained set, even when a denser grid changes the
    # coarse-cost ordering.
    pin_raw = search.get("standard_layer1_signatures_to_pin", []) or []
    pinned_signatures = set(tuple(x) for x in pin_raw if isinstance(x, (list, tuple)))
    pinned_standard: List[Layer1Case] = []
    if search.get("candidate_space_density") in {"expanded", "full"} and pinned_signatures:
        for x in sorted_cases:
            sig = layer1_signature(x)
            if sig in pinned_signatures and sig not in selected_by_sig:
                selected_by_sig[sig] = x
                pinned_standard.append(x)

    fallback_keep = max(0, int(search.get("layer1_fallback_keep", 8)))
    fallback_added: List[Layer1Case] = []
    if fallback_keep:
        for x in sorted_cases:
            sig = layer1_signature(x)
            if sig in selected_by_sig:
                continue
            selected_by_sig[sig] = x
            fallback_added.append(x)
            if len(fallback_added) >= fallback_keep:
                break

    kept = sorted(selected_by_sig.values(), key=lambda x: x.coarse_cost)
    standard_tile_keys = set(str(k) for k in search.get("standard_tile_keys", []) or [])
    audit = {
        "policy": "cost_topw_plus_diversity_plus_pinned_standard_plus_fallback",
        "configured_top_w": top_w,
        "kept_by_cost_topw": len(cost_kept),
        "diversity_beam_enabled": enabled,
        "diversity_group_fields": group_fields,
        "diversity_per_group_keep": per_group_keep,
        "diversity_max_extra": max_diversity_extra,
        "diversity_added_after_topw": len(diversity_added),
        "diversity_group_audit": group_counts,
        "pinned_standard_after_topw_and_diversity": len(pinned_standard),
        "fallback_keep": fallback_keep,
        "fallback_added_after_topw_diversity_and_pins": len(fallback_added),
        "final_kept": len(kept),
        "standard_tile_keys_count": len(standard_tile_keys),
        "standard_layer1_signatures_to_pin": len(pinned_signatures),
    }
    return kept, audit


# ------------------------------ 三层搜索流程 ------------------------------

def search_tiling_fusion(kf: KernelFeatures, hw: Dict[str, Any], search: Dict[str, Any]) -> Tuple[List[Layer1Case], List[Dict[str, Any]]]:
    """执行 Layer-1 搜索，生成容量合法且粗 cost 较低的 tiling/fusion 候选。"""
    """Layer 1: enumerate f+t+B, apply C2/C4 alignment and single-buffer capacity, keep Top-W."""
    cases: List[Layer1Case] = []
    rejected: List[Dict[str, Any]] = []
    top_w = int(search.get("layer1_top_w", search.get("beam_width", 24)))
    for tile, fusion, block_dim, loop_order, tail_strategy, reduce_tile_policy, layout_aware_tile in iter_layer1_raw_candidates(search):
        tile_m, tile_n, tile_k = int(tile["m"]), int(tile["n"]), int(tile["k"])
        ok, notes = satisfies_align_tile(tile_m, tile_n, tile_k, hw)
        if not ok:
            rejected.append({"layer": "L1", "candidate": {"fusion": fusion, "tile": tile, "block_dim": block_dim}, "reason": "tiling alignment violation", "notes": notes})
            continue
        tmp = Layer1Case(fusion=str(fusion), tile_m=tile_m, tile_n=tile_n, tile_k=tile_k, block_dim=int(block_dim), single_footprint={}, coarse_cost=0.0, align_notes=notes, loop_order=str(loop_order), tail_strategy=str(tail_strategy), reduce_tile_policy=str(reduce_tile_policy), layout_aware_tile=bool(layout_aware_tile))
        fp = estimate_max_live(tmp, kf, hw, single_buffer_only=True)
        overflow = None
        for s in RESOURCE_SCOPES:
            cap = memory_cap_bytes(hw, s)
            if cap and fp.get(s, 0) > cap:
                overflow = f"single-buffer {s.upper()} overflow"
                break
        if overflow:
            rejected.append({"layer": "L1", "candidate": {"fusion": fusion, "tile": tile, "block_dim": block_dim}, "reason": overflow, "footprint_bytes": fp})
            continue
        tmp.single_footprint = fp
        tmp.coarse_cost = coarse_cost_for_layer1(tmp, kf, hw, search)
        cases.append(tmp)
    # 在 beam 截断前移除重复的 Layer-1 tile shape。
    # 否则动态 block_dim 和固定/兜底子旋钮会为同一个大 tile 生成大量重复项，
    # 从而遮蔽 96/128/160/192 这类中等且规则的 tile。
    raw_case_count = len(cases)
    unique: Dict[Tuple[Any, ...], Layer1Case] = {}
    for x in cases:
        key = (x.fusion, x.tile_m, x.tile_n, x.tile_k)
        if key not in unique or x.coarse_cost < unique[key].coarse_cost:
            unique[key] = x
    cases = list(unique.values())
    dedup_removed = raw_case_count - len(cases)
    cases.sort(key=lambda x: x.coarse_cost)

    kept, beam_audit = select_diverse_layer1_beam(cases, top_w, search)
    beam_audit.update({
        "raw_valid_cases": raw_case_count,
        "dedup_removed_before_beam": dedup_removed,
        "unique_valid_cases": len(cases),
    })
    search["layer1_stability_audit"] = beam_audit
    return kept, rejected


def alloc_overlap(layer1: Layer1Case, kf: KernelFeatures, hw: Dict[str, Any], search: Dict[str, Any]) -> List[Dict[str, Any]]:
    """根据 double buffer、CV pipeline、sync policy 和模板估算可重叠比例。"""
    """Layer 2: choose MultiBufferPlan and CVPipelinePlan knobs.

    V2.7 keeps the previous Layer-2 blow-up by treating CVPipelinePlan as a
    small list of template-bundled plan candidates instead of a Cartesian
    product over stage/template/mixed/loop/balance/distance/policy.  This keeps
    the important scheduling choices but avoids thousands of near-duplicate
    combinations before Top-K pruning.
    """
    allowed_db = list(search.get("double_buffer", [False, True]))
    allowed_mb_templates = list(search.get("multibuffer_template", ["M0_no_multibuffer", "M1_input_double_buffer"]))
    allowed_ub_mult = [int(x) for x in search.get("ub_multiplier", [1])]
    allowed_l1_mult = [int(x) for x in search.get("l1_multiplier", [1])]
    allowed_ratios = list(search.get("cv_split_ratio", ["1:1"]))
    cv_plan_candidates = search.get("cv_pipeline_plan_candidates")
    if not isinstance(cv_plan_candidates, list) or not cv_plan_candidates:
        cv_plan_candidates = build_cv_pipeline_plan_candidates(kf, search)

    ub_cap = memory_cap_bytes(hw, "ub")
    base_ub = layer1.single_footprint.get("ub", 0)
    budget = max(0, ub_cap - base_ub)
    times = base_pipe_times(layer1, kf, hw, search)
    serial = times["load"] + max(times["cube"], times["vector"], times["fix"]) + times["store"]
    raw: List[Dict[str, Any]] = []

    # 逐 buffer multiplier 候选只依赖 double buffer，不依赖 CV 子旋钮。
    per_buffer_cache = {
        False: generate_per_buffer_multiplier_candidates(kf, search, db=False),
        True: generate_per_buffer_multiplier_candidates(kf, search, db=True),
    }
    eval_cap = int(search.get("layer2_raw_eval_cap_per_layer1", 4096))
    eval_count = 0
    stop_early = False

    for db, mb_tpl, cvp, ub_mult, l1_mult, ratio in itertools.product(
        allowed_db, allowed_mb_templates, cv_plan_candidates, allowed_ub_mult, allowed_l1_mult, allowed_ratios,
    ):
        stage = int(cvp.get("cv_pipeline_stage", 1))
        cv_tpl = str(cvp.get("cv_pipeline_template", "P0_no_cv_pipeline"))
        mixed = bool(cvp.get("enable_mixed_cv", False))
        cube_loop = int(cvp.get("tile_mix_cube_loop", 1))
        vector_loop = int(cvp.get("tile_mix_vector_loop", 1))
        balance = bool(cvp.get("auto_cv_balance", True))
        prod_dist = int(cvp.get("producer_consumer_distance", 1))
        stage_policy = str(cvp.get("stage_buffer_policy", "none"))

        # Generic staged CV overlap normally requires double buffering. The built-in
        # sparse-prefill reuse template is an explicit exception: it models the
        # manually reviewed large-SBS case where multibuffer=False is preferred to
        # avoid cbuf overflow while still allowing Q/K reuse and code motion.
        if stage > 1 and not db and cv_tpl != "P_PREFILL_LARGE_SBS_REUSE":
            continue
        if cv_tpl == "P_PREFILL_LARGE_SBS_REUSE" and (bool(db) or str(mb_tpl) != "M0_no_multibuffer"):
            continue
        if not _mb_template_compatible(bool(db), str(mb_tpl), int(stage)):
            continue
        if not _cv_template_compatible(stage, cv_tpl, mixed, cube_loop, vector_loop):
            continue
        if stage <= 1 and str(stage_policy) != "none":
            continue
        if stage <= 1 and prod_dist != 1:
            continue
        if not bool(db) and (int(ub_mult) > 1 or int(l1_mult) > 1):
            continue

        per_buffer_plans = per_buffer_cache[bool(db)]
        if str(mb_tpl) == "M0_no_multibuffer":
            per_buffer_plans = [per_buffer_plans[0] if per_buffer_plans else {}]

        for buffer_mults in per_buffer_plans:
            eval_count += 1
            if eval_count > eval_cap and len(raw) >= int(search.get("layer2_top_w", 8)):
                stop_early = True
                break
            buffer_json = _canonical_buffer_multipliers_json(buffer_mults)
            tmp = StrategyConfig(
                strategy_id="L2_tmp",
                fusion=layer1.fusion,
                tile_m=layer1.tile_m,
                tile_n=layer1.tile_n,
                tile_k=layer1.tile_k,
                block_dim=layer1.block_dim,
                double_buffer=bool(db),
                cv_pipeline_stage=stage,
                cv_split_ratio=str(ratio),
                memory_reuse_level="level2",
                sync_policy="keep_existing",
                dma_policy="keep_existing",
                loop_order=layer1.loop_order,
                tail_strategy=layer1.tail_strategy,
                multibuffer_template=str(mb_tpl),
                cv_pipeline_template=cv_tpl,
                enable_mixed_cv=mixed,
                tile_mix_cube_loop=cube_loop,
                tile_mix_vector_loop=vector_loop,
                auto_cv_balance=balance,
                reduce_tile_policy=layer1.reduce_tile_policy,
                layout_aware_tile=layer1.layout_aware_tile,
                ub_multiplier=int(ub_mult),
                l1_multiplier=int(l1_mult),
                stage_buffer_policy=stage_policy,
                producer_consumer_distance=prod_dist,
                buffer_multipliers_json=buffer_json,
            )
            # 真实编译语义：GM workspace 只是 off-chip fallback。
            # 如果 UB/L1 stage-buffer 方案可行，则不把 gm_workspace 当成普通候选。
            if stage_policy == "gm_workspace":
                gm_ok, _gm_reason, _gm_detail = gm_workspace_fallback_legality(tmp, kf, hw, search)
                if not gm_ok:
                    continue
            fp = estimate_max_live(tmp, kf, hw)
            extra_ub = max(0, fp.get("ub", 0) - base_ub)
            over_budget = extra_ub > budget
            if over_budget and extra_ub > budget + 96 * 1024:
                continue

            if stage <= 1:
                compute = times["cube"] + times["vector"] + times["fix"]
            else:
                ratio_penalty = {"1:1": 1.00, "1:2": 1.08 if times["vector"] > times["cube"] else 1.18, "2:1": 1.08 if times["cube"] > times["vector"] else 1.18}.get(str(ratio), 1.10)
                template_bonus = 0.94 if cv_tpl == "P2_stage2_balanced" and balance else (1.08 if cv_tpl == "P3_stage4_aggressive" and not balance else 1.0)
                mix_penalty = 0.97 if mixed else 1.0
                loop_balance_penalty = 1.0 + 0.03 * abs(cube_loop - vector_loop)
                prod_penalty = 1.0 + 0.025 * max(0, prod_dist - 1)
                stage_policy_bonus = 0.97 if stage_policy in {"ub_stage", "l1_stage"} else 1.0
                compute = max(times["cube"], times["vector"]) * ratio_penalty * template_bonus * mix_penalty * loop_balance_penalty * prod_penalty * stage_policy_bonus + times["fix"]
            overlapped = max(times["load"], compute, times["store"]) if db else times["load"] + compute + times["store"]
            gain = max(0.0, serial - overlapped)
            bonus = per_buffer_overlap_bonus(kf, buffer_mults)
            gain *= (1.0 + 0.18 * float(bonus.get("load_overlap_bonus", 0.0)) + 0.10 * float(bonus.get("store_overlap_bonus", 0.0)))
            extra_scope = per_buffer_extra_bytes_by_scope(kf, buffer_mults)
            score = gain / max(1.0, (extra_ub + sum(extra_scope.values())) / 1024.0 + 1.0)
            if over_budget:
                score *= 0.55
            raw.append({
                "double_buffer": bool(db), "multibuffer_template": str(mb_tpl),
                "cv_pipeline_stage": stage, "cv_pipeline_template": cv_tpl,
                "cv_pipeline_candidate_name": str(cvp.get("name", cv_tpl)),
                "enable_mixed_cv": mixed, "tile_mix_cube_loop": cube_loop,
                "tile_mix_vector_loop": vector_loop, "auto_cv_balance": balance,
                "producer_consumer_distance": prod_dist, "stage_buffer_policy": stage_policy,
                "buffer_multipliers": buffer_mults,
                "buffer_multipliers_json": buffer_json,
                "per_buffer_extra_bytes_by_scope": extra_scope,
                "per_buffer_overlap_bonus": bonus,
                "ub_multiplier": int(ub_mult), "l1_multiplier": int(l1_mult),
                "cv_split_ratio": str(ratio), "estimated_gain": gain, "extra_ub_bytes": extra_ub,
                "budget_bytes": budget, "over_budget_before_relax": over_budget, "allocation_score": score,
            })
        if stop_early:
            break

    if not raw:
        raw.append({
            "double_buffer": False, "multibuffer_template": "M0_no_multibuffer",
            "cv_pipeline_stage": 1, "cv_pipeline_template": "P0_no_cv_pipeline",
            "cv_pipeline_candidate_name": "P0_no_cv_pipeline",
            "enable_mixed_cv": False, "tile_mix_cube_loop": 1, "tile_mix_vector_loop": 1,
            "auto_cv_balance": False, "producer_consumer_distance": 1, "stage_buffer_policy": "none",
            "buffer_multipliers": {}, "buffer_multipliers_json": "{}",
            "per_buffer_extra_bytes_by_scope": {}, "per_buffer_overlap_bonus": {},
            "ub_multiplier": 1, "l1_multiplier": 1, "cv_split_ratio": "1:1",
            "estimated_gain": 0.0, "extra_ub_bytes": 0, "budget_bytes": budget, "allocation_score": 0.0,
        })
    raw.sort(key=lambda x: (-x["allocation_score"], x["extra_ub_bytes"]))
    return raw[: int(search.get("layer2_top_w", 8))]

def refine_inner(layer1: Layer1Case, overlap: Dict[str, Any], search: Dict[str, Any]) -> List[StrategyConfig]:
    """在给定 Layer-1 tiling 上枚举 MultiBuffer/CVPipeline/SyncPlan，并计算完整 cost。"""
    """Layer 3: enumerate SyncPlan sub-knobs while keeping non-focused params fixed."""
    out: List[StrategyConfig] = []
    for reuse, sync, sync_tpl, barrier_level, event_reuse, granularity, event_id_policy, sync_motion, dma in itertools.product(
        search.get("memory_reuse_level", ["level1"]),
        search.get("sync_policy", ["keep_existing"]),
        search.get("sync_template", ["Y0_keep_existing"]),
        search.get("barrier_level", ["medium"]),
        search.get("event_reuse", [False]),
        search.get("sync_granularity", ["op"]),
        search.get("event_id_policy", ["keep"]),
        search.get("sync_motion", ["none"]),
        search.get("dma_policy", ["keep_existing"]),
    ):
        if not _sync_template_compatible(str(sync), str(sync_tpl), bool(event_reuse), str(event_id_policy)):
            continue
        out.append(StrategyConfig(
            strategy_id="pending",
            fusion=layer1.fusion,
            tile_m=layer1.tile_m,
            tile_n=layer1.tile_n,
            tile_k=layer1.tile_k,
            block_dim=layer1.block_dim,
            double_buffer=bool(overlap["double_buffer"]),
            cv_pipeline_stage=int(overlap["cv_pipeline_stage"]),
            cv_split_ratio=str(overlap["cv_split_ratio"]),
            memory_reuse_level=str(reuse),
            sync_policy=str(sync),
            dma_policy=str(dma),
            loop_order=layer1.loop_order,
            tail_strategy=layer1.tail_strategy,
            multibuffer_template=str(overlap.get("multibuffer_template", "auto")),
            cv_pipeline_template=str(overlap.get("cv_pipeline_template", "auto")),
            sync_template=str(sync_tpl),
            enable_mixed_cv=bool(overlap.get("enable_mixed_cv", False)),
            tile_mix_cube_loop=int(overlap.get("tile_mix_cube_loop", 1)),
            tile_mix_vector_loop=int(overlap.get("tile_mix_vector_loop", 1)),
            auto_cv_balance=bool(overlap.get("auto_cv_balance", True)),
            barrier_level=str(barrier_level),
            event_reuse=bool(event_reuse),
            sync_granularity=str(granularity),
            reduce_tile_policy=layer1.reduce_tile_policy,
            layout_aware_tile=layer1.layout_aware_tile,
            ub_multiplier=int(overlap.get("ub_multiplier", 1)),
            l1_multiplier=int(overlap.get("l1_multiplier", 1)),
            stage_buffer_policy=str(overlap.get("stage_buffer_policy", "none")),
            buffer_multipliers_json=str(overlap.get("buffer_multipliers_json", "{}")),
            producer_consumer_distance=int(overlap.get("producer_consumer_distance", 1)),
            event_id_policy=str(event_id_policy),
            sync_motion=str(sync_motion),
        ))
    def _sync_rank(cfg: StrategyConfig) -> float:
        """根据同步策略的激进程度和可复用程度计算排序辅助分数。"""
        score = 0.0
        score += 3.0 if cfg.sync_policy == "graph_sync_solver" else 1.0
        score += {"Y3_event_reuse": 0.6, "Y2_graph_sync_solver": 0.5, "Y0_keep_existing": 0.2, "Y1_conservative_barrier": 0.1}.get(cfg.sync_template, 0.0)
        score += {"low": 0.3, "medium": 0.15, "high": 0.0}.get(cfg.barrier_level, 0.0)
        score += 0.25 if cfg.event_reuse else 0.0
        score += {"stage": 0.25, "tile": 0.15, "op": 0.0}.get(cfg.sync_granularity, 0.0)
        score += {"reuse": 0.25, "compact": 0.15, "keep": 0.0}.get(cfg.event_id_policy, 0.0)
        score += 0.08 if cfg.sync_motion == "local_move" else 0.0
        return score
    out.sort(key=lambda cfg: (-_sync_rank(cfg), cfg.barrier_level, cfg.sync_granularity))
    return out[: int(search.get("layer3_top_w", 12))]

def dedup_strategy_candidates(candidates: List[Tuple[StrategyConfig, Dict[str, Any]]]) -> Tuple[List[Tuple[StrategyConfig, Dict[str, Any]]], Dict[str, Any]]:
    """Deduplicate full strategy candidates using the stable strategy signature.

    Candidate ids are reassigned after dedup, so the search report is stable even
    if upstream enumeration order changes.  When two exact strategies appear, the
    first one is kept and the later duplicate count is recorded in search audit.
    """
    seen: Dict[Tuple[Any, ...], Tuple[StrategyConfig, Dict[str, Any]]] = {}
    duplicates = 0
    for cfg, meta in candidates:
        sig = strategy_signature(cfg)
        if sig in seen:
            duplicates += 1
            continue
        seen[sig] = (cfg, meta)
    out: List[Tuple[StrategyConfig, Dict[str, Any]]] = []
    for i, (cfg, meta) in enumerate(seen.values(), 1):
        out.append((replace(cfg, strategy_id=f"candidate_{i:05d}"), meta))
    return out, {
        "input_candidates": len(candidates),
        "unique_candidates": len(out),
        "dedup_removed": duplicates,
        "dedup_key": "strategy_signature_without_strategy_id",
    }


def build_layered_candidates(kf: KernelFeatures, hw: Dict[str, Any], search: Dict[str, Any]) -> Tuple[List[Tuple[StrategyConfig, Dict[str, Any]]], Dict[str, Any]]:
    """执行分层搜索流程：先 tiling 粗筛，再对内层三个 Plan 做精筛。"""
    layer1, l1_rejected = search_tiling_fusion(kf, hw, search)
    candidates: List[Tuple[StrategyConfig, Dict[str, Any]]] = []
    layer2_count = 0
    for l1 in layer1:
        overlaps = alloc_overlap(l1, kf, hw, search)
        layer2_count += len(overlaps)
        for ov in overlaps:
            for c in refine_inner(l1, ov, search):
                candidates.append((c, {"layer1_coarse_cost": l1.coarse_cost, "layer1_footprint": l1.single_footprint, "overlap_allocation": ov}))
    raw_layer3_candidates = len(candidates)
    candidates, dedup_audit = dedup_strategy_candidates(candidates)
    stability_audit = search.get("layer1_stability_audit", {})
    stats = {
        "layer1_kept": len(layer1),
        "layer1_rejected_count": len(l1_rejected),
        "layer1_rejected_preview": l1_rejected[:50],
        "layer2_allocations": layer2_count,
        "layer3_candidates_raw_before_dedup": raw_layer3_candidates,
        "layer3_candidates": len(candidates),
        "candidate_dedup_audit": dedup_audit,
        "layer1_stability_audit": stability_audit,
        "search_mode": "layered_beam_search",
    }
    return candidates, stats


def build_exhaustive_candidates(kf: KernelFeatures, hw: Dict[str, Any], search: Dict[str, Any]) -> Tuple[List[Tuple[StrategyConfig, Dict[str, Any]]], Dict[str, Any]]:
    """执行小规模穷举搜索，用于测试或验证分层搜索结果。"""
    candidates: List[Tuple[StrategyConfig, Dict[str, Any]]] = []
    rejected: List[Dict[str, Any]] = []
    l1_cases: List[Layer1Case] = []

    for tile, fusion, block_dim, loop_order, tail_strategy, reduce_tile_policy, layout_aware_tile in iter_layer1_raw_candidates(search):
        tile_m, tile_n, tile_k = int(tile["m"]), int(tile["n"]), int(tile["k"])
        ok, notes = satisfies_align_tile(tile_m, tile_n, tile_k, hw)
        if not ok:
            rejected.append({"layer": "L1", "candidate": {"fusion": fusion, "tile": tile, "block_dim": block_dim}, "reason": "tiling alignment violation", "notes": notes})
            continue
        l1 = Layer1Case(fusion=str(fusion), tile_m=tile_m, tile_n=tile_n, tile_k=tile_k, block_dim=int(block_dim), single_footprint={}, coarse_cost=0.0, align_notes=notes, loop_order=str(loop_order), tail_strategy=str(tail_strategy), reduce_tile_policy=str(reduce_tile_policy), layout_aware_tile=bool(layout_aware_tile))
        fp = estimate_max_live(l1, kf, hw, single_buffer_only=True)
        overflow = None
        for sp in RESOURCE_SCOPES:
            cap = memory_cap_bytes(hw, sp)
            if cap and fp.get(sp, 0) > cap:
                overflow = f"single-buffer {sp.upper()} overflow"
                break
        if overflow:
            rejected.append({"layer": "L1", "candidate": {"fusion": fusion, "tile": tile, "block_dim": block_dim}, "reason": overflow, "footprint_bytes": fp})
            continue
        l1.single_footprint = fp
        l1.coarse_cost = coarse_cost_for_layer1(l1, kf, hw, search)
        l1_cases.append(l1)

    idx = 0
    layer2_count = 0
    for l1 in l1_cases:
        for db, stage, ratio in itertools.product(
            search.get("double_buffer", [False, True]),
            search.get("cv_pipeline_stage", [1, 2, 4]),
            search.get("cv_split_ratio", ["1:1"]),
        ):
            layer2_count += 1
            ov = {"double_buffer": bool(db), "cv_pipeline_stage": int(stage), "cv_split_ratio": str(ratio), "exhaustive": True}
            for c in refine_inner(l1, ov, search):
                idx += 1
                c = replace(c, strategy_id=f"exhaustive_{idx:06d}")
                candidates.append((c, {"layer1_coarse_cost": l1.coarse_cost, "layer1_footprint": l1.single_footprint, "overlap_allocation": ov}))

    stats = {
        "layer1_kept": len(l1_cases),
        "layer1_rejected_count": len(rejected),
        "layer1_rejected_preview": rejected[:50],
        "layer2_allocations": layer2_count,
        "layer3_candidates": len(candidates),
        "search_mode": "exhaustive_cartesian_search",
        "raw_space_size": estimate_search_space_size(search),
        "note": "No Layer1/Layer2 beam truncation is applied in exhaustive mode.",
    }
    return candidates, stats


def _compact_search_for_quality_audit(search: Dict[str, Any]) -> Dict[str, Any]:
    """Build a deliberately small search space for Beam-vs-baseline quality checks.

    The goal is not to replace the normal search; it is a bounded audit that can
    be run quickly in CI.  We keep a subset of the user's active space so the
    comparison remains relevant to the current kernel/hardware while avoiding a
    large Cartesian explosion.
    """
    compact = copy.deepcopy(search)
    compact["candidate_space_density"] = "quality_audit_compact"
    compact["tile_candidates"] = list(compact.get("tile_candidates", []) or [])[: int(compact.get("quality_audit_tile_limit", 4))]
    compact["block_dim"] = list(compact.get("block_dim", []) or [])[: int(compact.get("quality_audit_block_dim_limit", 1))]
    compact["fusion"] = list(compact.get("fusion", ["keep_existing"]) or ["keep_existing"])[:1]
    compact["loop_order"] = list(compact.get("loop_order", ["mnk"]) or ["mnk"])[:1]
    compact["tail_strategy"] = list(compact.get("tail_strategy", ["guard"]) or ["guard"])[:1]
    compact["reduce_tile_policy"] = list(compact.get("reduce_tile_policy", ["full_k"]) or ["full_k"])[:1]
    compact["layout_aware_tile"] = list(compact.get("layout_aware_tile", [False]) or [False])[:1]
    compact["double_buffer"] = [False, True]
    compact["cv_pipeline_stage"] = [1, 2]
    compact["cv_split_ratio"] = list(compact.get("cv_split_ratio", ["1:1"]) or ["1:1"])[:1]
    compact["sync_policy"] = [x for x in ["keep_existing", "graph_sync_solver"] if x in set(compact.get("sync_policy", ["keep_existing", "graph_sync_solver"]))] or ["keep_existing"]
    compact["sync_template"] = ["Y0_keep_existing", "Y2_graph_sync_solver"]
    compact["barrier_level"] = ["medium"]
    compact["event_reuse"] = [False, True]
    compact["sync_granularity"] = ["op"]
    compact["event_id_policy"] = ["keep", "reuse"]
    compact["sync_motion"] = ["none"]
    compact["dma_policy"] = list(compact.get("dma_policy", ["keep_existing"]) or ["keep_existing"])[:1]
    compact["memory_reuse_level"] = list(compact.get("memory_reuse_level", ["level1"]) or ["level1"])[:1]
    compact["layer1_top_w"] = min(int(compact.get("layer1_top_w", 24)), int(compact.get("quality_audit_layer1_top_w", 4)))
    compact["layer2_top_w"] = min(int(compact.get("layer2_top_w", 8)), int(compact.get("quality_audit_layer2_top_w", 2)))
    compact["layer3_top_w"] = min(int(compact.get("layer3_top_w", 12)), int(compact.get("quality_audit_layer3_top_w", 4)))
    compact["layer1_diversity_max_extra"] = min(int(compact.get("layer1_diversity_max_extra", 12)), 4)
    compact["layer1_fallback_keep"] = min(int(compact.get("layer1_fallback_keep", 4)), 2)
    # Compact audit should not inherit standard-survivor pinning from the full run;
    # otherwise the baseline space is no longer the intentionally small space.
    compact.pop("standard_layer1_signatures_to_pin", None)
    compact.pop("standard_layer1_kept_for_stability", None)
    return compact


def _score_candidate_pool_for_audit(
    candidates: List[Tuple[StrategyConfig, Dict[str, Any]]],
    kf: KernelFeatures,
    hw: Dict[str, Any],
    search: Dict[str, Any],
    *,
    sample_budget: Optional[int] = None,
    random_seed: int = 42,
) -> Dict[str, Any]:
    """Feasibility-check and cost-score a candidate pool for search-quality audit."""
    pool = list(candidates)
    if sample_budget is not None and len(pool) > sample_budget:
        rng = random.Random(int(random_seed))
        pool = rng.sample(pool, min(int(sample_budget), len(pool)))
    legal: List[Dict[str, Any]] = []
    rejected = 0
    for c, meta in pool:
        final_c, ml, _trace, _reason, _detail = feasible_with_relax(c, kf, hw)
        if final_c is None:
            rejected += 1
            continue
        final_c = _strategy_template_fields(final_c)
        cost = estimate_cost(final_c, kf, hw, ml, search)
        legal.append({"strategy": asdict(final_c), "cost": cost, "meta": meta})
    legal.sort(key=lambda x: x["cost"]["predicted_cycles"])
    best = legal[0] if legal else None
    return {
        "input_candidates": len(candidates),
        "evaluated_candidates": len(pool),
        "legal_candidates": len(legal),
        "rejected_candidates": rejected,
        "best_cost": (best or {}).get("cost", {}).get("predicted_cycles"),
        "best_strategy_signature": list(strategy_signature(StrategyConfig(**best["strategy"]))) if best else None,
        "best_strategy_id": (best or {}).get("strategy", {}).get("strategy_id"),
        "top_signatures": [list(strategy_signature(StrategyConfig(**x["strategy"]))) for x in legal[:10]],
    }


compact_search_for_quality_audit = _compact_search_for_quality_audit
score_candidate_pool_for_audit = _score_candidate_pool_for_audit

def build_search_quality_audit(
    kf: KernelFeatures,
    hw: Dict[str, Any],
    search: Dict[str, Any],
    *,
    beam_best_cost: Optional[float] = None,
    random_budget: int = 128,
    random_seed: int = 42,
) -> Dict[str, Any]:
    """Compare layered Beam Search with compact exhaustive and random baselines.

    This is a bounded *audit*, not a replacement search mode.  It helps answer:
    does Beam Search behave sensibly on a small space where exhaustive enumeration
    is cheap, and does it beat a fixed-seed random baseline?
    """
    compact = _compact_search_for_quality_audit(search)
    beam_candidates, beam_stats = build_layered_candidates(kf, hw, copy.deepcopy(compact))
    exhaustive_candidates, exhaustive_stats = build_exhaustive_candidates(kf, hw, copy.deepcopy(compact))
    beam_score = _score_candidate_pool_for_audit(beam_candidates, kf, hw, compact)
    exhaustive_score = _score_candidate_pool_for_audit(exhaustive_candidates, kf, hw, compact)
    random_score = _score_candidate_pool_for_audit(
        exhaustive_candidates, kf, hw, compact,
        sample_budget=int(random_budget), random_seed=int(random_seed),
    )
    beam_cost = beam_score.get("best_cost")
    exh_cost = exhaustive_score.get("best_cost")
    rand_cost = random_score.get("best_cost")
    gap = None
    if beam_cost is not None and exh_cost not in (None, 0):
        gap = float(beam_cost) / float(exh_cost) - 1.0
    random_adv = None
    if beam_cost is not None and rand_cost not in (None, 0):
        random_adv = float(rand_cost) / float(beam_cost) - 1.0
    return {
        "enabled": True,
        "type": "bounded_audit_not_main_search",
        "compact_space": {
            "tile_candidates": len(compact.get("tile_candidates", []) or []),
            "block_dim_candidates": len(compact.get("block_dim", []) or []),
            "layer1_top_w": compact.get("layer1_top_w"),
            "layer2_top_w": compact.get("layer2_top_w"),
            "layer3_top_w": compact.get("layer3_top_w"),
        },
        "beam_on_compact": {**beam_score, "search_stats": {"layer1_kept": beam_stats.get("layer1_kept"), "layer3_candidates": beam_stats.get("layer3_candidates")}},
        "small_exhaustive_on_compact": {**exhaustive_score, "search_stats": {"layer1_kept": exhaustive_stats.get("layer1_kept"), "layer3_candidates": exhaustive_stats.get("layer3_candidates")}},
        "random_baseline_on_compact": {**random_score, "random_budget": int(random_budget), "random_seed": int(random_seed)},
        "beam_vs_small_exhaustive_gap_ratio": gap,
        "beam_found_small_exhaustive_best": bool(
            beam_score.get("best_strategy_signature") is not None
            and beam_score.get("best_strategy_signature") == exhaustive_score.get("best_strategy_signature")
        ),
        "small_exhaustive_best_in_beam_top10": bool(
            exhaustive_score.get("best_strategy_signature") in (beam_score.get("top_signatures") or [])
        ),
        "beam_advantage_over_random_ratio": random_adv,
        "main_beam_best_cost": beam_best_cost,
        "note": "Compact exhaustive/random baselines validate Beam Search behavior on a bounded subspace; they do not prove real-hardware optimality.",
    }


# ------------------------------ 合法性检查与 relax ------------------------------

def feasibility(c: StrategyConfig, max_live: Dict[str, int], hw: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    """检查候选策略是否满足硬件容量、对齐和基础语义约束，并返回失败原因。"""
    details = {}
    for space in RESOURCE_SCOPES:
        cap = memory_cap_bytes(hw, space)
        req = max_live.get(space, 0)
        details[space] = {"required_kb": round(req / 1024, 2), "available_kb": round(cap / 1024, 2)}
        if cap and req > cap:
            return False, f"{space.upper()} overflow", details
    # 轻量级 C3/C4 代理约束。
    if c.cv_pipeline_stage > 1 and not (c.double_buffer or c.memory_reuse_level in {"level1", "level0", "inplace"}):
        return False, "CV pipeline stage >1 needs buffering or aggressive memory reuse", details
    if c.sync_policy == "graph_sync_solver" and (c.num_sync if hasattr(c, "num_sync") else 1) == 0:
        return False, "graph sync solver selected for kernel without sync signal", details
    return True, "ok", details


def relax_candidate(c: StrategyConfig) -> Optional[StrategyConfig]:
    """当候选超出硬件边界时，保守缩小 tile 或关闭部分高压选项以尝试恢复合法性。"""
    # GM workspace 是 fallback，不是默认优化路径；如果被 fallback gate 拒绝，
    # 首先回退到片上 UB stage buffer，再由后续容量门控决定是否继续 relax。
    if str(getattr(c, "stage_buffer_policy", "none")) == "gm_workspace":
        return replace(c, stage_buffer_policy="ub_stage")
    if c.memory_reuse_level == "level2":
        return replace(c, memory_reuse_level="level1")
    if c.memory_reuse_level == "level1":
        return replace(c, memory_reuse_level="level0")
    if c.memory_reuse_level == "level0":
        return replace(c, memory_reuse_level="inplace")
    if c.double_buffer:
        return replace(c, double_buffer=False, buffer_multipliers_json="{}", ub_multiplier=1, l1_multiplier=1, multibuffer_template="M0_no_multibuffer")
    if c.cv_pipeline_stage > 1:
        next_stage = 2 if c.cv_pipeline_stage > 2 else 1
        return replace(c, cv_pipeline_stage=next_stage)
    # 优先缩小最宽的 tile 维度，同时保持 Cube 对齐。
    if c.tile_n > 64:
        return replace(c, tile_n=max(64, c.tile_n // 2))
    if c.tile_k > 64:
        return replace(c, tile_k=max(64, c.tile_k // 2))
    if c.tile_m > 16:
        return replace(c, tile_m=max(16, c.tile_m // 2))
    return None


def feasible_with_relax(c: StrategyConfig, kf: KernelFeatures, hw: Dict[str, Any], max_steps: int = 8) -> Tuple[Optional[StrategyConfig], Dict[str, int], List[Dict[str, Any]], str, Dict[str, Any]]:
    """先做 feasibility 检查，失败时尝试 relax，并返回最终合法候选及原因。"""
    trace: List[Dict[str, Any]] = []
    cur = c
    last_reason = ""
    last_detail: Dict[str, Any] = {}
    for step in range(max_steps + 1):
        ml = estimate_max_live(cur, kf, hw)
        ok, reason, detail = feasibility(cur, ml, hw)
        if ok:
            gm_ok, gm_reason, gm_detail = gm_workspace_fallback_legality(cur, kf, hw)
            if not gm_ok:
                ok, reason = False, gm_reason
                detail = {**detail, "gm_workspace_fallback_gate": gm_detail}
        if ok:
            return cur, ml, trace, "ok", detail
        last_reason, last_detail = reason, detail
        trace.append({"step": step, "strategy": asdict(cur), "reason": reason, "max_live": detail})
        nxt = relax_candidate(cur)
        if nxt is None:
            break
        cur = replace(nxt, strategy_id=c.strategy_id)  # 保留原始 ID，便于追踪
    return None, estimate_max_live(cur, kf, hw), trace, last_reason, last_detail


# ------------------------------ V2.7 四类 Plan 表示 ------------------------------

def _strategy_template_fields(c: StrategyConfig) -> StrategyConfig:
    """把 StrategyConfig 中的模板类字段整理为报告友好的字典。"""
    mb_tpl = c.multibuffer_template
    if mb_tpl == "auto":
        mb_tpl = "M0_no_multibuffer" if not c.double_buffer else "M1_input_double_buffer"
        if c.double_buffer and c.cv_pipeline_stage > 1:
            mb_tpl = "M4_cv_stage_aware_multibuffer"
    cv_tpl = c.cv_pipeline_template
    if cv_tpl == "auto":
        if c.cv_pipeline_stage <= 1:
            cv_tpl = "P0_no_cv_pipeline"
        elif c.cv_pipeline_stage == 2:
            cv_tpl = "P2_stage2_balanced"
        else:
            cv_tpl = "P3_stage4_aggressive"
    sync_tpl = c.sync_template
    if sync_tpl == "auto":
        sync_tpl = "Y2_graph_sync_solver" if c.sync_policy == "graph_sync_solver" else "Y0_keep_existing"
    return replace(c, multibuffer_template=mb_tpl, cv_pipeline_template=cv_tpl, sync_template=sync_tpl)


def build_four_plan_bundle(c: StrategyConfig, kf: KernelFeatures, hw: Dict[str, Any], max_live: Dict[str, int], search: Dict[str, Any]) -> Dict[str, Any]:
    """把 StrategyConfig 拆解成 Tiling/MultiBuffer/CVPipeline/Sync 四类 Plan 的结构化报告。"""
    c = _strategy_template_fields(c)
    artifact = get_artifact(search)
    artifact_mlir = artifact.get("mlir_evidence", {}) or {}
    artifact_des = artifact.get("des_evidence", {}) or {}
    generic_structure = artifact_mlir.get("generic_hivm_structure", {}) if isinstance(artifact_mlir, dict) else {}
    ping_pong_pairs = artifact_mlir.get("ping_pong_pairs", []) if isinstance(artifact_mlir, dict) else []
    cv_sequence = artifact_mlir.get("cv_op_sequence", {}) if isinstance(artifact_mlir, dict) else {}
    event_pairs = artifact_mlir.get("event_sync_pairs", []) if isinstance(artifact_mlir, dict) else []
    pshape = problem_shape(search, kf)
    n_tiles = estimate_num_tiles_for_tile(kf, search, {"m": c.tile_m, "n": c.tile_n, "k": c.tile_k})
    elem = 2
    acc = 4
    load_bytes = (c.tile_m * c.tile_k + c.tile_k * c.tile_n) * elem
    store_bytes = c.tile_m * c.tile_n * elem
    cube_ops = 2 * c.tile_m * c.tile_n * c.tile_k if kf.num_mmad else 0
    vector_ops = max(1, sum(kf.vector_op_counts.values())) * c.tile_m * c.tile_n
    tile_ok, align_notes = satisfies_align_tile(c.tile_m, c.tile_n, c.tile_k, hw)
    effects = strategy_effect_settings(hw)
    mb_cfg = effects.get("multibuffer", {})
    cv_cfg = effects.get("cv_pipeline", {})
    sync_cfg = effects.get("sync", {})

    mb_enabled = bool(c.double_buffer)
    buffer_multipliers = _parse_buffer_multipliers_json(c.buffer_multipliers_json)
    per_buffer_extra = per_buffer_extra_bytes_by_scope(kf, buffer_multipliers)
    per_buffer_bonus = per_buffer_overlap_bonus(kf, buffer_multipliers)
    input_mult = 2 if mb_enabled else 1
    stage_mult = max(1, min(int(c.cv_pipeline_stage), 4)) if c.cv_pipeline_stage > 1 else 1
    load_overlap = 0.0 if not mb_enabled else float(mb_cfg.get("load_overlap_no_cv", 0.55) if c.cv_pipeline_stage <= 1 else mb_cfg.get("load_overlap_with_cv", 0.68))
    store_overlap = 0.0 if not mb_enabled else float(mb_cfg.get("store_overlap", 0.35))
    mb_template_adjustment = (mb_cfg.get("template_adjustment") or {}).get(c.multibuffer_template, {"load_bonus": 0.0, "store_bonus": 0.0, "overhead": 0.0})
    if mb_enabled:
        load_overlap += float(mb_template_adjustment.get("load_bonus", 0.0))
        store_overlap += float(mb_template_adjustment.get("store_bonus", 0.0))
    load_overlap += float(per_buffer_bonus.get("load_overlap_bonus", 0.0))
    store_overlap += float(per_buffer_bonus.get("store_overlap_bonus", 0.0))
    load_overlap = min(float(mb_cfg.get("load_overlap_cap", 0.88)), load_overlap)
    store_overlap = min(float(mb_cfg.get("store_overlap_cap", 0.62)), store_overlap)

    has_cv = bool((kf.num_mmad and kf.vector_op_counts) or cv_sequence.get("cv_pipeline_candidate"))
    separable = has_cv and c.cv_pipeline_stage > 1
    cv_overlap = 0.0
    if c.cv_pipeline_stage == 2 and separable:
        if c.cv_pipeline_template == "P1_stage2_basic":
            cv_overlap = float(cv_cfg.get("stage2_basic_overlap", 0.50))
        elif c.cv_pipeline_template == "P_PREFILL_LARGE_SBS_REUSE":
            cv_overlap = float(cv_cfg.get("prefill_large_sbs_reuse_overlap", 0.64))
        else:
            cv_overlap = float(cv_cfg.get("stage2_balanced_overlap", 0.58))
    elif c.cv_pipeline_stage >= 4 and separable:
        cv_overlap = float(cv_cfg.get("stage4_overlap", 0.68))
    if c.enable_mixed_cv and c.cv_pipeline_stage > 1:
        cv_overlap += float(cv_cfg.get("mixed_cv_bonus", 0.04))
    if c.auto_cv_balance and c.cv_pipeline_stage > 1:
        cv_overlap += float(cv_cfg.get("auto_balance_bonus", 0.03))
    if c.cv_pipeline_template == "P_PREFILL_LARGE_SBS_REUSE":
        # 该内置模板有意采用 cube-heavy/vector-light 的混合方式，
        # 用于保留 QK/SV 序列附近的 K/Q 复用；不要像普通 CV mix 那样惩罚它的 loop imbalance。
        cv_overlap *= float(cv_cfg.get("prefill_reuse_overlap_multiplier", 1.02))
        cv_template_overhead = float((cv_cfg.get("template_overhead") or {}).get("P_PREFILL_LARGE_SBS_REUSE", 0.035))
    elif c.cv_pipeline_template == "P1_stage2_basic":
        cv_template_overhead = float((cv_cfg.get("template_overhead") or {}).get("P1_stage2_basic", 0.015))
    elif c.cv_pipeline_template == "P2_stage2_balanced":
        cv_template_overhead = float((cv_cfg.get("template_overhead") or {}).get("P2_stage2_balanced", 0.020))
    elif c.cv_pipeline_template == "P3_stage4_aggressive":
        cv_template_overhead = float((cv_cfg.get("template_overhead") or {}).get("P3_stage4_aggressive", 0.055))
    else:
        cv_template_overhead = float((cv_cfg.get("template_overhead") or {}).get("default", 0.020))
    tile_mix_balance_penalty = float(cv_cfg.get("tile_mix_balance_alpha", 0.04)) * abs(int(c.tile_mix_cube_loop) - int(c.tile_mix_vector_loop))
    if c.cv_pipeline_template != "P_PREFILL_LARGE_SBS_REUSE":
        cv_overlap *= max(float(cv_cfg.get("tile_mix_overlap_floor", 0.75)), 1.0 - tile_mix_balance_penalty)
    producer_consumer_distance_penalty = float(cv_cfg.get("producer_consumer_distance_alpha", 0.025)) * max(0, int(c.producer_consumer_distance) - 1)
    # 更远的 producer-consumer distance 可提供调度自由度，但也会增加 drain/stall；这里作为轻量折减。
    cv_overlap *= max(float(cv_cfg.get("producer_consumer_overlap_floor", 0.88)), 1.0 - producer_consumer_distance_penalty)
    cv_overlap = max(0.0, min(float(cv_cfg.get("cv_overlap_cap", 0.78)), cv_overlap))

    sync_ops = kf.num_pipe_barrier + kf.num_set_flag + kf.num_wait_flag + kf.num_sync_block_set + kf.num_sync_block_wait
    if c.sync_policy == "graph_sync_solver" and sync_ops > 0:
        barrier_mult = (sync_cfg.get("gss_barrier_mult") or {"low": 0.50, "medium": 0.65, "high": 0.80}).get(c.barrier_level, 0.65)
        event_mult = float(sync_cfg.get("gss_event_mult_reuse", 0.72) if c.event_reuse else sync_cfg.get("gss_event_mult_no_reuse", 0.80))
        granularity_mult = (sync_cfg.get("granularity_mult") or {"op": 1.00, "tile": 0.88, "stage": 0.78}).get(c.sync_granularity, 1.0)
        n_barrier = int(round(kf.num_pipe_barrier * barrier_mult * granularity_mult))
        n_set = int(round(kf.num_set_flag * event_mult * granularity_mult))
        n_wait = int(round(kf.num_wait_flag * event_mult * granularity_mult))
        sync_legality = {"status": "UNKNOWN", "reason": "estimated demo cannot prove GraphSyncSolver deadlock-free; requires real sync_plan sidecar"}
        stall_factor = float(sync_cfg.get("gss_base_stall", 0.70)) * (float(sync_cfg.get("event_reuse_stall_mult", 0.92)) if c.event_reuse else 1.0) * (sync_cfg.get("gss_granularity_stall_mult") or {"op": 1.0, "tile": 0.90, "stage": 0.82}).get(c.sync_granularity, 1.0)
        stall_factor *= (sync_cfg.get("event_id_policy_stall_mult") or {"keep": 1.00, "compact": 0.94, "reuse": 0.88}).get(c.event_id_policy, 1.0)
        stall_factor *= float(sync_cfg.get("gss_local_move_stall_mult", 0.96)) if c.sync_motion == "local_move" else 1.0
    else:
        barrier_mult = (sync_cfg.get("keep_barrier_mult") or {"low": 0.80, "medium": 1.00, "high": 1.25}).get(c.barrier_level, 1.0)
        n_barrier = int(round(kf.num_pipe_barrier * barrier_mult))
        n_set = kf.num_set_flag
        n_wait = kf.num_wait_flag
        sync_legality = {"status": "PASS_ESTIMATED" if sync_ops > 0 else "PASS", "reason": "keep existing sync or no sync signal"}
        stall_factor = (sync_cfg.get("keep_barrier_level_stall_mult") or {"low": 0.95, "medium": 1.00, "high": 1.10}).get(c.barrier_level, 1.0)
        stall_factor *= float(sync_cfg.get("keep_local_move_stall_mult", 0.98)) if c.sync_motion == "local_move" else 1.0

    sync_template_adjustment = (sync_cfg.get("template_adjustment") or {}).get(c.sync_template, {"barrier": 1.0, "event": 1.0, "stall": 1.0, "overhead": 0.0})
    n_barrier = int(round(n_barrier * float(sync_template_adjustment.get("barrier", 1.0))))
    n_set = int(round(n_set * float(sync_template_adjustment.get("event", 1.0))))
    n_wait = int(round(n_wait * float(sync_template_adjustment.get("event", 1.0))))
    stall_factor *= float(sync_template_adjustment.get("stall", 1.0))

    scope_utils = {
        s: (max_live.get(s, 0) / memory_cap_bytes(hw, s) if memory_cap_bytes(hw, s) else None)
        for s in RESOURCE_SCOPES
    }

    bundle = FourPlanBundle(
        model_version="V3.3-artifact-kernel-profile",
        fixed_parameters={
            "fusion": c.fusion,
            "block_dim": {"value": c.block_dim, "policy": "derived_default_not_searched"},
            "memory_reuse_level": c.memory_reuse_level,
            "cv_split_ratio": c.cv_split_ratio,
            "dma_policy": c.dma_policy,
        },
        tiling_plan=TilingPlan(
            source="estimated_plus_artifact_evidence",
            controllable_knobs={
                "tile_m": c.tile_m, "tile_n": c.tile_n, "tile_k": c.tile_k,
                "logical_axes": (generic_structure.get("logical_axes") if generic_structure.get("detected") else ["axis_m", "axis_n", "axis_k"]),
                "generic_logical_axes_evidence": {
                    "primary_tile_candidate": generic_structure.get("primary_tile_candidate", {}),
                    "candidate_tiles_from_cube_ops": generic_structure.get("candidate_tiles_from_cube_ops", []),
                    "conventional_tensor_signature": generic_structure.get("conventional_tensor_signature", {}),
                },
                "loop_order": c.loop_order,
                "tail_strategy": c.tail_strategy,
                "reduce_tile_policy": c.reduce_tile_policy,
                "layout_aware_tile": c.layout_aware_tile,
            },
            derived_features={
                "problem_shape": pshape,
                "num_tiles": n_tiles,
                "effective_reduce_tile_k": c.tile_k if c.reduce_tile_policy == "full_k" else max(16, c.tile_k // 2),
                "reduce_tile_policy_effect": "full reduction tile" if c.reduce_tile_policy == "full_k" else "split K/reduction tile; lower L1 pressure with extra loop overhead",
                "layout_aware_tile_enabled": c.layout_aware_tile,
                "load_bytes_per_tile": load_bytes,
                "store_bytes_per_tile": store_bytes,
                "cube_ops_per_tile": cube_ops,
                "vector_ops_proxy_per_tile": vector_ops,
                "tile_working_set_bytes_proxy": load_bytes + store_bytes + c.tile_m * c.tile_n * acc,
                "source_input_policy": "Python/Triton source is not parsed in V3.3; this plan is derived from MLIR plus optional DES/trace JSON evidence.",
                "artifact_memrefs_by_space": artifact_mlir.get("memrefs_by_space", {}),
                "artifact_unique_alloc_bytes_by_space": artifact_mlir.get("unique_alloc_bytes_by_space", {}),
                "artifact_static_max_live_bytes_by_space": artifact_mlir.get("static_max_live_bytes_by_space", {}),
                "artifact_mmad_count": (artifact_mlir.get("op_counts", {}) or {}).get("mmadL1", 0) + (artifact_mlir.get("op_counts", {}) or {}).get("mmad", 0),
                "artifact_nd2nz_count": (artifact_mlir.get("op_counts", {}) or {}).get("nd2nz", 0),
                "generic_hivm_structure": generic_structure,
                "generic_cube_shape_evidence": generic_structure.get("cube_shape_evidence", []),
                "generic_candidate_tiles_from_cube_ops": generic_structure.get("candidate_tiles_from_cube_ops", []),
                "generic_memrefs_by_space_detail": generic_structure.get("memrefs_by_space_detail", {}),
                "loop_trip_annotation": generic_structure.get("loop_trip_annotation"),
            },
            legality={
                "status": "PASS_ESTIMATED" if tile_ok else "FAIL",
                "checks": {"tile_align": tile_ok, "stride_legal": "UNKNOWN_WITHOUT_REAL_AUTOSCHEDULE"},
                "notes": align_notes,
            },
        ),
        multibuffer_plan=MultiBufferPlan(
            source="estimated_plus_artifact_evidence",
            controllable_knobs={
                "double_buffer": c.double_buffer,
                "template": c.multibuffer_template,
                "input_buffer_multiplier": input_mult,
                "stage_buffer_multiplier": stage_mult if c.cv_pipeline_stage > 1 else 1,
                "ub_multiplier": c.ub_multiplier,
                "l1_multiplier": c.l1_multiplier,
                "stage_buffer_policy": c.stage_buffer_policy,
                "buffer_multipliers": buffer_multipliers,
                "buffer_multiplier_domain": {b["name"]: [1, 2] for b in eligible_multibuffer_buffers(kf, search)},
                "detected_ping_pong_multibuffer": bool(ping_pong_pairs),
            },
            derived_features={
                "load_overlap_ratio": load_overlap,
                "store_overlap_ratio": store_overlap,
                "template_schedule_overhead_ratio": float(mb_template_adjustment.get("overhead", 0.0)),
                "template_cost_effect": mb_template_adjustment,
                "scope_utilization": scope_utils,
                "max_live_bytes": max_live,
                "per_scope_multiplier": {"ub": c.ub_multiplier, "l1": c.l1_multiplier, "l0a": 1, "l0b": 1, "l0c": 1},
                "per_buffer_extra_bytes_by_scope": per_buffer_extra,
                "per_buffer_overlap_bonus": per_buffer_bonus,
                "num_buffers_with_multiplier_2": int(per_buffer_bonus.get("num_doubled_buffers", 0)),
                "stage_buffer_policy_effect": c.stage_buffer_policy,
                "artifact_multibuffer_annotations": artifact_mlir.get("hivm_multi_buffer_annotations", 0),
                "artifact_multibuffer_slots_histogram": artifact_des.get("multi_buffer_slots_histogram", {}),
                "ping_pong_pairs": ping_pong_pairs,
                "buffer_level_multibuffer_detected": bool(ping_pong_pairs),
            },
            legality={
                "status": "PASS_ESTIMATED",
                "capacity_rule": "maxLive_S(T,M,P) <= Cap_S checked by estimated_max_live including per-buffer nbuf_b extra copies",
                "per_buffer_multiplier_rule": "for each eligible local buffer b, nbuf_b in {1,2}; illegal combinations are rejected by maxLive_S gate",
            },
        ),
        cv_pipeline_plan=CVPipelinePlan(
            source="estimated_plus_artifact_evidence",
            controllable_knobs={
                "stage_num": c.cv_pipeline_stage,
                "template": c.cv_pipeline_template,
                "enable_mixed_cv": c.enable_mixed_cv,
                "tile_mix_cube_loop": c.tile_mix_cube_loop,
                "tile_mix_vector_loop": c.tile_mix_vector_loop,
                "auto_cv_balance": c.auto_cv_balance,
                "producer_consumer_distance": c.producer_consumer_distance,
                "stage_buffer_policy": c.stage_buffer_policy,
            },
            derived_features={
                "has_cube": bool(kf.num_mmad),
                "has_vector": bool(kf.vector_op_counts),
                "separable_estimated": separable,
                "cv_overlap_ratio": cv_overlap,
                "stage_buffer_multiplier": stage_mult,
                "warmup_drain_factor": 0.02 * max(0, c.cv_pipeline_stage - 1) * (1.15 if c.cv_pipeline_template == "P3_stage4_aggressive" else 1.0),
                "template_schedule_overhead_ratio": float(cv_template_overhead),
                "tile_mix_balance_penalty": float(tile_mix_balance_penalty),
                "producer_consumer_distance_penalty": float(producer_consumer_distance_penalty),
                "stage_buffer_policy": c.stage_buffer_policy,
                "artifact_part_of_mix": artifact_mlir.get("hivm_part_of_mix", 0),
                "artifact_pipe_fraction": artifact_des.get("pipe_fraction", {}),
                "artifact_critical_pipe": artifact_des.get("critical_pipe"),
                "cv_op_sequence": cv_sequence,
                "cv_pipeline_candidate_from_op_sequence": bool(cv_sequence.get("cv_pipeline_candidate")),
                "cube_vector_layout_cube_sequence": bool(cv_sequence.get("cube_vector_layout_cube_sequence")),
                "cube_ops_in_sequence": cv_sequence.get("cube_ops", []),
                "vector_ops_in_sequence": cv_sequence.get("vector_ops", []),
                "layout_ops_in_sequence": cv_sequence.get("layout_ops", []),
            },
            legality={
                "status": "PASS_ESTIMATED" if (c.cv_pipeline_stage <= 1 or separable) else "FAIL",
                "reason": "estimated from cube/vector op sequence; real CVPipelining dry-run required for authoritative separability",
            },
        ),
        sync_plan=SyncPlan(
            source="estimated_plus_artifact_evidence",
            controllable_knobs={
                "policy": c.sync_policy,
                "template": c.sync_template,
                "barrier_level": c.barrier_level,
                "event_reuse": c.event_reuse,
                "sync_granularity": c.sync_granularity,
                "event_id_policy": c.event_id_policy,
                "sync_motion": c.sync_motion,
                "remove_redundant_sync": c.sync_policy == "graph_sync_solver",
                "sync_style_from_ir": "event" if event_pairs else ("barrier" if kf.num_pipe_barrier else "none"),
            },
            derived_features={
                "num_set_flag_estimated": n_set,
                "num_wait_flag_estimated": n_wait,
                "num_barrier_estimated": n_barrier,
                "raw_sync_ops": sync_ops,
                "stall_factor": stall_factor,
                "artifact_sync_counts_by_name": artifact_des.get("sync_counts_by_name", {}),
                "artifact_des_sync_ops": artifact_des.get("sync_ops"),
                "artifact_des_barrier_ops": artifact_des.get("barrier_ops"),
                "event_sync_pairs": event_pairs,
                "event_ids_detected": sorted({p.get("event_id") for p in event_pairs if p.get("event_id")}),
                "event_id_policy_effect": c.event_id_policy,
                "sync_motion_effect": c.sync_motion,
                "sync_template_cost_effect": sync_template_adjustment,
                "template_fixed_overhead_cycles": float(sync_template_adjustment.get("overhead", 0.0)),
            },
            legality=sync_legality,
        ),
    )
    return asdict(bundle)



def _deep_update_dict(base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并字典，用于把 cost-model config 覆盖到默认配置上。"""
    out = dict(base)
    for k, v in (update or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_update_dict(out[k], v)
        else:
            out[k] = v
    return out


def conservative_cost_safety(hw: Dict[str, Any]) -> Dict[str, Any]:
    """根据内存压力、stage 深度和同步复杂度加入保守安全系数，避免过度乐观。"""
    defaults = {
        "enabled": True,
        "pressure_threshold": {"ub": 0.80, "l1": 0.90, "l0a": 0.85, "l0b": 0.75, "l0c": 0.85},
        # pressure_penalty 已经有硬件 overflow 检查兜底，因此这里只作为“接近容量上限”的软惩罚。
        # 使用连续二次项 + per-scope cap，避免未溢出候选被单个 penalty 主导。
        "pressure_alpha": {"ub": 180.0, "l1": 60.0, "l0a": 120.0, "l0b": 220.0, "l0c": 120.0},
        "pressure_penalty_cap_per_scope": {"ub": 180.0, "l1": 60.0, "l0a": 120.0, "l0b": 220.0, "l0c": 120.0},
        # shape/tail penalty 只作为轻量 regularization，不再使用固定大额跳变。
        "tail_penalty_alpha": 60.0,
        "tail_penalty_power": 2.0,
        "tail_penalty_cap": 60.0,
        "irregular_tile_n_alpha": 80.0,
        "irregular_tile_n_power": 2.0,
        "irregular_tile_n_cap": 80.0,
        "preferred_tile_n": [64, 96, 128, 160, 192, 256],
        "large_tile_n_soft_cap": 192,
        "large_tile_n_alpha": 80.0,
        "large_tile_n_power": 2.0,
        "large_tile_n_cap": 120.0,
        "overlap_pressure_threshold": 0.75,
        "overlap_pressure_slope": 0.35,
    }
    user = hw.get("calibration", {}).get("cost_model_safety", {})
    if isinstance(user, dict):
        defaults = _deep_update_dict(defaults, user)
    return defaults


def cost_risk_settings(hw: Dict[str, Any], search: Dict[str, Any]) -> Dict[str, Any]:
    """返回当前 risk mode 下的 cost-model 风险降权配置。

    没有 profiling 数据时，不能让 GraphSyncSolver/CVPipeline 这类未验证优化拿满收益。
    conservative/balanced/aggressive 三种模式只改变风险项，不改变硬件 capacity gate。
    """
    mode = str(search.get("cost_risk_mode") or hw.get("calibration", {}).get("cost_risk_mode") or "conservative")
    defaults = {
        "conservative": {
            "cv_estimated_overlap_multiplier": 0.65,
            "cv_estimated_penalty_ratio": 0.08,
            "sync_unknown_penalty_per_op": 28.0,
            "sync_unknown_penalty_ratio": 0.35,
            "event_reuse_penalty_per_op": 6.0,
            "risk_score_bias": 0.0,
        },
        "balanced": {
            "cv_estimated_overlap_multiplier": 0.82,
            "cv_estimated_penalty_ratio": 0.035,
            "sync_unknown_penalty_per_op": 12.0,
            "sync_unknown_penalty_ratio": 0.16,
            "event_reuse_penalty_per_op": 2.5,
            "risk_score_bias": 0.0,
        },
        "aggressive": {
            "cv_estimated_overlap_multiplier": 1.0,
            "cv_estimated_penalty_ratio": 0.0,
            "sync_unknown_penalty_per_op": 0.0,
            "sync_unknown_penalty_ratio": 0.0,
            "event_reuse_penalty_per_op": 0.0,
            "risk_score_bias": 8.0,
        },
    }
    user_modes = hw.get("calibration", {}).get("cost_model_risk_modes", {})
    if isinstance(user_modes, dict):
        defaults = _deep_update_dict(defaults, user_modes)
    cfg = dict(defaults.get(mode, defaults["conservative"]))
    cfg["mode"] = mode if mode in defaults else "conservative"
    return cfg


def strategy_effect_settings(hw: Dict[str, Any]) -> Dict[str, Any]:
    """返回四类 Plan 进入 cost model 的经验影响参数。

    第一阶段把主要魔数从 build_four_plan_bundle 中移到 calibration.cost_model_strategy_effects。
    默认值仍保留在代码里作为兜底；正式运行建议使用 configs/cost_model_*.json 显式覆盖。
    """
    defaults = {
        "multibuffer": {
            "load_overlap_no_cv": 0.55,
            "load_overlap_with_cv": 0.68,
            "store_overlap": 0.35,
            "load_overlap_cap": 0.88,
            "store_overlap_cap": 0.62,
            "template_adjustment": {
                "M0_no_multibuffer": {"load_bonus": 0.00, "store_bonus": 0.00, "overhead": 0.00},
                "M1_input_double_buffer": {"load_bonus": 0.02, "store_bonus": 0.00, "overhead": 0.01},
                "M2_input_output_double_buffer": {"load_bonus": 0.03, "store_bonus": 0.05, "overhead": 0.015},
                "M3_ping_pong_detected": {"load_bonus": 0.05, "store_bonus": 0.03, "overhead": 0.01},
                "M4_cv_stage_aware_multibuffer": {"load_bonus": 0.06, "store_bonus": 0.03, "overhead": 0.025},
            },
        },
        "cv_pipeline": {
            "stage2_basic_overlap": 0.50,
            "stage2_balanced_overlap": 0.58,
            "prefill_large_sbs_reuse_overlap": 0.64,
            "stage4_overlap": 0.68,
            "mixed_cv_bonus": 0.04,
            "auto_balance_bonus": 0.03,
            "prefill_reuse_overlap_multiplier": 1.02,
            "template_overhead": {
                "P_PREFILL_LARGE_SBS_REUSE": 0.035,
                "P1_stage2_basic": 0.015,
                "P2_stage2_balanced": 0.020,
                "P3_stage4_aggressive": 0.055,
                "default": 0.020,
            },
            "tile_mix_balance_alpha": 0.04,
            "tile_mix_overlap_floor": 0.75,
            "producer_consumer_distance_alpha": 0.025,
            "producer_consumer_overlap_floor": 0.88,
            "cv_overlap_cap": 0.78,
        },
        "sync": {
            "gss_barrier_mult": {"low": 0.50, "medium": 0.65, "high": 0.80},
            "keep_barrier_mult": {"low": 0.80, "medium": 1.00, "high": 1.25},
            "gss_event_mult_reuse": 0.72,
            "gss_event_mult_no_reuse": 0.80,
            "granularity_mult": {"op": 1.00, "tile": 0.88, "stage": 0.78},
            "gss_base_stall": 0.70,
            "event_reuse_stall_mult": 0.92,
            "gss_granularity_stall_mult": {"op": 1.0, "tile": 0.90, "stage": 0.82},
            "event_id_policy_stall_mult": {"keep": 1.00, "compact": 0.94, "reuse": 0.88},
            "gss_local_move_stall_mult": 0.96,
            "keep_barrier_level_stall_mult": {"low": 0.95, "medium": 1.00, "high": 1.10},
            "keep_local_move_stall_mult": 0.98,
            "template_adjustment": {
                "Y0_keep_existing": {"barrier": 1.00, "event": 1.00, "stall": 1.00, "overhead": 0.00},
                "Y1_conservative_barrier": {"barrier": 1.10, "event": 1.00, "stall": 1.06, "overhead": 6.00},
                "Y2_graph_sync_solver": {"barrier": 0.92, "event": 0.94, "stall": 0.93, "overhead": 10.00},
                "Y3_event_reuse": {"barrier": 1.00, "event": 0.82, "stall": 0.90, "overhead": 8.00},
            },
        },
    }
    user = hw.get("calibration", {}).get("cost_model_strategy_effects", {})
    if isinstance(user, dict):
        defaults = _deep_update_dict(defaults, user)
    return defaults


def compute_risk_assessment(c: StrategyConfig, plans: Dict[str, Any], max_live: Dict[str, int], hw: Dict[str, Any], search: Dict[str, Any]) -> Dict[str, Any]:
    """给候选策略打风险等级。风险不是合法性失败，只是提示该策略依赖多少未验证假设。"""
    cfg = cost_risk_settings(hw, search)
    score = float(cfg.get("risk_score_bias", 0.0))
    reasons: List[str] = []

    sync_legality = ((plans.get("sync_plan") or {}).get("legality") or {}).get("status")
    cv_legality = ((plans.get("cv_pipeline_plan") or {}).get("legality") or {}).get("status")
    if c.sync_policy == "graph_sync_solver":
        score += 35.0
        reasons.append("uses graph_sync_solver; demo cannot prove deadlock-free sync rewrite")
    if sync_legality == "UNKNOWN":
        score += 30.0
        reasons.append("sync legality is UNKNOWN without real sync_plan sidecar")
    if c.event_reuse:
        score += 12.0
        reasons.append("uses event reuse; requires real event-id dependency validation")
    if c.cv_pipeline_stage > 1 and cv_legality == "PASS_ESTIMATED":
        score += 22.0
        reasons.append("CVPipeline separability is PASS_ESTIMATED, not pass-verified")
    if c.double_buffer:
        score += 5.0
        reasons.append("uses double/multi-buffer overlap assumptions")
    utils = {s: (max_live.get(s, 0) / memory_cap_bytes(hw, s) if memory_cap_bytes(hw, s) else 0.0) for s in RESOURCE_SCOPES}
    hot = {s: u for s, u in utils.items() if u and u >= 0.85}
    if hot:
        score += 15.0
        reasons.append("near hardware capacity boundary: " + ", ".join(f"{k}={v:.2f}" for k, v in sorted(hot.items())))
    level = "LOW" if score < 25.0 else ("MEDIUM" if score < 60.0 else "HIGH")
    return {
        "risk_level": level,
        "risk_score": float(round(score, 3)),
        "risk_mode": cfg.get("mode", "conservative"),
        "risk_reasons": reasons,
        "scope_utilization": {k: float(v) for k, v in utils.items()},
    }


def memory_pressure_penalty(scope_utilization: Dict[str, Any], hw: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """根据各层级 max-live/capacity 比例计算连续、封顶的内存压力软惩罚。

    注意：真正的容量越界已经由 feasibility/hardware boundary 处理。这里的 penalty 只表达
    “虽然没有 overflow，但已经接近硬件边界，overlap 和调度稳定性可能变差”。因此它必须是
    软项，不能在未溢出的情况下压过主要 compute/memory/sync cost。
    """
    cfg = conservative_cost_safety(hw)
    if not cfg.get("enabled", True):
        return 0.0, {"enabled": False}
    thresholds = cfg.get("pressure_threshold", {})
    alphas = cfg.get("pressure_alpha", {})
    caps = cfg.get("pressure_penalty_cap_per_scope", {})
    detail: Dict[str, Any] = {}
    total = 0.0
    for sp, util in (scope_utilization or {}).items():
        if util is None:
            continue
        u = float(util)
        th = float(thresholds.get(sp, 0.85))
        alpha = float(alphas.get(sp, 120.0))
        cap = float(caps.get(sp, alpha))
        # 归一化到 [threshold, 1.0] 区间，形成连续二次软惩罚。
        over_norm = max(0.0, u - th) / max(1e-6, 1.0 - th)
        raw_val = alpha * over_norm * over_norm
        val = min(cap, raw_val)
        if val:
            detail[str(sp)] = {
                "utilization": float(u),
                "threshold": float(th),
                "over_norm": float(over_norm),
                "raw_penalty": float(raw_val),
                "capped_penalty": float(val),
            }
            total += val
    return float(total), detail


def shape_regularization_penalty(c: StrategyConfig, kf: KernelFeatures, hw: Dict[str, Any], search: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """计算连续、低权重、可解释的 shape/tail 软惩罚。

    这个函数不再使用“tile_n 不在 preferred list 就固定 +400”的离散跳变。
    现在的处理方式是：
    1. 尾块按照尾部占 tile 的比例连续惩罚；
    2. tile_n 与最近 preferred tile_n 的距离越远，惩罚越大，但有 cap；
    3. 过大的 tile_n 用连续 soft-cap 惩罚。

    因此该项只作为轻量 regularization，避免异常 shape 钻 cost model 空子，
    不应成为 predicted_cycles 改善的主导来源。
    """
    cfg = conservative_cost_safety(hw)
    if not cfg.get("enabled", True):
        return 0.0, {"enabled": False}
    pshape = problem_shape(search, kf)
    n_total = int(pshape.get("n_total", 1) or 1)
    tile_n = max(1, int(c.tile_n))
    preferred = sorted({int(x) for x in cfg.get("preferred_tile_n", []) if int(x) > 0})
    total = 0.0
    detail: Dict[str, Any] = {
        "n_total": n_total,
        "tile_n": tile_n,
        "preferred_tile_n": preferred,
        "tail_n": 0,
        "tail_fraction": 0.0,
        "tail_penalty": 0.0,
        "nearest_preferred_tile_n": None,
        "preferred_distance_fraction": 0.0,
        "irregular_tile_n_penalty": 0.0,
        "large_tile_n_penalty": 0.0,
        "regularization_mode": "continuous_low_weight_capped",
    }

    if n_total > 1:
        tail = n_total % tile_n
        detail["tail_n"] = int(tail)
        if tail != 0:
            # tail 越接近半个 tile，mask/pad/peel 额外成本越明显；很小的尾巴只轻微惩罚。
            tail_fraction = min(tail, tile_n - tail) / max(1.0, float(tile_n))
            alpha = float(cfg.get("tail_penalty_alpha", cfg.get("tail_penalty_cycles", 60.0)))
            power = float(cfg.get("tail_penalty_power", 2.0))
            cap = float(cfg.get("tail_penalty_cap", alpha))
            raw_v = alpha * (tail_fraction ** power)
            v = min(cap, raw_v)
            detail["tail_fraction"] = float(tail_fraction)
            detail["tail_penalty"] = float(v)
            total += v

    if preferred:
        nearest = min(preferred, key=lambda x: abs(x - tile_n))
        denom = max(64.0, float(nearest), float(tile_n))
        distance_fraction = abs(tile_n - nearest) / denom
        alpha = float(cfg.get("irregular_tile_n_alpha", min(float(cfg.get("irregular_tile_n_penalty_cycles", 80.0)), 80.0)))
        power = float(cfg.get("irregular_tile_n_power", 2.0))
        cap = float(cfg.get("irregular_tile_n_cap", alpha))
        raw_v = alpha * (distance_fraction ** power)
        v = min(cap, raw_v)
        detail["nearest_preferred_tile_n"] = int(nearest)
        detail["preferred_distance_fraction"] = float(distance_fraction)
        detail["irregular_tile_n_penalty"] = float(v)
        total += v

    soft_cap = int(cfg.get("large_tile_n_soft_cap", 10**9))
    if tile_n > soft_cap:
        alpha = float(cfg.get("large_tile_n_alpha", 80.0))
        power = float(cfg.get("large_tile_n_power", 2.0))
        cap = float(cfg.get("large_tile_n_cap", alpha))
        raw_v = alpha * ((tile_n - soft_cap) / 64.0) ** power
        v = min(cap, raw_v)
        detail["large_tile_n_penalty"] = float(v)
        total += v
    return float(total), detail



def estimate_scalar_control_time(c: StrategyConfig | Layer1Case, kf: KernelFeatures, search: Dict[str, Any], kernel_profile: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """估算每 tile 的 scalar/control/address 开销。

    该项只基于 MLIR 与编译产物抽取出的结构计数，并随 tile 形状变化；
    它不是 profiling 校准项。小 tile 会带来更多循环/地址计算/同步编排开销，
    因此这里通过 tile volume 和 K 切分策略加入 fragmentation penalty。
    """
    if not isinstance(kernel_profile, dict) or not kernel_profile.get("enabled"):
        return 0.0, {"enabled": False}
    raw = kernel_profile.get("raw_features", {}) if isinstance(kernel_profile.get("raw_features", {}), dict) else {}
    weights = kernel_profile.get("weights", {}) if isinstance(kernel_profile.get("weights", {}), dict) else {}
    scalar_counts = raw.get("scalar_family_counts", {}) if isinstance(raw.get("scalar_family_counts", {}), dict) else {}
    scalar_score = float(raw.get("scalar_score", 0.0) or 0.0)
    sync_score = float(raw.get("sync_score", 0.0) or 0.0)
    scalar_mult = float(weights.get("scalar_control_multiplier", 1.0) or 1.0)
    small_tile_scale = float(weights.get("small_tile_scalar_penalty_scale", 1.0) or 1.0)
    loop_weighted_scalar_multiplier = float(weights.get("loop_weighted_scalar_multiplier", 1.0) or 1.0)
    alignment_penalty_scale = float(weights.get("alignment_penalty_scale", 1.0) or 1.0)
    pshape = problem_shape(search, kf)
    total_vol = max(1.0, float(pshape.get("m_total", 64)) * float(pshape.get("n_total", 128)) * float(pshape.get("k_total", 128)))
    tile_vol = max(1.0, float(c.tile_m) * float(c.tile_n) * float(c.tile_k))
    rel = max(1.0, total_vol / tile_vol)
    # fragmentation_factor 越大，说明 tile 越碎；幂次取小，避免单项压垮原模型。
    fragmentation_factor = min(3.5, rel ** 0.18)
    if getattr(c, "reduce_tile_policy", "full_k") == "half_k":
        fragmentation_factor *= 1.08
    if getattr(c, "tail_strategy", "mask_or_pad") == "peel":
        fragmentation_factor *= 1.04
    elif getattr(c, "tail_strategy", "mask_or_pad") == "pad":
        fragmentation_factor *= 1.02
    if getattr(c, "double_buffer", False):
        fragmentation_factor *= 1.03  # buffer selector / ping-pong index 管理开销
    if int(getattr(c, "cv_pipeline_stage", 1)) > 1:
        fragmentation_factor *= 1.04  # stage 编排开销
    # 将全局结构计数压成 per-tile 开销代理；保守封顶，防止一个样例把所有 cost 拉爆。
    advanced = raw.get("advanced_mlir_features", {}) if isinstance(raw.get("advanced_mlir_features", {}), dict) else {}
    loop_weighted = advanced.get("loop_weighted", {}) if isinstance(advanced.get("loop_weighted", {}), dict) else {}
    lw_counts = loop_weighted.get("loop_weighted_counts_by_component", {}) if isinstance(loop_weighted.get("loop_weighted_counts_by_component", {}), dict) else {}
    loop_scalar_ops = float(lw_counts.get("scalar", 0.0) or 0.0)
    inner_sync = float(loop_weighted.get("inner_loop_sync_count", 0.0) or 0.0)
    structural_ops = scalar_score + 0.25 * sync_score + 0.18 * loop_scalar_ops + 0.35 * inner_sync
    base_per_tile = 6.0 + min(240.0, 0.045 * structural_ops)
    per_tile = base_per_tile * scalar_mult * small_tile_scale * loop_weighted_scalar_multiplier * alignment_penalty_scale * fragmentation_factor
    # 对只有少量 scalar 证据的 kernel 不引入明显扰动。
    if structural_ops < 20:
        per_tile *= 0.25
    detail = {
        "enabled": True,
        "source": kernel_profile.get("source"),
        "kernel_type": kernel_profile.get("kernel_type"),
        "scalar_score": scalar_score,
        "sync_score_for_scalar_term": sync_score,
        "scalar_family_counts": scalar_counts,
        "scalar_control_multiplier": scalar_mult,
        "small_tile_scalar_penalty_scale": small_tile_scale,
        "loop_weighted_scalar_multiplier": loop_weighted_scalar_multiplier,
        "alignment_penalty_scale": alignment_penalty_scale,
        "loop_weighted_scalar_ops": float(loop_scalar_ops),
        "inner_loop_sync_count": float(inner_sync),
        "fragmentation_factor": float(fragmentation_factor),
        "base_per_tile_cycles": float(base_per_tile),
        "per_tile_scalar_control_cycles": float(per_tile),
        "uses_profiling_target": False,
    }
    return float(per_tile), detail


def pressure_adjust_overlap(load_overlap: float, store_overlap: float, cv_overlap: float, scope_utilization: Dict[str, Any], hw: Dict[str, Any]) -> Tuple[float, float, float, float]:
    """根据内存压力降低可重叠比例，防止高压力场景下 overlap 估计过于激进。"""
    cfg = conservative_cost_safety(hw)
    if not cfg.get("enabled", True):
        return load_overlap, store_overlap, cv_overlap, 1.0
    u = max(float((scope_utilization or {}).get("ub", 0.0) or 0.0), float((scope_utilization or {}).get("l0b", 0.0) or 0.0))
    th = float(cfg.get("overlap_pressure_threshold", 0.75))
    slope = float(cfg.get("overlap_pressure_slope", 0.35))
    factor = max(0.70, 1.0 - slope * max(0.0, u - th) / max(1e-6, 1.0 - th))
    return load_overlap * factor, store_overlap * factor, cv_overlap * factor, float(factor)

def estimate_cost(c: StrategyConfig, kf: KernelFeatures, hw: Dict[str, Any], max_live: Dict[str, int], search: Dict[str, Any]) -> Dict[str, float]:
    """完整 analytical cost model：汇总 pipe 时间、overlap、penalty、安全系数和 breakdown。"""
    c = _strategy_template_fields(c)
    plans = build_four_plan_bundle(c, kf, hw, max_live, search)
    p = plans["tiling_plan"]["derived_features"]
    mb = plans["multibuffer_plan"]["derived_features"]
    cv = plans["cv_pipeline_plan"]["derived_features"]
    sy = plans["sync_plan"]["derived_features"]
    risk_cfg = cost_risk_settings(hw, search)
    sync_legality_status = ((plans.get("sync_plan") or {}).get("legality") or {}).get("status")
    cv_legality_status = ((plans.get("cv_pipeline_plan") or {}).get("legality") or {}).get("status")
    times = base_pipe_times(c, kf, hw, search)
    load_time, store_time = times["load"], times["store"]
    cube_time, vector_time, fix_time = times["cube"], times["vector"], times["fix"]

    artifact = get_artifact(search)
    des = artifact.get("des_evidence", {}) if isinstance(artifact, dict) else {}
    pipe_frac = des.get("pipe_fraction", {}) if isinstance(des, dict) else {}
    kernel_profile = search.get("kernel_cost_profile", {}) if isinstance(search.get("kernel_cost_profile", {}), dict) else {}
    kp_weights = kernel_profile.get("weights", {}) if isinstance(kernel_profile.get("weights", {}), dict) else {}
    # MLIR + 产物结构 profile：修正各分项 cycles 的基础估计；不使用 profiling target / DES makespan。
    memory_cycle_correction = float(kp_weights.get("memory_cycle_correction", kp_weights.get("memory_multiplier", 1.0)) or 1.0)
    compute_cycle_correction = float(kp_weights.get("compute_cycle_correction", kp_weights.get("compute_multiplier", 1.0)) or 1.0)
    vector_cycle_correction = float(kp_weights.get("vector_cycle_correction", kp_weights.get("vector_multiplier", 1.0)) or 1.0)
    sync_cycle_correction = float(kp_weights.get("sync_cycle_correction", kp_weights.get("sync_multiplier", 1.0)) or 1.0)
    overlap_confidence = float(kp_weights.get("overlap_confidence", kp_weights.get("overlap_reward_scale", 1.0)) or 1.0)
    cv_overlap_confidence = float(kp_weights.get("cv_overlap_confidence", kp_weights.get("cv_reward_scale", 1.0)) or 1.0)
    memory_path_cycle_correction = float(kp_weights.get("memory_path_cycle_correction", kp_weights.get("memory_path_multiplier", 1.0)) or 1.0)
    alignment_cycle_correction = float(kp_weights.get("alignment_cycle_correction", kp_weights.get("alignment_penalty_scale", 1.0)) or 1.0)
    workspace_pressure_correction = float(kp_weights.get("workspace_pressure_correction", kp_weights.get("buffer_pressure_scale", 1.0)) or 1.0)
    cv_pattern_opportunity_correction = float(kp_weights.get("cv_pattern_opportunity_correction", kp_weights.get("cv_pattern_opportunity_scale", 1.0)) or 1.0)

    load_time *= memory_cycle_correction * memory_path_cycle_correction
    store_time *= memory_cycle_correction * memory_path_cycle_correction
    fix_time *= memory_cycle_correction * alignment_cycle_correction
    cube_time *= compute_cycle_correction
    vector_time *= vector_cycle_correction * alignment_cycle_correction

    # DES/product pipe_fraction 只作为编译产物结构证据；不做 makespan 校准。
    # overlap 的主因仍来自 candidate strategy；结构证据只给窄范围 confidence 修正。
    mte_pressure = float(pipe_frac.get("mte2", 0.0)) + float(pipe_frac.get("mte3", 0.0)) + float(pipe_frac.get("mte", 0.0))
    vector_pressure = float(pipe_frac.get("vector", 0.0))
    cube_pressure = float(pipe_frac.get("cube", 0.0))
    load_overlap_ratio = float(mb.get("load_overlap_ratio", 0.0)) * max(0.85, 1.0 - 0.10 * mte_pressure) * overlap_confidence
    store_overlap_ratio = float(mb.get("store_overlap_ratio", 0.0)) * max(0.85, 1.0 - 0.08 * mte_pressure) * overlap_confidence
    cv_overlap = float(cv.get("cv_overlap_ratio", 0.0)) * cv_overlap_confidence * cv_pattern_opportunity_correction
    if vector_pressure or cube_pressure:
        balance = min(max(vector_pressure, 1e-6), max(cube_pressure, 1e-6)) / max(max(vector_pressure, 1e-6), max(cube_pressure, 1e-6))
        cv_overlap *= (0.75 + 0.25 * balance)
    raw_cv_overlap_before_risk = float(cv_overlap)
    cv_estimated_overlap_multiplier = 1.0
    if c.cv_pipeline_stage > 1 and cv_legality_status == "PASS_ESTIMATED":
        cv_estimated_overlap_multiplier = float(risk_cfg.get("cv_estimated_overlap_multiplier", 1.0))
        cv_overlap *= cv_estimated_overlap_multiplier
    load_overlap_ratio, store_overlap_ratio, cv_overlap, overlap_pressure_factor = pressure_adjust_overlap(
        load_overlap_ratio, store_overlap_ratio, cv_overlap, mb.get("scope_utilization") or {}, hw
    )
    load_exposed = load_time * (1.0 - load_overlap_ratio)
    store_exposed = store_time * (1.0 - store_overlap_ratio)
    cube_vector = cube_time + vector_time - cv_overlap * min(cube_time, vector_time) + fix_time
    workspace_exposed, workspace_detail = workspace_transfer_time(c, kf, hw, search)
    workspace_exposed *= workspace_pressure_correction
    # GM workspace read/write 复用 MTE2/MTE3，不是独立 pipeline。真实编译中它更像
    # spill/fallback traffic：即使主 load/store 能被双缓冲掩盖，workspace 额外流量
    # 仍需作为暴露代价叠加，而不是只进入 max() 被完全隐藏。
    warmup_drain = (load_time + store_time + cube_vector + workspace_exposed) * float(cv.get("warmup_drain_factor", 0.0))
    # 模板类参数产生的轻量调度开销：多缓冲 slot 管理、CV stage 编排、mix imbalance 等。
    mb_template_overhead = (load_time + store_time) * float(mb.get("template_schedule_overhead_ratio", 0.0))
    cv_template_overhead = cube_vector * float(cv.get("template_schedule_overhead_ratio", 0.0))
    tile_mix_penalty_cycles = cube_vector * float(cv.get("tile_mix_balance_penalty", 0.0))
    producer_consumer_penalty_cycles = cube_vector * float(cv.get("producer_consumer_distance_penalty", 0.0))
    template_schedule_overhead = mb_template_overhead + cv_template_overhead + tile_mix_penalty_cycles + producer_consumer_penalty_cycles
    scalar_control_time, scalar_control_detail = estimate_scalar_control_time(c, kf, search, kernel_profile)

    if c.double_buffer or c.cv_pipeline_stage > 1:
        steady_tile_time = max(load_exposed, cube_vector, store_exposed) + workspace_exposed + warmup_drain + template_schedule_overhead + scalar_control_time
    else:
        steady_tile_time = load_time + cube_vector + store_time + workspace_exposed + template_schedule_overhead + scalar_control_time

    raw_sync_ops = float(sy.get("raw_sync_ops", 0.0))
    n_barrier = float(sy.get("num_barrier_estimated", 0.0))
    n_set = float(sy.get("num_set_flag_estimated", 0.0))
    n_wait = float(sy.get("num_wait_flag_estimated", 0.0))
    barrier_cost = hw.get("calibration", {}).get("pipe_barrier", {}).get("cycles_per_inner_iteration", 7500)
    des_sync_ops = sy.get("artifact_des_sync_ops")
    sync_scale = 1.0
    if des_sync_ops is not None and raw_sync_ops > 0:
        sync_scale = max(0.5, min(6.0, float(des_sync_ops) / max(1.0, raw_sync_ops)))
    sync_cost = (n_barrier * min(150.0, barrier_cost / 50.0) + (n_set + n_wait) * 8.0) * float(sy.get("stall_factor", 1.0)) * sync_scale * sync_cycle_correction
    sync_cost += float(sy.get("template_fixed_overhead_cycles", 0.0))

    # 第一阶段改造：没有 profiling/sidecar 时，对未验证合法性的收益显式降权。
    # 这不是硬件实测校准，而是防止 GraphSyncSolver/CVPipeline 在 demo 中过度乐观。
    sync_unknown_penalty = 0.0
    event_reuse_penalty = 0.0
    if c.sync_policy == "graph_sync_solver" and sync_legality_status == "UNKNOWN":
        sync_unknown_penalty = (
            raw_sync_ops * float(risk_cfg.get("sync_unknown_penalty_per_op", 0.0))
            + sync_cost * float(risk_cfg.get("sync_unknown_penalty_ratio", 0.0))
        )
    if c.event_reuse and sync_legality_status == "UNKNOWN":
        event_reuse_penalty = raw_sync_ops * float(risk_cfg.get("event_reuse_penalty_per_op", 0.0))
    cv_estimated_penalty = 0.0
    if c.cv_pipeline_stage > 1 and cv_legality_status == "PASS_ESTIMATED":
        cv_estimated_penalty = (cube_time + vector_time) * float(risk_cfg.get("cv_estimated_penalty_ratio", 0.0))
    legality_risk_penalty = float(sync_unknown_penalty + event_reuse_penalty + cv_estimated_penalty)

    # 容量压力在未溢出时只是软惩罚；真正的 overflow 由 feasibility 处理。
    pressure_penalty, pressure_detail = memory_pressure_penalty(mb.get("scope_utilization") or {}, hw)
    shape_penalty, shape_penalty_detail = shape_regularization_penalty(c, kf, hw, search)

    n_tiles = float(p.get("num_tiles", 1))
    max_cores = get_available_cores(kf, hw)
    active_blocks = max(1, min(int(c.block_dim), int(max_cores), int(math.ceil(n_tiles))))
    waves = int(math.ceil(n_tiles / active_blocks))
    tail_efficiency = n_tiles / max(1.0, waves * active_blocks)
    tail_efficiency = max(0.20, min(1.0, tail_efficiency))
    effective_parallelism = max(1.0, active_blocks * tail_efficiency)

    parallelized_tile_cycles = n_tiles * steady_tile_time / effective_parallelism
    total_cycles = parallelized_tile_cycles + sync_cost + pressure_penalty + shape_penalty + legality_risk_penalty
    risk_assessment = compute_risk_assessment(c, plans, max_live, hw, search)
    overlap_savings = {
        "load_overlap_saving": float(load_time * load_overlap_ratio),
        "store_overlap_saving": float(store_time * store_overlap_ratio),
        "cv_overlap_saving": float(cv_overlap * min(cube_time, vector_time)),
        "raw_cv_overlap_before_risk": float(raw_cv_overlap_before_risk),
        "cv_estimated_overlap_multiplier": float(cv_estimated_overlap_multiplier),
    }
    improvement_attribution = {
        "note": "Attribution is analytical decomposition, not measured speedup attribution.",
        "positive_cost_components_cycles": {
            "parallelized_tile_cycles": float(parallelized_tile_cycles),
            "sync_cost": float(sync_cost),
            "memory_pressure_penalty": float(pressure_penalty),
            "shape_regularization_penalty": float(shape_penalty),
            "legality_risk_penalty": float(legality_risk_penalty),
        },
        "optimistic_savings_proxies_per_tile": overlap_savings,
        "risk_adjustments_cycles": {
            "sync_unknown_penalty": float(sync_unknown_penalty),
            "event_reuse_penalty": float(event_reuse_penalty),
            "cv_estimated_penalty": float(cv_estimated_penalty),
        },
    }
    return {
        "cost_model_version": "V3.3.1-structure-aware-cycle-corrections",
        "cost_risk_mode": risk_cfg.get("mode", "conservative"),
        "risk_assessment": risk_assessment,
        "risk_level": risk_assessment.get("risk_level"),
        "n_tiles": n_tiles,
        "tau_load": float(load_time),
        "tau_store": float(store_time),
        "tau_cube": float(cube_time),
        "tau_vector": float(vector_time),
        "tau_fix": float(fix_time),
        "des_assisted": bool(des.get("available")) if isinstance(des, dict) else False,
        "artifact_critical_pipe": des.get("critical_pipe") if isinstance(des, dict) else None,
        "artifact_pipe_fraction_vector": float(pipe_frac.get("vector", 0.0)) if isinstance(pipe_frac, dict) else 0.0,
        "artifact_pipe_fraction_cube": float(pipe_frac.get("cube", 0.0)) if isinstance(pipe_frac, dict) else 0.0,
        "artifact_pipe_fraction_mte": float(mte_pressure),
        "kernel_cost_profile_enabled": bool(kernel_profile.get("enabled")) if isinstance(kernel_profile, dict) else False,
        "kernel_cost_profile_type": kernel_profile.get("kernel_type") if isinstance(kernel_profile, dict) else None,
        "kernel_cost_profile_dominant_component": kernel_profile.get("dominant_component") if isinstance(kernel_profile, dict) else None,
        "kernel_cost_profile_ratios": kernel_profile.get("ratios", {}) if isinstance(kernel_profile, dict) else {},
        "kernel_cost_profile_weights": kp_weights,
        "sync_scale_from_des": float(sync_scale),
        "sync_multiplier_from_kernel_profile": float(sync_cycle_correction),
        "sync_cycle_correction": float(sync_cycle_correction),
        "memory_path_multiplier": float(memory_path_cycle_correction),
        "memory_cycle_correction": float(memory_cycle_correction),
        "memory_path_cycle_correction": float(memory_path_cycle_correction),
        "sync_criticality_multiplier": 1.0,
        "alignment_penalty_scale": float(alignment_cycle_correction),
        "compute_cycle_correction": float(compute_cycle_correction),
        "vector_cycle_correction": float(vector_cycle_correction),
        "alignment_cycle_correction": float(alignment_cycle_correction),
        "buffer_pressure_scale": float(workspace_pressure_correction),
        "workspace_pressure_correction": float(workspace_pressure_correction),
        "cv_pattern_opportunity_scale": float(cv_pattern_opportunity_correction),
        "overlap_confidence": float(overlap_confidence),
        "cv_overlap_confidence": float(cv_overlap_confidence),
        "cv_pattern_opportunity_correction": float(cv_pattern_opportunity_correction),
        "load_exposed": float(load_exposed),
        "store_exposed": float(store_exposed),
        "workspace_exposed": float(workspace_exposed),
        "workspace_detail": workspace_detail,
        "cube_vector_time": float(cube_vector),
        "steady_tile_time": float(steady_tile_time),
        "tile_time": float(steady_tile_time),
        "compute_time": float(cube_vector),
        "sync_cost": float(sync_cost),
        "template_schedule_overhead": float(template_schedule_overhead),
        "scalar_control_time": float(scalar_control_time),
        "scalar_control_detail": scalar_control_detail,
        "memory_pressure_penalty": float(pressure_penalty),
        "shape_regularization_penalty": float(shape_penalty),
        "pressure_penalty_detail": pressure_detail,
        "shape_penalty_detail": shape_penalty_detail,
        "legality_risk_penalty": float(legality_risk_penalty),
        "sync_unknown_penalty": float(sync_unknown_penalty),
        "event_reuse_penalty": float(event_reuse_penalty),
        "cv_estimated_penalty": float(cv_estimated_penalty),
        "improvement_attribution": improvement_attribution,
        "overlap_pressure_factor": float(overlap_pressure_factor),
        "cv_estimated_overlap_multiplier": float(cv_estimated_overlap_multiplier),
        "max_cores": float(max_cores),
        "active_blocks": float(active_blocks),
        "waves": float(waves),
        "tail_efficiency": float(tail_efficiency),
        "effective_parallelism": float(effective_parallelism),
        "parallel_eff": float(effective_parallelism / max(1.0, float(max_cores))),
        "cost_breakdown": {
            "warmup_drain": float(warmup_drain),
            "per_tile_load_exposed": float(load_exposed),
            "per_tile_store_exposed": float(store_exposed),
            "per_tile_workspace_exposed": float(workspace_exposed),
            "gm_workspace_bytes": float(workspace_detail.get("workspace_bytes", 0) if isinstance(workspace_detail, dict) else 0),
            "gm_workspace_bytes_per_tile_total": float(workspace_detail.get("bytes_per_tile_total", 0) if isinstance(workspace_detail, dict) else 0),
            "workspace_detail": workspace_detail,
            "per_tile_cube_vector_pipeline": float(cube_vector),
            "per_tile_steady": float(steady_tile_time),
            "template_schedule_overhead": float(template_schedule_overhead),
            "scalar_control_time": float(scalar_control_time),
            "scalar_control_detail": scalar_control_detail,
            "kernel_cost_profile": kernel_profile,
            "mb_template_overhead": float(mb_template_overhead),
            "cv_template_overhead": float(cv_template_overhead),
            "tile_mix_penalty_cycles": float(tile_mix_penalty_cycles),
            "producer_consumer_penalty_cycles": float(producer_consumer_penalty_cycles),
            "parallelized_tile_cycles": float(parallelized_tile_cycles),
            "sync_cost": float(sync_cost),
            "legality_risk_penalty": float(legality_risk_penalty),
            "sync_unknown_penalty": float(sync_unknown_penalty),
            "event_reuse_penalty": float(event_reuse_penalty),
            "cv_estimated_penalty": float(cv_estimated_penalty),
            "improvement_attribution": improvement_attribution,
            "risk_assessment": risk_assessment,
            "cost_risk_mode": risk_cfg.get("mode", "conservative"),
            "memory_pressure_penalty": float(pressure_penalty),
            "shape_regularization_penalty": float(shape_penalty),
            "pressure_penalty_detail": pressure_detail,
            "shape_penalty_detail": shape_penalty_detail,
            "overlap_pressure_factor": float(overlap_pressure_factor),
            "tail_efficiency": float(tail_efficiency),
        },
        "predicted_cycles": float(total_cycles),
    }


# ------------------------------ cost model ------------------------------

def reason_for_candidate(c: StrategyConfig, cost: Dict[str, float], ml: Dict[str, int], hw: Dict[str, Any]) -> List[str]:
    """为候选策略生成中文解释，说明其主要收益来源和潜在风险。"""
    reasons = []
    reasons.append("Layered search selected this StrategyConfig after L1 tiling/fusion pruning, L2 overlap allocation, and L3 refinement.")
    if c.double_buffer:
        reasons.append("m=double_buffer enables the document-3 overlap model: serial load+compute+store moves toward max(load, compute, store).")
    if c.cv_pipeline_stage > 1:
        reasons.append(f"s={c.cv_pipeline_stage} models CV soft-pipeline overlap; r={c.cv_split_ratio} balances Cube/Vector chunks.")
    if c.sync_policy == "graph_sync_solver":
        reasons.append("y=graph_sync_solver uses a lower analytical sync-cost proxy than keep_existing/inject-style sync.")
    if c.dma_policy == "prefetch_nd2nz":
        reasons.append("d=prefetch_nd2nz reduces exposed ND2NZ/CubeMTE2 transfer cost in the analytical proxy.")
    if c.fusion != "keep_existing":
        reasons.append("f=fusion reduces vector chain/startup cost in the analytical proxy.")
    ub_cap = memory_cap_bytes(hw, "ub") / 1024
    reasons.append(f"PlanMemory-style estimated maxLive_UB={ml['ub']/1024:.2f} KB within {ub_cap:.2f} KB capacity.")
    reasons.append(f"Predicted tile_time={cost['tile_time']:.2f} cycles, n_tiles={int(cost['n_tiles'])}.")
    return reasons


# ---------------------------------------------------------------------------
# Current IR 状态恢复
# ---------------------------------------------------------------------------
# 旧版本报告使用 baseline-like 候选作为优化前参考。
# 这会导致 optimized/target IR 输入后仍显示虚高 speedup。
# 下面这一组函数改为从输入 IR 当前文本中恢复已有优化状态，
# 并用同一个 cost model 估算 current_ir_estimated_predicted_cycles。
def _read_kernel_text(path: str) -> str:
    """读取输入 kernel 文本，缺失时返回空字符串。"""
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _has_current_multibuffer(text: str) -> bool:
    """从当前输入 IR 文本判断是否已经存在 multibuffer/ping-pong 迹象。"""
    return bool(
        re.search(r"\bmulti_buffer\s*=\s*[2-9]", text)
        or re.search(r"hivm\.multi_buffer\s*=\s*[2-9]", text)
        or (re.search(r"\bping\b|_ping\b", text, re.I) and re.search(r"\bpong\b|_pong\b", text, re.I))
    )


def _has_current_cv_pipeline(text: str) -> bool:
    """从当前输入 IR 文本判断是否已经存在 Cube/Vector pipeline 迹象。"""
    return bool(
        ("cube_loop" in text and "vector_loop" in text)
        or "hivm.part_of_mix" in text
        or re.search(r"cv[_-]?pipeline", text, re.I)
    )


def _sync_attr_from_text(text: str) -> str:
    """根据当前输入 IR 的同步算子数量推断同步策略。"""
    m = re.search(r'hivm\.sync\s*=\s*"([^"}]+)"', text)
    return m.group(1) if m else "unknown"


def _aligned_current_dim(value: Any, total: int, align: int, default: int) -> int:
    """将当前 IR 推断出的 tile 维度对齐并限制在候选取值范围内。"""
    try:
        v = int(value)
    except Exception:
        v = 0
    if v <= 0:
        v = min(max(align, int(default)), max(align, int(total)))
    if v % align != 0:
        v = _align(v, align)
    return max(align, int(v))


def infer_current_ir_strategy(kernel_path: str, kf: KernelFeatures, hw: Dict[str, Any], search: Dict[str, Any]) -> StrategyConfig:
    """从输入 IR 的可见结构恢复 current_ir_estimated_strategy，作为当前 IR 状态近似。"""
    text = _read_kernel_text(kernel_path)
    pshape = problem_shape(search, kf)
    cm, cn, ck = cube_tile(hw)
    m_total = int(pshape.get("m_total", kf.inferred_problem_shape.get("m_total", 64)) or 64)
    n_total = int(pshape.get("n_total", kf.inferred_problem_shape.get("n_total", 128)) or 128)
    k_total = int(pshape.get("k_total", kf.inferred_problem_shape.get("k_total", 128)) or 128)
    tile_m = _aligned_current_dim(pshape.get("extracted_tile_m", 0), m_total, cm, min(m_total, 64))
    tile_n = _aligned_current_dim(pshape.get("extracted_tile_n", 0), n_total, cn, min(n_total, 128))
    tile_k = _aligned_current_dim(pshape.get("extracted_tile_k", 0), k_total, ck, min(k_total, 128))
    cur_tile = {"m": tile_m, "n": tile_n, "k": tile_k}
    n_tiles = estimate_num_tiles_for_tile(kf, search, cur_tile)
    block_dim = select_default_block_dim_for_tile(n_tiles, get_available_cores(kf, hw))

    double_buffer = _has_current_multibuffer(text)
    cv_stage = 2 if _has_current_cv_pipeline(text) else 1
    mb_template = "M0_no_multibuffer"
    if double_buffer and cv_stage > 1:
        mb_template = "M4_cv_stage_aware_multibuffer"
    elif double_buffer:
        mb_template = "M1_input_double_buffer"
    cv_template = "P2_stage2_balanced" if cv_stage > 1 else "P0_no_cv_pipeline"

    return StrategyConfig(
        strategy_id="current_ir_estimated",
        fusion="keep_existing",
        tile_m=tile_m, tile_n=tile_n, tile_k=tile_k,
        block_dim=block_dim,
        double_buffer=double_buffer,
        cv_pipeline_stage=cv_stage,
        cv_split_ratio="1:1",
        memory_reuse_level="level1",
        sync_policy="keep_existing",
        dma_policy="keep_existing",
        loop_order="outer_mnk",
        tail_strategy="mask_or_pad",
        multibuffer_template=mb_template,
        cv_pipeline_template=cv_template,
        sync_template="Y0_keep_existing",
        enable_mixed_cv=False,
        tile_mix_cube_loop=1,
        tile_mix_vector_loop=1,
        auto_cv_balance=True,
        barrier_level="medium",
        event_reuse=False,
        sync_granularity="op",
        reduce_tile_policy="full_k",
        layout_aware_tile=True,
        ub_multiplier=1,
        l1_multiplier=1,
        stage_buffer_policy="none",
        buffer_multipliers_json="{}",
        producer_consumer_distance=1,
        event_id_policy="keep",
        sync_motion="none",
    )


def build_current_ir_estimate(kernel_path: str, kf: KernelFeatures, hw: Dict[str, Any], search: Dict[str, Any]) -> Dict[str, Any]:
    """计算当前 IR 估计策略的 cost、feasibility 和硬件边界占用。"""
    c = _strategy_template_fields(infer_current_ir_strategy(kernel_path, kf, hw, search))
    ml = estimate_max_live(c, kf, hw)
    ok, reason, detail = feasibility(c, ml, hw)
    cost = estimate_cost(c, kf, hw, ml, search)
    text = _read_kernel_text(kernel_path)
    return {
        "strategy": asdict(c),
        "max_live_bytes": ml,
        "cost": cost,
        "feasible": ok,
        "feasibility_reason": reason,
        "feasibility_detail": detail,
        "meta": {
            "type": "current_ir_estimated",
            "note": "Input-aware analytical estimate recovered from visible IR features; not measured hardware time.",
            "recovered_features": {
                "multi_buffer_detected": _has_current_multibuffer(text),
                "cv_pipeline_detected": _has_current_cv_pipeline(text),
                "sync_attr": _sync_attr_from_text(text),
                "explicit_sync_ops": {
                    "pipe_barrier": kf.num_pipe_barrier,
                    "set_flag": kf.num_set_flag,
                    "wait_flag": kf.num_wait_flag,
                    "sync_block_set": kf.num_sync_block_set,
                    "sync_block_wait": kf.num_sync_block_wait,
                },
            },
        },
    }


# ---------------------------------------------------------------------------
# 报告生成
# ---------------------------------------------------------------------------
# 报告会同时输出 JSON sidecars、中文 Markdown 和中文 HTML。
# HTML/Markdown 中的“当前输入 IR”指 current_ir_estimated_strategy，
# “最优候选”指搜索空间内 predicted_cycles 最低的 legal strategy。
# ------------------------------ 报告生成 ------------------------------


# Report writers live in strategy_search.report.
from .report import write_html_report, write_markdown_report


# Rewrite emitters live in strategy_search.rewrite.
from .rewrite import emit_strategy_rewrite_outputs, _split_paths
from .des_profile import (
    load_des_profile_summary,
    summarize_des_trace,
    build_single_trace_calibration,
    apply_single_trace_calibration_to_cost,
    write_des_profile_summary,
)



def _load_des_calibration_summaries(args: argparse.Namespace, des_paths: List[str]) -> List[Any]:
    """读取可选 artifact DES summary，用于 legacy/offline calibration；V3.3 主路线默认关闭。"""
    summaries: List[Any] = []
    for path in _split_csv_paths(getattr(args, "artifact_des_summary", None) or getattr(args, "des_profile_summary", None)):
        if Path(path).exists():
            summaries.append(load_des_profile_summary(path))
    # 如果用户没有显式提供 summary，但开启了 legacy calibration，则允许直接从 artifact DES graph raw JSON 构建一次 summary。
    if not summaries and getattr(args, "des_calibration_mode", "off") != "off":
        for path in des_paths:
            if Path(path).exists():
                summaries.append(summarize_des_trace(path, mlir_file=getattr(args, "kernel", "")))
    return summaries


def _write_des_calibration_sidecars(out: Path, summaries: List[Any], calibration: Dict[str, Any]) -> None:
    """输出 DES summary 和 calibration report，方便审计与后续复用。"""
    if summaries:
        write_json(out / "des_profile_summaries.json", [s.to_dict() if hasattr(s, "to_dict") else asdict(s) for s in summaries])
        # 单样本时额外输出一个固定文件名，后续可直接 --artifact-des-summary 复用。
        if len(summaries) == 1:
            write_des_profile_summary(summaries[0], out / "des_profile_summary.json")
    write_json(out / "cost_calibration_report.json", calibration or {"enabled": False, "reason": "DES calibration disabled or unavailable"})

def run(args: argparse.Namespace) -> None:
    """执行完整寻优流程：解析输入、构建搜索空间、搜索候选、输出报告和 JSON。"""
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    kf = parse_kernel_features(args.kernel)
    hw = apply_cost_model_config(load_json(args.hardware_config), getattr(args, "cost_model_config", None), getattr(args, "cost_risk_mode", "conservative"))
    des_paths = _split_csv_paths(getattr(args, "artifact_des_graph", None) or getattr(args, "des_profile", None) or getattr(args, "desgraph", None))
    trace_paths = _split_csv_paths(getattr(args, "artifact_trace", None) or getattr(args, "trace_profile", None) or getattr(args, "trace", None))
    deprecated_source_paths = _split_csv_paths(getattr(args, "source", None))
    if deprecated_source_paths:
        print("Warning: --source is deprecated and ignored in V3.3; Python/Triton source is not parsed as structured input. Use --artifact-des-graph/--artifact-trace JSON inputs.")
    artifact_profile = build_artifact_profile(
        args.kernel,
        des_paths,
        trace_paths,
        deprecated_source_paths=deprecated_source_paths,
    )
    des_calibration_summaries = _load_des_calibration_summaries(args, des_paths)

    auto_search = auto_generate_search_space(kf, hw, getattr(args, "candidate_space", "standard"))
    # Diagnosis-guided mode is optional. Default mode remains pure strategy search without external diagnosis.
    guided_enabled = getattr(args, "guided_mode", "off") != "off"
    hints = build_diagnosis_hints(
        desgraph_paths=des_paths,
        bound_report_paths=_split_paths(getattr(args, "bound_report", None)),
        counterfactual_paths=_split_paths(getattr(args, "counterfactual", None)),
        multi_kernel_paths=_split_paths(getattr(args, "multi_kernel_report", None)),
        enabled=guided_enabled,
        mode=getattr(args, "guided_mode", "diagnosis"),
    )
    search = merge_search_space(auto_search, getattr(args, "search_space", None))
    # Rebuild dynamic block_dim bounds after any user override.
    # Diagnosis may prune tiles, then V2.7 converts block_dim into a derived
    # value for each remaining tiling plan.
    search = refresh_dynamic_candidate_space(search, kf, hw)
    search = apply_guided_search_adjustments(search, hints, getattr(args, "guided_strength", "soft"))
    search = refresh_dynamic_candidate_space(search, kf, hw)
    search = apply_v2_focus_space(search, kf, hw)

    # Stage2a stability preparation: for expanded/full searches, compute the
    # Layer-1 survivors of the standard space under the same post-override /
    # guided / focus pipeline, then pin those signatures in the denser search.
    # This keeps runtime bounded while guaranteeing the standard beam frontier is
    # not silently lost when the candidate space is made denser.
    requested_density = getattr(args, "candidate_space", "standard")
    if requested_density in {"expanded", "full"}:
        std_auto = auto_generate_search_space(kf, hw, "standard")
        std_search = merge_search_space(std_auto, getattr(args, "search_space", None))
        std_search = refresh_dynamic_candidate_space(std_search, kf, hw)
        std_search = apply_guided_search_adjustments(std_search, hints, getattr(args, "guided_strength", "soft"))
        std_search = refresh_dynamic_candidate_space(std_search, kf, hw)
        std_search = apply_v2_focus_space(std_search, kf, hw)
        std_l1, _std_rejected = search_tiling_fusion(kf, hw, std_search)
        search["standard_layer1_signatures_to_pin"] = [list(layer1_signature(x)) for x in std_l1]
        search["standard_layer1_kept_for_stability"] = len(std_l1)

    search["artifact_profile"] = asdict(artifact_profile)
    # 基于 MLIR + 编译产物文件生成 kernel-specific cost profile。
    # 它不读取 profiling target / DES makespan，只改变 analytical cost 的结构权重。
    search["kernel_cost_profile"] = build_kernel_cost_profile(
        kf,
        asdict(artifact_profile),
        enabled=kernel_profile_enabled(args),
    )
    search["des_calibration_mode"] = getattr(args, "des_calibration_mode", "off")
    search["des_profile_summaries"] = [s.to_dict() if hasattr(s, "to_dict") else asdict(s) for s in des_calibration_summaries]
    search["cost_risk_mode"] = getattr(args, "cost_risk_mode", "conservative")
    search["cost_model_config"] = getattr(args, "cost_model_config", None)
    search["enable_search_quality_audit"] = bool(getattr(args, "enable_search_quality_audit", False))
    search["search_quality_random_budget"] = int(getattr(args, "search_quality_random_budget", 128))
    search["search_quality_random_seed"] = int(getattr(args, "search_quality_random_seed", 42))

    write_json(out / "effective_search_space.json", search)
    write_json(out / "artifact_profile.json", asdict(artifact_profile))
    write_json(out / "kernel_cost_profile.json", search.get("kernel_cost_profile", {"enabled": False}))
    write_artifact_audits(out, asdict(artifact_profile), hw)
    write_json(out / "diagnosis_guidance_report.json", asdict(hints))
    write_json(out / "analysis_coverage_report.json", {
        "guided_mode": hints.mode,
        "source_files": hints.source_files,
        "coverage": hints.coverage,
        "unknown_signals": hints.unknown_signals,
        "note": "Coverage is for currently provided original-repo output files. Unknown future fields fall back to default search.",
    })

    search_mode = getattr(args, "search_mode", "layered")
    if search_mode == "exhaustive":
        layered_candidates, search_stats = build_exhaustive_candidates(kf, hw, search)
    else:
        layered_candidates, search_stats = build_layered_candidates(kf, hw, search)
    search_stats["guided_mode"] = hints.mode
    search_stats["requested_search_mode"] = search_mode
    search_stats["diagnosis_signals"] = hints.signals
    search_stats["diagnosis_variable_bias"] = hints.variable_bias
    search_stats["hardware_constraints_summary"] = search.get("hardware_constraints_summary", {})
    search_stats["search_space_size_estimate"] = search.get("search_space_size_estimate", estimate_search_space_size(search))
    search_audit = {
        "stage": "V3.3-artifact-kernel-profile",
        "candidate_space_density": getattr(args, "candidate_space", "standard"),
        "search_mode": search_mode,
        "standard_candidates_included": bool(search.get("standard_candidates_included", False)),
        "standard_tile_keys_count": len(search.get("standard_tile_keys", []) or []),
        "tile_candidates_count": len(search.get("tile_candidates", []) or []),
        "layer1_stability_audit": search_stats.get("layer1_stability_audit", {}),
        "candidate_dedup_audit": search_stats.get("candidate_dedup_audit", {}),
        "search_space_size_estimate": search_stats.get("search_space_size_estimate", {}),
        "note": "Stage2b adds diversity-preserving Layer-1 beam selection, standard survivor pinning, deterministic fallback retention, and exact strategy dedup by stable signature.",
    }
    legal: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    relaxed_success: List[Dict[str, Any]] = []

    for c, meta in layered_candidates:
        final_c, ml, trace, reason, detail = feasible_with_relax(c, kf, hw)
        if final_c is None:
            rejected.append({"strategy": asdict(c), "reason": reason, "max_live": detail, "relax_trace": trace, "meta": meta})
            continue
        final_c = _strategy_template_fields(final_c)
        cost = estimate_cost(final_c, kf, hw, ml, search)
        plans = build_four_plan_bundle(final_c, kf, hw, ml, search)
        # Diagnosis is used only to prune/shape the search space.
        # It is not used to change the optimization objective.
        # Final selection always minimizes predicted_cycles.
        _, diag_reasons = strategy_diagnosis_bias(final_c, hints)
        item = {"strategy": asdict(final_c), "max_live_bytes": ml, "cost": cost, "meta": meta, "relax_trace": trace, "diagnosis_reasons": diag_reasons}
        if plans is not None:
            item["plans"] = plans
        legal.append(item)
        if trace:
            relaxed_success.append(item)

    legal_before_dedup = len(legal)
    deduped_legal: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for item in legal:
        sig = strategy_signature(StrategyConfig(**item["strategy"]))
        prev = deduped_legal.get(sig)
        if prev is None or item["cost"]["predicted_cycles"] < prev["cost"]["predicted_cycles"]:
            deduped_legal[sig] = item
    legal = list(deduped_legal.values())
    search_stats["post_relax_legal_dedup_audit"] = {
        "input_legal_candidates": legal_before_dedup,
        "unique_legal_candidates": len(legal),
        "dedup_removed_after_relax": legal_before_dedup - len(legal),
        "dedup_key": "strategy_signature_without_strategy_id",
    }
    search_audit["post_relax_legal_dedup_audit"] = search_stats["post_relax_legal_dedup_audit"]
    search_audit["num_candidates_legal_after_relax"] = len(legal)
    search_audit["num_candidates_rejected_after_relax"] = len(rejected)

    if not legal:
        raise SystemExit("No legal candidates found. Please reduce search space or relax demo constraints.")

    # 先构建未校准的 current-IR analytical estimate；若提供 DES summary，
    # 再用 single-trace prior 对 current 和所有候选做同一尺度校准，并重新排序。
    current_ir = build_current_ir_estimate(args.kernel, kf, hw, search)
    cost_calibration: Dict[str, Any] = {"enabled": False, "mode": getattr(args, "des_calibration_mode", "off")}
    if getattr(args, "des_calibration_mode", "off") == "single_trace_prior" and des_calibration_summaries:
        cost_calibration = build_single_trace_calibration(
            des_calibration_summaries[0],
            float(current_ir["cost"].get("predicted_cycles", 0.0)),
            max_extra_overlap_gain=float(getattr(args, "des_calibration_overlap_extra", 0.15)),
        )
        current_ir["cost"] = apply_single_trace_calibration_to_cost(current_ir["cost"], cost_calibration)
        current_ir.setdefault("meta", {})["des_calibration"] = cost_calibration
        for item in legal:
            item["cost"] = apply_single_trace_calibration_to_cost(item["cost"], cost_calibration)
        search["des_cost_calibration"] = cost_calibration
    else:
        search["des_cost_calibration"] = cost_calibration

    # Strict optimization rule: final best candidate is always selected by predicted_cycles.
    # Diagnosis guidance is used only to prune/shape the search space.
    legal.sort(key=lambda x: x["cost"]["predicted_cycles"])
    top_k = int(search.get("top_k", 10))
    top = legal[:top_k]
    best = top[0]

    if bool(getattr(args, "enable_search_quality_audit", False)):
        search_quality = build_search_quality_audit(
            kf, hw, search,
            beam_best_cost=float(best["cost"].get("predicted_cycles", 0.0)),
            random_budget=int(getattr(args, "search_quality_random_budget", 128)),
            random_seed=int(getattr(args, "search_quality_random_seed", 42)),
        )
    else:
        search_quality = {"enabled": False, "note": "Pass --enable-search-quality-audit to run compact exhaustive/random baselines."}
    search_stats["search_quality_audit"] = search_quality
    search_audit["search_quality_audit"] = search_quality

    speedup = (current_ir["cost"]["predicted_cycles"] / best["cost"]["predicted_cycles"]) if (current_ir.get("feasible", True) and best["cost"]["predicted_cycles"]) else None

    selected = dict(best)
    selected["predicted_speedup_vs_current_ir_estimated"] = speedup
    selected["current_ir_estimated_reference"] = current_ir
    selected["reason"] = reason_for_candidate(StrategyConfig(**best["strategy"]), best["cost"], best["max_live_bytes"], hw)
    if guided_enabled:
        selected["reason"].append("Diagnosis-guided mode was enabled; diagnosis was used only for search-space pruning/narrowing. Final selection always minimizes predicted_cycles.")
        selected["reason"].extend(best.get("diagnosis_reasons", [])[:8])

    buffer_life_report = {
        "num_buffers": len(kf.buffers),
        "buffers": [asdict(b) for b in kf.buffers[:500]],
        "static_max_live_bytes": kf.static_max_live_bytes,
        "selected_max_live_bytes": best["max_live_bytes"],
        "selected_max_live_utilization": {
            s: (best["max_live_bytes"].get(s, 0) / memory_cap_bytes(hw, s) if memory_cap_bytes(hw, s) else None)
            for s in RESOURCE_SCOPES
        },
    }

    report = {
        "scope": "V3.0 vTriton-bridge strategy search demo; optional annotation/safe structural HIVM rewrite bundle is emitted when --enable-ir-rewrite is used",
        "input_kernel": os.path.abspath(args.kernel),
        "hardware_config": os.path.abspath(args.hardware_config),
        "search_space": os.path.abspath(args.search_space) if args.search_space else "AUTO_GENERATED",
        "model_version": "V3.3-artifact-kernel-profile",
        "guided_mode": hints.mode,
        "search_mode": getattr(args, "search_mode", "layered"),
        "candidate_space_density": getattr(args, "candidate_space", "standard"),
        "guided_strength": getattr(args, "guided_strength", "soft"),
        "cost_risk_mode": getattr(args, "cost_risk_mode", "conservative"),
        "cost_model_config": getattr(args, "cost_model_config", None),
        "des_calibration_mode": getattr(args, "des_calibration_mode", "off"),
        "des_cost_calibration": cost_calibration,
        "kernel_cost_profile": search.get("kernel_cost_profile", {"enabled": False}),
        "des_profile_summaries": [x.to_dict() if hasattr(x, "to_dict") else asdict(x) for x in des_calibration_summaries],
        "external_analysis_sources": hints.source_files,
        "kernel_features": asdict(kf),
        "effective_search_space_summary": {
            "candidate_generation": search.get("candidate_generation"),
            "hardware_constraints_summary": search.get("hardware_constraints_summary"),
            "search_space_size_estimate": search.get("search_space_size_estimate"),
            "tile_task_counts": search.get("tile_task_counts"),
            "tile_to_block_dim_candidates": search.get("tile_to_block_dim_candidates"),
        },
        "search_stats": search_stats,
        "search_audit": search_audit,
        "num_candidates_legal_after_relax": len(legal),
        "num_candidates_rejected_after_relax": len(rejected),
        "num_candidates_relaxed_successfully": len(relaxed_success),
        "current_ir_estimated_strategy": current_ir,
        "best_strategy_id": best["strategy"]["strategy_id"],
        "best_predicted_cycles": best["cost"]["predicted_cycles"],
        "current_ir_estimated_predicted_cycles": current_ir["cost"]["predicted_cycles"],
        "predicted_speedup_vs_current_ir_estimated": speedup,
        "top_k": top,
        "notes": [
            "Default mode remains diagnosis-independent layered search.",
            "Guided mode consumes original-repo outputs such as DES graph, bound report, counterfactual report, and multi-kernel report as search-space pruning/narrowing priors.",
            "Guidance strength controls behavior: soft keeps the guided search space broad; balanced reduces beams; aggressive prunes low-priority values with exploration fallbacks. Final selection always uses predicted_cycles.",
            "The demo keeps fusion/memory_reuse/cv_split_ratio/dma_policy fixed or derived, and searches TilingPlan, MultiBufferPlan, CVPipelinePlan, and SyncPlan knobs with generic HIVM structure evidence.",
            "Plan sidecars expose controllable knobs, derived cost features, legality status, and optional HIVM artifact evidence extracted from MLIR/DES/trace JSON inputs.",
            "Python/Triton source files are not parsed as input in V3.3; source-derived optimization ideas are captured only as manually reviewed built-in templates.",
            "Sample artifact values are never hard-coded as required inputs; optional JSON artifacts provide schema/evidence for plan parameterization, hardware-boundary audit, and artifact-assisted cost audit.",
            "Artifact kernel profile uses only MLIR/product structural evidence to adjust compute/memory/vector/scalar/sync weights; it does not use profiling target, DES makespan, or measured latency."
        ],
    }

    _write_des_calibration_sidecars(out, des_calibration_summaries, cost_calibration)
    write_json(out / "selected_strategy.json", selected)
    write_json(out / "cost_breakdown.json", {
        "selected_strategy_id": best["strategy"]["strategy_id"],
        "selected_cost_breakdown": best["cost"].get("cost_breakdown", {}),
        "top_cost_breakdowns": [
            {"strategy_id": x["strategy"]["strategy_id"], "predicted_cycles": x["cost"].get("predicted_cycles"), "cost_breakdown": x["cost"].get("cost_breakdown", {})}
            for x in top
        ],
    })
    if best.get("plans") is not None:
        write_json(out / "selected_plan.json", best["plans"])
        write_json(out / "top_plans.json", [{"strategy_id": x["strategy"]["strategy_id"], "predicted_cycles": x["cost"]["predicted_cycles"], "plans": x.get("plans")} for x in top])
    write_json(out / "top_candidates.json", top)
    write_json(out / "search_audit.json", search_audit)
    write_json(out / "layer1_rejected_candidates.json", search_stats.get("layer1_rejected_preview", []))
    write_json(out / "rejected_candidates.json", {"post_relax_rejected": rejected[:300], "layer1_rejected_preview": search_stats.get("layer1_rejected_preview", [])})
    write_json(out / "relaxed_candidates.json", relaxed_success[:300])
    write_json(out / "search_report.json", report)
    write_json(out / "buffer_life_report.json", buffer_life_report)
    write_markdown_report(out, args, kf, search_stats, legal, rejected, relaxed_success, selected, current_ir, speedup, top)
    write_html_report(out, args, kf, search_stats, legal, rejected, relaxed_success, selected, current_ir, speedup, top, hw)

    emit_strategy_rewrite_outputs(out, args, selected, des_paths, trace_paths)

    print(f"Generated document-3-aligned demo outputs in: {out}")
    speedup_msg = "N/A" if speedup is None else f"{speedup:.3f}x"
    print(f"Best strategy: {best['strategy']['strategy_id']} predicted_cycles={best['cost']['predicted_cycles']:.2f}, speedup_vs_current_ir={speedup_msg}")
    if guided_enabled:
        print(f"Guided mode: {hints.mode}, signals={len(hints.signals)}, bias={hints.variable_bias}")
    print(f"Layer1 kept={search_stats['layer1_kept']}, Layer3 candidates={search_stats['layer3_candidates']}, legal={len(legal)}, rejected={len(rejected)}, relaxed={len(relaxed_success)}")

def main() -> None:
    """命令行入口函数，负责解析参数并调用 run。"""
    ap = argparse.ArgumentParser(description="HIVM/AscendNPU-IR 四类 Plan 参数寻优 demo：TilingPlan, MultiBufferPlan, CVPipelinePlan, SyncPlan")
    ap.add_argument("--kernel", required=True, help="Path to HIVM/NPUIR MLIR kernel, e.g. .hivm.mlir or .npuir.mlir")
    ap.add_argument("--hardware-config", required=True, help="Path to hardware config JSON, e.g. configs/ascend_910b.json")
    ap.add_argument("--search-space", default=None, help="Optional search space JSON override. If omitted, search space is auto-generated.")
    ap.add_argument("--candidate-space", choices=["standard", "expanded", "full"], default="standard", help="Candidate-space density for auto generation. standard: representative fast space; expanded: denser hardware/kernel-aware grid; full: all aligned tile values in the demo discrete grid, potentially very large.")
    ap.add_argument("--guided-mode", choices=["off", "diagnosis"], default="off", help="off: pure search; diagnosis: use original-repo analysis outputs")
    ap.add_argument("--search-mode", choices=["layered", "exhaustive"], default="layered", help="layered: document-3 layered/beam search; exhaustive: enumerate a broader demo Cartesian subset; not a full four-plan oracle baseline")
    ap.add_argument("--enable-search-quality-audit", action="store_true", help="Run bounded Beam-vs-small-exhaustive and Beam-vs-random baseline audit on a compact subspace.")
    ap.add_argument("--search-quality-random-budget", type=int, default=128, help="Random baseline candidate budget used by --enable-search-quality-audit.")
    ap.add_argument("--search-quality-random-seed", type=int, default=42, help="Random seed used by --enable-search-quality-audit.")
    ap.add_argument("--guided-strength", choices=["soft", "balanced", "aggressive"], default="soft", help="soft: ranking bias only; balanced: reduce beams; aggressive: diagnosis-guided pruning for search efficiency")
    ap.add_argument("--cost-risk-mode", choices=["conservative", "balanced", "aggressive"], default="conservative", help="Risk-aware cost mode. conservative is recommended when no profiling data is available; aggressive keeps optimistic overlap/sync benefits.")
    ap.add_argument("--cost-model-config", default=None, help="Optional JSON config for cost_model_safety, cost_model_risk_modes, and cost_model_strategy_effects. See configs/cost_model_*.json.")
    ap.add_argument("--artifact-kernel-profile", choices=["on", "off"], default="on", help="on: derive kernel-specific cost weights from MLIR and MLIR-derived compiler/modeling artifacts only; no profiling target, DES makespan, or global scale is used.")
    ap.add_argument("--artifact-des-graph", default=None, help="Preferred V3.3 input: comma-separated MLIR-derived DES graph artifact JSON files, e.g. prefill_des.json. Used only as structural artifact evidence.")
    ap.add_argument("--artifact-trace", default=None, help="Preferred V3.3 input: comma-separated MLIR-derived Perfetto/Chrome trace artifact JSON files, e.g. prefill_trace.json. Used only as structural artifact evidence.")
    ap.add_argument("--artifact-des-summary", default=None, help="Optional prebuilt artifact DES summary JSON for legacy/offline experiments; not needed for the default V3.3 artifact-kernel-profile path.")
    ap.add_argument("--des-profile", default=None, help="Deprecated alias for --artifact-des-graph. The file is treated as a MLIR-derived artifact, not as profiling data.")
    ap.add_argument("--trace-profile", default=None, help="Deprecated alias for --artifact-trace. The file is treated as a MLIR-derived artifact, not as profiling data.")
    ap.add_argument("--des-profile-summary", default=None, help="Deprecated alias for --artifact-des-summary.")
    ap.add_argument("--des-calibration-mode", choices=["off", "single_trace_prior"], default="off", help="Legacy/offline experiment only. Keep off for V3.3 online search. single_trace_prior uses DES makespan/global scale and is not the default artifact-kernel-profile model.")
    ap.add_argument("--des-calibration-overlap-extra", type=float, default=0.15, help="Legacy calibration option used only when --des-calibration-mode=single_trace_prior.")
    ap.add_argument("--desgraph", default=None, help="Deprecated alias for --artifact-des-graph; kept for backward compatibility.")
    ap.add_argument("--trace", default=None, help="Deprecated alias for --artifact-trace; kept for backward compatibility.")
    ap.add_argument("--source", default=None, help="Deprecated and ignored. Python/Triton source is not parsed as structured input.")
    ap.add_argument("--bound-report", default=None, help="Optional comma-separated performance bound report JSON files from original repo")
    ap.add_argument("--counterfactual", default=None, help="Optional comma-separated counterfactual report JSON files")
    ap.add_argument("--multi-kernel-report", default=None, help="Optional comma-separated multi-kernel report JSON files")

    ap.add_argument("--vtriton-bindings", default=None, help="Optional vTriton tritonsim_hivm_bindings.jsonl sidecar(s), comma-separated. Recorded into candidate bundle.")
    ap.add_argument("--vtriton-compile-commands", default=None, help="Optional vTriton tritonsim_hivm_compile_commands.jsonl sidecar(s), comma-separated. Recorded into candidate bundle.")
    ap.add_argument("--enable-ir-rewrite", action="store_true", help="Emit V3.0 strategy-to-HIVM rewrite outputs: annotated IR, optional safe structural IR, pass config, edit script, vTriton bundle.")
    ap.add_argument("--rewrite-mode", choices=["annotation", "safe_structural", "both"], default="annotation", help="annotation: only strategy attrs; safe_structural: also conservative sync/buffer attr rewrite; both: emit both files.")
    ap.add_argument("--rewrite-safety", choices=["conservative", "aggressive"], default="conservative", help="conservative: do not delete sync ops; aggressive: may remove obvious pipe_barrier lines under GSS, still requires vTriton verification.")
    ap.add_argument("--output-dir", required=True, help="Directory to write selected_strategy/search_report outputs")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
