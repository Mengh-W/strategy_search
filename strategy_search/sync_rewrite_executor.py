# -*- coding: utf-8 -*-
"""Restricted SyncPlan rewrite executor.

This module intentionally implements a *conservative, text-level* SyncPlan
mutation for local end-to-end plumbing.  It is not a replacement for the real
vTriton/HivmOpsEditor mutation path.

Supported V4.3 mutation:
  * selected pipe_barrier actions from sync_precision_contract.json;
  * only hivm.hir.pipe_barrier[...] textual anchors;
  * no PIPE_ALL by default;
  * at most one action by default;
  * replaces the barrier line with an official-syntax-like set_flag/wait_flag
    pair using a freshly generated EVENT_ID-style event attribute name.

Why this is useful:
  * proves SyncPlan can go from selected_plan -> contract -> mutated MLIR;
  * gives a concrete optimized.sync_rewritten.mlir artifact for inspection;
  * keeps production claims blocked until HivmOpsEditor verifies the same idea.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

SYNC_REWRITE_EXECUTOR_VERSION = "hivm_sync_rewrite_executor_v2"

_PIPE_BARRIER_RE = re.compile(r"^(?P<indent>\s*)hivm\.hir\.pipe_barrier\s*\[\s*<(?P<pipe>[^>]+)>\s*\](?P<suffix>.*)$")


def _load_json(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _normalize_pipe(pipe: str | None) -> str | None:
    if not pipe:
        return None
    p = str(pipe).strip().strip('"').strip()
    if p.startswith("<") and p.endswith(">"):
        p = p[1:-1]
    return p


def _line_from_barrier_action(action: Dict[str, Any]) -> int | None:
    target = action.get("target") if isinstance(action.get("target"), dict) else {}
    anchor = target.get("anchor") if isinstance(target.get("anchor"), dict) else {}
    line = anchor.get("line")
    if isinstance(line, int):
        return line
    try:
        return int(line)
    except Exception:
        return None


def _pipe_from_barrier_action(action: Dict[str, Any]) -> str | None:
    target = action.get("target") if isinstance(action.get("target"), dict) else {}
    norm = target.get("normalized_barrier") if isinstance(target.get("normalized_barrier"), dict) else {}
    return _normalize_pipe(norm.get("set_pipe") or norm.get("pipe"))


def select_rewritable_sync_actions(
    contract: Dict[str, Any],
    *,
    max_actions: int = 1,
    allow_pipe_all: bool = False,
) -> List[Dict[str, Any]]:
    """Return the restricted subset of barrier actions that this executor can mutate."""
    selected: List[Dict[str, Any]] = []
    for action in contract.get("actions", []):
        if not isinstance(action, dict):
            continue
        if action.get("mutation_kind") != "barrier_to_directional_event_pair":
            continue
        line = _line_from_barrier_action(action)
        pipe = _pipe_from_barrier_action(action)
        if not line or not pipe:
            continue
        if pipe == "PIPE_ALL" and not allow_pipe_all:
            continue
        chosen = dict(action)
        chosen["_rewrite_line"] = line
        chosen["_rewrite_pipe"] = pipe
        selected.append(chosen)
        if len(selected) >= max_actions:
            break
    return selected


def apply_restricted_sync_rewrite(
    ir_text: str,
    contract: Dict[str, Any],
    *,
    max_actions: int = 1,
    allow_pipe_all: bool = False,
    event_prefix: str = "EVENT_ID_AUTO",
) -> Tuple[str, Dict[str, Any]]:
    """Apply the restricted SyncPlan pipe_barrier lowering/emulation.

    The generated set/wait pair uses official bracket-style syntax:
      hivm.hir.set_flag[<PIPE_X>, <PIPE_X>, EVENT_ID_AUTO0]
      hivm.hir.wait_flag[<PIPE_X>, <PIPE_X>, EVENT_ID_AUTO0]

    This is deliberately marked as an emulation/prototype rather than an
    optimizing production lowering.
    """
    actions = select_rewritable_sync_actions(contract, max_actions=max_actions, allow_pipe_all=allow_pipe_all)
    lines = ir_text.splitlines()
    rewritten: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    # Map 1-indexed line to action.
    by_line: Dict[int, Dict[str, Any]] = {int(a["_rewrite_line"]): a for a in actions}
    out_lines: List[str] = []
    event_id = 0
    for line_no, line in enumerate(lines, start=1):
        action = by_line.get(line_no)
        if not action:
            out_lines.append(line)
            continue
        m = _PIPE_BARRIER_RE.match(line)
        if not m:
            skipped.append({
                "action_id": action.get("action_id"),
                "line": line_no,
                "reason": "target_line_not_pipe_barrier_text_anchor",
                "text": line.strip()[:240],
            })
            out_lines.append(line)
            continue
        pipe = _normalize_pipe(m.group("pipe")) or action.get("_rewrite_pipe")
        if pipe == "PIPE_ALL" and not allow_pipe_all:
            skipped.append({
                "action_id": action.get("action_id"),
                "line": line_no,
                "reason": "pipe_all_not_allowed_in_restricted_rewrite",
                "text": line.strip()[:240],
            })
            out_lines.append(line)
            continue
        ev = f"{event_prefix}{event_id}"
        event_id += 1
        indent = m.group("indent") or ""
        out_lines.append(f"{indent}// HIVM V4.3 restricted SyncPlan rewrite: original {line.strip()}")
        out_lines.append(f"{indent}hivm.hir.set_flag[<{pipe}>, <{pipe}>, {ev}]")
        out_lines.append(f"{indent}hivm.hir.wait_flag[<{pipe}>, <{pipe}>, {ev}]")
        rewritten.append({
            "action_id": action.get("action_id"),
            "mutation_kind": action.get("mutation_kind"),
            "line": line_no,
            "original": line.strip(),
            "replacement": [
                f"hivm.hir.set_flag[<{pipe}>, <{pipe}>, {ev}]",
                f"hivm.hir.wait_flag[<{pipe}>, <{pipe}>, {ev}]",
            ],
            "event_id": ev,
            "pipe": pipe,
        })
    report = {
        "schema_version": SYNC_REWRITE_EXECUTOR_VERSION,
        "rewrite_kind": "portable_sync_pipe_barrier_to_set_wait_pair",
        "contract_schema_version": contract.get("schema_version"),
        "requested_action_count": len(actions),
        "rewritten_action_count": len(rewritten),
        "skipped_action_count": len(skipped),
        "rewritten_actions": rewritten,
        "skipped_actions": skipped,
        "mutation_performed": bool(rewritten),
        "production_rewrite_claim_allowed": False,
        "requires_real_backend_followup": True,
        "safety_boundary": [
            "text-level restricted rewrite only; not MLIR Operation mutation",
            "same-pipe set/wait pair is a conservative barrier-emulation anchor, not a proven optimization",
            "event id is emitted as an EVENT_ID-style bracket attribute rather than an undefined SSA value",
            "supports multi-action rewriting under max_actions policy; each action remains independently traceable",
            "PIPE_ALL is skipped by default",
            "real HivmOpsEditor must reparse, roundtrip, verify, and run DES/trace before production claim",
        ],
    }
    return "\n".join(out_lines) + ("\n" if ir_text.endswith("\n") else ""), report


def apply_restricted_sync_rewrite_from_files(
    ir_path: str | Path,
    contract_path: str | Path,
    output_ir_path: str | Path,
    report_path: str | Path,
    *,
    max_actions: int = 1,
    allow_pipe_all: bool = False,
) -> Dict[str, Any]:
    ir_text = Path(ir_path).read_text(encoding="utf-8")
    contract = _load_json(contract_path)
    new_text, report = apply_restricted_sync_rewrite(ir_text, contract, max_actions=max_actions, allow_pipe_all=allow_pipe_all)
    Path(output_ir_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_ir_path).write_text(new_text, encoding="utf-8")
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


__all__ = [
    "SYNC_REWRITE_EXECUTOR_VERSION",
    "select_rewritable_sync_actions",
    "apply_restricted_sync_rewrite",
    "apply_restricted_sync_rewrite_from_files",
]
