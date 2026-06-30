# -*- coding: utf-8 -*-
"""V6.0 real operation materialization for four-plan semantic rewrite outputs.

V5.8/V5.9 made TilingPlan and CVPipelinePlan semantics explicit, but part of
that semantics still lived in comments such as ``tile-slice binding`` or
``CVPipeline stage binding``.  This module moves those semantics onto concrete
IR operations as attributes/annotation operations so the optimized HIVM candidate
is a better Linux-backend handoff artifact.

Boundary: this is still a portable textual materializer.  It does not replace
the official Ascend Linux HIVM/MLIR parser, verifier, backend compiler, or
correctness/msprof validation.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

_HIVM_OP_RE = re.compile(r"(?P<indent>\s*)hivm\.hir\.(?P<op>[A-Za-z0-9_]+)(?P<body>.*)$")
_TILE_BIND_RE = re.compile(r"HIVM V5\.8 tile-slice binding:\s*role=(?P<role>\S+)\s+offsets=(?P<offsets>.*?)\s+shape=(?P<shape>.*?)\s+axes=(?P<axes>.*)$")
_REDUCTION_RE = re.compile(r"HIVM V5\.8 reduction binding:\s*(?P<body>.*)$")
_STAGE_RE = re.compile(r"HIVM V5\.8 CVPipeline stage binding:\s*role=(?P<role>\S+)\s+schedule=(?P<schedule>\S+)\s+distance=(?P<distance>\S+)")
_TAIL_GUARD_RE = re.compile(r"HIVM V5\.6 TilingPlan tail guard:\s*strategy=(?P<strategy>\S+)")
_REDUCE_GUARD_RE = re.compile(r"HIVM V5\.6 TilingPlan reduction guard:\s*policy=(?P<policy>\S+)\s+effective_k_tile=(?P<k>\S+)")
_LAYOUT_GUARD_RE = re.compile(r"HIVM V5\.6 TilingPlan layout guard:\s*layout_aware_tile=(?P<enabled>\S+)")
_SCHEDULE_BEGIN_RE = re.compile(r"HIVM V5\.8 CVPipeline semantic schedule begin")
_SCHEDULE_PARAM_RE = re.compile(r"stage_num=(?P<stage_num>\d+)\s+template=(?P<template>\S+)\s+producer_consumer_distance=(?P<distance>\S+)\s+stage_buffer_policy=(?P<policy>\S+)")
_EVENT_OP_RE = re.compile(r"hivm\.hir\.(wait_flag|set_flag)\b")
_MB_SLOT_RE = re.compile(r"(?P<name>%[A-Za-z_][A-Za-z0-9_.$-]*_mb\d+_(?:ping|pong))")
_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_.$-])(%[A-Za-z_][A-Za-z0-9_.$-]*)\b")
_ALLOC_RE = re.compile(r"(?P<name>%[A-Za-z_][A-Za-z0-9_.$-]*)\s*=\s*memref\.alloc\(\)\s*:\s*(?P<type>memref<[^\n]+>)")

SEMANTIC_MARKER_PATTERNS = [
    "HIVM V5.8 tile-slice binding",
    "HIVM V5.8 reduction binding",
    "HIVM V5.8 CVPipeline stage binding",
    "HIVM V5.6 TilingPlan tail guard",
    "HIVM V5.6 TilingPlan reduction guard",
    "HIVM V5.6 TilingPlan layout guard",
]


def _json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _clean_attr_value(x: Any) -> str:
    s = str(x).strip()
    # Keep values parser-friendly; the detailed raw value remains in JSON report.
    s = s.replace('"', "'")
    s = s.replace("\\", "/")
    s = re.sub(r"\s+", " ", s)
    return s[:240]


def _attrs_to_string(attrs: Dict[str, Any]) -> str:
    parts = []
    for k, v in attrs.items():
        if isinstance(v, bool):
            parts.append(f"{k}={'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            parts.append(f"{k}={v}")
        else:
            parts.append(f"{k}=\"{_clean_attr_value(v)}\"")
    return ", ".join(parts)


def _add_attrs_to_hivm_op(line: str, attrs: Dict[str, Any]) -> str:
    attr_s = _attrs_to_string(attrs)
    if not attr_s:
        return line
    # Append to an existing trailing attr dict when possible.
    stripped = line.rstrip()
    if stripped.endswith("}") and "{" in stripped:
        idx = stripped.rfind("}")
        prefix = stripped[:idx]
        # Avoid a double comma for empty dicts.
        if prefix.rstrip().endswith("{"):
            new_line = prefix + attr_s + "}"
        else:
            new_line = prefix + ", " + attr_s + "}"
        return new_line + line[len(stripped):]
    return stripped + " {" + attr_s + "}" + line[len(stripped):]


def _annotation_mark(indent: str, target: str, attrs: Dict[str, Any], typ: str = "index") -> str:
    return f"{indent}annotation.mark {target} {{{_attrs_to_string(attrs)}}} : {typ}"


def _classify_pipeline_region(op: str, stage_role: str | None) -> str:
    if op in {"load", "copy", "nd2nz"} or (stage_role and "load" in stage_role):
        return "producer_load_or_layout"
    if op in {"mmad"} or (stage_role and "compute" in stage_role):
        return "steady_compute"
    if op in {"fixpipe", "store"} or (stage_role and "store" in stage_role):
        return "consumer_store_or_fixpipe"
    if op in {"vreduce", "vsub", "vexp", "vdiv"} or (stage_role and "vector" in stage_role):
        return "vector_postprocess"
    if op in {"wait_flag", "set_flag"}:
        return "dependency_sync"
    return "unclassified"


def materialize_v60_real_operation_attrs(text: str) -> Tuple[str, Dict[str, Any]]:
    """Move semantic rewrite comments to actual op attrs / annotation.mark ops."""
    pending_tile: Dict[str, Any] | None = None
    pending_reduction: Dict[str, Any] | None = None
    pending_stage: Dict[str, Any] | None = None
    schedule_ctx: Dict[str, Any] = {}
    actions: List[Dict[str, Any]] = []
    new_lines: List[str] = []
    skipped_schedule_comment = False

    for ln, line in enumerate(text.splitlines(), start=1):
        m = _TILE_BIND_RE.search(line)
        if m:
            pending_tile = {
                "role": m.group("role"),
                "offsets": m.group("offsets"),
                "shape": m.group("shape"),
                "axes": m.group("axes"),
                "source_line": ln,
            }
            # Comment removed; materialized on the next real op.
            continue
        m = _REDUCTION_RE.search(line)
        if m:
            pending_reduction = {"body": m.group("body"), "source_line": ln}
            continue
        m = _STAGE_RE.search(line)
        if m:
            pending_stage = {
                "role": m.group("role"),
                "schedule": m.group("schedule"),
                "distance": m.group("distance"),
                "source_line": ln,
            }
            continue
        m = _TAIL_GUARD_RE.search(line)
        if m:
            indent = re.match(r"\s*", line).group(0)
            new_lines.append(_annotation_mark(indent, "%m_outer", {
                "hivm.v60_tail_guard_materialized": True,
                "hivm.tail_strategy": m.group("strategy"),
                "hivm.guard_axes": "M,N,K",
                "hivm.guard_kind": "tile_boundary_or_mask_or_pad",
            }))
            actions.append({"line": ln, "plan": "TilingPlan", "materialized": "tail_strategy_guard_annotation", "target": "%m_outer"})
            continue
        m = _REDUCE_GUARD_RE.search(line)
        if m:
            indent = re.match(r"\s*", line).group(0)
            new_lines.append(_annotation_mark(indent, "%k_outer", {
                "hivm.v60_reduce_guard_materialized": True,
                "hivm.reduce_tile_policy": m.group("policy"),
                "hivm.effective_k_tile": m.group("k"),
                "hivm.accumulator_phase": "init_update_final_store",
            }))
            actions.append({"line": ln, "plan": "TilingPlan", "materialized": "reduce_tile_policy_accumulator_guard", "target": "%k_outer"})
            continue
        m = _LAYOUT_GUARD_RE.search(line)
        if m:
            indent = re.match(r"\s*", line).group(0)
            new_lines.append(_annotation_mark(indent, "%m_outer", {
                "hivm.v60_layout_guard_materialized": True,
                "hivm.layout_aware_tile": m.group("enabled"),
                "hivm.layout_alignment_guard": "tile_shape_matches_layout_constraints",
            }))
            actions.append({"line": ln, "plan": "TilingPlan", "materialized": "layout_aware_tile_legality_guard", "target": "%m_outer"})
            continue
        if _SCHEDULE_BEGIN_RE.search(line):
            skipped_schedule_comment = True
            continue
        m = _SCHEDULE_PARAM_RE.search(line)
        if m:
            schedule_ctx = m.groupdict()
            indent = re.match(r"\s*", line).group(0)
            new_lines.append(_annotation_mark(indent, "%c0", {
                "hivm.v60_pipeline_schedule_materialized": True,
                "hivm.stage_num": int(schedule_ctx.get("stage_num") or 0),
                "hivm.template": schedule_ctx.get("template"),
                "hivm.producer_consumer_distance": schedule_ctx.get("distance"),
                "hivm.stage_buffer_policy": schedule_ctx.get("policy"),
                "hivm.schedule_regions": "prologue,steady,epilogue",
            }))
            actions.append({"line": ln, "plan": "CVPipelinePlan", "materialized": "pipeline_schedule_annotation", "target": "%c0"})
            skipped_schedule_comment = True
            continue
        if skipped_schedule_comment and any(tok in line for tok in ["// prologue:", "// steady:", "// epilogue:", "HIVM V5.8 CVPipeline semantic schedule end"]):
            continue

        opm = _HIVM_OP_RE.search(line)
        if opm:
            attrs: Dict[str, Any] = {"hivm.v60_real_operation_materialized": True}
            op = opm.group("op")
            is_event_op = op in {"wait_flag", "set_flag"}
            # Tile/reduction bindings belong to the data/compute op that follows.
            # CVPipeline may insert wait/set edges between the binding comment and
            # the original op; do not accidentally attach tiling semantics to those
            # synchronization events.
            if pending_tile and not is_event_op:
                attrs.update({
                    "hivm.v60_tiling_materialized": True,
                    "hivm.tile_role": pending_tile.get("role"),
                    "hivm.tile_offsets": pending_tile.get("offsets"),
                    "hivm.tile_shape": pending_tile.get("shape"),
                    "hivm.tile_axes": pending_tile.get("axes"),
                })
                actions.append({"source_line": pending_tile.get("source_line"), "target_line": ln, "plan": "TilingPlan", "materialized": "tile_slice_attrs_on_hivm_op", "op": op, "role": pending_tile.get("role")})
                pending_tile = None
            if pending_reduction and not is_event_op:
                attrs.update({
                    "hivm.v60_reduction_materialized": True,
                    "hivm.reduction_binding": pending_reduction.get("body"),
                    "hivm.accumulator_semantics": "partial_init_update_final_store",
                })
                actions.append({"source_line": pending_reduction.get("source_line"), "target_line": ln, "plan": "TilingPlan", "materialized": "reduction_attrs_on_compute_op", "op": op})
                pending_reduction = None
            if pending_stage:
                region = _classify_pipeline_region(op, pending_stage.get("role"))
                attrs.update({
                    "hivm.v60_cvpipeline_materialized": True,
                    "hivm.pipeline_stage_role": pending_stage.get("role"),
                    "hivm.pipeline_schedule": pending_stage.get("schedule"),
                    "hivm.pipeline_region": region,
                    "hivm.producer_consumer_distance": pending_stage.get("distance"),
                    "hivm.tile_index_expr": "producer=i+distance,consumer=i",
                })
                if schedule_ctx:
                    attrs.update({
                        "hivm.pipeline_template": schedule_ctx.get("template"),
                        "hivm.pipeline_stage_num": schedule_ctx.get("stage_num"),
                        "hivm.stage_buffer_policy": schedule_ctx.get("policy"),
                    })
                actions.append({"source_line": pending_stage.get("source_line"), "target_line": ln, "plan": "CVPipelinePlan", "materialized": "pipeline_stage_attrs_on_hivm_op", "op": op, "role": pending_stage.get("role"), "region": region})
                pending_stage = None
            if _EVENT_OP_RE.search(line):
                attrs.update({
                    "hivm.v60_sync_dependency_regenerated": True,
                    "hivm.sync_source": "schedule_graph_after_tiling_multibuffer_cvpipeline",
                    "hivm.dependency_scope": "stage_or_tile",
                })
                actions.append({"target_line": ln, "plan": "SyncPlan", "materialized": "regenerated_dependency_attrs_on_event_op", "op": op})
            new_lines.append(_add_attrs_to_hivm_op(line, attrs))
            continue

        new_lines.append(line)

    report = {
        "schema_version": "hivm_v60_real_operation_materialization_report_v1",
        "mutation_performed": bool(actions),
        "materialized_action_count": len(actions),
        "actions": actions[:500],
        "pending_unmaterialized": {
            "tile": pending_tile,
            "reduction": pending_reduction,
            "stage": pending_stage,
        },
        "linux_backend_validation_required": True,
    }
    return "\n".join(new_lines) + ("\n" if text.endswith("\n") else ""), report


def build_multibuffer_use_def_coverage(text: str) -> Dict[str, Any]:
    defs: Dict[str, str] = {}
    for m in _ALLOC_RE.finditer(text):
        defs[m.group("name")] = m.group("type")
    slot_names = sorted({m.group("name") for m in _MB_SLOT_RE.finditer(text)})
    base_to_slots: Dict[str, Dict[str, List[str]]] = {}
    for name in slot_names:
        base = re.sub(r"_mb\d+_(ping|pong)$", "", name)
        slot = "ping" if name.endswith("_ping") else "pong"
        base_to_slots.setdefault(base, {"ping": [], "pong": []})[slot].append(name)
    token_counts: Dict[str, int] = {}
    for tok in _TOKEN_RE.findall("\n".join([ln.split("//", 1)[0] for ln in text.splitlines()])):
        token_counts[tok] = token_counts.get(tok, 0) + 1
    rows: List[Dict[str, Any]] = []
    for base, slots in sorted(base_to_slots.items()):
        ping_uses = sum(token_counts.get(x, 0) for x in slots.get("ping", []))
        pong_uses = sum(token_counts.get(x, 0) for x in slots.get("pong", []))
        original_uses = token_counts.get(base, 0)
        rows.append({
            "base_buffer": base,
            "ping_slots": slots.get("ping", []),
            "pong_slots": slots.get("pong", []),
            "original_token_uses_after_rewrite": original_uses,
            "ping_token_uses": ping_uses,
            "pong_token_uses": pong_uses,
            "has_ping_and_pong": bool(slots.get("ping")) and bool(slots.get("pong")),
            "unrewritten_use_risk": original_uses > 1,  # definition plus real uses is a risk in textual MVPs.
        })
    blockers = [r for r in rows if not r["has_ping_and_pong"]]
    return {
        "schema_version": "hivm_v60_multibuffer_use_def_coverage_v1",
        "buffer_count": len(rows),
        "rows": rows,
        "all_materialized_buffers_have_ping_pong": not blockers,
        "blockers": blockers,
        "note": "original_token_uses_after_rewrite is conservative because some original buffers remain valid accumulators or non-bufferized ops; Linux use-def verifier is still required.",
    }


def audit_semantic_markers_as_logic(text: str) -> Dict[str, Any]:
    marker_lines: List[Dict[str, Any]] = []
    for ln, line in enumerate(text.splitlines(), start=1):
        if any(p in line for p in SEMANTIC_MARKER_PATTERNS):
            marker_lines.append({"line": ln, "text": line.strip()[:240]})
    # Also check that the important V6 attrs exist.
    required_attrs = [
        "hivm.v60_tiling_materialized",
        "hivm.v60_reduction_materialized",
        "hivm.v60_cvpipeline_materialized",
        "hivm.v60_sync_dependency_regenerated",
        "hivm.v60_tail_guard_materialized",
        "hivm.v60_reduce_guard_materialized",
        "hivm.v60_pipeline_schedule_materialized",
    ]
    missing = [a for a in required_attrs if a not in text]
    blockers: List[Dict[str, Any]] = []
    if marker_lines:
        blockers.append({"kind": "semantic_marker_comment_still_present", "count": len(marker_lines), "detail": marker_lines[:120]})
    if missing:
        blockers.append({"kind": "missing_required_v60_materialized_attr", "missing": missing})
    return {
        "schema_version": "hivm_v60_semantic_marker_materialization_audit_v1",
        "passed_v60_marker_materialization_audit": not blockers,
        "semantic_marker_as_logic_count": len(marker_lines),
        "required_v60_attrs": required_attrs,
        "missing_required_v60_attrs": missing,
        "blockers": blockers,
        "linux_compile_ready_claim": False,
        "backend_validation_required": True,
    }


def write_v60_real_operation_materialization_outputs(input_ir: str | Path, output_dir: str | Path) -> Dict[str, Any]:
    p = Path(input_ir)
    out = Path(output_dir)
    text = p.read_text(encoding="utf-8", errors="ignore")
    materialized, materialization_report = materialize_v60_real_operation_attrs(text)
    final_path = out / "optimized.four_plan_real_operation_materialized.hivm.mlir"
    final_path.write_text(materialized, encoding="utf-8")
    mb_cov = build_multibuffer_use_def_coverage(materialized)
    marker_audit = audit_semantic_markers_as_logic(materialized)
    _json(out / "v60_real_operation_materialization_report.json", materialization_report)
    _json(out / "v60_multibuffer_use_def_coverage.json", mb_cov)
    _json(out / "v60_semantic_marker_materialization_audit.json", marker_audit)
    return {
        "v60_real_operation_materialized_ir": str(final_path),
        "real_operation_materialization": materialization_report,
        "multibuffer_use_def_coverage": mb_cov,
        "semantic_marker_materialization_audit": marker_audit,
    }
