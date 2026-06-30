# -*- coding: utf-8 -*-
"""V5.9 syntax/schedule hardening for four-plan operation rewrite outputs.

This pass is still portable/textual; it does not replace the official Linux
MLIR/HIVM parser or verifier.  Its job is to remove obvious textual blockers
introduced by previous MVP rewrites before handing the candidate to Linux.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

_ADDR_RE = re.compile(r"#hivm\.address_space<(?P<space>[A-Za-z0-9_]+)>(?!>)")
_BRACKET_EVENT_RE = re.compile(
    r"(?P<indent>\s*)hivm\.hir\.(?P<op>wait_flag|set_flag)\[<PIPE_(?P<src>[A-Za-z0-9_]+)>,\s*<PIPE_(?P<dst>[A-Za-z0-9_]+)>,\s*(?P<event>[A-Za-z0-9_.$-]+)\]"
)
_SIMPLE_BRACKET_EVENT_RE = re.compile(
    r"(?P<indent>\s*)hivm\.hir\.(?P<op>wait_flag|set_flag)\[<PIPE_(?P<src>[A-Za-z0-9_]+)>,\s*(?P<event>[A-Za-z0-9_.$-]+)\]"
)


def repair_memref_address_space_closures(text: str) -> Tuple[str, Dict[str, Any]]:
    """Fix a common MVP textual bug: memref types missing the outer '>'.

    Example before:
      memref<32x64xf16, #hivm.address_space<ub>, memref<...>
    Example after:
      memref<32x64xf16, #hivm.address_space<ub>>, memref<...>
    """
    repairs: List[Dict[str, Any]] = []
    new_lines: List[str] = []
    for ln, line in enumerate(text.splitlines(), start=1):
        before = line
        after = _ADDR_RE.sub(lambda m: f"#hivm.address_space<{m.group('space')}>>", line)
        if after != before:
            repairs.append({"line": ln, "before": before.strip()[:220], "after": after.strip()[:220]})
        new_lines.append(after)
    return "\n".join(new_lines) + ("\n" if text.endswith("\n") else ""), {
        "schema_version": "hivm_v59_memref_closure_repair_report_v1",
        "mutation_performed": bool(repairs),
        "repair_count": len(repairs),
        "repairs": repairs[:200],
    }


def normalize_bracket_event_ops(text: str) -> Tuple[str, Dict[str, Any]]:
    """Normalize V5.5 bracket-style events back to attr-style HIVM op syntax.

    The original sample uses attr-style ``hivm.hir.wait_flag {pipe=...,event=...}``.
    The bracket style is useful for a report, but it is more likely to be rejected
    by a real HIVM parser.  We preserve producer/consumer pipe information as
    attributes while restoring a normal operation form.
    """
    rewrites: List[Dict[str, Any]] = []
    new_lines: List[str] = []
    for ln, line in enumerate(text.splitlines(), start=1):
        m = _BRACKET_EVENT_RE.match(line)
        if m:
            pipe = m.group("dst") if m.group("op") == "wait_flag" else m.group("src")
            new_line = (
                f"{m.group('indent')}hivm.hir.{m.group('op')} "
                f"{{pipe=\"{pipe}\", event=\"{m.group('event')}\", "
                f"producer_pipe=\"{m.group('src')}\", consumer_pipe=\"{m.group('dst')}\", "
                f"hivm.v59_event_normalized=true}}"
            )
            rewrites.append({"line": ln, "from": line.strip(), "to": new_line.strip()})
            new_lines.append(new_line)
            continue
        m2 = _SIMPLE_BRACKET_EVENT_RE.match(line)
        if m2:
            new_line = f"{m2.group('indent')}hivm.hir.{m2.group('op')} {{pipe=\"{m2.group('src')}\", event=\"{m2.group('event')}\", hivm.v59_event_normalized=true}}"
            rewrites.append({"line": ln, "from": line.strip(), "to": new_line.strip()})
            new_lines.append(new_line)
            continue
        new_lines.append(line)
    return "\n".join(new_lines) + ("\n" if text.endswith("\n") else ""), {
        "schema_version": "hivm_v59_event_op_normalization_report_v1",
        "mutation_performed": bool(rewrites),
        "rewrite_count": len(rewrites),
        "rewrites": rewrites[:200],
    }


def _line_comment_stripped(line: str) -> str:
    return line.split("//", 1)[0]


def audit_v59_textual_legality(text: str) -> Dict[str, Any]:
    code_lines = [_line_comment_stripped(x) for x in text.splitlines()]
    code = "\n".join(code_lines)
    malformed_memref_lines: List[Dict[str, Any]] = []
    bracket_event_lines: List[Dict[str, Any]] = []
    placeholder_lines: List[Dict[str, Any]] = []
    for ln, raw in enumerate(code_lines, start=1):
        if "#hivm.address_space<" in raw and re.search(r"#hivm\.address_space<[A-Za-z0-9_]+>(?!>)", raw):
            malformed_memref_lines.append({"line": ln, "text": raw.strip()[:220]})
        if "hivm.hir.wait_flag[" in raw or "hivm.hir.set_flag[" in raw:
            bracket_event_lines.append({"line": ln, "text": raw.strip()[:220]})
        if any(tok in raw for tok in ["<PIPE_", "D_tile", "propagate_from_input"]):
            placeholder_lines.append({"line": ln, "text": raw.strip()[:220]})
    blockers: List[Dict[str, Any]] = []
    if malformed_memref_lines:
        blockers.append({"kind": "malformed_nested_memref_address_space", "detail": malformed_memref_lines[:80]})
    if bracket_event_lines:
        blockers.append({"kind": "bracket_style_event_ops", "detail": bracket_event_lines[:80]})
    # D_tile and propagate markers inside comments are OK; in code they are blockers.
    if placeholder_lines:
        blockers.append({"kind": "unlowered_code_placeholder", "detail": placeholder_lines[:80]})
    return {
        "schema_version": "hivm_v59_textual_legality_audit_v1",
        "passed_v59_textual_legality_audit": not blockers,
        "malformed_memref_line_count": len(malformed_memref_lines),
        "bracket_event_line_count": len(bracket_event_lines),
        "unlowered_code_placeholder_line_count": len(placeholder_lines),
        "blockers": blockers,
        "linux_compile_ready_claim": False,
        "backend_validation_required": True,
    }


def write_v59_hardening_reports(input_ir: str | Path, output_dir: str | Path) -> Dict[str, Any]:
    p = Path(input_ir)
    out = Path(output_dir)
    text = p.read_text(encoding="utf-8", errors="ignore")
    text1, memref_report = repair_memref_address_space_closures(text)
    text2, event_report = normalize_bracket_event_ops(text1)
    final_path = out / "optimized.four_plan_operation_rewrite.v59_syntax_hardened.hivm.mlir"
    final_path.write_text(text2, encoding="utf-8")
    audit = audit_v59_textual_legality(text2)
    (out / "v59_memref_closure_repair_report.json").write_text(json.dumps(memref_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "v59_event_op_normalization_report.json").write_text(json.dumps(event_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "v59_textual_legality_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"v59_syntax_hardened_ir": str(final_path), "memref_closure_repair": memref_report, "event_op_normalization": event_report, "textual_legality_audit": audit}
