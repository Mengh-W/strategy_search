#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Restricted HIVM true-rewrite prototype.

This tool intentionally performs *real textual IR rewrites* only for tiny,
explicitly marked positive fixtures.  It is not a production MLIR/HivmOpsEditor
backend.  Its purpose is to move the project beyond dry-run reports by proving
that the pipeline can emit genuinely changed .hivm.mlir files under strict,
auditable patterns.

Safety policy:
- Refuse to mutate unless the input contains a restricted fixture marker or the
  caller passes --allow-unmarked-fixture.
- Only support tiny positive-case patterns with no nested unknown regions.
- Write a machine-readable report with exact changed lines and blockers.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

RESTRICTED_MARKERS = [
    "Restricted Phase-6C",
    "restricted_q_load_hoist_mutation_positive",
    "restricted_gm_roundtrip_deletion_positive",
    "restricted_q_load_in_loop_positive",
    "restricted_gm_roundtrip_positive",
]


def write_json(path: Optional[str], data: Any) -> None:
    if path:
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def has_marker(text: str) -> bool:
    return any(m in text for m in RESTRICTED_MARKERS)


def brace_delta(line: str) -> int:
    # Good enough for tiny fixtures.  Not a full MLIR parser.
    return line.count("{") - line.count("}")


def find_matching_loop_end(lines: List[str], loop_idx: int) -> Optional[int]:
    depth = 0
    started = False
    for i in range(loop_idx, len(lines)):
        depth += brace_delta(lines[i])
        if "{" in lines[i]:
            started = True
        if started and depth <= 0:
            return i
    return None


def _extract_out_buffer(line: str) -> Optional[str]:
    m = re.search(r"outs\(\s*(%[A-Za-z0-9_]+)", line)
    return m.group(1) if m else None


def _line_uses_loop_iv(line: str, iv: str) -> bool:
    return bool(iv and re.search(rf"\b{re.escape(iv)}\b", line))


def rewrite_q_load_hoist(lines: List[str]) -> Tuple[List[str], Dict[str, Any]]:
    """Move a Q_gm load + nd2nz pair immediately before a simple scf.for.

    Pattern:
        scf.for %j = ... {
          hivm.hir.load ins(%Q_gm ...) outs(%q_ub ...)
          hivm.hir.nd2nz ins(%q_ub ...) outs(%q_l1 ...)
          ... no writes to %q_ub / %q_l1 after the pair ...
        }

    This is a true mutation for restricted positive fixtures only.
    """
    actions: List[Dict[str, Any]] = []
    blockers: List[str] = []
    for i, line in enumerate(lines):
        lm = re.search(r"\bscf\.for\s+(%[A-Za-z0-9_]+)\b.*\{", line)
        if not lm:
            continue
        iv = lm.group(1)
        end = find_matching_loop_end(lines, i)
        if end is None:
            blockers.append("no_matching_loop_end")
            continue
        # Find first two non-comment, non-empty lines in loop body.
        body_indices = [j for j in range(i + 1, end) if lines[j].strip() and not lines[j].lstrip().startswith("//")]
        if len(body_indices) < 2:
            continue
        a, b = body_indices[0], body_indices[1]
        load_line = lines[a]
        nd_line = lines[b]
        if not ("hivm.hir.load" in load_line and "%Q_gm" in load_line and "outs(" in load_line):
            continue
        if not ("hivm.hir.nd2nz" in nd_line):
            continue
        q_ub = _extract_out_buffer(load_line)
        q_l1 = _extract_out_buffer(nd_line)
        if not q_ub or not q_l1 or q_ub not in nd_line:
            blockers.append("q_load_nd2nz_buffer_chain_not_proven")
            continue
        if _line_uses_loop_iv(load_line, iv) or _line_uses_loop_iv(nd_line, iv):
            blockers.append("candidate_uses_loop_induction_variable")
            continue
        # Require no later writes to q_ub/q_l1 inside the loop body.
        later = lines[b + 1:end]
        write_pat = re.compile(r"outs\([^\)]*(%[A-Za-z0-9_]+)")
        later_writes: List[Dict[str, Any]] = []
        for k, txt in enumerate(later, start=b + 2):
            if "outs(" in txt:
                for bm in re.finditer(r"%[A-Za-z0-9_]+", txt.split("outs(", 1)[1]):
                    name = bm.group(0)
                    if name in {q_ub, q_l1}:
                        later_writes.append({"line": k, "buffer": name, "text": txt.strip()})
        if later_writes:
            blockers.append("loop_body_writes_q_buffer_after_candidate")
            return lines, {
                "mutation_kind": "q_load_hoist",
                "mutation_performed": False,
                "changed_line_count": 0,
                "blockers": blockers,
                "later_writes": later_writes,
            }
        indent = lines[a][:len(lines[a]) - len(lines[a].lstrip())]
        hoisted = [
            indent + "// [phase6c_true_rewrite] hoisted invariant Q load+nd2nz from simple loop\n",
            load_line,
            nd_line,
        ]
        new_lines = list(lines)
        # Remove b then a to preserve indices.
        del new_lines[b]
        del new_lines[a]
        # Insert before loop line.
        new_lines[i:i] = hoisted
        actions.append({
            "type": "q_load_hoist",
            "loop_line": i + 1,
            "load_line_before": a + 1,
            "nd2nz_line_before": b + 1,
            "inserted_before_loop_line": i + 1,
            "buffers": {"q_ub": q_ub, "q_l1": q_l1},
            "structural_change": "moved two operation lines before scf.for",
        })
        return new_lines, {
            "mutation_kind": "q_load_hoist",
            "mutation_performed": True,
            "changed_line_count": 2,
            "actions": actions,
            "blockers": [],
        }
    return lines, {
        "mutation_kind": "q_load_hoist",
        "mutation_performed": False,
        "changed_line_count": 0,
        "blockers": blockers or ["restricted_q_load_hoist_pattern_not_found"],
    }


