# -*- coding: utf-8 -*-
"""V5.7 Linux precompile audit for four-plan operation rewrite outputs.

This module is deliberately conservative.  It does not claim that a textual HIVM
candidate can replace the official Linux MLIR/HIVM verifier.  Instead it catches
portable issues that would almost certainly block backend compilation, and it
produces a concrete blocker list before the file is handed to Ascend Linux.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple
from strategy_search.operation_rewrite.syntax_hardening_v59 import write_v59_hardening_reports

VERSION = "V5.7-linux-precompile-audit"

_DEF_RE = re.compile(r"(?<![A-Za-z0-9_.$-])(%[A-Za-z_][A-Za-z0-9_.$-]*)\s*=")
_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_.$-])(%[A-Za-z_][A-Za-z0-9_.$-]*)\b")
_MEMREF_USE_RE = re.compile(r"(?P<name>%[A-Za-z_][A-Za-z0-9_.$-]*)\s*:\s*(?P<type>memref<[^>]+>)")
_FUNC_ARG_RE = re.compile(r"(?P<name>%[A-Za-z_][A-Za-z0-9_.$-]*)\s*:\s*(?P<type>memref<[^>]+>)")
_ALLOC_RE = re.compile(r"(?P<name>%[A-Za-z_][A-Za-z0-9_.$-]*)\s*=\s*memref\.alloc\(\)\s*:\s*(?P<type>memref<[^>]+>)")
_FUNC_SIG_RE = re.compile(r"func\.func\s+@[^(]+\((?P<args>.*?)\)\s*\{", re.S)

COMMENT_PREFIXES = ("//", "#")


def _strip_line_comment(line: str) -> str:
    idx = line.find("//")
    return line[:idx] if idx >= 0 else line


def _line_no_ranges(text: str) -> Iterable[Tuple[int, str]]:
    for i, line in enumerate(text.splitlines(), start=1):
        yield i, line


def _collect_defs(text: str) -> Dict[str, List[int]]:
    defs: Dict[str, List[int]] = {}
    for ln, line in _line_no_ranges(text):
        code = _strip_line_comment(line)
        for m in _DEF_RE.finditer(code):
            defs.setdefault(m.group(1), []).append(ln)
    return defs


def _collect_tokens(text: str) -> Dict[str, List[int]]:
    tokens: Dict[str, List[int]] = {}
    for ln, line in _line_no_ranges(text):
        code = _strip_line_comment(line)
        for m in _TOKEN_RE.finditer(code):
            tokens.setdefault(m.group(1), []).append(ln)
    return tokens


def _collect_func_args(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    m = _FUNC_SIG_RE.search(text)
    if not m:
        return out
    args = m.group("args")
    for mm in _FUNC_ARG_RE.finditer(args):
        out[mm.group("name")] = mm.group("type")
    return out


def _collect_alloc_types(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for line in text.splitlines():
        code = _strip_line_comment(line)
        m = _ALLOC_RE.search(code)
        if m:
            out[m.group("name")] = m.group("type")
    return out


def _split_top_level_commas(s: str) -> List[str]:
    out: List[str] = []
    cur: List[str] = []
    depth = 0
    for ch in s:
        if ch == "<":
            depth += 1
        elif ch == ">" and depth > 0:
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur).strip())
    return [x for x in out if x]


def _collect_use_types(text: str) -> Dict[str, Dict[str, List[int]]]:
    uses: Dict[str, Dict[str, List[int]]] = {}
    # Parse the dominant HIVM operation syntax: ins(%a, %b : memref<...>, memref<...>)
    # and outs(%x : memref<...>).  This avoids false positives from assigning the
    # first type in a multi-operand list to every operand.
    group_re = re.compile(r"(?:ins|outs)\((?P<body>[^)]*)\)")
    for ln, line in _line_no_ranges(text):
        code = _strip_line_comment(line)
        for gm in group_re.finditer(code):
            body = gm.group("body")
            if ":" not in body:
                continue
            left, right = body.split(":", 1)
            vars_ = _TOKEN_RE.findall(left)
            types = re.findall(r"memref<[^>]+>", right)
            if not vars_ or not types:
                continue
            if len(types) == 1 and len(vars_) > 1:
                # Some synthetic examples use one shared type; apply it to all vars.
                types = types * len(vars_)
            for name, typ in zip(vars_, types):
                uses.setdefault(name, {}).setdefault(typ, []).append(ln)
        # Do not parse arbitrary ``%x : memref`` fragments here: HIVM operation
        # operand lists are typed positionally after a shared colon, and generic
        # regex matching creates false mismatches for multi-operand ops.
    return uses


def _extract_dims(memref_type: str) -> List[int]:
    m = re.search(r"memref<([^x>]+(?:x[^x>]+)*)x(?:f16|f32|i\d+|index)", memref_type)
    if not m:
        return []
    dims: List[int] = []
    for p in m.group(1).split("x"):
        try:
            dims.append(int(p))
        except Exception:
            pass
    return dims


def infer_problem_bounds_from_signature(text: str) -> Dict[str, int]:
    """Infer conservative M/N/K symbols from common FA-like function args.

    For the sample FA style:
      Q_gm: M x D
      K_gm: S x D
      V_gm: S x D
      O_gm: M x D
    We expose M, N and K symbols only as backend validation constants.  They are
    not a substitute for official axis analysis.
    """
    args = _collect_func_args(text)
    q = next((t for n, t in args.items() if n.lower().startswith("%q")), None)
    k = next((t for n, t in args.items() if n.lower().startswith("%k")), None)
    o = next((t for n, t in args.items() if n.lower().startswith("%o")), None)
    qd = _extract_dims(q or "")
    kd = _extract_dims(k or "")
    od = _extract_dims(o or "")
    bounds: Dict[str, int] = {}
    if qd:
        bounds["M"] = qd[0]
        if len(qd) > 1:
            bounds["D"] = qd[1]
    # FA-like convention used by the sample:
    #   Q: M x D_head, K/V: N_seq x D_head, O: M x D_out.
    # TilingPlan uses tile_m for M, tile_n for sequence/N, tile_k for reduction/head D.
    if kd:
        bounds["N"] = kd[0]
        if len(kd) > 1:
            bounds["K"] = kd[1]
    elif qd and len(qd) > 1:
        bounds["K"] = qd[1]
    if od and len(od) > 1:
        bounds.setdefault("D", od[1])
    return bounds



def remove_duplicate_identical_allocs(text: str) -> Tuple[str, Dict[str, Any]]:
    """Remove repeated identical memref.alloc definitions for the same SSA value.

    This fixes a common interaction between CVPipeline slot binding and
    MultiBuffer slot creation where both stages emit the same alloc line.  Only
    byte-identical name/type alloc duplicates are removed; non-identical duplicate
    SSA definitions remain blockers for the audit.
    """
    seen: set[Tuple[str, str]] = set()
    removed: List[Dict[str, Any]] = []
    new_lines: List[str] = []
    for ln, line in _line_no_ranges(text):
        m = _ALLOC_RE.search(_strip_line_comment(line))
        if m:
            key = (m.group("name"), m.group("type"))
            if key in seen:
                removed.append({"line": ln, "value": key[0], "type": key[1]})
                new_lines.append(re.match(r"\s*", line).group(0) + f"// HIVM V5.7 precompile hardening: removed duplicate identical alloc for {key[0]}")
                continue
            seen.add(key)
        new_lines.append(line)
    return "\n".join(new_lines) + ("\n" if text.endswith("\n") else ""), {"mutation_performed": bool(removed), "removed_duplicate_allocs": removed}

def _extract_selected_tile_constants_from_comments(text: str) -> Dict[str, int]:
    m = re.search(r"tile_m=(?P<m>\d+)\s+tile_n=(?P<n>\d+)\s+tile_k=(?P<k>\d+)", text)
    if not m:
        return {}
    return {"tile_m": int(m.group("m")), "tile_n": int(m.group("n")), "tile_k": int(m.group("k"))}


def materialize_missing_index_constants(text: str, bounds: Dict[str, int] | None = None) -> Tuple[str, Dict[str, Any]]:
    """Insert arith.constant definitions for V5.6/V5.7 tiling symbols if missing.

    This is only a precompile hardening step for textual candidates.  If the
    official HIVM dialect uses a different constant syntax, Linux backend should
    replace this with HivmOpsEditor-built constants.
    """
    bounds = bounds or infer_problem_bounds_from_signature(text)
    selected_tiles = _extract_selected_tile_constants_from_comments(text)
    tokens = _collect_tokens(text)
    defs = _collect_defs(text)
    needed: Dict[str, int] = {}
    symbolic_defaults = {"%cM": bounds.get("M"), "%cN": bounds.get("N"), "%cK": bounds.get("K"), "%c0": 0}
    # The sample HIVM uses %cE/%cB as sequence-loop end/block symbols.  For
    # precompile handoff we materialize conservative constants when they are
    # otherwise undefined; official axis binding may override these on Linux.
    symbolic_defaults["%cE"] = bounds.get("N")
    symbolic_defaults["%cB"] = selected_tiles.get("tile_n") or bounds.get("N")
    for raw, val in symbolic_defaults.items():
        if raw in tokens and raw not in defs and val is not None:
            needed[raw] = int(val)
    # Tile step constants such as %c32/%c64/%c128.
    for tok in tokens:
        m = re.fullmatch(r"%c(\d+)", tok)
        if m and tok not in defs:
            needed[tok] = int(m.group(1))
    if not needed:
        return text, {"mutation_performed": False, "inserted_constants": {}, "bounds": bounds}
    lines = text.splitlines()
    insert_at = None
    func_indent = "    "
    for i, line in enumerate(lines):
        if "func.func" in line and line.rstrip().endswith("{"):
            insert_at = i + 1
            func_indent = re.match(r"\s*", line).group(0) + "  "
            break
    if insert_at is None:
        return text, {"mutation_performed": False, "inserted_constants": {}, "bounds": bounds, "blocker": "no_func_body_anchor"}
    const_lines = [f"{func_indent}// HIVM V5.7 precompile hardening: materialized tiling/index constants"]
    for name, val in sorted(needed.items(), key=lambda kv: (len(kv[0]), kv[0])):
        const_lines.append(f"{func_indent}{name} = arith.constant {val} : index")
    new_lines = lines[:insert_at] + const_lines + lines[insert_at:]
    return "\n".join(new_lines) + ("\n" if text.endswith("\n") else ""), {
        "mutation_performed": True,
        "inserted_constants": needed,
        "bounds": bounds,
        "note": "Portable textual constant materialization; replace with official HivmOpsEditor constants in production if needed.",
    }



def harmonize_operand_types_to_declarations(text: str) -> Tuple[str, Dict[str, Any]]:
    """Rewrite HIVM ins/outs operand type lists to match declared SSA memref types.

    The V5.6 textual shape rewrite may update allocs but leave some operation
    signatures with stale positional memref types.  This pass fixes only the
    type annotations for already-declared values; it does not change operands,
    operation order, or buffer semantics.
    """
    declarations = {**_collect_func_args(text), **_collect_alloc_types(text)}
    group_re = re.compile(r"(?P<head>(?:ins|outs)\()(?P<body>[^)]*)(?P<tail>\))")
    rewrites: List[Dict[str, Any]] = []

    def fix_group(match: re.Match, line_no: int) -> str:
        body = match.group("body")
        if ":" not in body:
            return match.group(0)
        left, right = body.split(":", 1)
        vars_ = _TOKEN_RE.findall(left)
        types = re.findall(r"memref<[^>]+>", right)
        if not vars_ or not types:
            return match.group(0)
        if len(types) == 1 and len(vars_) > 1:
            types = types * len(vars_)
        if len(types) != len(vars_):
            return match.group(0)
        changed = False
        new_types: List[str] = []
        for var, typ in zip(vars_, types):
            declared = declarations.get(var)
            if declared and declared != typ:
                rewrites.append({"line": line_no, "value": var, "from_type": typ, "to_type": declared})
                new_types.append(declared)
                changed = True
            else:
                new_types.append(typ)
        if not changed:
            return match.group(0)
        return f"{match.group('head')}{left} : {', '.join(new_types)}{match.group('tail')}"

    new_lines: List[str] = []
    for ln, line in _line_no_ranges(text):
        code_comment_split = line.split("//", 1)
        code = code_comment_split[0]
        comment = "//" + code_comment_split[1] if len(code_comment_split) > 1 else ""
        def repl(m: re.Match) -> str:
            return fix_group(m, ln)
        new_code = group_re.sub(repl, code)
        new_lines.append(new_code + comment)
    return "\n".join(new_lines) + ("\n" if text.endswith("\n") else ""), {"mutation_performed": bool(rewrites), "rewritten_operand_type_count": len(rewrites), "rewrites": rewrites[:200]}

def audit_linux_precompile_candidate(text: str) -> Dict[str, Any]:
    defs = _collect_defs(text)
    tokens = _collect_tokens(text)
    func_args = _collect_func_args(text)
    defined = set(defs) | set(func_args)
    duplicate_defs = {k: v for k, v in defs.items() if len(v) > 1}
    # Constants in comments are stripped; func args are counted as defined.
    undefined_tokens = {k: sorted(set(v)) for k, v in tokens.items() if k not in defined and not re.fullmatch(r"%[A-Z]", k)}

    alloc_types = _collect_alloc_types(text)
    use_types = _collect_use_types(text)
    type_mismatches: List[Dict[str, Any]] = []
    for name, declared_type in {**func_args, **alloc_types}.items():
        typed_uses = use_types.get(name, {})
        for use_type, lines in typed_uses.items():
            if use_type != declared_type:
                type_mismatches.append({"value": name, "declared_type": declared_type, "use_type": use_type, "lines": lines[:20]})

    required_markers = [
        "TilingPlan semantic operation rewrite",
        "MultiBufferPlan true rewrite",
        "CVPipelinePlan sync edge",
        "SyncPlan operation rewrite",
    ]
    marker_checks = {m: (m in text) for m in required_markers}
    brace_balanced = text.count("{") == text.count("}")

    blockers: List[Dict[str, Any]] = []
    if not brace_balanced:
        blockers.append({"kind": "brace_balance", "detail": {"open": text.count("{"), "close": text.count("}")}})
    if duplicate_defs:
        blockers.append({"kind": "duplicate_ssa_definition", "detail": duplicate_defs})
    if undefined_tokens:
        blockers.append({"kind": "undefined_ssa_or_symbol", "detail": undefined_tokens})
    if type_mismatches:
        blockers.append({"kind": "memref_type_mismatch", "detail": type_mismatches[:50]})
    missing_markers = [k for k, v in marker_checks.items() if not v]
    if missing_markers:
        blockers.append({"kind": "missing_four_plan_marker", "detail": missing_markers})

    passed = not blockers
    return {
        "schema_version": "hivm_v57_linux_precompile_audit_v1",
        "version": VERSION,
        "passed_portable_precompile_audit": passed,
        "linux_compile_ready_claim": False,
        "backend_validation_required": True,
        "brace_balanced": brace_balanced,
        "marker_checks": marker_checks,
        "duplicate_ssa_definition_count": len(duplicate_defs),
        "undefined_symbol_count": len(undefined_tokens),
        "memref_type_mismatch_count": len(type_mismatches),
        "blockers": blockers,
        "note": "If this audit passes, the candidate is only precompile-audit-clean. Linux MLIR/HIVM parse/verifier/backend compile/correctness/msprof are still mandatory.",
    }


def write_v57_precompile_audit_outputs(input_ir: str | Path, output_dir: str | Path) -> Dict[str, Any]:
    p = Path(input_ir)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    text = p.read_text(encoding="utf-8", errors="ignore")
    dedup_text, dedup_report = remove_duplicate_identical_allocs(text)
    const_text, const_report = materialize_missing_index_constants(dedup_text)
    hardened_text, type_harmonize_report = harmonize_operand_types_to_declarations(const_text)
    hardened = out / "optimized.four_plan_operation_rewrite.precompile_hardened.hivm.mlir"
    hardened.write_text(hardened_text, encoding="utf-8")
    audit = audit_linux_precompile_candidate(hardened_text)
    v59_outputs = write_v59_hardening_reports(hardened, out)
    (out / "v57_deduplicate_alloc_report.json").write_text(json.dumps(dedup_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "v57_constant_materialization_report.json").write_text(json.dumps(const_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "v57_operand_type_harmonization_report.json").write_text(json.dumps(type_harmonize_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "v57_linux_precompile_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"hardened_ir": str(hardened), "deduplicate_alloc": dedup_report, "constant_materialization": const_report, "operand_type_harmonization": type_harmonize_report, "precompile_audit": audit, "v59_hardening": v59_outputs}
