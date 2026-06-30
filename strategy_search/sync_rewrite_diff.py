# -*- coding: utf-8 -*-
"""Diff helpers for portable SyncPlan rewrite outputs."""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Any, Dict, List

SYNC_REWRITE_DIFF_VERSION = "hivm_sync_rewrite_diff_v1"

_SYNC_OP_RE = re.compile(r"hivm\.hir\.(pipe_barrier|set_flag|wait_flag|sync_block(?:_set|_wait)?)")


def sync_rewrite_diff_report(original_text: str, rewritten_text: str, *, fromfile: str = "original", tofile: str = "rewritten") -> Dict[str, Any]:
    diff_lines = list(difflib.unified_diff(
        original_text.splitlines(),
        rewritten_text.splitlines(),
        fromfile=fromfile,
        tofile=tofile,
        lineterm="",
        n=3,
    ))
    sync_related = [ln for ln in diff_lines if _SYNC_OP_RE.search(ln) or "restricted SyncPlan rewrite" in ln]
    return {
        "schema_version": SYNC_REWRITE_DIFF_VERSION,
        "diff_kind": "portable_sync_rewrite_unified_diff",
        "num_diff_lines": len(diff_lines),
        "num_sync_related_diff_lines": len(sync_related),
        "unified_diff": diff_lines[:2000],
        "sync_related_diff": sync_related[:1000],
    }


def write_sync_rewrite_diff_report(original_ir: str | Path, rewritten_ir: str | Path, output_report: str | Path) -> Dict[str, Any]:
    original_path = Path(original_ir)
    rewritten_path = Path(rewritten_ir)
    report = sync_rewrite_diff_report(
        original_path.read_text(encoding="utf-8", errors="replace"),
        rewritten_path.read_text(encoding="utf-8", errors="replace"),
        fromfile=str(original_path),
        tofile=str(rewritten_path),
    )
    Path(output_report).parent.mkdir(parents=True, exist_ok=True)
    Path(output_report).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


__all__ = ["SYNC_REWRITE_DIFF_VERSION", "sync_rewrite_diff_report", "write_sync_rewrite_diff_report"]
