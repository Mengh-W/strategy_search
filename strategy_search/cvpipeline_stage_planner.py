# -*- coding: utf-8 -*-
"""CVPipelinePlan staged rewrite planner.

V4.10 turns the previous SyncPlan and MultiBufferPlan evidence into a
text-level CVPipeline stage plan.  It classifies HIVM/MLIR lines into coarse
pipeline stages (load / compute / store / sync / view), groups nearby operations
into stage segments, estimates pipeline readiness, and emits a guarded rewrite
plan scaffold.  No operations are moved in this module.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from .multibuffer_stage_boundary import analyze_multibuffer_stage_boundaries, build_stage_mutation_plan
except Exception:  # pragma: no cover
    analyze_multibuffer_stage_boundaries = None  # type: ignore
    build_stage_mutation_plan = None  # type: ignore

CVPIPELINE_STAGE_PLANNER_VERSION = "hivm_cvpipeline_stage_planner_v1"
CVPIPELINE_REWRITE_PLAN_VERSION = "hivm_cvpipeline_rewrite_plan_v1"

_HIVM_OP_RE = re.compile(r"hivm\.hir\.(?P<op>[A-Za-z0-9_]+)")
_ASSIGN_RE = re.compile(r"^\s*(?P<result>%[A-Za-z0-9_.$-]+)\s*=")
_SYMBOL_RE = re.compile(r"%[A-Za-z0-9_.$-]+")
_FOR_RE = re.compile(r"\b(?:scf|affine)\.for\b")

LOAD_OPS = {
    "load", "copy_gm_to_ub", "data_copy", "nd2nz", "copy", "load_gm_to_ub",
}
STORE_OPS = {
    "store", "fixpipe", "copy_ub_to_gm", "data_copy_out", "copy",
}
COMPUTE_OPS = {
    "mmad", "mmadL1", "mad", "matmul", "vadd", "vsub", "vmul", "vmax", "vmin", "vexp",
    "vsel", "vcmp", "vcast", "vnot", "vand", "vor", "vbrc", "vreduce", "varange", "vconv",
    "vmuls", "vadds", "relu", "sigmoid", "exp", "reduce", "transpose",
}
SYNC_OPS = {"set_flag", "wait_flag", "pipe_barrier", "sync_block", "sync_block_set", "sync_block_wait"}
VIEW_KEYWORDS = ["pointer_cast", "memref.subview", "memref.reinterpret_cast", "memref.cast", "memref.alloc"]


def _is_comment(line: str) -> bool:
    return line.strip().startswith("//")


def _short(line: str, n: int = 240) -> str:
    return line.strip()[:n]


def _hivm_short_op(line: str) -> Optional[str]:
    m = _HIVM_OP_RE.search(line)
    return m.group("op") if m else None


def classify_line(line: str) -> Tuple[str, str, List[str]]:
    """Return coarse stage, op_name, and textual tags for one line."""
    if _is_comment(line) or not line.strip():
        return "non_op", "comment_or_blank", []
    tags: List[str] = []
    short = _hivm_short_op(line)
    op_name = f"hivm.hir.{short}" if short else "unknown"
    if _FOR_RE.search(line):
        return "loop", "scf.for" if "scf.for" in line else "affine.for", ["loop_boundary"]
    if any(k in line for k in VIEW_KEYWORDS):
        tags.append("buffer_view")
        if "pointer_cast" in line:
            op_name = "hivm.hir.pointer_cast"
        elif "memref.subview" in line:
            op_name = "memref.subview"
        elif "memref.reinterpret_cast" in line:
            op_name = "memref.reinterpret_cast"
        elif "memref.cast" in line:
            op_name = "memref.cast"
        elif "memref.alloc" in line:
            op_name = "memref.alloc"
        return "view", op_name, tags
    if "memref.load" in line:
        return "load", "memref.load", ["memory_read"]
    if "memref.store" in line:
        return "store", "memref.store", ["memory_write"]
    if short in SYNC_OPS:
        return "sync", op_name, ["sync"]
    if short in LOAD_OPS:
        # nd2nz/copy can be producer or consumer, but as a CVPipeline stage they are transfer-like.
        return "load", op_name, ["transfer_or_format"]
    if short in STORE_OPS:
        return "store", op_name, ["store_or_fixpipe"]
    if short in COMPUTE_OPS or (short and (short.startswith("v") or "mad" in short.lower())):
        return "compute", op_name, ["compute"]
    if short:
        return "other_hivm", op_name, ["hivm_other"]
    if any(k in line for k in ["arith.", "math.", "vector.", "affine.apply"]):
        return "compute", "mlir.compute_like", ["aux_compute"]
    return "other", op_name, []


def _symbols(line: str) -> List[str]:
    return _SYMBOL_RE.findall(line)


def _result_symbol(line: str) -> Optional[str]:
    m = _ASSIGN_RE.match(line)
    return m.group("result") if m else None


def build_operation_records(ir_text: str) -> List[Dict[str, Any]]:
    lines = ir_text.splitlines()
    records: List[Dict[str, Any]] = []
    loop_stack: List[Dict[str, Any]] = []
    for i, line in enumerate(lines, start=1):
        stage, op_name, tags = classify_line(line)
        rec = {
            "line": i,
            "stage": stage,
            "op": op_name,
            "text": _short(line),
            "result": _result_symbol(line),
            "symbols": _symbols(line)[:40],
            "tags": tags,
            "loop_depth": len(loop_stack),
            "loop_context": [dict(x) for x in loop_stack[-4:]],
        }
        # Process loop entry after recording current line as loop boundary with new context.
        if stage == "loop":
            iv_match = re.search(r"(?P<iv>%[A-Za-z0-9_.$-]+)\s*=", line)
            loop = {"line": i, "kind": op_name, "iv": iv_match.group("iv") if iv_match else None, "text": _short(line, 180)}
            loop_stack.append(loop)
            rec["loop_depth"] = len(loop_stack)
            rec["loop_context"] = [dict(x) for x in loop_stack[-4:]]
        records.append(rec)
        stripped = line.strip()
        pops = max(0, stripped.count("}") - stripped.count("{"))
        for _ in range(pops):
            if loop_stack:
                loop_stack.pop()
    return records


def group_stage_segments(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group consecutive pipeline-relevant records into coarse segments."""
    segments: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    relevant = {"load", "compute", "store", "sync", "view"}
    for rec in records:
        stage = rec["stage"]
        if stage not in relevant:
            if current is not None and stage in {"loop", "other_hivm"}:
                current.setdefault("interleaved_context", []).append({"line": rec["line"], "stage": stage, "op": rec["op"]})
            continue
        key = (stage, rec.get("loop_depth", 0))
        if current is None or current.get("stage") != key[0] or current.get("loop_depth") != key[1] or rec["line"] - current["end_line"] > 6:
            if current is not None:
                segments.append(current)
            current = {
                "segment_id": f"segment_{len(segments):04d}",
                "stage": stage,
                "start_line": rec["line"],
                "end_line": rec["line"],
                "loop_depth": rec.get("loop_depth", 0),
                "loop_context": rec.get("loop_context", []),
                "ops": [],
                "op_counts": {},
                "defined_symbols": [],
                "used_symbols": [],
            }
        current["end_line"] = rec["line"]
        current["ops"].append({"line": rec["line"], "op": rec["op"], "text": rec["text"], "result": rec.get("result"), "tags": rec.get("tags", [])})
        current["op_counts"][rec["op"]] = current["op_counts"].get(rec["op"], 0) + 1
        if rec.get("result"):
            current["defined_symbols"].append(rec["result"])
        for s in rec.get("symbols", []):
            if s != rec.get("result"):
                current["used_symbols"].append(s)
    if current is not None:
        segments.append(current)
    for seg in segments:
        seg["op_count"] = len(seg.get("ops", []))
        seg["defined_symbols"] = sorted(set(seg.get("defined_symbols", [])))[:80]
        seg["used_symbols"] = sorted(set(seg.get("used_symbols", [])))[:120]
    return segments


