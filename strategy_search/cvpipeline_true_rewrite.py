# -*- coding: utf-8 -*-
"""CVPipelinePlan restricted true rewrite executor.

V4.10 produced a stage planner only.  V5.1 performs a deliberately restricted
but visible IR mutation for CVPipelinePlan:

* identify load/view -> compute -> store pipeline windows;
* insert explicit SyncPlan event edges between load->compute and compute->store;
* wrap the selected window with pipeline-group markers;
* optionally bind visible MultiBuffer ping slot symbols already present in the IR;
* emit optimized MLIR, rewrite report, validation, and diff.

This is not production HivmOpsEditor operation-level scheduling.  It is a
portable true-rewrite closure: the output MLIR is actually changed and the
pipeline synchronization structure is visible, while risky operation movement,
loop skewing, and prologue/steady/epilogue cloning are left to the real backend.
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .cvpipeline_stage_planner import analyze_cvpipeline_stages, build_cvpipeline_rewrite_plan

CVPIPELINE_TRUE_REWRITE_VERSION = "hivm_cvpipeline_restricted_true_rewrite_v1"
CVPIPELINE_TRUE_VALIDATION_VERSION = "hivm_cvpipeline_restricted_true_validation_v1"
CVPIPELINE_TRUE_DIFF_VERSION = "hivm_cvpipeline_restricted_true_diff_v1"

_SYMBOL_RE = re.compile(r"%[A-Za-z0-9_.$-]+")
_MB_PING_RE = re.compile(r"(?P<sym>%[A-Za-z0-9_.$-]+_mb\d+_ping)\b")
_MB_PONG_RE = re.compile(r"(?P<sym>%[A-Za-z0-9_.$-]+_mb\d+_pong)\b")


def _line(lines: List[str], line_no: Optional[int]) -> str:
    if line_no is None:
        return ""
    try:
        line_no = int(line_no)
    except Exception:
        return ""
    if 1 <= line_no <= len(lines):
        return lines[line_no - 1]
    return ""


def _indent_of(line: str) -> str:
    m = re.match(r"\s*", line or "")
    return m.group(0) if m else ""


def _symbol_rx(symbol: str) -> re.Pattern[str]:
    return re.compile(r"(?<![A-Za-z0-9_.$-]){}(?![A-Za-z0-9_.$-])".format(re.escape(symbol)))


def _replace_symbol(line: str, old: str, new: str) -> str:
    return _symbol_rx(old).sub(new, line)


def _collect_multibuffer_slots(ir_text: str) -> Dict[str, Dict[str, str]]:
    """Return base-symbol -> {ping,pong} best-effort map from V5.0 slot names."""
    slots: Dict[str, Dict[str, str]] = {}
    for m in _MB_PING_RE.finditer(ir_text):
        ping = m.group("sym")
        base = re.sub(r"_mb\d+_ping$", "", ping)
        slots.setdefault(base, {})["ping"] = ping
    for m in _MB_PONG_RE.finditer(ir_text):
        pong = m.group("sym")
        base = re.sub(r"_mb\d+_pong$", "", pong)
        slots.setdefault(base, {})["pong"] = pong
    return slots


def _choose_slot_binding_for_action(action: Dict[str, Any], ir_text: str) -> Optional[Dict[str, Any]]:
    """Best-effort: find a ping/pong slot whose base symbol appears in action segments."""
    slots = _collect_multibuffer_slots(ir_text)
    if not slots:
        return None
    symbols: List[str] = []
    for seg in ((action.get("stage_segments") or {}).values()):
        if isinstance(seg, dict):
            # The compact rewrite plan does not carry symbols.  Fall back to line-span text below.
            pass
    # Fallback: choose first available slot; V5.1 is deliberately restricted and reports this as best-effort.
    for base, pair in sorted(slots.items()):
        if pair.get("ping") and pair.get("pong"):
            return {"base_symbol": base, "ping": pair["ping"], "pong": pair["pong"], "binding_policy": "best_effort_existing_multibuffer_slot"}
    return None


def build_cvpipeline_true_rewrite_actions(stage_plan: Dict[str, Any], ir_text: str, max_actions: int = 1) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    raw = stage_plan.get("actions") or []
    raw_sorted = sorted(
        raw,
        key=lambda a: (
            0 if a.get("risk_level") == "LOW" else 1,
            int((a.get("line_span") or [10**9])[0] or 10**9),
        ),
    )
    used_spans: List[Tuple[int, int]] = []
    for idx, a in enumerate(raw_sorted):
        if len(actions) >= max_actions:
            break
        if a.get("status") != "STAGE_PLANNED_NOT_MUTATED":
            continue
        if a.get("risk_level") not in {"LOW", "MEDIUM"}:
            continue
        span = a.get("line_span") or []
        if len(span) != 2 or not span[0] or not span[1]:
            continue
        start, end = int(span[0]), int(span[1])
        if any(not (end < s or start > e) for s, e in used_spans):
            continue
        segs = a.get("stage_segments") or {}
        load_span = ((segs.get("load_or_view") or {}).get("line_span") or [])
        compute_span = ((segs.get("compute") or {}).get("line_span") or [])
        store_span = ((segs.get("store") or {}).get("line_span") or [])
        if len(load_span) != 2 or len(compute_span) != 2 or len(store_span) != 2:
            continue
        slot_binding = _choose_slot_binding_for_action(a, ir_text)
        action_id = f"cvpipeline_true_rewrite_action_{len(actions):04d}"
        actions.append({
            "action_id": action_id,
            "source_stage_action_id": a.get("action_id"),
            "mutation_kind": "restricted_pipeline_sync_and_slot_binding_rewrite",
            "risk_level": a.get("risk_level"),
            "window_id": a.get("window_id"),
            "line_span": [start, end],
            "stage_line_spans": {
                "load_or_view": [int(load_span[0]), int(load_span[1])],
                "compute": [int(compute_span[0]), int(compute_span[1])],
                "store": [int(store_span[0]), int(store_span[1])],
            },
            "events": {
                "load_to_compute": f"EVENT_ID_CVP_L2C_{len(actions)}",
                "compute_to_store": f"EVENT_ID_CVP_C2S_{len(actions)}",
            },
            "pipes": {
                "load_to_compute": {"set_pipe": "PIPE_MTE2", "wait_pipe": "PIPE_V"},
                "compute_to_store": {"set_pipe": "PIPE_V", "wait_pipe": "PIPE_MTE3"},
            },
            "slot_binding": slot_binding,
            "rewrite_policy": {
                "mode": "additive_pipeline_sync_edges_with_optional_slot_binding",
                "operation_movement": False,
                "loop_skewing": False,
                "prologue_steady_epilogue_materialization": "metadata_and_sync_edges_only",
            },
            "reasons": a.get("reasons", []),
            "warnings": a.get("warnings", []),
        })
        used_spans.append((start, end))
    return actions


def _sync_lines_after_load(indent: str, action: Dict[str, Any]) -> List[str]:
    e = action["events"]["load_to_compute"]
    p = action["pipes"]["load_to_compute"]
    return [
        f"{indent}// HIVM V5.1 CVPipelinePlan sync edge: load_to_compute ({action['action_id']})",
        f"{indent}hivm.hir.set_flag[<{p['set_pipe']}>, <{p['wait_pipe']}>, {e}]",
    ]


def _sync_lines_before_compute(indent: str, action: Dict[str, Any]) -> List[str]:
    e = action["events"]["load_to_compute"]
    p = action["pipes"]["load_to_compute"]
    return [
        f"{indent}// HIVM V5.1 CVPipelinePlan wait edge: load_to_compute ({action['action_id']})",
        f"{indent}hivm.hir.wait_flag[<{p['set_pipe']}>, <{p['wait_pipe']}>, {e}]",
    ]


def _sync_lines_after_compute(indent: str, action: Dict[str, Any]) -> List[str]:
    e = action["events"]["compute_to_store"]
    p = action["pipes"]["compute_to_store"]
    return [
        f"{indent}// HIVM V5.1 CVPipelinePlan sync edge: compute_to_store ({action['action_id']})",
        f"{indent}hivm.hir.set_flag[<{p['set_pipe']}>, <{p['wait_pipe']}>, {e}]",
    ]


def _sync_lines_before_store(indent: str, action: Dict[str, Any]) -> List[str]:
    e = action["events"]["compute_to_store"]
    p = action["pipes"]["compute_to_store"]
    return [
        f"{indent}// HIVM V5.1 CVPipelinePlan wait edge: compute_to_store ({action['action_id']})",
        f"{indent}hivm.hir.wait_flag[<{p['set_pipe']}>, <{p['wait_pipe']}>, {e}]",
    ]


def apply_cvpipeline_true_rewrite(ir_text: str, true_actions: List[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    lines = ir_text.splitlines()
    insert_before: Dict[int, List[str]] = {}
    insert_after: Dict[int, List[str]] = {}
    line_replacements: Dict[int, List[Dict[str, Any]]] = {}
    rewritten_actions: List[Dict[str, Any]] = []
    skipped_actions: List[Dict[str, Any]] = []

    for action in true_actions:
        spans = action.get("stage_line_spans") or {}
        load_start, load_end = spans.get("load_or_view", [None, None])
        compute_start, compute_end = spans.get("compute", [None, None])
        store_start, store_end = spans.get("store", [None, None])
        if not all([load_start, load_end, compute_start, compute_end, store_start, store_end]):
            skipped_actions.append({**action, "skip_reason": "missing_stage_line_span"})
            continue
        if max(load_end, compute_end, store_end) > len(lines):
            skipped_actions.append({**action, "skip_reason": "line_span_out_of_range"})
            continue
        indent = _indent_of(_line(lines, int(load_start)))
        insert_before.setdefault(int(load_start), []).extend([
            f"{indent}// HIVM V5.1 CVPipelinePlan group begin: {action['action_id']} window={action.get('window_id')}",
            f"{indent}//   restricted=true operation_movement=false loop_skewing=false",
        ])
        insert_after.setdefault(int(load_end), []).extend(_sync_lines_after_load(indent, action))
        insert_before.setdefault(int(compute_start), []).extend(_sync_lines_before_compute(indent, action))
        insert_after.setdefault(int(compute_end), []).extend(_sync_lines_after_compute(indent, action))
        insert_before.setdefault(int(store_start), []).extend(_sync_lines_before_store(indent, action))
        insert_after.setdefault(int(store_end), []).extend([
            f"{indent}// HIVM V5.1 CVPipelinePlan group end: {action['action_id']}",
        ])

        # Optional binding: if V5.0 MultiBuffer slots are visible, bind first symbol appearance inside
        # selected stage lines to ping for load/compute and preserve pong for follow-up pipeline skew.
        binding = action.get("slot_binding") or {}
        base, ping = binding.get("base_symbol"), binding.get("ping")
        replacement_lines: List[int] = []
        if base and ping:
            for ln in range(int(load_start), int(store_end) + 1):
                text = _line(lines, ln)
                if base in text and ping not in text and not text.strip().startswith("//"):
                    line_replacements.setdefault(ln, []).append({
                        "action_id": action["action_id"],
                        "old_symbol": base,
                        "new_symbol": ping,
                        "role": "pipeline_slot_binding_ping",
                    })
                    replacement_lines.append(ln)
                    # Keep this restricted: at most two local replacements per action.
                    if len(replacement_lines) >= 2:
                        break
        rewritten_actions.append({
            **action,
            "status": "REWRITTEN",
            "inserted_sync_edges": ["load_to_compute", "compute_to_store"],
            "inserted_event_count": 4,
            "slot_binding_replacement_lines": replacement_lines,
        })

    out: List[str] = []
    replacement_records: List[Dict[str, Any]] = []
    for ln, line in enumerate(lines, start=1):
        for extra in insert_before.get(ln, []):
            out.append(extra)
        current = line
        reps = line_replacements.get(ln, [])
        for rep in reps:
            before = current
            current = _replace_symbol(current, rep["old_symbol"], rep["new_symbol"])
            replacement_records.append({
                **rep,
                "line": ln,
                "before": before.strip()[:400],
                "after": current.strip()[:400],
            })
        if reps:
            indent = _indent_of(current)
            for rep in reps:
                out.append(f"{indent}// HIVM V5.1 CVPipelinePlan slot binding: {rep['old_symbol']} -> {rep['new_symbol']} ({rep['action_id']})")
        out.append(current)
        for extra in insert_after.get(ln, []):
            out.append(extra)

    report = {
        "schema_version": CVPIPELINE_TRUE_REWRITE_VERSION,
        "version": "V5.1-cvpipeline-restricted-true-rewrite",
        "mutation_kind": "restricted_pipeline_sync_and_slot_binding_rewrite",
        "mutation_performed": bool(rewritten_actions),
        "requested_action_count": len(true_actions),
        "rewritten_action_count": len(rewritten_actions),
        "skipped_action_count": len(skipped_actions),
        "rewritten_actions": rewritten_actions,
        "skipped_actions": skipped_actions,
        "replacement_records": replacement_records,
        "replacement_count": len(replacement_records),
        "semantic_mutation_performed": bool(rewritten_actions),
        "production_rewrite_claim_allowed": False,
        "claim_boundary": "portable restricted text-level CVPipelinePlan rewrite; inserts official-style EVENT_ID sync edges and optional slot binding but does not move operations or perform loop skewing",
    }
    return "\n".join(out) + ("\n" if ir_text.endswith("\n") else ""), report


def validate_cvpipeline_true_rewrite(original_ir: str, rewritten_ir: str, rewrite_report: Dict[str, Any]) -> Dict[str, Any]:
    actions = rewrite_report.get("rewritten_actions") or []
    checks: List[Dict[str, Any]] = []
    checks.append({"name": "mutation_performed", "passed": bool(actions), "details": {"rewritten_action_count": len(actions)}})
    missing_events: List[str] = []
    for a in actions:
        for e in (a.get("events") or {}).values():
            if e not in rewritten_ir:
                missing_events.append(e)
    checks.append({"name": "pipeline_events_inserted", "passed": not missing_events, "details": {"missing_events": missing_events}})
    set_count = rewritten_ir.count("CVPipelinePlan sync edge")
    wait_count = rewritten_ir.count("CVPipelinePlan wait edge")
    checks.append({"name": "load_compute_and_compute_store_edges_present", "passed": set_count >= 2 * len(actions) and wait_count >= 2 * len(actions), "details": {"sync_edge_markers": set_count, "wait_edge_markers": wait_count}})
    checks.append({"name": "pipeline_group_markers_present", "passed": rewritten_ir.count("CVPipelinePlan group begin") >= len(actions) and rewritten_ir.count("CVPipelinePlan group end") >= len(actions), "details": {}})
    # We do not require slot replacement because the input may not have run V5.0; if it did, report it.
    checks.append({"name": "slot_binding_optional_and_reported", "passed": True, "details": {"replacement_count": rewrite_report.get("replacement_count", 0)}})
    passed = all(c["passed"] for c in checks)
    return {
        "schema_version": CVPIPELINE_TRUE_VALIDATION_VERSION,
        "version": "V5.1-cvpipeline-restricted-true-rewrite",
        "passed": passed,
        "checks": checks,
        "production_rewrite_claim_allowed": False,
        "claim_boundary": "portable structural validation only; no MLIR verifier/DES/msprof was run",
    }


def build_cvpipeline_true_rewrite_diff(original_ir: str, rewritten_ir: str) -> Dict[str, Any]:
    diff_lines = list(difflib.unified_diff(
        original_ir.splitlines(), rewritten_ir.splitlines(),
        fromfile="original_cvpipeline_input", tofile="optimized_cvpipeline_rewritten", lineterm="", n=3,
    ))
    cv_lines = [x for x in diff_lines if "CVPipelinePlan" in x or "hivm_cvp_" in x or "set_flag" in x or "wait_flag" in x]
    return {
        "schema_version": CVPIPELINE_TRUE_DIFF_VERSION,
        "diff_kind": "portable_cvpipeline_true_rewrite_unified_diff",
        "num_diff_lines": len(diff_lines),
        "num_cvpipeline_related_diff_lines": len(cv_lines),
        "unified_diff": diff_lines[:3000],
        "cvpipeline_related_diff": cv_lines[:1500],
    }


def write_cvpipeline_true_rewrite_outputs(
    ir_path: str | Path,
    selected_plan_path: str | Path,
    output_dir: str | Path,
    max_windows: int = 50,
    max_actions: int = 2,
) -> Dict[str, Any]:
    ir_path = Path(ir_path)
    selected_plan_path = Path(selected_plan_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ir_text = ir_path.read_text(encoding="utf-8")
    selected_plan = json.loads(selected_plan_path.read_text(encoding="utf-8")) if selected_plan_path.exists() else {}

    stage_report = analyze_cvpipeline_stages(ir_text, selected_plan, max_windows=max_windows)
    stage_plan = build_cvpipeline_rewrite_plan(stage_report)
    true_actions = build_cvpipeline_true_rewrite_actions(stage_plan, ir_text, max_actions=max_actions)
    rewritten_ir, rewrite_report = apply_cvpipeline_true_rewrite(ir_text, true_actions)
    validation = validate_cvpipeline_true_rewrite(ir_text, rewritten_ir, rewrite_report)
    diff_report = build_cvpipeline_true_rewrite_diff(ir_text, rewritten_ir)

    paths = {
        "stage_report_path": output_dir / "cvpipeline_stage_report.json",
        "stage_plan_path": output_dir / "cvpipeline_rewrite_plan.json",
        "true_action_path": output_dir / "cvpipeline_true_rewrite_actions.json",
        "optimized_ir_path": output_dir / "optimized.cvpipeline_rewritten.hivm.mlir",
        "rewrite_report_path": output_dir / "cvpipeline_true_rewrite_report.json",
        "validation_path": output_dir / "cvpipeline_true_rewrite_validation.json",
        "diff_path": output_dir / "cvpipeline_true_rewrite_diff.json",
        "summary_path": output_dir / "cvpipeline_true_rewrite_summary.json",
    }
    paths["stage_report_path"].write_text(json.dumps(stage_report, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["stage_plan_path"].write_text(json.dumps(stage_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["true_action_path"].write_text(json.dumps({
        "schema_version": "hivm_cvpipeline_true_rewrite_actions_v1",
        "version": "V5.1-cvpipeline-restricted-true-rewrite",
        "action_count": len(true_actions),
        "actions": true_actions,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["optimized_ir_path"].write_text(rewritten_ir, encoding="utf-8")
    paths["rewrite_report_path"].write_text(json.dumps(rewrite_report, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["validation_path"].write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["diff_path"].write_text(json.dumps(diff_report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "schema_version": "hivm_cvpipeline_true_rewrite_summary_v1",
        "version": "V5.1-cvpipeline-restricted-true-rewrite",
        "input_ir": str(ir_path),
        "pipeline_window_count": stage_report.get("pipeline_window_count"),
        "pipeline_window_status_counts": stage_report.get("pipeline_window_status_counts"),
        "stage_plan_action_count": stage_plan.get("action_count"),
        "true_rewrite_action_count": len(true_actions),
        "mutation_performed": rewrite_report.get("mutation_performed"),
        "rewritten_action_count": rewrite_report.get("rewritten_action_count"),
        "replacement_count": rewrite_report.get("replacement_count"),
        "num_cvpipeline_related_diff_lines": diff_report.get("num_cvpipeline_related_diff_lines"),
        "passed_portable_validation": validation.get("passed"),
        "semantic_mutation_performed": rewrite_report.get("semantic_mutation_performed"),
        "production_rewrite_claim_allowed": False,
        "claim_boundary": rewrite_report.get("claim_boundary"),
    }
    paths["summary_path"].write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {k: str(v) for k, v in paths.items()} | {"summary": summary}
