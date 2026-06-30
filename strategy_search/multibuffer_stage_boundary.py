# -*- coding: utf-8 -*-
"""MultiBufferPlan stage-boundary analysis.

V4.8 can find buffer-like anchors.  V4.9 links each selected anchor to a
text-level producer/consumer/sync/loop context so that future Operation-level
ping-pong rewrite can decide whether the anchor is a plausible double-buffer
candidate.  This module is intentionally conservative: it does not clone buffers
or replace uses.  It emits stage-boundary reports and mutation-plan scaffolds.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .multibuffer_rewrite_readiness import analyze_multibuffer_readiness, build_multibuffer_mutation_plan

MULTIBUFFER_STAGE_BOUNDARY_VERSION = "hivm_multibuffer_stage_boundary_v1"
MULTIBUFFER_STAGE_PLAN_VERSION = "hivm_multibuffer_stage_mutation_plan_v1"

_HIVM_OP_RE = re.compile(r"hivm\.hir\.(?P<op>[A-Za-z0-9_]+)")
_SYMBOL_RE_TEMPLATE = r"(?<![A-Za-z0-9_.$-]){}(?![A-Za-z0-9_.$-])"
_FOR_RE = re.compile(r"\b(?:scf|affine)\.for\b")
_IF_RE = re.compile(r"\bscf\.if\b")
_ASSIGN_RE = re.compile(r"^\s*(?P<var>%[A-Za-z0-9_.$-]+)\s*=\s*(?P<expr>.*)$")

TRANSFER_PRODUCER_OPS = {"load", "nd2nz", "copy", "copy_gm_to_ub", "data_copy"}
TRANSFER_CONSUMER_OPS = {"store", "fixpipe", "nd2nz", "copy", "data_copy"}
COMPUTE_OPS = {
    "mmad", "mmadL1", "mad", "vadd", "vsub", "vmul", "vmax", "vmin", "vexp", "vsel", "vcmp",
    "vcast", "vnot", "vand", "vor", "vbrc", "vreduce", "varange", "vconv", "vmuls", "vadds",
}
SYNC_OPS = {"set_flag", "wait_flag", "pipe_barrier", "sync_block_set", "sync_block_wait", "sync_block"}
VIEW_OP_NAMES = {"memref.subview", "memref.cast", "memref.reinterpret_cast"}


def _is_comment(line: str) -> bool:
    return line.strip().startswith("//")


def _op_name(line: str) -> str:
    m = _HIVM_OP_RE.search(line)
    if m:
        return f"hivm.hir.{m.group('op')}"
    for name in sorted(VIEW_OP_NAMES):
        if name in line:
            return name
    if "memref.load" in line:
        return "memref.load"
    if "memref.store" in line:
        return "memref.store"
    if "scf.for" in line:
        return "scf.for"
    if "affine.for" in line:
        return "affine.for"
    return "unknown"


def _short(line: str, n: int = 260) -> str:
    return line.strip()[:n]


def _symbol_rx(symbol: str) -> re.Pattern[str]:
    return re.compile(_SYMBOL_RE_TEMPLATE.format(re.escape(symbol)))


def _has_symbol(line: str, symbol: str) -> bool:
    return bool(_symbol_rx(symbol).search(line))


def _section_context(line: str, symbol: str) -> str:
    """Classify how a symbol is used in a line using simple textual cues."""
    # These cues match common MLIR op assembly style and HIVM examples: ins(...)
    # usually reads, outs(...) usually writes.  This is only a text-level hint.
    sidx = line.find(symbol)
    before = line[: max(0, sidx)]
    # Look at nearest marker before the symbol.
    nearest_ins = before.rfind("ins")
    nearest_outs = before.rfind("outs")
    nearest_operands = before.rfind("(")
    if nearest_outs > nearest_ins and nearest_outs > nearest_operands - 40:
        return "write_like_outs"
    if nearest_ins > nearest_outs and nearest_ins > nearest_operands - 80:
        return "read_like_ins"
    if "memref.store" in line:
        # memref.store value, buffer[...] => buffer use is write-like if symbol appears after comma.
        comma = line.find(",")
        if comma >= 0 and sidx > comma:
            return "write_like_store_target"
    if "memref.load" in line:
        return "read_like_load_source"
    return "ambiguous"


def _line_record(lines: List[str], line_no: int, symbol: Optional[str] = None) -> Dict[str, Any]:
    text = lines[line_no - 1] if 1 <= line_no <= len(lines) else ""
    op = _op_name(text)
    rec = {"line": line_no, "op": op, "text": _short(text)}
    if symbol:
        rec["symbol_context"] = _section_context(text, symbol)
    return rec


def build_loop_context(lines: List[str]) -> Dict[int, List[Dict[str, Any]]]:
    """Best-effort lexical loop/region context per line.

    We do not parse MLIR.  We keep a small stack for lines containing scf.for or
    affine.for and pop on braces.  This is good enough to flag whether a buffer
    anchor and its uses likely sit inside a repeated region.
    """
    active: List[Dict[str, Any]] = []
    per_line: Dict[int, List[Dict[str, Any]]] = {}
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        # Attach existing active loops before processing the current line.
        per_line[i] = [dict(x) for x in active]
        if not _is_comment(line) and _FOR_RE.search(line):
            m = re.search(r"(?P<ivar>%[A-Za-z0-9_.$-]+)\s*=", line)
            loop = {
                "kind": "affine.for" if "affine.for" in line else "scf.for",
                "line": i,
                "iv": m.group("ivar") if m else None,
                "text": _short(line, 220),
            }
            active.append(loop)
            per_line[i] = [dict(x) for x in active]
        # Rough pop: a line with more closing than opening braces closes regions.
        close_count = stripped.count("}")
        open_count = stripped.count("{")
        pops = max(0, close_count - open_count)
        for _ in range(pops):
            if active:
                active.pop()
    return per_line


def _collect_neighborhood_sync(lines: List[str], start: int, end: int, margin: int = 30) -> List[Dict[str, Any]]:
    lo = max(1, min(start, end) - margin)
    hi = min(len(lines), max(start, end) + margin)
    out: List[Dict[str, Any]] = []
    for ln in range(lo, hi + 1):
        line = lines[ln - 1]
        if _is_comment(line):
            continue
        op = _op_name(line)
        short = op.split(".")[-1]
        if short in SYNC_OPS or op in {"hivm.hir.pipe_barrier", "hivm.hir.set_flag", "hivm.hir.wait_flag"}:
            out.append(_line_record(lines, ln))
    return out[:120]


def _extract_symbol_uses(lines: List[str], symbol: str, def_line: int) -> List[Dict[str, Any]]:
    rx = _symbol_rx(symbol)
    uses: List[Dict[str, Any]] = []
    for i, line in enumerate(lines, start=1):
        if i == def_line or _is_comment(line):
            continue
        if not rx.search(line):
            continue
        uses.append(_line_record(lines, i, symbol=symbol))
    return uses


def _classify_stage_records(uses: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    producers: List[Dict[str, Any]] = []
    consumers: List[Dict[str, Any]] = []
    ambiguous: List[Dict[str, Any]] = []
    for u in uses:
        op = str(u.get("op") or "")
        short = op.split(".")[-1]
        ctx = str(u.get("symbol_context") or "")
        rec = dict(u)
        if ctx.startswith("write_like"):
            producers.append(rec)
        elif ctx.startswith("read_like"):
            consumers.append(rec)
        elif op == "memref.store":
            producers.append(rec)
        elif op == "memref.load":
            consumers.append(rec)
        elif short in TRANSFER_PRODUCER_OPS and ctx != "read_like_ins":
            # load/copy/nd2nz are producer-like only when the symbol is an output.
            ambiguous.append(rec)
        elif short in COMPUTE_OPS or short in TRANSFER_CONSUMER_OPS:
            consumers.append(rec)
        elif op in VIEW_OP_NAMES or op.startswith("memref."):
            ambiguous.append(rec)
        else:
            ambiguous.append(rec)
    return producers, consumers, ambiguous


def _nearest_stage_pair(producers: List[Dict[str, Any]], consumers: List[Dict[str, Any]], def_line: int) -> Dict[str, Any]:
    if not producers or not consumers:
        return {"has_pair": False, "producer": None, "consumer": None, "distance": None, "direction": None}
    best = None
    for p in producers:
        for c in consumers:
            dist = int(c["line"]) - int(p["line"])
            # Prefer producer-before-consumer, then compact pairs near the def.
            penalty = 0 if dist >= 0 else 10000
            score = penalty + abs(dist) + abs(int(p["line"]) - def_line) * 0.1
            if best is None or score < best[0]:
                best = (score, p, c, dist)
    assert best is not None
    _, p, c, dist = best
    return {
        "has_pair": True,
        "producer": p,
        "consumer": c,
        "distance": dist,
        "direction": "producer_before_consumer" if dist >= 0 else "consumer_before_producer_or_cross_iteration",
    }


def analyze_stage_boundary_for_anchor(anchor: Dict[str, Any], lines: List[str], loop_context: Dict[int, List[Dict[str, Any]]]) -> Dict[str, Any]:
    symbol = str(anchor.get("symbol") or "")
    def_line = int(anchor.get("line") or 0)
    uses = _extract_symbol_uses(lines, symbol, def_line) if symbol else []
    producers, consumers, ambiguous = _classify_stage_records(uses)
    pair = _nearest_stage_pair(producers, consumers, def_line)
    if pair.get("has_pair"):
        p_line = int(pair["producer"]["line"])
        c_line = int(pair["consumer"]["line"])
        sync = _collect_neighborhood_sync(lines, p_line, c_line, margin=35)
        loop_lines = sorted({x.get("line") for x in (loop_context.get(p_line, []) + loop_context.get(c_line, []) + loop_context.get(def_line, [])) if x.get("line")})
    else:
        sync = _collect_neighborhood_sync(lines, def_line, uses[-1]["line"] if uses else def_line, margin=25)
        loop_lines = sorted({x.get("line") for x in loop_context.get(def_line, []) if x.get("line")})

    blockers: List[str] = []
    warnings: List[str] = []
    reasons: List[str] = []
    score = 0
    scope = anchor.get("scope")
    readiness = anchor.get("readiness")
    if readiness == "BLOCKED" or anchor.get("risk_level") == "BLOCKED":
        blockers.append("readiness_layer_blocked_candidate")
    if scope in {"GM", "UNKNOWN"}:
        blockers.append("non_local_or_unknown_scope_not_pingpong_target")
    elif scope in {"UB", "L1_CBUF"}:
        score += 25
        reasons.append("local_scope_suitable_for_pingpong")
    elif scope in {"L0A", "L0B", "L0C"}:
        warnings.append("l0_fragment_scope_requires_backend_verifier")
        score += 5

    if producers:
        score += 20
        reasons.append("producer_like_use_detected")
    else:
        blockers.append("no_producer_like_use_detected")
    if consumers:
        score += 20
        reasons.append("consumer_like_use_detected")
    else:
        blockers.append("no_consumer_like_use_detected")
    if pair.get("has_pair"):
        if pair.get("direction") == "producer_before_consumer":
            score += 15
            reasons.append("producer_consumer_order_detected")
        else:
            warnings.append("nearest_consumer_before_producer_may_be_cross_iteration")
            score += 6
    if loop_lines:
        score += 10
        reasons.append("loop_context_detected")
    else:
        warnings.append("no_loop_context_detected_textually")
    if sync:
        score += 10
        reasons.append("sync_context_detected_near_stage_pair")
    else:
        warnings.append("no_nearby_sync_context_detected")
    if len(ambiguous) > len(producers) + len(consumers) + 3:
        warnings.append("many_ambiguous_uses_need_operation_level_alias_analysis")

    if blockers:
        boundary_status = "BLOCKED"
    elif score >= 80:
        boundary_status = "READY_FOR_PINGPONG_PLAN"
    elif score >= 55:
        boundary_status = "REVIEW_REQUIRED"
    else:
        boundary_status = "LOW_CONFIDENCE"

    return {
        "anchor_id": anchor.get("id"),
        "symbol": symbol,
        "target": {
            "line": def_line,
            "kind": anchor.get("kind"),
            "scope": scope,
            "type": anchor.get("type"),
            "text": anchor.get("text"),
        },
        "readiness_status": anchor.get("readiness"),
        "stage_boundary_status": boundary_status,
        "stage_boundary_score": score,
        "risk_level": "BLOCKED" if blockers else ("LOW" if boundary_status == "READY_FOR_PINGPONG_PLAN" else "MEDIUM" if boundary_status == "REVIEW_REQUIRED" else "HIGH"),
        "producer_candidates": producers[:20],
        "consumer_candidates": consumers[:20],
        "ambiguous_uses": ambiguous[:20],
        "nearest_stage_pair": pair,
        "sync_context": sync[:40],
        "loop_context_lines": loop_lines,
        "loop_context_preview": [x for ln in loop_lines for x in loop_context.get(int(ln), []) if x.get("line") == ln][:8],
        "reasons": reasons,
        "warnings": warnings,
        "blockers": blockers,
        "required_for_real_mutation": [
            "confirm_def_use_with_MLIR_dominance",
            "confirm_alias_group_for_view_chain",
            "derive_loop_iteration_parity_or_stage_index",
            "create_ping_pong_slot_for_target_scope",
            "rewrite_producer_and_consumer_uses_in_distinct_stage_regions",
            "insert_or_reuse_SyncPlan_event_edges",
            "run_HivmOpsEditor_export_and_mlir_verify",
        ],
    }


def analyze_multibuffer_stage_boundaries(
    ir_text: str,
    selected_plan: Optional[Dict[str, Any]] = None,
    max_candidates: int = 80,
) -> Dict[str, Any]:
    readiness = analyze_multibuffer_readiness(ir_text, selected_plan or {}, max_candidates=max_candidates)
    lines = ir_text.splitlines()
    loop_context = build_loop_context(lines)
    analyses = [
        analyze_stage_boundary_for_anchor(anchor, lines, loop_context)
        for anchor in readiness.get("selected_candidates", [])
    ]
    status_counts: Dict[str, int] = {}
    risk_counts: Dict[str, int] = {}
    scope_counts: Dict[str, int] = {}
    for a in analyses:
        status_counts[a["stage_boundary_status"]] = status_counts.get(a["stage_boundary_status"], 0) + 1
        risk_counts[a["risk_level"]] = risk_counts.get(a["risk_level"], 0) + 1
        scope = ((a.get("target") or {}).get("scope") or "UNKNOWN")
        scope_counts[scope] = scope_counts.get(scope, 0) + 1
    selected_for_plan = [a for a in analyses if a.get("stage_boundary_status") in {"READY_FOR_PINGPONG_PLAN", "REVIEW_REQUIRED"}]
    return {
        "schema_version": MULTIBUFFER_STAGE_BOUNDARY_VERSION,
        "version": "V4.9-multibuffer-stage-boundary-analysis",
        "input_anchor_count": readiness.get("anchor_count"),
        "readiness_counts": readiness.get("readiness_counts"),
        "analyzed_candidate_count": len(analyses),
        "stage_boundary_status_counts": status_counts,
        "risk_counts": risk_counts,
        "scope_counts": scope_counts,
        "selected_for_stage_plan_count": len(selected_for_plan),
        "stage_boundary_candidates": analyses,
        "selected_for_stage_plan": selected_for_plan,
        "claim_boundary": "stage-boundary analysis only; no buffer clone/use replacement is performed",
    }


def build_stage_mutation_plan(stage_report: Dict[str, Any]) -> Dict[str, Any]:
    actions: List[Dict[str, Any]] = []
    for idx, c in enumerate(stage_report.get("selected_for_stage_plan", [])):
        pair = c.get("nearest_stage_pair") or {}
        target = c.get("target") or {}
        actions.append({
            "action_id": f"multibuffer_stage_plan_action_{idx:04d}",
            "mutation_kind": "double_buffer_stage_boundary_plan",
            "status": "STAGE_PLANNED_NOT_MUTATED",
            "stage_boundary_status": c.get("stage_boundary_status"),
            "risk_level": c.get("risk_level"),
            "target": {
                "symbol": c.get("symbol"),
                "line": target.get("line"),
                "kind": target.get("kind"),
                "scope": target.get("scope"),
                "type": target.get("type"),
                "text": target.get("text"),
            },
            "producer": pair.get("producer"),
            "consumer": pair.get("consumer"),
            "producer_consumer_distance": pair.get("distance"),
            "sync_context_preview": c.get("sync_context", [])[:12],
            "loop_context_lines": c.get("loop_context_lines", []),
            "proposed_pingpong_rewrite": {
                "slot_count": 2,
                "producer_slot_expr": "slot[iteration % 2]",
                "consumer_slot_expr": "slot[(iteration + required_lag) % 2]",
                "requires_sync_edge": True,
                "requires_capacity_multiplier": 2,
            },
            "hivmopseditor_migration": {
                "operation_level_steps": [
                    "locate target defining op by line/symbol",
                    "locate producer and consumer operations from stage pair",
                    "clone target buffer op or create second slot in same address space",
                    "rewrite producer stage uses to ping/pong slot",
                    "rewrite consumer stage uses to lagged slot",
                    "insert/reuse SyncPlan set_flag/wait_flag edges",
                    "delete obsolete barrier only after verifier passes",
                    "exportToFile and mlir::verify",
                ],
                "required_editor_capabilities": [
                    "listOps with source locations",
                    "clone operation or create equivalent buffer/view op",
                    "replace uses within region",
                    "insert set_flag/wait_flag around stage boundary",
                    "verify/export roundtrip",
                ],
            },
            "blockers_before_semantic_mutation": c.get("blockers", []) + [
                "need real alias/dominance analysis",
                "need exact loop parity expression from MLIR region",
                "need capacity gate for doubled local buffer",
                "need verifier and DES/trace validation",
            ],
        })
    return {
        "schema_version": MULTIBUFFER_STAGE_PLAN_VERSION,
        "version": "V4.9-multibuffer-stage-boundary-analysis",
        "overall_decision": "MULTIBUFFER_STAGE_PLAN_READY_NOT_MUTATED" if actions else "NO_STAGE_BOUNDARY_CANDIDATES",
        "action_count": len(actions),
        "actions": actions,
        "semantic_mutation_performed": False,
        "production_rewrite_claim_allowed": False,
    }


def annotate_stage_boundaries(ir_text: str, stage_plan: Dict[str, Any], max_annotations: int = 30) -> Tuple[str, Dict[str, Any]]:
    lines = ir_text.splitlines()
    by_line: Dict[int, List[Dict[str, Any]]] = {}
    for a in (stage_plan.get("actions") or [])[:max_annotations]:
        target = a.get("target") or {}
        try:
            line = int(target.get("line"))
        except Exception:
            continue
        by_line.setdefault(line, []).append(a)
    out: List[str] = []
    inserted = 0
    for i, line in enumerate(lines, start=1):
        for a in by_line.get(i, []):
            target = a.get("target") or {}
            prod = a.get("producer") or {}
            cons = a.get("consumer") or {}
            out.append(f"// HIVM V4.9 MultiBufferPlan stage-boundary candidate: {a.get('action_id')} risk={a.get('risk_level')} status={a.get('stage_boundary_status')}")
            out.append(f"//   target={target.get('symbol')} scope={target.get('scope')} producer_line={prod.get('line')} consumer_line={cons.get('line')} rewrite=stage_planned_not_mutated")
            inserted += 1
        out.append(line)
    return "\n".join(out) + ("\n" if ir_text.endswith("\n") else ""), {
        "schema_version": "hivm_multibuffer_stage_annotation_v1",
        "annotation_performed": inserted > 0,
        "inserted_annotation_count": inserted,
        "semantic_mutation_performed": False,
        "claim_boundary": "stage-boundary comments only; original IR operations are not changed",
    }


def write_multibuffer_stage_outputs(
    ir_path: str | Path,
    selected_plan_path: str | Path,
    output_dir: str | Path,
    max_candidates: int = 80,
    max_annotations: int = 30,
) -> Dict[str, Any]:
    ir_path = Path(ir_path)
    selected_plan_path = Path(selected_plan_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ir_text = ir_path.read_text(encoding="utf-8")
    selected_plan = json.loads(selected_plan_path.read_text(encoding="utf-8")) if selected_plan_path.exists() else {}
    stage_report = analyze_multibuffer_stage_boundaries(ir_text, selected_plan, max_candidates=max_candidates)
    stage_plan = build_stage_mutation_plan(stage_report)
    annotated, annotation_report = annotate_stage_boundaries(ir_text, stage_plan, max_annotations=max_annotations)

    stage_report_path = output_dir / "multibuffer_stage_boundary_report.json"
    stage_plan_path = output_dir / "multibuffer_stage_mutation_plan.json"
    annotated_path = output_dir / "multibuffer_stage_annotated_not_mutated.hivm.mlir"
    annotation_report_path = output_dir / "multibuffer_stage_annotation_report.json"
    summary_path = output_dir / "multibuffer_stage_boundary_summary.json"

    stage_report_path.write_text(json.dumps(stage_report, ensure_ascii=False, indent=2), encoding="utf-8")
    stage_plan_path.write_text(json.dumps(stage_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    annotated_path.write_text(annotated, encoding="utf-8")
    annotation_report_path.write_text(json.dumps(annotation_report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "version": "V4.9-multibuffer-stage-boundary-analysis",
        "schema_version": "hivm_multibuffer_stage_boundary_summary_v1",
        "input_ir": str(ir_path),
        "input_anchor_count": stage_report.get("input_anchor_count"),
        "readiness_counts": stage_report.get("readiness_counts"),
        "analyzed_candidate_count": stage_report.get("analyzed_candidate_count"),
        "stage_boundary_status_counts": stage_report.get("stage_boundary_status_counts"),
        "risk_counts": stage_report.get("risk_counts"),
        "scope_counts": stage_report.get("scope_counts"),
        "selected_for_stage_plan_count": stage_report.get("selected_for_stage_plan_count"),
        "stage_mutation_plan_action_count": stage_plan.get("action_count"),
        "annotation_performed": annotation_report.get("annotation_performed"),
        "semantic_mutation_performed": False,
        "production_rewrite_claim_allowed": False,
        "next_step": "CVPipelinePlan staged planner or guarded HivmOpsEditor multibuffer mutation after real verifier is available",
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "stage_report_path": str(stage_report_path),
        "stage_plan_path": str(stage_plan_path),
        "annotated_ir_path": str(annotated_path),
        "annotation_report_path": str(annotation_report_path),
        "summary_path": str(summary_path),
        "summary": summary,
    }
