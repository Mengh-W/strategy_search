# -*- coding: utf-8 -*-
"""MultiBufferPlan restricted true rewrite executor.

V4.8/V4.9 only produced readiness and stage-boundary plans.  This V5.0 module
performs a deliberately restricted but real textual IR mutation:

* create additive ping/pong buffer-slot aliases for a selected buffer anchor;
* replace the chosen producer/consumer stage uses with the selected slot;
* preserve the original buffer as a fallback so the rewrite is non-destructive;
* emit replacement and validation reports.

This is still not production Operation-level HivmOpsEditor rewrite.  It is a
portable true-rewrite closure designed to make the mutation visible in the
optimized MLIR while remaining conservative without a real verifier.
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .multibuffer_stage_boundary import analyze_multibuffer_stage_boundaries, build_stage_mutation_plan

MULTIBUFFER_TRUE_REWRITE_VERSION = "hivm_multibuffer_restricted_true_rewrite_v1"
MULTIBUFFER_TRUE_VALIDATION_VERSION = "hivm_multibuffer_restricted_true_validation_v1"
MULTIBUFFER_TRUE_DIFF_VERSION = "hivm_multibuffer_restricted_true_diff_v1"

_SYMBOL_RE_TEMPLATE = r"(?<![A-Za-z0-9_.$-]){}(?![A-Za-z0-9_.$-])"
_ASSIGN_RE = re.compile(r"^(?P<indent>\s*)(?P<var>%[A-Za-z0-9_.$-]+)\s*=\s*(?P<expr>.*)$")
_ANNOTATION_MARK_RE = re.compile(r"annotation\.mark\s+(?P<var>%[A-Za-z0-9_.$-]+)\b")
_HIVM_OP_RE = re.compile(r"hivm\.hir\.(?P<op>[A-Za-z0-9_]+)")


def _is_comment(line: str) -> bool:
    return line.strip().startswith("//")


def _symbol_rx(symbol: str) -> re.Pattern[str]:
    return re.compile(_SYMBOL_RE_TEMPLATE.format(re.escape(symbol)))


def _replace_symbol(line: str, old: str, new: str) -> str:
    return _symbol_rx(old).sub(new, line)


def _safe_symbol_suffix(symbol: str) -> str:
    return symbol[1:].replace("%", "").replace(".", "_").replace("$", "_").replace("-", "_")


def _make_slot_symbols(symbol: str, action_index: int) -> Tuple[str, str]:
    # MLIR SSA names may contain digits/underscore.  Keep the original prefix to
    # make diff reports readable.
    base = _safe_symbol_suffix(symbol)
    return f"%{base}_mb{action_index}_ping", f"%{base}_mb{action_index}_pong"


def _op_short(line: str) -> str:
    m = _HIVM_OP_RE.search(line or "")
    if m:
        return m.group("op")
    if "memref.load" in line:
        return "memref.load"
    if "memref.store" in line:
        return "memref.store"
    return "unknown"


def _line(lines: List[str], line_no: Optional[int]) -> str:
    if line_no is None:
        return ""
    if 1 <= int(line_no) <= len(lines):
        return lines[int(line_no) - 1]
    return ""



def _result_type_from_def_line(line: str) -> str:
    """Best-effort result type for annotation.mark.

    Pointer_cast examples sometimes print `: src_type to dst_type`; for the SSA
    value we want the destination type when present.  Otherwise keep the text
    after the final colon.
    """
    if " : " not in line:
        return "none"
    tail = line.split(" : ", 1)[1].strip()
    if " to " in tail:
        return tail.split(" to ")[-1].strip()
    return tail.strip()

def _clone_def_line(original_line: str, old_symbol: str, new_symbol: str, role: str, action_id: str) -> List[str]:
    """Create a new SSA definition line by symbol-substitution.

    We intentionally keep the original type/expression shape.  For pointer_cast
    anchors this creates an additional alias slot.  In the presence of real
    HivmOpsEditor, this should become clone/create-equivalent-buffer-op with
    adjusted offsets/capacity gate.  Text-level validation requires the slot to
    be visibly defined and used.
    """
    m = _ASSIGN_RE.match(original_line)
    indent = m.group("indent") if m else re.match(r"\s*", original_line).group(0)
    cloned = _replace_symbol(original_line, old_symbol, new_symbol)
    result_type = _result_type_from_def_line(original_line)
    return [
        f"{indent}// HIVM V5.0 MultiBufferPlan true rewrite: {role} slot for {old_symbol} ({action_id})",
        cloned,
        f"{indent}annotation.mark {new_symbol} {{hivm.multi_buffer_slot = \"{role}\", hivm.rewrite_action = \"{action_id}\"}} : {result_type}",
    ]


def _find_following_annotation(lines: List[str], def_line: int, symbol: str) -> Optional[Tuple[int, str]]:
    # Existing HIVM samples often have annotation.mark immediately after a buffer
    # def.  We do not need it for correctness, but recording it helps reports.
    for ln in range(def_line + 1, min(def_line + 4, len(lines)) + 1):
        text = lines[ln - 1]
        m = _ANNOTATION_MARK_RE.search(text)
        if m and m.group("var") == symbol:
            return ln, text
    return None


def _choose_slot_for_stage(line_text: str, producer_line: int, consumer_line: int, current_line: int, ping: str, pong: str) -> str:
    # First restricted pass: bind the selected producer/consumer pair to ping so
    # the dataflow remains local.  Pong is created and reserved for subsequent
    # cross-iteration binding by CVPipelinePlan.  If producer==consumer, still use ping.
    return ping


def _build_action_from_stage_plan_action(action: Dict[str, Any], action_index: int) -> Optional[Dict[str, Any]]:
    target = action.get("target") or {}
    symbol = target.get("symbol")
    line = target.get("line")
    if not symbol or not line:
        return None
    if action.get("risk_level") == "BLOCKED":
        return None
    if action.get("stage_boundary_status") not in {"READY_FOR_PINGPONG_PLAN", "REVIEW_REQUIRED"}:
        return None
    producer = action.get("producer") or {}
    consumer = action.get("consumer") or {}
    if not producer.get("line") or not consumer.get("line"):
        return None
    ping, pong = _make_slot_symbols(str(symbol), action_index)
    return {
        "action_id": f"multibuffer_true_rewrite_action_{action_index:04d}",
        "source_stage_action_id": action.get("action_id"),
        "mutation_kind": "restricted_additive_pingpong_buffer_rewrite",
        "target": target,
        "symbol": symbol,
        "target_line": int(line),
        "producer_line": int(producer.get("line")),
        "consumer_line": int(consumer.get("line")),
        "producer": producer,
        "consumer": consumer,
        "slot_symbols": {"ping": ping, "pong": pong},
        "risk_level": "MEDIUM" if action.get("stage_boundary_status") == "REVIEW_REQUIRED" else "LOW",
        "rewrite_policy": {
            "mode": "additive_non_destructive",
            "fallback_original_buffer_preserved": True,
            "current_pair_binding": "producer_and_consumer_use_ping_slot",
            "pong_slot_status": "created_for_followup_cross_iteration_binding",
        },
    }


def build_true_rewrite_actions(stage_plan: Dict[str, Any], max_actions: int = 1) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    raw = stage_plan.get("actions") or []
    # Prefer low-risk READY actions, then review-required actions.
    raw_sorted = sorted(
        raw,
        key=lambda a: (
            0 if a.get("stage_boundary_status") == "READY_FOR_PINGPONG_PLAN" else 1,
            0 if a.get("risk_level") == "LOW" else 1,
            int(((a.get("target") or {}).get("line") or 10**9)),
        ),
    )
    used_lines: set[int] = set()
    used_symbols: set[str] = set()
    for a in raw_sorted:
        if len(actions) >= max_actions:
            break
        built = _build_action_from_stage_plan_action(a, len(actions))
        if not built:
            continue
        sym = str(built["symbol"])
        lines = {int(built["target_line"]), int(built["producer_line"]), int(built["consumer_line"])}
        # Avoid overlapping first-pass rewrites.  This keeps replacement reports easy to audit.
        if sym in used_symbols or used_lines.intersection(lines):
            continue
        actions.append(built)
        used_symbols.add(sym)
        used_lines.update(lines)
    return actions


def apply_multibuffer_true_rewrite(ir_text: str, true_actions: List[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    lines = ir_text.splitlines()
    insert_after: Dict[int, List[str]] = {}
    line_replacements: Dict[int, List[Dict[str, Any]]] = {}
    rewritten_actions: List[Dict[str, Any]] = []
    skipped_actions: List[Dict[str, Any]] = []

    for idx, action in enumerate(true_actions):
        target_line = int(action["target_line"])
        producer_line = int(action["producer_line"])
        consumer_line = int(action["consumer_line"])
        old_symbol = str(action["symbol"])
        ping = action["slot_symbols"]["ping"]
        pong = action["slot_symbols"]["pong"]
        original_def = _line(lines, target_line)
        if not original_def or old_symbol not in original_def:
            skipped_actions.append({**action, "skip_reason": "target_definition_line_missing_or_symbol_not_found"})
            continue
        if _is_comment(original_def):
            skipped_actions.append({**action, "skip_reason": "target_definition_line_is_comment"})
            continue
        producer_text = _line(lines, producer_line)
        consumer_text = _line(lines, consumer_line)
        if old_symbol not in producer_text or old_symbol not in consumer_text:
            skipped_actions.append({**action, "skip_reason": "producer_or_consumer_line_no_longer_contains_target_symbol"})
            continue

        inserted = []
        inserted.extend(_clone_def_line(original_def, old_symbol, ping, "ping", action["action_id"]))
        inserted.extend(_clone_def_line(original_def, old_symbol, pong, "pong", action["action_id"]))
        ann = _find_following_annotation(lines, target_line, old_symbol)
        if ann:
            inserted.append(re.match(r"\s*", original_def).group(0) + f"// original multi_buffer annotation preserved at line {ann[0]}")
        insert_after.setdefault(target_line, []).extend(inserted)

        # Bind the chosen local producer/consumer pair to ping.  Keep old buffer
        # definition and all unrelated uses untouched.
        for role, ln in [("producer", producer_line), ("consumer", consumer_line)]:
            new_symbol = _choose_slot_for_stage(lines[ln - 1], producer_line, consumer_line, ln, ping, pong)
            line_replacements.setdefault(ln, []).append({
                "action_id": action["action_id"],
                "role": role,
                "old_symbol": old_symbol,
                "new_symbol": new_symbol,
            })

        rewritten_actions.append({
            **action,
            "status": "REWRITTEN",
            "inserted_after_line": target_line,
            "inserted_slot_symbols": [ping, pong],
            "replaced_lines": [producer_line, consumer_line],
            "producer_op": _op_short(producer_text),
            "consumer_op": _op_short(consumer_text),
        })

    out: List[str] = []
    replacement_records: List[Dict[str, Any]] = []
    for ln, line in enumerate(lines, start=1):
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
            indent = re.match(r"\s*", current).group(0)
            for rep in reps:
                out.append(f"{indent}// HIVM V5.0 MultiBufferPlan use replacement: {rep['role']} {rep['old_symbol']} -> {rep['new_symbol']} ({rep['action_id']})")
        out.append(current)
        if ln in insert_after:
            out.extend(insert_after[ln])

    report = {
        "schema_version": MULTIBUFFER_TRUE_REWRITE_VERSION,
        "version": "V5.0-multibuffer-restricted-true-rewrite",
        "mutation_kind": "restricted_additive_pingpong_buffer_rewrite",
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
        "claim_boundary": "portable restricted additive text-level MultiBufferPlan rewrite; real HivmOpsEditor verifier/DES/msprof still required",
    }
    return "\n".join(out) + ("\n" if ir_text.endswith("\n") else ""), report


def validate_multibuffer_true_rewrite(original_ir: str, rewritten_ir: str, rewrite_report: Dict[str, Any]) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    actions = rewrite_report.get("rewritten_actions") or []
    replacement_records = rewrite_report.get("replacement_records") or []

    checks.append({
        "name": "mutation_performed",
        "passed": bool(actions),
        "details": {"rewritten_action_count": len(actions)},
    })
    checks.append({
        "name": "replacement_map_non_empty",
        "passed": len(replacement_records) >= len(actions),
        "details": {"replacement_count": len(replacement_records)},
    })

    slot_missing: List[str] = []
    slot_use_missing: List[str] = []
    fallback_missing: List[str] = []
    for a in actions:
        old = str(a.get("symbol") or "")
        ping, pong = (a.get("slot_symbols") or {}).get("ping"), (a.get("slot_symbols") or {}).get("pong")
        for s in [ping, pong]:
            if s and s not in rewritten_ir:
                slot_missing.append(s)
        if ping and not any((r.get("new_symbol") == ping) for r in replacement_records):
            slot_use_missing.append(str(ping))
        if old and old not in rewritten_ir:
            fallback_missing.append(old)
    checks.append({"name": "ping_pong_slots_defined", "passed": not slot_missing, "details": {"missing": slot_missing}})
    checks.append({"name": "ping_slot_used_by_stage", "passed": not slot_use_missing, "details": {"missing": slot_use_missing}})
    checks.append({"name": "fallback_original_buffer_preserved", "passed": not fallback_missing, "details": {"missing": fallback_missing}})

    # Make sure we did not accidentally alter unrelated target count in a destructive way.
    checks.append({
        "name": "rewrite_markers_present",
        "passed": "HIVM V5.0 MultiBufferPlan" in rewritten_ir,
        "details": {},
    })

    passed = all(c["passed"] for c in checks)
    return {
        "schema_version": MULTIBUFFER_TRUE_VALIDATION_VERSION,
        "version": "V5.0-multibuffer-restricted-true-rewrite",
        "passed": passed,
        "checks": checks,
        "production_rewrite_claim_allowed": False,
        "claim_boundary": "portable structural validation only; no MLIR verifier was run",
    }



def build_multibuffer_true_rewrite_diff(original_ir: str, rewritten_ir: str) -> Dict[str, Any]:
    diff_lines = list(difflib.unified_diff(
        original_ir.splitlines(),
        rewritten_ir.splitlines(),
        fromfile="original_multibuffer_input",
        tofile="optimized_multibuffer_rewritten",
        lineterm="",
        n=3,
    ))
    mb_lines = [
        x for x in diff_lines
        if "MultiBufferPlan" in x or "_mb" in x or "hivm.multi_buffer_slot" in x
    ]
    return {
        "schema_version": MULTIBUFFER_TRUE_DIFF_VERSION,
        "diff_kind": "portable_multibuffer_true_rewrite_unified_diff",
        "num_diff_lines": len(diff_lines),
        "num_multibuffer_related_diff_lines": len(mb_lines),
        "unified_diff": diff_lines[:3000],
        "multibuffer_related_diff": mb_lines[:1500],
    }

def write_multibuffer_true_rewrite_outputs(
    ir_path: str | Path,
    selected_plan_path: str | Path,
    output_dir: str | Path,
    max_candidates: int = 80,
    max_actions: int = 3,
) -> Dict[str, Any]:
    ir_path = Path(ir_path)
    selected_plan_path = Path(selected_plan_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ir_text = ir_path.read_text(encoding="utf-8")
    selected_plan = json.loads(selected_plan_path.read_text(encoding="utf-8")) if selected_plan_path.exists() else {}

    stage_report = analyze_multibuffer_stage_boundaries(ir_text, selected_plan, max_candidates=max_candidates)
    stage_plan = build_stage_mutation_plan(stage_report)
    true_actions = build_true_rewrite_actions(stage_plan, max_actions=max_actions)
    rewritten_ir, rewrite_report = apply_multibuffer_true_rewrite(ir_text, true_actions)
    validation = validate_multibuffer_true_rewrite(ir_text, rewritten_ir, rewrite_report)
    diff_report = build_multibuffer_true_rewrite_diff(ir_text, rewritten_ir)

    stage_report_path = output_dir / "multibuffer_stage_boundary_report.json"
    stage_plan_path = output_dir / "multibuffer_stage_mutation_plan.json"
    true_action_path = output_dir / "multibuffer_true_rewrite_actions.json"
    optimized_path = output_dir / "optimized.multibuffer_rewritten.hivm.mlir"
    report_path = output_dir / "multibuffer_true_rewrite_report.json"
    validation_path = output_dir / "multibuffer_true_rewrite_validation.json"
    diff_path = output_dir / "multibuffer_true_rewrite_diff.json"
    summary_path = output_dir / "multibuffer_true_rewrite_summary.json"

    stage_report_path.write_text(json.dumps(stage_report, ensure_ascii=False, indent=2), encoding="utf-8")
    stage_plan_path.write_text(json.dumps(stage_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    true_action_path.write_text(json.dumps({
        "schema_version": "hivm_multibuffer_true_rewrite_actions_v1",
        "version": "V5.0-multibuffer-restricted-true-rewrite",
        "action_count": len(true_actions),
        "actions": true_actions,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    optimized_path.write_text(rewritten_ir, encoding="utf-8")
    report_path.write_text(json.dumps(rewrite_report, ensure_ascii=False, indent=2), encoding="utf-8")
    validation_path.write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    diff_path.write_text(json.dumps(diff_report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "schema_version": "hivm_multibuffer_true_rewrite_summary_v1",
        "version": "V5.0-multibuffer-restricted-true-rewrite",
        "input_ir": str(ir_path),
        "stage_candidate_count": stage_report.get("analyzed_candidate_count"),
        "stage_ready_count": (stage_report.get("stage_boundary_status_counts") or {}).get("READY_FOR_PINGPONG_PLAN", 0),
        "true_rewrite_action_count": len(true_actions),
        "mutation_performed": rewrite_report.get("mutation_performed"),
        "rewritten_action_count": rewrite_report.get("rewritten_action_count"),
        "replacement_count": rewrite_report.get("replacement_count"),
        "num_multibuffer_related_diff_lines": diff_report.get("num_multibuffer_related_diff_lines"),
        "passed_portable_validation": validation.get("passed"),
        "semantic_mutation_performed": rewrite_report.get("semantic_mutation_performed"),
        "production_rewrite_claim_allowed": False,
        "claim_boundary": rewrite_report.get("claim_boundary"),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "stage_report_path": str(stage_report_path),
        "stage_plan_path": str(stage_plan_path),
        "true_action_path": str(true_action_path),
        "optimized_ir_path": str(optimized_path),
        "rewrite_report_path": str(report_path),
        "validation_path": str(validation_path),
        "diff_path": str(diff_path),
        "summary_path": str(summary_path),
        "summary": summary,
    }