def rewrite_gm_roundtrip_delete(lines: List[str]) -> Tuple[List[str], Dict[str, Any]]:
    """Delete a tiny same-GM store+reload pair when the reload destination is unused.

    Pattern:
        load %A_gm -> %tmp_ub
        store %tmp_ub -> %A_gm
        load %A_gm -> %tmp2_ub

    The deletion removes the store and reload only when the second destination is
    unused later.  This is only for restricted positive fixtures.
    """
    blockers: List[str] = []
    for i in range(len(lines) - 2):
        l0, l1, l2 = lines[i], lines[i + 1], lines[i + 2]
        if not ("hivm.hir.load" in l0 and "hivm.hir.store" in l1 and "hivm.hir.load" in l2):
            continue
        gm0 = re.search(r"ins\(\s*(%[A-Za-z0-9_]+).*address_space<gm>", l0)
        ub0 = _extract_out_buffer(l0)
        store_in = re.search(r"ins\(\s*(%[A-Za-z0-9_]+)", l1)
        gm1 = re.search(r"outs\(\s*(%[A-Za-z0-9_]+).*address_space<gm>", l1)
        gm2 = re.search(r"ins\(\s*(%[A-Za-z0-9_]+).*address_space<gm>", l2)
        ub2 = _extract_out_buffer(l2)
        if not (gm0 and ub0 and store_in and gm1 and gm2 and ub2):
            blockers.append("failed_to_parse_store_load_buffers")
            continue
        if not (gm0.group(1) == gm1.group(1) == gm2.group(1)):
            blockers.append("gm_base_mismatch")
            continue
        if store_in.group(1) != ub0:
            blockers.append("store_input_not_loaded_buffer")
            continue
        # The reload dest must be unused after line i+2 for this deletion to be safe in the fixture.
        after = "\n".join(lines[i + 3:])
        if re.search(rf"\b{re.escape(ub2)}\b", after):
            blockers.append("reload_destination_used_later")
            continue
        new_lines = list(lines)
        indent = lines[i + 1][:len(lines[i + 1]) - len(lines[i + 1].lstrip())]
        new_lines[i + 1] = indent + "// [phase6c_true_rewrite] removed restricted redundant GM store round-trip: " + lines[i + 1].strip() + "\n"
        new_lines[i + 2] = indent + "// [phase6c_true_rewrite] removed restricted redundant GM reload: " + lines[i + 2].strip() + "\n"
        return new_lines, {
            "mutation_kind": "gm_roundtrip_deletion",
            "mutation_performed": True,
            "deleted_pair_count": 1,
            "changed_line_count": 2,
            "actions": [{
                "type": "gm_roundtrip_deletion",
                "load_source_line": i + 1,
                "store_deleted_line": i + 2,
                "reload_deleted_line": i + 3,
                "gm": gm0.group(1),
                "tmp_buffer": ub0,
                "reload_buffer": ub2,
                "structural_change": "commented out one store and one reload in restricted fixture",
            }],
            "blockers": [],
        }
    return lines, {
        "mutation_kind": "gm_roundtrip_deletion",
        "mutation_performed": False,
        "deleted_pair_count": 0,
        "changed_line_count": 0,
        "blockers": blockers or ["restricted_gm_roundtrip_pattern_not_found"],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Restricted true HIVM IR rewriter for Phase-6C positive fixtures")
    ap.add_argument("--print-capabilities", action="store_true")
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument("--mutation-kind", choices=["q_load_hoist", "gm_roundtrip_deletion"])
    ap.add_argument("--input")
    ap.add_argument("--output")
    ap.add_argument("--report")
    ap.add_argument("--allow-unmarked-fixture", action="store_true")
    args = ap.parse_args()

    if args.print_capabilities:
        print(json.dumps({
            "backend": "restricted_hivm_true_rewriter_phase6c",
            "backend_kind": "restricted_textual_true_rewriter",
            "is_real_mlir_backend": False,
            "uses_hivmopseditor": False,
            "uses_mlir_operation_walk": False,
            "restricted_true_mutation": True,
            "production_mutation": False,
            "mutate_q_load_hoist": True,
            "mutate_gm_roundtrip_deletion": True,
            "requires_restricted_fixture_marker": True,
        }, ensure_ascii=False))
        return 0

    if not args.mutate:
        write_json(args.report, {"status": "no_mutate_requested"})
        return 0
    if not args.input or not args.output or not args.mutation_kind:
        write_json(args.report, {"status": "failed", "blockers": ["missing_required_input_output_or_mutation_kind"]})
        return 2
    text = Path(args.input).read_text(encoding="utf-8")
    if not args.allow_unmarked_fixture and not has_marker(text):
        Path(args.output).write_text(text, encoding="utf-8")
        write_json(args.report, {
            "schema_version": "restricted_hivm_true_rewrite_report_v1",
            "backend": "restricted_hivm_true_rewriter_phase6c",
            "mutation_kind": args.mutation_kind,
            "mutation_performed": False,
            "production_mutation": False,
            "blockers": ["input_missing_restricted_fixture_marker"],
            "status": "refused_unmarked_input",
        })
        return 1

    lines = text.splitlines(keepends=True)
    if args.mutation_kind == "q_load_hoist":
        new_lines, result = rewrite_q_load_hoist(lines)
    else:
        new_lines, result = rewrite_gm_roundtrip_delete(lines)
    out_text = "".join(new_lines)
    Path(args.output).write_text(out_text, encoding="utf-8")
    report = {
        "schema_version": "restricted_hivm_true_rewrite_report_v1",
        "backend": "restricted_hivm_true_rewriter_phase6c",
        "backend_kind": "restricted_textual_true_rewriter",
        "is_real_mlir_backend": False,
        "uses_hivmopseditor": False,
        "uses_mlir_operation_walk": False,
        "production_mutation": False,
        "restricted_true_mutation": bool(result.get("mutation_performed")),
        "status": "mutated_restricted_fixture" if result.get("mutation_performed") else "no_mutation_performed",
        "input": args.input,
        "output": args.output,
        **result,
        "disclaimer": "This is a real file-level IR mutation for restricted positive fixtures only. It is not a production MLIR/HivmOpsEditor rewrite backend.",
    }
    write_json(args.report, report)
    return 0 if result.get("mutation_performed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
