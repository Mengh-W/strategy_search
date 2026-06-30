# -*- coding: utf-8 -*-
"""Validation helpers for restricted SyncPlan portable rewrite.

These checks are intentionally lightweight and portable: they do not replace
MLIR/HivmOpsEditor verification.  They answer whether the local restricted
rewrite produced the expected textual structural delta and whether the generated
set/wait events are internally paired.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

SYNC_REWRITE_VALIDATOR_VERSION = "hivm_sync_rewrite_validator_v1"

_PIPE_BARRIER_RE = re.compile(r"hivm\.hir\.pipe_barrier")
_SET_FLAG_RE = re.compile(r"hivm\.hir\.set_flag")
_WAIT_FLAG_RE = re.compile(r"hivm\.hir\.wait_flag")
_GEN_EVENT_RE = re.compile(r"(EVENT_ID_AUTO\d+|%hivm_sync_auto\d+)")


def _count(text: str, pattern: re.Pattern[str]) -> int:
    return len(pattern.findall(text))


def _brace_balance_ok(text: str) -> bool:
    return text.count("{") == text.count("}")


def _generated_event_records(text: str) -> Dict[str, Dict[str, Any]]:
    records: Dict[str, Dict[str, Any]] = {}
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = _GEN_EVENT_RE.search(line)
        if not m:
            continue
        ev = m.group(1)
        rec = records.setdefault(ev, {"set_lines": [], "wait_lines": [], "other_lines": []})
        if "hivm.hir.set_flag" in line:
            rec["set_lines"].append(lineno)
        elif "hivm.hir.wait_flag" in line:
            rec["wait_lines"].append(lineno)
        else:
            rec["other_lines"].append(lineno)
    return records


def validate_restricted_sync_rewrite_texts(original_text: str, rewritten_text: str, rewrite_report: Dict[str, Any]) -> Dict[str, Any]:
    before = {
        "pipe_barrier": _count(original_text, _PIPE_BARRIER_RE),
        "set_flag": _count(original_text, _SET_FLAG_RE),
        "wait_flag": _count(original_text, _WAIT_FLAG_RE),
        "line_count": len(original_text.splitlines()),
    }
    after = {
        "pipe_barrier": _count(rewritten_text, _PIPE_BARRIER_RE),
        "set_flag": _count(rewritten_text, _SET_FLAG_RE),
        "wait_flag": _count(rewritten_text, _WAIT_FLAG_RE),
        "line_count": len(rewritten_text.splitlines()),
    }
    expected_rewrites = int(rewrite_report.get("rewritten_action_count") or 0)
    generated_events = _generated_event_records(rewritten_text)
    event_pair_errors: List[Dict[str, Any]] = []
    for ev, rec in sorted(generated_events.items()):
        if len(rec.get("set_lines", [])) != 1 or len(rec.get("wait_lines", [])) != 1:
            event_pair_errors.append({"event_id": ev, "reason": "generated_event_not_exactly_one_set_and_one_wait", **rec})
        elif rec["set_lines"][0] > rec["wait_lines"][0]:
            event_pair_errors.append({"event_id": ev, "reason": "generated_wait_before_set", **rec})

    delta = {k: after[k] - before[k] for k in before}
    checks = {
        "brace_balance_before_ok": _brace_balance_ok(original_text),
        "brace_balance_after_ok": _brace_balance_ok(rewritten_text),
        # Raw textual pipe_barrier count includes the preserved traceability comment,
        # so the structural check is performed with non-comment counts below.
        "set_flag_increased_by_expected": delta["set_flag"] == expected_rewrites,
        "wait_flag_increased_by_expected": delta["wait_flag"] == expected_rewrites,
        "line_count_increased_by_expected": delta["line_count"] == expected_rewrites,  # 1 line -> comment + set + wait = +2? split removes original line, adds 3 lines => +2 per rewrite. But pipe_barrier count remains in comment, so see below.
        "generated_events_paired": not event_pair_errors,
    }
    # Because the original barrier is preserved in a comment for traceability,
    # the textual pipe_barrier count does not necessarily decrease.  Compute a
    # stricter non-comment count as the actual structural delta.
    def non_comment_count(text: str, pattern: re.Pattern[str]) -> int:
        return sum(1 for line in text.splitlines() if pattern.search(line) and not line.lstrip().startswith("//"))
    before_nc = {"pipe_barrier": non_comment_count(original_text, _PIPE_BARRIER_RE)}
    after_nc = {"pipe_barrier": non_comment_count(rewritten_text, _PIPE_BARRIER_RE)}
    checks["non_comment_pipe_barrier_decreased_by_expected"] = (after_nc["pipe_barrier"] - before_nc["pipe_barrier"]) == -expected_rewrites
    checks["line_count_increased_by_expected"] = delta["line_count"] == 2 * expected_rewrites

    passed = all(bool(v) for v in checks.values()) and bool(rewrite_report.get("mutation_performed")) == (expected_rewrites > 0)
    return {
        "schema_version": SYNC_REWRITE_VALIDATOR_VERSION,
        "validation_kind": "portable_restricted_sync_rewrite_structural_delta",
        "before_counts": before,
        "after_counts": after,
        "before_non_comment_counts": before_nc,
        "after_non_comment_counts": after_nc,
        "delta_counts": delta,
        "expected_rewrites": expected_rewrites,
        "generated_events": generated_events,
        "event_pair_errors": event_pair_errors,
        "checks": checks,
        "passed_portable_validation": passed,
        "production_rewrite_claim_allowed": False,
        "requires_real_hivmopseditor_verify": True,
    }


def validate_restricted_sync_rewrite_files(original_ir: str | Path, rewritten_ir: str | Path, rewrite_report: str | Path, output_report: str | Path) -> Dict[str, Any]:
    original_text = Path(original_ir).read_text(encoding="utf-8")
    rewritten_text = Path(rewritten_ir).read_text(encoding="utf-8")
    report = json.loads(Path(rewrite_report).read_text(encoding="utf-8"))
    validation = validate_restricted_sync_rewrite_texts(original_text, rewritten_text, report)
    Path(output_report).parent.mkdir(parents=True, exist_ok=True)
    Path(output_report).write_text(json.dumps(validation, indent=2, ensure_ascii=False), encoding="utf-8")
    return validation


__all__ = [
    "SYNC_REWRITE_VALIDATOR_VERSION",
    "validate_restricted_sync_rewrite_texts",
    "validate_restricted_sync_rewrite_files",
]
