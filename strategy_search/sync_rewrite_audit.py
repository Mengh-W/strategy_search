# -*- coding: utf-8 -*-
"""Safety and audit helpers for portable SyncPlan rewrite.

The audit layer is intentionally conservative.  It does not prove semantic
correctness; instead it makes every portable/text-level rewrite explainable and
mappable to the future HivmOpsEditor mutation path.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

SYNC_REWRITE_AUDIT_VERSION = "hivm_sync_rewrite_audit_v1"

_PIPE_BARRIER_RE = re.compile(r"^\s*hivm\.hir\.pipe_barrier\s*\[\s*<(?P<pipe>[^>]+)>\s*\]")
_SET_RE = re.compile(r"^\s*hivm\.hir\.set_flag\s*\[\s*<(?P<set>[^>]+)>\s*,\s*<(?P<wait>[^>]+)>\s*,\s*(?P<event>[^\]]+)\]")
_WAIT_RE = re.compile(r"^\s*hivm\.hir\.wait_flag\s*\[\s*<(?P<set>[^>]+)>\s*,\s*<(?P<wait>[^>]+)>\s*,\s*(?P<event>[^\]]+)\]")
_SYNC_BLOCK_RE = re.compile(r"^\s*hivm\.hir\.sync_block")
_SYNC_ANY_RE = re.compile(r"hivm\.hir\.(pipe_barrier|set_flag|wait_flag|sync_block(?:_set|_wait)?)")


def _is_comment(line: str) -> bool:
    return line.strip().startswith("//")


def _normalize_pipe(pipe: Any) -> str:
    p = str(pipe or "").strip().strip('"')
    if p.startswith("<") and p.endswith(">"):
        p = p[1:-1]
    return p or "UNKNOWN_PIPE"


def _count_sync_ops(ir_text: str) -> Dict[str, Any]:
    by_kind = {"pipe_barrier": 0, "set_flag": 0, "wait_flag": 0, "sync_block": 0}
    by_pipe: Dict[str, Dict[str, int]] = {}
    generated_event_count = 0
    lines: List[Dict[str, Any]] = []
    for lineno, line in enumerate(ir_text.splitlines(), start=1):
        if _is_comment(line):
            continue
        kind = None
        pipe = None
        m = _PIPE_BARRIER_RE.search(line)
        if m:
            kind = "pipe_barrier"
            pipe = _normalize_pipe(m.group("pipe"))
        else:
            m = _SET_RE.search(line)
            if m:
                kind = "set_flag"
                pipe = _normalize_pipe(m.group("set"))
                if "EVENT_ID_AUTO" in m.group("event") or "%hivm_sync_auto" in m.group("event"):
                    generated_event_count += 1
            else:
                m = _WAIT_RE.search(line)
                if m:
                    kind = "wait_flag"
                    pipe = _normalize_pipe(m.group("wait"))
                    if "EVENT_ID_AUTO" in m.group("event") or "%hivm_sync_auto" in m.group("event"):
                        generated_event_count += 1
                elif _SYNC_BLOCK_RE.search(line):
                    kind = "sync_block"
                    pipe = "SYNC_BLOCK"
        if not kind:
            continue
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_pipe.setdefault(pipe or "UNKNOWN_PIPE", {}).setdefault(kind, 0)
        by_pipe[pipe or "UNKNOWN_PIPE"][kind] += 1
        lines.append({"line": lineno, "kind": kind, "pipe": pipe, "text": line.strip()[:240]})
    return {
        "by_kind": by_kind,
        "by_pipe": by_pipe,
        "generated_event_reference_count": generated_event_count,
        "sync_lines": lines[:2000],
    }


def _barrier_lines(ir_text: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for lineno, line in enumerate(ir_text.splitlines(), start=1):
        if _is_comment(line):
            continue
        m = _PIPE_BARRIER_RE.search(line)
        if m:
            out.append({"line": lineno, "pipe": _normalize_pipe(m.group("pipe")), "text": line.strip()[:240]})
    return out


def _contract_actions(contract: Dict[str, Any]) -> List[Dict[str, Any]]:
    actions = contract.get("actions", [])
    return [a for a in actions if isinstance(a, dict)]


def _action_line(action: Dict[str, Any]) -> int | None:
    target = action.get("target") if isinstance(action.get("target"), dict) else {}
    anchor = target.get("anchor") if isinstance(target.get("anchor"), dict) else {}
    value = action.get("_rewrite_line") or anchor.get("line")
    try:
        return int(value)
    except Exception:
        return None


def _action_pipe(action: Dict[str, Any]) -> str:
    if action.get("_rewrite_pipe"):
        return _normalize_pipe(action.get("_rewrite_pipe"))
    target = action.get("target") if isinstance(action.get("target"), dict) else {}
    norm = target.get("normalized_barrier") if isinstance(target.get("normalized_barrier"), dict) else {}
    return _normalize_pipe(norm.get("set_pipe") or norm.get("pipe"))


def _neighborhood(lines: List[str], line_no: int, radius: int = 2) -> List[Dict[str, Any]]:
    start = max(1, line_no - radius)
    end = min(len(lines), line_no + radius)
    out: List[Dict[str, Any]] = []
    for ln in range(start, end + 1):
        text = lines[ln - 1]
        if _SYNC_ANY_RE.search(text) and not _is_comment(text):
            out.append({"line": ln, "text": text.strip()[:240]})
    return out


def _risk_for_action(action: Dict[str, Any], original_lines: List[str], all_barriers: List[Dict[str, Any]], rewritten_ids: set[str]) -> Dict[str, Any]:
    action_id = str(action.get("action_id") or "")
    line_no = _action_line(action)
    pipe = _action_pipe(action)
    reasons: List[str] = []
    blockers: List[str] = []
    warnings: List[str] = []

    if action.get("mutation_kind") != "barrier_to_directional_event_pair":
        blockers.append("unsupported_mutation_kind")
    if line_no is None:
        blockers.append("missing_text_line_anchor")
    if pipe == "PIPE_ALL":
        blockers.append("pipe_all_requires_global_dependency_proof")
    if pipe == "UNKNOWN_PIPE":
        blockers.append("unknown_pipe")

    if pipe in {"PIPE_MTE2", "PIPE_MTE3", "PIPE_MTE1"}:
        reasons.append("memory_transfer_pipe_barrier_candidate")
    elif pipe == "PIPE_V":
        warnings.append("vector_pipe_barrier_candidate_requires_compute_dependency_review")
    elif pipe.startswith("PIPE_"):
        warnings.append("non_standard_or_less_common_pipe_review_required")

    neighborhood: List[Dict[str, Any]] = []
    if line_no is not None:
        neighborhood = _neighborhood(original_lines, line_no, radius=2)
        if len(neighborhood) > 1:
            warnings.append("nearby_sync_ops_within_two_lines")
        prev_next = [b for b in all_barriers if b["line"] != line_no and abs(b["line"] - line_no) <= 3]
        if prev_next:
            warnings.append("consecutive_or_dense_pipe_barrier_region")

    if action_id not in rewritten_ids:
        warnings.append("not_rewritten_in_current_run")

    if blockers:
        level = "BLOCKED"
    elif pipe in {"PIPE_MTE2", "PIPE_MTE3", "PIPE_MTE1"} and not warnings:
        level = "LOW"
    elif pipe in {"PIPE_MTE2", "PIPE_MTE3", "PIPE_MTE1"}:
        level = "MEDIUM"
    elif pipe == "PIPE_V":
        level = "MEDIUM"
    else:
        level = "HIGH"

    return {
        "action_id": action.get("action_id"),
        "line": line_no,
        "pipe": pipe,
        "risk_level": level,
        "risk_reasons": reasons,
        "warnings": warnings,
        "blockers": blockers,
        "nearby_sync_context": neighborhood,
        "rewrite_status": "rewritten" if action_id in rewritten_ids else "not_rewritten",
        "portable_rewrite_rule": "pipe_barrier_to_same_pipe_set_wait_pair" if level != "BLOCKED" else "blocked",
        "hivmopseditor_migration": {
            "target_lookup": "Operation line/source-location + op kind hivm.hir.pipe_barrier",
            "api_sequence": [
                "editor.addSetFlagWaitFlagBefore(target, setPipe, waitPipe, eventAttr)",
                "editor.deleteOp(target)",
                "editor.exportToFile(outputPath)",
                "mlir::verify(*module)",
            ],
            "must_be_verified_by_real_backend": True,
        },
    }


def build_sync_rewrite_audit(
    original_text: str,
    rewritten_text: str,
    contract: Dict[str, Any],
    rewrite_report: Dict[str, Any],
    validation_report: Dict[str, Any] | None = None,
    before_liveness: Dict[str, Any] | None = None,
    after_liveness: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build an audit report for portable SyncPlan rewrite."""
    original_lines = original_text.splitlines()
    barriers = _barrier_lines(original_text)
    before_counts = _count_sync_ops(original_text)
    after_counts = _count_sync_ops(rewritten_text)
    rewritten_actions = rewrite_report.get("rewritten_actions", []) if isinstance(rewrite_report, dict) else []
    rewritten_ids = {str(a.get("action_id")) for a in rewritten_actions if isinstance(a, dict)}
    barrier_actions = [a for a in _contract_actions(contract) if a.get("mutation_kind") == "barrier_to_directional_event_pair"]
    action_audits = [_risk_for_action(a, original_lines, barriers, rewritten_ids) for a in barrier_actions]

    risk_counts: Dict[str, int] = {}
    for item in action_audits:
        risk_counts[item["risk_level"]] = risk_counts.get(item["risk_level"], 0) + 1

    before_kind = before_counts["by_kind"]
    after_kind = after_counts["by_kind"]
    structural_delta = {
        "pipe_barrier_delta": after_kind.get("pipe_barrier", 0) - before_kind.get("pipe_barrier", 0),
        "set_flag_delta": after_kind.get("set_flag", 0) - before_kind.get("set_flag", 0),
        "wait_flag_delta": after_kind.get("wait_flag", 0) - before_kind.get("wait_flag", 0),
        "sync_block_delta": after_kind.get("sync_block", 0) - before_kind.get("sync_block", 0),
        "expected_set_wait_delta_from_rewrite": int(rewrite_report.get("rewritten_action_count", 0) or 0),
    }
    structural_delta["delta_matches_rewrite_count"] = (
        structural_delta["pipe_barrier_delta"] == -structural_delta["expected_set_wait_delta_from_rewrite"]
        and structural_delta["set_flag_delta"] == structural_delta["expected_set_wait_delta_from_rewrite"]
        and structural_delta["wait_flag_delta"] == structural_delta["expected_set_wait_delta_from_rewrite"]
    )

    generated_events = [a.get("event_id") for a in rewritten_actions if isinstance(a, dict)]
    unique_generated_events = sorted({str(e) for e in generated_events if e})
    event_naming = {
        "generated_event_count": len(generated_events),
        "unique_generated_event_count": len(unique_generated_events),
        "all_generated_events_unique": len(generated_events) == len(unique_generated_events),
        "generated_events_preview": unique_generated_events[:50],
    }

    migration_actions = [
        {
            "action_id": a.get("action_id"),
            "line": a.get("line"),
            "pipe": a.get("pipe"),
            "event_id": a.get("event_id"),
            "operation_level_target": "hivm.hir.pipe_barrier",
            "hivmopseditor_api_sequence": ["addSetFlagWaitFlagBefore", "deleteOp", "exportToFile", "verify"],
        }
        for a in rewritten_actions if isinstance(a, dict)
    ]

    validation_passed = bool((validation_report or {}).get("passed_portable_validation", False))
    liveness_after_passed = bool((after_liveness or {}).get("passed_portable_liveness", False))
    audit_passed = bool(rewrite_report.get("mutation_performed")) and structural_delta["delta_matches_rewrite_count"] and event_naming["all_generated_events_unique"]

    batch_warnings: List[str] = []
    rewritten_count = int(rewrite_report.get("rewritten_action_count", 0) or 0)
    if rewritten_count > 50:
        batch_warnings.append("large_batch_rewrite_requires_real_backend_regression_before_claim")
    if risk_counts.get("BLOCKED", 0):
        batch_warnings.append("some_contract_barrier_actions_are_blocked_and_must_not_be_mutated")
    if not validation_passed:
        batch_warnings.append("portable_structural_validation_not_passed")
    if not liveness_after_passed:
        batch_warnings.append("portable_liveness_after_not_passed")

    return {
        "schema_version": SYNC_REWRITE_AUDIT_VERSION,
        "audit_kind": "portable_syncplan_rewrite_safety_audit",
        "production_rewrite_claim_allowed": False,
        "audit_decision": "PORTABLE_REWRITE_AUDITED_NOT_PRODUCTION" if audit_passed else "PORTABLE_REWRITE_AUDIT_FAILED_OR_INCOMPLETE",
        "claim_boundary": "text-level portable rewrite audit only; real HivmOpsEditor parse/verify/DES/msprof still required",
        "before_sync_counts": before_counts["by_kind"],
        "after_sync_counts": after_counts["by_kind"],
        "before_sync_by_pipe": before_counts["by_pipe"],
        "after_sync_by_pipe": after_counts["by_pipe"],
        "structural_delta": structural_delta,
        "event_naming": event_naming,
        "risk_counts": risk_counts,
        "batch_warnings": batch_warnings,
        "candidate_action_count": len(barrier_actions),
        "rewritten_action_count": rewrite_report.get("rewritten_action_count"),
        "skipped_action_count": rewrite_report.get("skipped_action_count"),
        "action_audit": action_audits[:5000],
        "hivmopseditor_migration_action_list": migration_actions[:5000],
        "audit_passed_portable_level": audit_passed,
        "validation_passed_portable_level": validation_passed,
        "liveness_after_passed_portable_level": liveness_after_passed,
    }


def write_sync_rewrite_audit_report(
    original_ir: str | Path,
    rewritten_ir: str | Path,
    contract_path: str | Path,
    rewrite_report_path: str | Path,
    validation_report_path: str | Path | None,
    before_liveness_path: str | Path | None,
    after_liveness_path: str | Path | None,
    output_report: str | Path,
) -> Dict[str, Any]:
    def read_json(path: str | Path | None) -> Dict[str, Any]:
        if not path:
            return {}
        p = Path(path)
        if not p.exists():
            return {}
        return json.loads(p.read_text(encoding="utf-8"))

    report = build_sync_rewrite_audit(
        Path(original_ir).read_text(encoding="utf-8", errors="replace"),
        Path(rewritten_ir).read_text(encoding="utf-8", errors="replace"),
        read_json(contract_path),
        read_json(rewrite_report_path),
        read_json(validation_report_path),
        read_json(before_liveness_path),
        read_json(after_liveness_path),
    )
    Path(output_report).parent.mkdir(parents=True, exist_ok=True)
    Path(output_report).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


__all__ = [
    "SYNC_REWRITE_AUDIT_VERSION",
    "build_sync_rewrite_audit",
    "write_sync_rewrite_audit_report",
]
