# -*- coding: utf-8 -*-
"""Phase-2B lightweight legality analysis for HIVM structural rewrite.

This module is intentionally conservative and dependency-free.  It does not
pretend to replace the target MLIR/vTriton parser.  Its job is to turn the
project's edit-script contract into auditable pre-mutation evidence:

* Which operation anchors are visible in the candidate IR?
* Which edits have enough local evidence for the Python fallback to try them?
* Which edits must be skipped until a production vTriton/HivmOpsEditor backend
  can prove dependency, liveness, and event-legality properties?

The design follows the official MLIR rewrite discipline used elsewhere in the
project docs: match explicit operation anchors, check legality before mutation,
perform mutation through an owned rewriter/backend, and record every skipped or
applied edit.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .structural_edit_schema import OFFICIAL_REWRITE_GUIDANCE, legality_contract

_BARRIER_ALL_PAT = re.compile(r"\bhivm\.(?:hir\.)?(?:pipe_barrier\[<PIPE_ALL>\]|barrier\b.*mode\s*=\s*\"ALL\")")
_SET_FLAG_PAT = re.compile(r"\bhivm\.(?:hir\.)?set_flag\[")
_WAIT_FLAG_PAT = re.compile(r"\bhivm\.(?:hir\.)?wait_flag\[")
_SYNC_PAT = re.compile(r"\bhivm\.(?:hir\.)?(?:set_flag|wait_flag)\[")
_VECTOR_PAT = re.compile(r"\bhivm\.(?:hir\.)?v(?:add|sub|mul|div|exp|reduce|max|min|rec|sqrt)\b|\bhivm\.(?:hir\.)?(?:cast|softmax)\b")
_CUBE_PAT = re.compile(r"\bhivm\.(?:hir\.)?(?:mmad|mmadL1|matmul)\b")
_FIXPIPE_PAT = re.compile(r"\bhivm\.(?:hir\.)?fixpipe\b")
_LOAD_PAT = re.compile(r"\bhivm\.(?:hir\.)?load\b")
_STORE_PAT = re.compile(r"\bhivm\.(?:hir\.)?store\b")

_MEMREF_VAR_PAT = re.compile(r"(%[\w.$-]+)\s*:\s*memref<[^>]+#hivm\.address_space<([^>]+)>")


def _extract_ins_outs_vars(line: str) -> Dict[str, List[Dict[str, str]]]:
    """Extract simple memref SSA vars and HIVM address spaces from ins/outs.

    This is deliberately shallow: it works on single-line HIVM ops and is only
    used to produce conservative GM round-trip candidates.  The production
    backend must re-check with the target MLIR/vTriton parser.
    """
    def _section(name: str) -> str:
        m = re.search(r"\b" + name + r"\s*\((.*?)\)", line)
        return m.group(1) if m else ""
    out: Dict[str, List[Dict[str, str]]] = {"ins": [], "outs": []}
    for sec in ("ins", "outs"):
        for var, space in _MEMREF_VAR_PAT.findall(_section(sec)):
            out[sec].append({"var": var, "space": space.lower()})
    return out


def _has_gm_to_ub_load(line: str) -> bool:
    io = _extract_ins_outs_vars(line)
    return bool(_LOAD_PAT.search(line) and any(x["space"] == "gm" for x in io["ins"]) and any(x["space"] in {"ub", "l1", "cbuf"} for x in io["outs"]))


def _has_ub_to_gm_store(line: str) -> bool:
    io = _extract_ins_outs_vars(line)
    return bool(_STORE_PAT.search(line) and any(x["space"] in {"ub", "l1", "cbuf"} for x in io["ins"]) and any(x["space"] == "gm" for x in io["outs"]))


def _find_conservative_gm_roundtrip_candidates(raw_lines: List[str]) -> List[Dict[str, Any]]:
    """Find adjacent/near-adjacent GM store->load round-trip candidates.

    A candidate is *not* permission to delete.  It only says that a GM store and
    a later GM load appear to touch the same GM SSA var with no compute/store in
    between.  Deletion requires target MLIR alias/dependency validation.
    """
    candidates: List[Dict[str, Any]] = []
    for i, line in enumerate(raw_lines):
        if line.lstrip().startswith("//") or not _has_ub_to_gm_store(line):
            continue
        store_io = _extract_ins_outs_vars(line)
        gm_outs = [x["var"] for x in store_io["outs"] if x["space"] == "gm"]
        ub_ins = [x["var"] for x in store_io["ins"] if x["space"] in {"ub", "l1", "cbuf"}]
        if not gm_outs:
            continue
        blocked = False
        for j in range(i + 1, min(len(raw_lines), i + 8)):
            nxt = raw_lines[j]
            if nxt.lstrip().startswith("//") or not nxt.strip():
                continue
            if _CUBE_PAT.search(nxt) or _VECTOR_PAT.search(nxt) or _FIXPIPE_PAT.search(nxt) or _STORE_PAT.search(nxt):
                blocked = True
                break
            if _has_gm_to_ub_load(nxt):
                load_io = _extract_ins_outs_vars(nxt)
                gm_ins = [x["var"] for x in load_io["ins"] if x["space"] == "gm"]
                ub_outs = [x["var"] for x in load_io["outs"] if x["space"] in {"ub", "l1", "cbuf"}]
                same_gm = sorted(set(gm_outs).intersection(gm_ins))
                if same_gm:
                    candidates.append({
                        "store_line": i + 1,
                        "load_line": j + 1,
                        "same_gm_vars": same_gm,
                        "store_ub_inputs": ub_ins,
                        "load_ub_outputs": ub_outs,
                        "distance": j - i,
                        "local_blocked_by_compute_or_store": blocked,
                        "delete_permission": False,
                        "reason": "nearby store->load touches same GM SSA var; requires alias/dependency proof before deletion",
                        "store_op": line.strip(),
                        "load_op": nxt.strip(),
                    })
                break
    return candidates



def _code_lines(ir_text: str) -> List[Tuple[int, str]]:
    """Return non-comment MLIR lines with 1-based line numbers."""
    out: List[Tuple[int, str]] = []
    for i, line in enumerate(ir_text.splitlines(), 1):
        if line.lstrip().startswith("//"):
            continue
        out.append((i, line))
    return out


def _find_simple_scf_loop_bounds(lines: List[str]) -> List[Tuple[int, int]]:
    regions: List[Tuple[int, int]] = []
    for i, line in enumerate(lines):
        if "scf.for" not in line or "{" not in line:
            continue
        depth = line.count("{") - line.count("}")
        for j in range(i + 1, len(lines)):
            depth += lines[j].count("{") - lines[j].count("}")
            if depth <= 0:
                regions.append((i, j))
                break
    return regions


def analyze_hivm_ir_for_structural_rewrite(ir_text: str) -> Dict[str, Any]:
    """Collect lightweight structural anchors used by the Phase-2B checks."""
    code = _code_lines(ir_text)
    raw_lines = ir_text.splitlines()
    barrier_lines: List[int] = []
    set_lines: List[int] = []
    wait_lines: List[int] = []
    cube_lines: List[int] = []
    fixpipe_lines: List[int] = []
    vector_lines: List[int] = []
    load_lines: List[int] = []
    store_lines: List[int] = []
    duplicate_sync_pairs: List[Dict[str, Any]] = []
    prev_sync = None
    prev_line = None

    for lineno, line in code:
        stripped = line.strip()
        if _BARRIER_ALL_PAT.search(line):
            barrier_lines.append(lineno)
        if _SET_FLAG_PAT.search(line):
            set_lines.append(lineno)
        if _WAIT_FLAG_PAT.search(line):
            wait_lines.append(lineno)
        if _CUBE_PAT.search(line):
            cube_lines.append(lineno)
        if _FIXPIPE_PAT.search(line):
            fixpipe_lines.append(lineno)
        if _VECTOR_PAT.search(line):
            vector_lines.append(lineno)
        if _LOAD_PAT.search(line):
            load_lines.append(lineno)
        if _STORE_PAT.search(line):
            store_lines.append(lineno)
        is_sync = bool(_SYNC_PAT.search(line))
        if is_sync and prev_sync == stripped:
            duplicate_sync_pairs.append({"line": lineno, "previous_line": prev_line, "op": stripped})
        prev_sync = stripped if is_sync else None
        prev_line = lineno if is_sync else None

    # Find the first vector op that appears after a cube/fixpipe anchor and is not
    # immediately preceded by a set/wait flag.  This mirrors the Python fallback
    # but reports it before mutation.
    cv_boundary_candidates: List[Dict[str, Any]] = []
    seen_cv_anchor: int | None = None
    for lineno, line in code:
        if _CUBE_PAT.search(line) or _FIXPIPE_PAT.search(line):
            seen_cv_anchor = lineno
        if seen_cv_anchor is not None and _VECTOR_PAT.search(line):
            prev_idx = lineno - 2
            prev_raw = raw_lines[prev_idx] if 0 <= prev_idx < len(raw_lines) else ""
            cv_boundary_candidates.append({
                "vector_line": lineno,
                "last_cube_or_fixpipe_line": seen_cv_anchor,
                "already_immediately_synchronized": bool(_SYNC_PAT.search(prev_raw)),
                "vector_op": line.strip(),
            })

    # Conservative Q hoist candidate search.
    q_hoist_candidates: List[Dict[str, Any]] = []
    for start, end in _find_simple_scf_loop_bounds(raw_lines):
        body = raw_lines[start + 1:end]
        load_idx = nd_idx = None
        for off, line in enumerate(body):
            if "hivm.hir.load" in line and "%Q_gm" in line and "%q_ub" in line:
                load_idx = off
            if load_idx is not None and off > load_idx and "hivm.hir.nd2nz" in line and "%q_ub" in line and "%q_l1" in line:
                nd_idx = off
                break
        if load_idx is None or nd_idx is None:
            continue
        m_ind = re.search(r"scf\.for\s+(%[\w.$-]+)", raw_lines[start])
        ind = m_ind.group(1) if m_ind else None
        block = body[load_idx: nd_idx + 1]
        q_hoist_candidates.append({
            "loop_line": start + 1,
            "loop_end_line": end + 1,
            "load_line": start + 2 + load_idx,
            "nd2nz_line": start + 2 + nd_idx,
            "loop_induction": ind,
            "uses_loop_induction": bool(ind and any(ind in b for b in block)),
            "ops": [b.strip() for b in block],
        })

    gm_roundtrip_candidates = _find_conservative_gm_roundtrip_candidates(raw_lines)

    return {
        "schema_version": "hivm_structural_anchor_analysis_v1",
        "op_counts": {
            "barrier_all": len(barrier_lines),
            "set_flag": len(set_lines),
            "wait_flag": len(wait_lines),
            "cube": len(cube_lines),
            "fixpipe": len(fixpipe_lines),
            "vector": len(vector_lines),
            "load": len(load_lines),
            "store": len(store_lines),
            "gm_roundtrip_candidate": len(gm_roundtrip_candidates),
        },
        "anchors": {
            "barrier_all_lines": barrier_lines,
            "set_flag_lines": set_lines,
            "wait_flag_lines": wait_lines,
            "cube_lines": cube_lines,
            "fixpipe_lines": fixpipe_lines,
            "vector_lines": vector_lines,
            "load_lines": load_lines,
            "store_lines": store_lines,
            "cv_boundary_candidates": cv_boundary_candidates,
            "q_hoist_candidates": q_hoist_candidates,
            "duplicate_sync_pairs": duplicate_sync_pairs,
            "gm_roundtrip_candidates": gm_roundtrip_candidates,
        },
    }


def _status(passed: bool, reason: str, evidence: Any = None, requires_target_parser: bool = True) -> Dict[str, Any]:
    return {
        "passed_local_precheck": passed,
        "reason": reason,
        "evidence": evidence,
        "requires_target_mlir_or_vtriton_validation": requires_target_parser,
    }


def evaluate_edit_legality(edit: Dict[str, Any], anchor_analysis: Dict[str, Any], safety: str = "balanced") -> Dict[str, Any]:
    """Evaluate one edit against local evidence.

    The returned status is deliberately called a *local precheck*.  A production
    backend must still parse the IR with the target dialect and run dependency / 
    liveness checks before relying on speedup or correctness claims.
    """
    typ = str(edit.get("type"))
    anchors = anchor_analysis.get("anchors", {})
    safety = str(safety or "balanced").lower()
    if not edit.get("enabled", True):
        return _status(False, "edit disabled by selected safety level", {"edit_type": typ})
    if typ == "replace_barrier_all_with_directional_sync":
        lines = anchors.get("barrier_all_lines", [])
        max_edits = int(edit.get("max_edits", 0) or 0)
        return _status(bool(lines and max_edits > 0), "explicit coarse barrier anchor found" if lines else "no explicit barrier_all anchor found", {"candidate_lines": lines[:max_edits], "max_edits": max_edits})
    if typ in {"insert_sync_before_first_vector_op", "insert_cv_boundary_sync"}:
        candidates = [c for c in anchors.get("cv_boundary_candidates", []) if not c.get("already_immediately_synchronized")]
        return _status(bool(candidates), "cube/fixpipe to vector boundary found" if candidates else "no unsynchronized vector boundary after cube/fixpipe", {"candidate_count": len(candidates), "first_candidates": candidates[:3]})
    if typ in {"hoist_invariant_q_load_from_simple_loop", "hoist_loop_invariant_q_load"}:
        candidates = [c for c in anchors.get("q_hoist_candidates", []) if not c.get("uses_loop_induction")]
        return _status(bool(candidates), "simple loop-invariant Q load/nd2nz candidate found" if candidates else "no conservative loop-invariant Q load candidate", {"candidate_count": len(candidates), "first_candidates": candidates[:3]})
    if typ == "remove_adjacent_duplicate_sync_pairs":
        candidates = anchors.get("duplicate_sync_pairs", [])
        return _status(bool(candidates and safety == "aggressive"), "adjacent duplicate sync candidate found under aggressive safety" if candidates else "no adjacent duplicate sync candidate", {"candidate_count": len(candidates), "safety": safety, "first_candidates": candidates[:5]})
    if typ == "remove_redundant_gm_roundtrip":
        candidates = anchors.get("gm_roundtrip_candidates", [])
        # Phase-2E exposes candidates but does not grant deletion permission.
        # The production backend must prove alias/dependency/liveness first.
        reason = (
            "GM round-trip candidates detected but deletion is deferred until target alias/dependency proof"
            if candidates
            else "no conservative GM round-trip candidate found; deletion deferred"
        )
        return _status(False, reason, {"candidate_count": len(candidates), "first_candidates": candidates[:5], "deletion_deferred": True})
    return _status(False, f"unsupported edit type in local legality checker: {typ}", {"edit_type": typ})


def build_structural_legality_report(ir_text: str, edit_script: Dict[str, Any], safety: str = "balanced") -> Dict[str, Any]:
    """Build a report tying edit-script intent to explicit local anchors."""
    anchors = analyze_hivm_ir_for_structural_rewrite(ir_text)
    edit_reports: List[Dict[str, Any]] = []
    for idx, edit in enumerate(edit_script.get("edits", [])):
        leg = evaluate_edit_legality(edit, anchors, safety)
        edit_reports.append({
            "index": idx,
            "type": edit.get("type"),
            "enabled": edit.get("enabled"),
            "local_precheck": leg,
            "required_gates_from_script": (edit.get("legality") or {}).get("required_gates", []),
            "mutation_kinds": edit.get("mutation_kinds", []),
            "reason": edit.get("reason"),
        })
    passed = [e for e in edit_reports if e["local_precheck"].get("passed_local_precheck")]
    failed = [e for e in edit_reports if not e["local_precheck"].get("passed_local_precheck")]
    return {
        "schema_version": "hivm_structural_legality_report_v1",
        "producer": "strategy_search_demo_v3.3.2_phase2e_gm_roundtrip_legality_precheck",
        "rewrite_safety": safety,
        "official_rewrite_guidance": OFFICIAL_REWRITE_GUIDANCE,
        "legality_contract": legality_contract(),
        "anchor_analysis": anchors,
        "edit_prechecks": edit_reports,
        "summary": {
            "total_edits": len(edit_reports),
            "local_precheck_passed": len(passed),
            "local_precheck_failed_or_deferred": len(failed),
            "production_backend_required": True,
        },
        "hard_boundary": [
            "Local precheck is not a correctness proof.",
            "Target MLIR/vTriton parser validation is still required after mutation.",
            "Dependency graph, buffer live range, and event live range checks remain Phase-3 work.",
            "Phase-2E detects GM round-trip candidates but never deletes them without target alias/dependency proof.",
        ],
    }
