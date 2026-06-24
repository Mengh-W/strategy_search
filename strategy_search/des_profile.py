# -*- coding: utf-8 -*-
"""MLIR-derived DES artifact summary and legacy calibration helpers.

V3.3 treats DES graph JSON files such as prefill_des.json as compiler/modeling
artifacts generated from MLIR, not as real profiling data. The default online
cost model uses only structural fields from these artifacts. Helpers that use
DES makespan/global-scale calibration are kept only for legacy/offline experiments.

This module treats a DES JSON as one kernel/strategy-level sample.  The raw
``operations`` array may contain many operation records, but for cost-model
artifact-aware cost modeling we summarize it into a small, reusable structural
summary. The summary can be built offline once, then consumed by the strategy
search CLI without repeatedly scanning a large raw artifact graph.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


SUMMARY_SCHEMA_VERSION = "artifact_des_summary_v1"


@dataclass
class DESProfileSummary:
    """Kernel/strategy-level structural summary extracted from one MLIR-derived DES artifact graph."""

    schema_version: str = SUMMARY_SCHEMA_VERSION
    sample_id: str = ""
    mlir_file: str = ""
    des_trace_file: str = ""
    trace_schema_version: str = ""
    schedule_truncated: bool = False
    clock_ghz: float = 0.0
    num_ops: int = 0
    makespan_cycles: float = 0.0
    total_duration_cycles: float = 0.0
    total_weighted_duration_cycles: float = 0.0
    critical_path_cycles: float = 0.0
    observed_overlap_ratio: float = 0.0
    pipe_busy_cycles: Dict[str, float] = field(default_factory=dict)
    pipe_weighted_duration_cycles: Dict[str, float] = field(default_factory=dict)
    pipe_op_counts: Dict[str, int] = field(default_factory=dict)
    op_name_counts: Dict[str, int] = field(default_factory=dict)
    sync_count: int = 0
    barrier_count: int = 0
    event_count: int = 0
    dependency_edges: int = 0
    total_bytes: float = 0.0
    total_flops: float = 0.0
    dominant_pipe: str = ""
    pipe_busy_fraction: Dict[str, float] = field(default_factory=dict)
    top_ops_by_duration: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _num(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default


def _norm_pipe(pipe: str) -> str:
    p = str(pipe or "").strip().lower()
    if p in {"pipe_s", "s", "scalar"} or "scalar" in p:
        return "scalar"
    if "mte2" in p or p in {"load", "pipe_mte2"}:
        return "mte2"
    if "mte3" in p or "store" in p:
        return "mte3"
    if "mte" in p or "dma" in p or "copy" in p:
        return "mte"
    if "cube" in p or p in {"m", "pipe_m"}:
        return "cube"
    if "vector" in p or p in {"v", "pipe_v"}:
        return "vector"
    if "sync" in p or "barrier" in p:
        return "sync"
    if "unknown" in p or not p:
        return "unknown"
    return p


def _default_sample_id(path: Path) -> str:
    name = path.name
    for suffix in (".json", ".des", ".profile", ".trace"):
        name = name.replace(suffix, "")
    return name or path.stem


def summarize_des_trace(path: str | Path, *, mlir_file: str = "", sample_id: str = "") -> DESProfileSummary:
    """Read one raw MLIR-derived DES artifact graph and return a kernel-level structural summary."""
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    ops = data.get("operations", []) if isinstance(data, dict) else []
    if not isinstance(ops, list):
        ops = []

    pipe_busy: Dict[str, float] = {}
    pipe_weighted: Dict[str, float] = {}
    pipe_counts: Dict[str, int] = {}
    name_counts: Dict[str, int] = {}
    total_duration = 0.0
    total_weighted_duration = 0.0
    makespan = 0.0
    sync_count = 0
    barrier_count = 0
    event_count = 0
    dependency_edges = 0
    total_bytes = 0.0
    total_flops = 0.0
    top_heap: List[Dict[str, Any]] = []

    for op in ops:
        if not isinstance(op, dict):
            continue
        name = str(op.get("name", "unknown") or "unknown")
        pipe = _norm_pipe(str(op.get("pipe", "unknown") or "unknown"))
        mult = max(1.0, _num(op.get("loop_multiplier", 1.0), 1.0))
        raw_duration = _num(op.get("duration", 0.0), 0.0)
        start = _num(op.get("start_cycle", 0.0), 0.0)
        end = _num(op.get("end_cycle", start + raw_duration), start + raw_duration)
        if end < start:
            end = start + max(0.0, raw_duration)
        scheduled_span = max(0.0, end - start)
        if scheduled_span == 0.0 and raw_duration > 0:
            scheduled_span = raw_duration
        weighted_duration = raw_duration * mult

        total_duration += scheduled_span
        total_weighted_duration += weighted_duration
        makespan = max(makespan, end)
        pipe_busy[pipe] = pipe_busy.get(pipe, 0.0) + scheduled_span
        pipe_weighted[pipe] = pipe_weighted.get(pipe, 0.0) + weighted_duration
        pipe_counts[pipe] = pipe_counts.get(pipe, 0) + 1
        name_counts[name] = name_counts.get(name, 0) + 1

        lname = name.lower()
        if bool(op.get("is_sync")) or "flag" in lname or "sync" in lname or "barrier" in lname:
            sync_count += 1
        if bool(op.get("is_barrier")) or "barrier" in lname:
            barrier_count += 1
        if str(op.get("event_id", "") or ""):
            event_count += 1
        deps = op.get("depends_on", [])
        if isinstance(deps, list):
            dependency_edges += len(deps)

        total_bytes += _num(op.get("bytes", 0.0), 0.0) * mult
        total_flops += _num(op.get("flops", 0.0), 0.0) * mult
        top_heap.append({
            "id": op.get("id"),
            "name": name,
            "pipe": pipe,
            "duration": raw_duration,
            "scheduled_span_cycles": scheduled_span,
            "weighted_duration_cycles": weighted_duration,
            "start_cycle": start,
            "end_cycle": end,
            "line": op.get("line"),
            "bytes": op.get("bytes", 0),
            "flops": op.get("flops", 0),
        })

    denom = max(total_duration, 1.0)
    observed_overlap = max(0.0, min(0.999, 1.0 - makespan / denom)) if total_duration > 0 else 0.0
    busy_total = sum(pipe_busy.values()) or 1.0
    pipe_frac = {k: v / busy_total for k, v in sorted(pipe_busy.items())}
    dominant = max(pipe_busy.items(), key=lambda kv: kv[1])[0] if pipe_busy else ""
    top_ops = sorted(top_heap, key=lambda x: float(x.get("weighted_duration_cycles", x.get("duration", 0.0)) or 0.0), reverse=True)[:20]

    notes = [
        "One artifact DES graph corresponds to one kernel/strategy-level structural artifact sample.",
        "Do not randomly split operations from the same trace into train/test for kernel-level cost calibration.",
        "total_duration_cycles and pipe_busy_cycles use scheduled wall-cycle spans (end_cycle-start_cycle), while total_weighted_duration_cycles preserves duration*loop_multiplier evidence for repeated/static-expanded ops.",
    ]
    if bool(data.get("schedule_truncated", False)):
        notes.append("schedule_truncated=true; makespan/overlap may be incomplete.")

    return DESProfileSummary(
        sample_id=sample_id or _default_sample_id(p),
        mlir_file=str(mlir_file or ""),
        des_trace_file=str(p),
        trace_schema_version=str(data.get("schema_version", "") if isinstance(data, dict) else ""),
        schedule_truncated=bool(data.get("schedule_truncated", False) if isinstance(data, dict) else False),
        clock_ghz=_num(data.get("clock_ghz", 0.0) if isinstance(data, dict) else 0.0),
        num_ops=len([op for op in ops if isinstance(op, dict)]),
        makespan_cycles=float(makespan),
        total_duration_cycles=float(total_duration),
        total_weighted_duration_cycles=float(total_weighted_duration),
        critical_path_cycles=float(makespan),
        observed_overlap_ratio=float(observed_overlap),
        pipe_busy_cycles={k: float(v) for k, v in sorted(pipe_busy.items())},
        pipe_weighted_duration_cycles={k: float(v) for k, v in sorted(pipe_weighted.items())},
        pipe_op_counts={k: int(v) for k, v in sorted(pipe_counts.items())},
        op_name_counts=dict(sorted(name_counts.items(), key=lambda kv: kv[1], reverse=True)[:100]),
        sync_count=int(sync_count),
        barrier_count=int(barrier_count),
        event_count=int(event_count),
        dependency_edges=int(dependency_edges),
        total_bytes=float(total_bytes),
        total_flops=float(total_flops),
        dominant_pipe=dominant,
        pipe_busy_fraction=pipe_frac,
        top_ops_by_duration=top_ops,
        notes=notes,
    )


def load_des_profile_summary(path: str | Path) -> DESProfileSummary:
    """Load either a prebuilt summary or a raw DES trace and return a summary."""
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict) and data.get("schema_version") == SUMMARY_SCHEMA_VERSION:
        allowed = set(DESProfileSummary.__dataclass_fields__.keys())
        return DESProfileSummary(**{k: v for k, v in data.items() if k in allowed})
    return summarize_des_trace(p)


def write_des_profile_summary(summary: DESProfileSummary, output: str | Path) -> None:
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def load_manifest(path: str | Path) -> List[Dict[str, Any]]:
    """Load a future multi-sample manifest.

    Supported forms:
    1. {"samples": [{"sample_id": ..., "mlir_file": ..., "des_trace_file": ...}]}
    2. [{"sample_id": ..., "mlir_file": ..., "des_trace_file": ...}]
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    samples = data.get("samples", []) if isinstance(data, dict) else data
    return [x for x in samples if isinstance(x, dict)] if isinstance(samples, list) else []


