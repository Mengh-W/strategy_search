# -*- coding: utf-8 -*-
"""Portable sync/event liveness report.

This is a conservative textual report used by the portable SyncPlan rewrite
path.  It does not replace HivmOpsEditor/MLIR/DES verification.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

SYNC_LIVENESS_REPORT_VERSION = "hivm_sync_liveness_report_v1"

_EVENT_ID_RE = re.compile(r"(EVENT_ID[A-Za-z0-9_]*|%hivm_sync_auto\d+|%[A-Za-z_][A-Za-z0-9_$.]*)")
_SET_RE = re.compile(r"hivm\.hir\.set_flag")
_WAIT_RE = re.compile(r"hivm\.hir\.wait_flag")
_PIPE_BARRIER_RE = re.compile(r"hivm\.hir\.pipe_barrier")
_SYNC_BLOCK_RE = re.compile(r"hivm\.hir\.sync_block")
_BRACKET_RE = re.compile(r"\[\s*([^\]]+)\s*\]")
_LEGACY_EVENT_RE = re.compile(r"event\s*=\s*\"?([A-Za-z0-9_%$.]+)\"?")


def _extract_event(line: str) -> str:
    legacy = _LEGACY_EVENT_RE.search(line)
    if legacy:
        return legacy.group(1)
    bracket = _BRACKET_RE.search(line)
    if bracket:
        parts = [p.strip() for p in bracket.group(1).split(",")]
        if len(parts) >= 3:
            return parts[2]
    candidates = _EVENT_ID_RE.findall(line)
    return candidates[-1] if candidates else f"UNKNOWN_EVENT_LINE"


def build_sync_liveness_report(ir_text: str) -> Dict[str, Any]:
    events: Dict[str, Dict[str, Any]] = {}
    sync_ops: List[Dict[str, Any]] = []
    for lineno, line in enumerate(ir_text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        kind = None
        if _SET_RE.search(line):
            kind = "set"
        elif _WAIT_RE.search(line):
            kind = "wait"
        elif _PIPE_BARRIER_RE.search(line):
            kind = "pipe_barrier"
        elif _SYNC_BLOCK_RE.search(line):
            kind = "sync_block"
        if not kind:
            continue
        rec = {"line": lineno, "kind": kind, "text": stripped[:240]}
        sync_ops.append(rec)
        if kind in {"set", "wait"}:
            ev = _extract_event(line)
            slot = events.setdefault(ev, {"set_lines": [], "wait_lines": [], "ops": []})
            slot[f"{kind}_lines"].append(lineno)
            slot["ops"].append(rec)

    event_reports: List[Dict[str, Any]] = []
    blockers: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    for ev, slot in sorted(events.items()):
        set_lines = slot["set_lines"]
        wait_lines = slot["wait_lines"]
        status = "OK_PAIRED" if len(set_lines) >= 1 and len(wait_lines) >= 1 else "UNPAIRED"
        if not set_lines or not wait_lines:
            warnings.append({"event_id": ev, "reason": "event_missing_set_or_wait", "set_lines": set_lines, "wait_lines": wait_lines})
        if set_lines and wait_lines and min(wait_lines) < min(set_lines):
            warnings.append({"event_id": ev, "reason": "wait_before_set_text_order", "set_lines": set_lines, "wait_lines": wait_lines})
        if len(set_lines) > 1 or len(wait_lines) > 1:
            warnings.append({"event_id": ev, "reason": "event_reused_multiple_sets_or_waits_textual", "set_lines": set_lines, "wait_lines": wait_lines})
        event_reports.append({
            "event_id": ev,
            "status": status,
            "set_count": len(set_lines),
            "wait_count": len(wait_lines),
            "set_lines": set_lines,
            "wait_lines": wait_lines,
        })

    return {
        "schema_version": SYNC_LIVENESS_REPORT_VERSION,
        "report_kind": "portable_textual_sync_event_liveness",
        "num_sync_ops": len(sync_ops),
        "num_events": len(events),
        "num_pipe_barrier": sum(1 for x in sync_ops if x["kind"] == "pipe_barrier"),
        "num_sync_block": sum(1 for x in sync_ops if x["kind"] == "sync_block"),
        "event_reports": event_reports[:1000],
        "warnings": warnings[:1000],
        "blockers": blockers,
        "passed_portable_liveness": not blockers,
        "production_rewrite_claim_allowed": False,
        "requires_real_scheduler_or_des_liveness": True,
    }


def write_sync_liveness_report(ir_path: str | Path, output_report: str | Path) -> Dict[str, Any]:
    report = build_sync_liveness_report(Path(ir_path).read_text(encoding="utf-8", errors="replace"))
    Path(output_report).parent.mkdir(parents=True, exist_ok=True)
    Path(output_report).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


__all__ = ["SYNC_LIVENESS_REPORT_VERSION", "build_sync_liveness_report", "write_sync_liveness_report"]