def _segment_dependency_edges(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    symbol_defs: Dict[str, str] = {}
    for seg in segments:
        for s in seg.get("defined_symbols", []):
            symbol_defs.setdefault(s, seg["segment_id"])
    edges: List[Dict[str, Any]] = []
    seen = set()
    for seg in segments:
        for s in seg.get("used_symbols", []):
            src = symbol_defs.get(s)
            if not src or src == seg["segment_id"]:
                continue
            key = (src, seg["segment_id"], s)
            if key in seen:
                continue
            seen.add(key)
            edges.append({"src": src, "dst": seg["segment_id"], "symbol": s, "reason": "textual_def_use"})
    return edges[:1000]


def _find_pipeline_windows(segments: List[Dict[str, Any]], max_windows: int = 50) -> List[Dict[str, Any]]:
    windows: List[Dict[str, Any]] = []
    n = len(segments)
    for i, seg in enumerate(segments):
        if seg["stage"] not in {"load", "view"}:
            continue
        # Search ahead for compute and store with only modest distance.
        compute = None
        store = None
        syncs: List[Dict[str, Any]] = []
        for j in range(i + 1, min(n, i + 12)):
            s = segments[j]
            if s["stage"] == "sync":
                syncs.append(s)
            elif s["stage"] == "compute" and compute is None:
                compute = s
            elif s["stage"] == "store" and compute is not None:
                store = s
                break
        if compute and store:
            loop_context = seg.get("loop_context") or compute.get("loop_context") or store.get("loop_context") or []
            score = 35
            reasons = ["load_compute_store_order_detected"]
            warnings: List[str] = []
            if syncs:
                score += 20
                reasons.append("sync_segment_between_load_compute_store")
            else:
                warnings.append("no_sync_segment_inside_window")
            if loop_context:
                score += 20
                reasons.append("loop_context_detected")
            else:
                warnings.append("no_loop_context_detected")
            # shared symbols signal def-use proximity.
            shared_lc = set(seg.get("defined_symbols", []) + seg.get("used_symbols", [])) & set(compute.get("used_symbols", []) + compute.get("defined_symbols", []))
            shared_cs = set(compute.get("defined_symbols", []) + compute.get("used_symbols", [])) & set(store.get("used_symbols", []) + store.get("defined_symbols", []))
            if shared_lc or shared_cs:
                score += 15
                reasons.append("textual_symbol_overlap_between_stages")
            else:
                warnings.append("weak_textual_symbol_overlap_need_alias_analysis")
            if seg["stage"] == "view":
                score += 5
                reasons.append("view_segment_can_attach_to_load_stage")
            status = "READY_FOR_CVPIPELINE_PLAN" if score >= 75 else "REVIEW_REQUIRED" if score >= 55 else "LOW_CONFIDENCE"
            windows.append({
                "window_id": f"cv_window_{len(windows):04d}",
                "status": status,
                "score": score,
                "risk_level": "LOW" if status == "READY_FOR_CVPIPELINE_PLAN" else "MEDIUM" if status == "REVIEW_REQUIRED" else "HIGH",
                "load_or_view_segment": seg["segment_id"],
                "compute_segment": compute["segment_id"],
                "store_segment": store["segment_id"],
                "sync_segments": [s["segment_id"] for s in syncs],
                "line_span": [seg["start_line"], store["end_line"]],
                "loop_context": loop_context[:4],
                "reasons": reasons,
                "warnings": warnings,
                "required_multibuffer": True,
            })
            if len(windows) >= max_windows:
                break
    return windows


def _load_json_if_exists(path: Optional[str | Path]) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def analyze_cvpipeline_stages(
    ir_text: str,
    selected_plan: Optional[Dict[str, Any]] = None,
    multibuffer_stage_report: Optional[Dict[str, Any]] = None,
    max_windows: int = 50,
) -> Dict[str, Any]:
    records = build_operation_records(ir_text)
    segments = group_stage_segments(records)
    edges = _segment_dependency_edges(segments)
    windows = _find_pipeline_windows(segments, max_windows=max_windows)
    stage_counts: Dict[str, int] = {}
    op_counts: Dict[str, int] = {}
    for r in records:
        stage_counts[r["stage"]] = stage_counts.get(r["stage"], 0) + 1
        op_counts[r["op"]] = op_counts.get(r["op"], 0) + 1
    window_counts: Dict[str, int] = {}
    for w in windows:
        window_counts[w["status"]] = window_counts.get(w["status"], 0) + 1

    mb_ready_count = 0
    mb_plan_actions: List[Dict[str, Any]] = []
    if multibuffer_stage_report:
        mb_ready_count = int(multibuffer_stage_report.get("selected_for_stage_plan_count") or 0)
        mb_plan_actions = multibuffer_stage_report.get("selected_for_stage_plan", [])[:80]
    elif analyze_multibuffer_stage_boundaries is not None:
        try:
            mb_report = analyze_multibuffer_stage_boundaries(ir_text, selected_plan or {}, max_candidates=80)
            mb_ready_count = int(mb_report.get("selected_for_stage_plan_count") or 0)
            mb_plan_actions = mb_report.get("selected_for_stage_plan", [])[:80]
        except Exception:
            mb_ready_count = 0
            mb_plan_actions = []

    blockers: List[str] = []
    warnings: List[str] = []
    if not windows:
        blockers.append("no_load_compute_store_pipeline_window_detected")
    if mb_ready_count <= 0:
        warnings.append("no_multibuffer_stage_plan_available_pipeline_rewrite_will_remain_planner_only")
    if stage_counts.get("sync", 0) <= 0:
        warnings.append("no_sync_ops_detected_cvpipeline_needs_syncplan_edges")

    return {
        "schema_version": CVPIPELINE_STAGE_PLANNER_VERSION,
        "version": "V4.10-cvpipeline-stage-rewrite-planner",
        "record_count": len(records),
        "stage_counts": stage_counts,
        "top_op_counts": dict(sorted(op_counts.items(), key=lambda kv: kv[1], reverse=True)[:40]),
        "segment_count": len(segments),
        "segments": segments[:500],
        "dependency_edge_count": len(edges),
        "dependency_edges": edges,
        "pipeline_window_count": len(windows),
        "pipeline_window_status_counts": window_counts,
        "pipeline_windows": windows,
        "multibuffer_stage_ready_count": mb_ready_count,
        "multibuffer_stage_plan_preview": mb_plan_actions[:20],
        "warnings": warnings,
        "blockers": blockers,
        "claim_boundary": "CVPipeline stage planner only; no operation reordering or semantic mutation is performed",
    }


def build_cvpipeline_rewrite_plan(stage_report: Dict[str, Any]) -> Dict[str, Any]:
    actions: List[Dict[str, Any]] = []
    segment_by_id = {s["segment_id"]: s for s in stage_report.get("segments", [])}
    for idx, w in enumerate(stage_report.get("pipeline_windows", [])):
        if w.get("status") not in {"READY_FOR_CVPIPELINE_PLAN", "REVIEW_REQUIRED"}:
            continue
        load_seg = segment_by_id.get(w.get("load_or_view_segment"), {})
        compute_seg = segment_by_id.get(w.get("compute_segment"), {})
        store_seg = segment_by_id.get(w.get("store_segment"), {})
        actions.append({
            "action_id": f"cvpipeline_stage_plan_action_{idx:04d}",
            "mutation_kind": "cvpipeline_stage_rewrite_plan",
            "status": "STAGE_PLANNED_NOT_MUTATED",
            "risk_level": w.get("risk_level"),
            "window_id": w.get("window_id"),
            "line_span": w.get("line_span"),
            "stage_segments": {
                "load_or_view": {"segment_id": load_seg.get("segment_id"), "line_span": [load_seg.get("start_line"), load_seg.get("end_line")], "op_count": load_seg.get("op_count"), "op_counts": load_seg.get("op_counts")},
                "compute": {"segment_id": compute_seg.get("segment_id"), "line_span": [compute_seg.get("start_line"), compute_seg.get("end_line")], "op_count": compute_seg.get("op_count"), "op_counts": compute_seg.get("op_counts")},
                "store": {"segment_id": store_seg.get("segment_id"), "line_span": [store_seg.get("start_line"), store_seg.get("end_line")], "op_count": store_seg.get("op_count"), "op_counts": store_seg.get("op_counts")},
                "sync_segments": w.get("sync_segments", []),
            },
            "proposed_staged_rewrite": {
                "stage_0": "prefetch/load_or_view for iteration i+1 into ping/pong buffer",
                "stage_1": "compute iteration i from previous buffer slot",
                "stage_2": "store/fixpipe iteration i-1 when safe",
                "required_sync_edges": ["load_to_compute", "compute_to_store"],
                "requires_multibuffer": True,
                "requires_loop_skew_or_software_pipeline_indexing": True,
            },
            "hivmopseditor_migration": {
                "required_capabilities": [
                    "locate stage segment operations by source line",
                    "clone or move load/view ops into prologue/steady-state stage",
                    "rewrite buffer uses according to MultiBufferPlan slots",
                    "insert or reuse SyncPlan set_flag/wait_flag edges",
                    "preserve dominance and SSA uses",
                    "exportToFile and mlir::verify",
                ],
                "migration_priority": "after_multibuffer_semantic_mutation_available",
            },
            "blockers_before_semantic_mutation": [
                "need operation-level dominance and dependency graph",
                "need valid MultiBufferPlan semantic mutation",
                "need exact loop prologue/steady/epilogue transformation",
                "need real MLIR verifier and DES/trace validation",
            ],
            "reasons": w.get("reasons", []),
            "warnings": w.get("warnings", []),
        })
    return {
        "schema_version": CVPIPELINE_REWRITE_PLAN_VERSION,
        "version": "V4.10-cvpipeline-stage-rewrite-planner",
        "overall_decision": "CVPIPELINE_STAGE_PLAN_READY_NOT_MUTATED" if actions else "NO_CVPIPELINE_STAGE_PLAN",
        "action_count": len(actions),
        "actions": actions,
        "semantic_mutation_performed": False,
        "production_rewrite_claim_allowed": False,
        "claim_boundary": "planner/scaffold only; no operation movement is performed",
    }


def annotate_cvpipeline_windows(ir_text: str, plan: Dict[str, Any], max_annotations: int = 20) -> Tuple[str, Dict[str, Any]]:
    lines = ir_text.splitlines()
    by_line: Dict[int, List[Dict[str, Any]]] = {}
    for a in (plan.get("actions") or [])[:max_annotations]:
        span = a.get("line_span") or []
        if not span:
            continue
        try:
            line = int(span[0])
        except Exception:
            continue
        by_line.setdefault(line, []).append(a)
    out: List[str] = []
    inserted = 0
    for i, line in enumerate(lines, start=1):
        for a in by_line.get(i, []):
            segs = a.get("stage_segments") or {}
            out.append(f"// HIVM V4.10 CVPipelinePlan window: {a.get('action_id')} risk={a.get('risk_level')} status={a.get('status')}")
            out.append(f"//   load={((segs.get('load_or_view') or {}).get('segment_id'))} compute={((segs.get('compute') or {}).get('segment_id'))} store={((segs.get('store') or {}).get('segment_id'))} rewrite=stage_planned_not_mutated")
            inserted += 1
        out.append(line)
    return "\n".join(out) + ("\n" if ir_text.endswith("\n") else ""), {
        "schema_version": "hivm_cvpipeline_annotation_v1",
        "annotation_performed": inserted > 0,
        "inserted_annotation_count": inserted,
        "semantic_mutation_performed": False,
        "claim_boundary": "CVPipeline comments only; original operations are not moved",
    }


def write_cvpipeline_stage_outputs(
    ir_path: str | Path,
    selected_plan_path: str | Path,
    output_dir: str | Path,
    multibuffer_stage_report_path: Optional[str | Path] = None,
    max_windows: int = 50,
    max_annotations: int = 20,
) -> Dict[str, Any]:
    ir_path = Path(ir_path)
    selected_plan_path = Path(selected_plan_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ir_text = ir_path.read_text(encoding="utf-8")
    selected_plan = json.loads(selected_plan_path.read_text(encoding="utf-8")) if selected_plan_path.exists() else {}
    mb_report = _load_json_if_exists(multibuffer_stage_report_path)
    stage_report = analyze_cvpipeline_stages(ir_text, selected_plan, mb_report, max_windows=max_windows)
    plan = build_cvpipeline_rewrite_plan(stage_report)
    annotated, annotation_report = annotate_cvpipeline_windows(ir_text, plan, max_annotations=max_annotations)

    paths = {
        "stage_report_path": output_dir / "cvpipeline_stage_report.json",
        "rewrite_plan_path": output_dir / "cvpipeline_rewrite_plan.json",
        "annotated_ir_path": output_dir / "cvpipeline_stage_annotated_not_mutated.hivm.mlir",
        "annotation_report_path": output_dir / "cvpipeline_annotation_report.json",
        "summary_path": output_dir / "cvpipeline_stage_planner_summary.json",
    }
    paths["stage_report_path"].write_text(json.dumps(stage_report, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["rewrite_plan_path"].write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["annotated_ir_path"].write_text(annotated, encoding="utf-8")
    paths["annotation_report_path"].write_text(json.dumps(annotation_report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "schema_version": "hivm_cvpipeline_stage_planner_summary_v1",
        "version": "V4.10-cvpipeline-stage-rewrite-planner",
        "input_ir": str(ir_path),
        "record_count": stage_report.get("record_count"),
        "stage_counts": stage_report.get("stage_counts"),
        "segment_count": stage_report.get("segment_count"),
        "dependency_edge_count": stage_report.get("dependency_edge_count"),
        "pipeline_window_count": stage_report.get("pipeline_window_count"),
        "pipeline_window_status_counts": stage_report.get("pipeline_window_status_counts"),
        "multibuffer_stage_ready_count": stage_report.get("multibuffer_stage_ready_count"),
        "cvpipeline_rewrite_plan_action_count": plan.get("action_count"),
        "annotation_performed": annotation_report.get("annotation_performed"),
        "semantic_mutation_performed": False,
        "production_rewrite_claim_allowed": False,
        "next_step": "unified four-plan rewrite controller or CVPipeline dependency proof after real verifier is available",
    }
    paths["summary_path"].write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {k: str(v) for k, v in paths.items()} | {"summary": summary}