def summarize_manifest(path: str | Path) -> List[DESProfileSummary]:
    out: List[DESProfileSummary] = []
    for item in load_manifest(path):
        trace = item.get("des_trace_file") or item.get("des_profile") or item.get("trace")
        if not trace:
            continue
        out.append(summarize_des_trace(
            trace,
            mlir_file=str(item.get("mlir_file", "") or ""),
            sample_id=str(item.get("sample_id", "") or ""),
        ))
    return out


def build_single_trace_calibration(summary: DESProfileSummary, current_analytical_cycles: float, *, max_extra_overlap_gain: float = 0.15) -> Dict[str, Any]:
    """Build a conservative single-trace calibration context.

    The only fully data-aligned transform is the global scale that maps the
    current IR analytical estimate onto the DES makespan.  Additional fields are
    priors used to cap overly optimistic overlap benefits in candidate scoring.
    """
    current = float(current_analytical_cycles or 0.0)
    target = float(summary.makespan_cycles or 0.0)
    global_scale = target / current if current > 0 and target > 0 else 1.0
    observed = float(summary.observed_overlap_ratio or 0.0)
    overlap_cap = max(0.0, min(0.95, observed + max(0.0, float(max_extra_overlap_gain))))
    return {
        "enabled": bool(target > 0 and current > 0),
        "mode": "single_trace_prior",
        "target": "DES_makespan_cycles",
        "sample_id": summary.sample_id,
        "des_trace_file": summary.des_trace_file,
        "mlir_file": summary.mlir_file,
        "des_makespan_cycles": target,
        "current_ir_analytical_cycles": current,
        "global_scale": float(global_scale),
        "observed_overlap_ratio": observed,
        "max_extra_overlap_gain": float(max_extra_overlap_gain),
        "overlap_cap": float(overlap_cap),
        "dominant_pipe": summary.dominant_pipe,
        "pipe_busy_fraction": summary.pipe_busy_fraction,
        "sync_density": float((summary.sync_count + summary.barrier_count) / max(1, summary.num_ops)),
        "num_ops": int(summary.num_ops),
        "notes": [
            "Single-trace calibration aligns analytical current-IR cycles to DES makespan.",
            "This is DES-level calibration, not real hardware msprof calibration.",
        ],
    }


def apply_single_trace_calibration_to_cost(cost: Dict[str, Any], calibration: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of cost with calibrated predicted_cycles and audit fields."""
    if not calibration or not calibration.get("enabled"):
        return cost
    out = dict(cost)
    analytical = float(cost.get("predicted_cycles", 0.0) or 0.0)
    scale = float(calibration.get("global_scale", 1.0) or 1.0)
    scaled = analytical * scale

    # Conservative overlap cap: candidates with very large estimated overlap
    # savings receive an extra penalty after global scaling. This prevents a
    # single DES trace with already-high overlap from making DB/CV plans look
    # unrealistically free.
    savings = (((cost.get("improvement_attribution") or {}).get("optimistic_savings_proxies_per_tile") or {}) if isinstance(cost.get("improvement_attribution"), dict) else {})
    overlap_saving = sum(float(savings.get(k, 0.0) or 0.0) for k in ("load_overlap_saving", "store_overlap_saving", "cv_overlap_saving"))
    raw_per_tile = max(1.0, float(cost.get("tau_load", 0.0) or 0.0) + float(cost.get("tau_store", 0.0) or 0.0) + float(cost.get("tau_cube", 0.0) or 0.0) + float(cost.get("tau_vector", 0.0) or 0.0))
    estimated_overlap_ratio = max(0.0, min(0.999, overlap_saving / raw_per_tile))
    cap = float(calibration.get("overlap_cap", 0.95) or 0.95)
    n_tiles = float(cost.get("n_tiles", 1.0) or 1.0)
    eff_parallel = max(1.0, float(cost.get("effective_parallelism", 1.0) or 1.0))
    excess = max(0.0, estimated_overlap_ratio - cap)
    overlap_cap_penalty = excess * raw_per_tile * n_tiles / eff_parallel

    calibrated = scaled + overlap_cap_penalty * scale
    out["analytical_predicted_cycles_before_des_calibration"] = analytical
    out["predicted_cycles"] = float(calibrated)
    out["des_calibrated"] = True
    out["des_calibration"] = {
        "mode": calibration.get("mode"),
        "sample_id": calibration.get("sample_id"),
        "target": calibration.get("target"),
        "global_scale": scale,
        "des_makespan_cycles": calibration.get("des_makespan_cycles"),
        "estimated_candidate_overlap_ratio": float(estimated_overlap_ratio),
        "overlap_cap": cap,
        "overlap_cap_penalty_cycles_after_scale": float(overlap_cap_penalty * scale),
    }
    cb = dict(out.get("cost_breakdown", {}) or {})
    cb["des_calibration"] = out["des_calibration"]
    cb["analytical_predicted_cycles_before_des_calibration"] = analytical
    cb["calibrated_predicted_cycles"] = float(calibrated)
    out["cost_breakdown"] = cb
    return out
