# -*- coding: utf-8 -*-
"""vTriton-compatible / vTriton-inspired structural HIVM rewrite bridge.

This module is intentionally separate from ``rewrite.py``:
- rewrite.py Step-1/2/2C emits attributes and hints;
- this module emits and applies real operation-sequence edits.

The first supported edits are conservative, pattern-based, and auditable:
1) replace coarse ``hivm.hir.barrier {mode = "ALL"}`` with directional
   set_flag/wait_flag pairs;
2) insert a directional set_flag/wait_flag pair before the first vector op in a
   CV region;
3) hoist an obviously invariant Q load + nd2nz pair from a simple scf.for loop;
4) remove adjacent duplicate set_flag/wait_flag pairs.

These edits deliberately mirror the kind of CRUD primitives exposed by
vTriton's tools/hivm-crud wrapper around HivmOpsEditor, while keeping a pure
Python fallback so this demo can run without a local vTriton/LLVM build.
"""
from __future__ import annotations

import json
import hashlib
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .structural_edit_schema import (
    MUTATION_KINDS,
    OFFICIAL_REWRITE_GUIDANCE,
    legality_contract,
    structural_edit_schema,
    validate_structural_edit_script,
)

# Real MLIR/HIVM parser + HivmOpsEditor (Phase-3A integration)
try:
    from .hivm_parser import (
        MLIRModule, MLIRFunction, MLIRRegion, MLIRBlock, MLIROperation,
        parse_hivm_file, parse_hivm_text, serialize_module, write_module,
    )
    from .hivm_ops_editor import (
        HivmOpsEditor, HivmOpInfo,
        PipeAttr, EventAttr,
        HIVM_SYNC_OPS, HIVM_DMA_OPS,
    )
    _HAS_REAL_PARSER = True
except ImportError:
    _HAS_REAL_PARSER = False


def _num(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


_VECTOR_PAT = re.compile(r"\bhivm\.(?:hir\.)?v(?:add|sub|mul|div|exp|reduce|max|min|rec|sqrt)\b|\bhivm\.(?:hir\.)?(?:cast|softmax)\b")
_CUBE_PAT = re.compile(r"\bhivm\.(?:hir\.)?(?:mmad|mmadL1|matmul)\b")
_FIXPIPE_PAT = re.compile(r"\bhivm\.(?:hir\.)?fixpipe\b")
_BARRIER_ALL_PAT = re.compile(r"\bhivm\.(?:hir\.)?(?:pipe_barrier\[<PIPE_ALL>\]|barrier\b.*mode\s*=\s*\"ALL\")")
_SET_WAIT_PAT = re.compile(r"\bhivm\.(?:hir\.)?(?:set_flag|wait_flag)\[")


@dataclass
class StructuralRewriteResult:
    text: str
    changes: List[Dict[str, Any]]
    skipped: List[Dict[str, Any]]
    edit_script: Dict[str, Any]


def build_structural_edit_script(strategy: Dict[str, Any], safety: str = "balanced") -> Dict[str, Any]:
    """Build a concrete operation-level edit script.

    The script is intentionally explicit and JSON-serializable so it can be
    consumed by either this Python fallback or a future vTriton HivmOpsEditor
    binary.
    """
    safety = str(safety or "balanced").lower()
    stage = int(_num(strategy.get("cv_pipeline_stage", 1), 1))
    sync_policy = strategy.get("sync_policy")

    edits: List[Dict[str, Any]] = []
    if sync_policy == "graph_sync_solver":
        edits.append({
            "type": "replace_barrier_all_with_directional_sync",
            "enabled": safety in {"balanced", "aggressive"},
            "max_edits": 4 if safety == "balanced" else 999,
            "anchor": {"kind": "op", "pattern": "hivm.hir.barrier {mode = \"ALL\"} or pipe_barrier[<PIPE_ALL>]"},
            "mutation_kinds": MUTATION_KINDS["replace_barrier_all_with_directional_sync"],
            "legality": {
                "required_gates": [
                    "explicit_PIPE_ALL_or_barrier_ALL_anchor_found",
                    "fresh_event_id_policy",
                    "local_replacement_only_no_sync_motion",
                    "post_rewrite_vtriton_parse_required",
                ],
                "status_before_backend": "requires_backend_check",
            },
            "replacement": [
                "hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_M>, <EVENT_ID0>]",
                "hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_M>, <EVENT_ID0>]",
            ],
            "reason": "selected SyncPlan uses graph_sync_solver; replace coarse all-pipe barrier with directional pipe sync when pattern is explicit",
        })
        edits.append({
            "type": "remove_adjacent_duplicate_sync_pairs",
            "enabled": safety == "aggressive",
            "max_edits": 8,
            "anchor": {"kind": "adjacent_sync_pair", "pattern": "identical neighboring set_flag/wait_flag op lines"},
            "mutation_kinds": MUTATION_KINDS["remove_adjacent_duplicate_sync_pairs"],
            "legality": {
                "required_gates": ["exact_duplicate_anchor", "aggressive_safety_only", "post_rewrite_vtriton_parse_required"],
                "status_before_backend": "requires_backend_check",
            },
            "reason": "aggressive-only cleanup of immediately duplicated set/wait lines",
        })

    if stage > 1:
        edits.append({
            "type": "insert_sync_before_first_vector_op",
            "enabled": safety in {"balanced", "aggressive"},
            "max_edits": 1 if safety == "balanced" else 4,
            "anchor": {"kind": "op_sequence", "after": "cube_or_fixpipe", "before": "first_vector_op"},
            "mutation_kinds": MUTATION_KINDS["insert_sync_before_first_vector_op"],
            "legality": {
                "required_gates": [
                    "cube_or_fixpipe_anchor_found",
                    "vector_consumer_anchor_found",
                    "fresh_event_id_policy",
                    "no_existing_immediate_sync_before_vector",
                    "post_rewrite_vtriton_parse_required",
                ],
                "status_before_backend": "requires_backend_check",
            },
            "insert_before": "first vector op after cube/fixpipe anchor",
            "sync_lines": [
                "hivm.hir.set_flag[<PIPE_FIX>, <PIPE_V>, <EVENT_ID1>]",
                "hivm.hir.wait_flag[<PIPE_FIX>, <PIPE_V>, <EVENT_ID1>]",
            ],
            "reason": "selected CVPipelinePlan has stage>1; materialize a minimal directional sync boundary before vector stage",
        })

    if strategy.get("double_buffer") or str(strategy.get("dma_policy", "")).lower() in {"overlap", "prefetch", "hoist_q"}:
        edits.append({
            "type": "hoist_invariant_q_load_from_simple_loop",
            "enabled": safety in {"balanced", "aggressive"},
            "max_edits": 1,
            "anchor": {"kind": "simple_scf_for_body", "pattern": "Q_gm load -> q_ub; q_ub nd2nz -> q_l1"},
            "mutation_kinds": MUTATION_KINDS["hoist_invariant_q_load_from_simple_loop"],
            "legality": {
                "required_gates": [
                    "simple_scf_for_region_found",
                    "candidate_does_not_use_loop_induction",
                    "no_intermediate_write_to_Q_or_q_buffers",
                    "post_rewrite_vtriton_parse_required",
                ],
                "status_before_backend": "requires_backend_check",
            },
            "reason": "pattern-specific FA cleanup: hoist repeated Q_gm -> q_ub -> q_l1 load from a simple KV loop when it does not use loop induction",
        })

    # Phase-2E: expose GM round-trip removal as a first-class edit request,
    # but keep deletion deferred until the target backend proves alias/dependency.
    # Python fallback intentionally does not implement this edit.
    if str(strategy.get("dma_policy", "")).lower() in {"overlap", "prefetch", "hoist_q", "remove_gm_roundtrip"} or strategy.get("double_buffer"):
        edits.append({
            "type": "remove_redundant_gm_roundtrip",
            "enabled": safety in {"balanced", "aggressive"},
            "max_edits": 1 if safety == "balanced" else 4,
            "anchor": {"kind": "nearby_store_load_pair", "pattern": "UB/L1 store -> same GM, then same GM load -> UB/L1"},
            "mutation_kinds": MUTATION_KINDS["remove_redundant_gm_roundtrip"],
            "legality": {
                "required_gates": [
                    "same_gm_ssa_base_or_proven_alias",
                    "no_intermediate_consumer_or_writer",
                    "store_result_not_observable_at_kernel_boundary",
                    "target_mlir_alias_dependency_proof_required",
                    "post_rewrite_vtriton_parse_required",
                ],
                "status_before_backend": "deferred_until_target_alias_dependency_check",
            },
            "reason": "Phase-2E request only: detect possible GM round-trip candidates but do not delete without target alias/dependency proof",
        })

    script = {
        "schema_version": "hivm_structural_edit_script_v1",
        "producer": "strategy_search_demo_v3.3.2_phase2g_vtriton_adapter_manifest",
        "backend_model": "vtriton_hivm_crud_compatible_python_fallback__production_target_hivm_strategy_rewrite",
        "official_rewrite_guidance": OFFICIAL_REWRITE_GUIDANCE,
        "rewrite_safety": safety,
        "strategy_id": strategy.get("strategy_id"),
        "selected_plan_summary": {
            "sync_policy": strategy.get("sync_policy"),
            "cv_pipeline_stage": strategy.get("cv_pipeline_stage"),
            "cv_pipeline_template": strategy.get("cv_pipeline_template"),
            "double_buffer": strategy.get("double_buffer"),
            "dma_policy": strategy.get("dma_policy"),
        },
        "edits": edits,
        "guards": [
            "Only apply fallback edits to explicit HIVM op anchors.",
            "Never delete data movement or compute ops unless a dedicated redundancy pattern is proven.",
            "Production mutation should be implemented with vTriton/HivmOpsEditor or MLIR PatternRewriter-style APIs, not free-form text replacement.",
            "After structural rewrite, run tritonsim-hivm or vTriton parser to validate IR syntax and DES/trace delta.",
        ],
        "legality_contract": legality_contract(),
    }
    ok, errors = validate_structural_edit_script(script)
    script["schema_validation"] = {"passed": ok, "errors": errors}
    return script


def _apply_replace_barrier_all(lines: List[str], edit: Dict[str, Any]) -> Tuple[List[str], List[Dict[str, Any]], List[Dict[str, Any]]]:
    changes: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    if not edit.get("enabled"):
        skipped.append({"type": edit.get("type"), "reason": "disabled_by_safety"})
        return lines, changes, skipped
    max_edits = int(edit.get("max_edits", 1))
    replacement = list(edit.get("replacement") or [])
    out: List[str] = []
    count = 0
    for idx, line in enumerate(lines, 1):
        if count < max_edits and _BARRIER_ALL_PAT.search(line):
            indent = _indent_of(line)
            out.append(indent + "// [structural_rewrite] replaced coarse PIPE_ALL barrier with directional set/wait; original: " + line.strip())
            for repl in replacement:
                out.append(indent + repl)
            changes.append({
                "type": "replace_barrier_all_with_directional_sync",
                "line": idx,
                "before": line.strip(),
                "after": replacement,
                "structural_change": True,
            })
            count += 1
        else:
            out.append(line)
    if count == 0:
        skipped.append({"type": edit.get("type"), "reason": "no_PIPE_ALL_or_barrier_ALL_anchor_found"})
    return out, changes, skipped


def _apply_insert_sync_before_vector(lines: List[str], edit: Dict[str, Any]) -> Tuple[List[str], List[Dict[str, Any]], List[Dict[str, Any]]]:
    changes: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    if not edit.get("enabled"):
        skipped.append({"type": edit.get("type"), "reason": "disabled_by_safety"})
        return lines, changes, skipped
    max_edits = int(edit.get("max_edits", 1))
    sync_lines = list(edit.get("sync_lines") or [])
    out: List[str] = []
    seen_cube_or_fix = False
    inserted = 0
    for idx, line in enumerate(lines, 1):
        if _CUBE_PAT.search(line) or _FIXPIPE_PAT.search(line):
            seen_cube_or_fix = True
        is_vector = bool(_VECTOR_PAT.search(line))
        already_has_prev_sync = bool(out and _SET_WAIT_PAT.search(out[-1]))
        if seen_cube_or_fix and is_vector and inserted < max_edits and not already_has_prev_sync:
            indent = _indent_of(line)
            out.append(indent + "// [structural_rewrite] inserted CV directional sync before vector stage")
            for repl in sync_lines:
                out.append(indent + repl)
            changes.append({
                "type": "insert_sync_before_first_vector_op",
                "line": idx,
                "target": line.strip(),
                "inserted": sync_lines,
                "structural_change": True,
            })
            inserted += 1
        out.append(line)
    if inserted == 0:
        skipped.append({"type": edit.get("type"), "reason": "no_vector_anchor_after_cube_or_already_synchronized"})
    return out, changes, skipped


def _find_simple_scf_loop_bounds(lines: List[str]) -> List[Tuple[int, int]]:
    """Return (start,end) indices for simple brace-balanced scf.for regions."""
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


def _apply_hoist_invariant_q_load(lines: List[str], edit: Dict[str, Any]) -> Tuple[List[str], List[Dict[str, Any]], List[Dict[str, Any]]]:
    changes: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    if not edit.get("enabled"):
        skipped.append({"type": edit.get("type"), "reason": "disabled_by_safety"})
        return lines, changes, skipped
    max_edits = int(edit.get("max_edits", 1))
    if max_edits <= 0:
        return lines, changes, skipped

    for start, end in _find_simple_scf_loop_bounds(lines):
        body = lines[start + 1:end]
        # Exact conservative FA pattern: Q_gm load to q_ub, then q_ub nd2nz to q_l1.
        load_idx = nd_idx = None
        for off, line in enumerate(body):
            if "hivm.hir.load" in line and "%Q_gm" in line and "%q_ub" in line and "%" not in line.split("ins", 1)[0]:
                load_idx = off
            if load_idx is not None and off > load_idx and "hivm.hir.nd2nz" in line and "%q_ub" in line and "%q_l1" in line:
                nd_idx = off
                break
        if load_idx is None or nd_idx is None:
            continue
        block = body[load_idx: nd_idx + 1]
        # Guard: hoisted lines must not mention the loop induction variable from the scf.for line.
        m_ind = re.search(r"scf\.for\s+(%[\w.$-]+)", lines[start])
        ind = m_ind.group(1) if m_ind else None
        if ind and any(ind in b for b in block):
            skipped.append({"type": edit.get("type"), "reason": "candidate_uses_loop_induction", "loop_line": start + 1})
            continue
        # Rewrite: insert before loop, remove from body.
        out = list(lines[:start])
        loop_indent = _indent_of(lines[start])
        out.append(loop_indent + "// [structural_rewrite] hoisted invariant Q load/nd2nz from KV loop")
        out.extend(block)
        new_body = body[:load_idx] + body[nd_idx + 1:]
        out.extend([lines[start]] + new_body + lines[end:])
        changes.append({
            "type": "hoist_invariant_q_load_from_simple_loop",
            "loop_line": start + 1,
            "removed_lines_in_loop": [start + 2 + load_idx, start + 2 + nd_idx],
            "hoisted_lines": [b.strip() for b in block],
            "structural_change": True,
        })
        return out, changes, skipped

    skipped.append({"type": edit.get("type"), "reason": "no_simple_Q_gm_to_q_ub_to_q_l1_loop_pattern_found"})
    return lines, changes, skipped


def _apply_remove_adjacent_duplicate_sync(lines: List[str], edit: Dict[str, Any]) -> Tuple[List[str], List[Dict[str, Any]], List[Dict[str, Any]]]:
    changes: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    if not edit.get("enabled"):
        skipped.append({"type": edit.get("type"), "reason": "disabled_by_safety"})
        return lines, changes, skipped
    max_edits = int(edit.get("max_edits", 1))
    out: List[str] = []
    removed = 0
    prev_sync = None
    for idx, line in enumerate(lines, 1):
        is_sync = bool(_SET_WAIT_PAT.search(line))
        norm = line.strip()
        if is_sync and prev_sync == norm and removed < max_edits:
            out.append(_indent_of(line) + "// [structural_rewrite] removed adjacent duplicate sync: " + norm)
            changes.append({"type": "remove_adjacent_duplicate_sync_pairs", "line": idx, "removed": norm, "structural_change": True})
            removed += 1
            continue
        out.append(line)
        prev_sync = norm if is_sync else None
    if removed == 0:
        skipped.append({"type": edit.get("type"), "reason": "no_adjacent_duplicate_sync_found"})
    return out, changes, skipped


_APPLIERS = {
    "replace_barrier_all_with_directional_sync": _apply_replace_barrier_all,
    "insert_sync_before_first_vector_op": _apply_insert_sync_before_vector,
    "hoist_invariant_q_load_from_simple_loop": _apply_hoist_invariant_q_load,
    "remove_adjacent_duplicate_sync_pairs": _apply_remove_adjacent_duplicate_sync,
}


def apply_structural_rewrite(ir_text: str, strategy: Dict[str, Any], safety: str = "balanced") -> StructuralRewriteResult:
    """Apply structural rewrite edits to HIVM text.

    When the real MLIR/HIVM parser + HivmOpsEditor is available, uses the
    editor-based approach for proper IR-level mutations. Otherwise, falls
    back to text-level regex replacement.
    """
    if _HAS_REAL_PARSER:
        return _apply_structural_rewrite_via_editor(ir_text, strategy, safety)
    return _apply_structural_rewrite_via_text(ir_text, strategy, safety)


def _apply_structural_rewrite_via_text(ir_text: str, strategy: Dict[str, Any], safety: str = "balanced") -> StructuralRewriteResult:
    """Apply structural rewrite edits using text-level regex replacement (legacy fallback)."""
    script = build_structural_edit_script(strategy, safety)
    lines = ir_text.splitlines()
    all_changes: List[Dict[str, Any]] = []
    all_skipped: List[Dict[str, Any]] = []
    for edit in script.get("edits", []):
        typ = edit.get("type")
        applier = _APPLIERS.get(str(typ))
        if not applier:
            all_skipped.append({"type": typ, "reason": "unsupported_by_python_fallback"})
            continue
        lines, changes, skipped = applier(lines, edit)
        all_changes.extend(changes)
        all_skipped.extend(skipped)
    text = "\n".join(lines) + ("\n" if ir_text.endswith("\n") else "")
    return StructuralRewriteResult(text=text, changes=all_changes, skipped=all_skipped, edit_script=script)


# =============================================================================
# Editor-based structural rewrite (Phase-3A: real MLIR/HIVM parser integration)
# =============================================================================

def _apply_structural_rewrite_via_editor(ir_text: str, strategy: Dict[str, Any], safety: str = "balanced") -> StructuralRewriteResult:
    """Apply structural rewrite edits using the real MLIR parser + HivmOpsEditor.

    This is the production-grade approach: parse → edit IR tree → serialize.
    Every edit is recorded with before/after op-level detail.
    """
    script = build_structural_edit_script(strategy, safety)
    all_changes: List[Dict[str, Any]] = []
    all_skipped: List[Dict[str, Any]] = []

    if not _HAS_REAL_PARSER:
        all_skipped.append({"type": "editor_rewrite", "reason": "real_parser_not_available"})
        return _apply_structural_rewrite_via_text(ir_text, strategy, safety)

    try:
        module = parse_hivm_text(ir_text)
        editor = HivmOpsEditor(module)
    except Exception as e:
        all_skipped.append({"type": "editor_rewrite", "reason": f"parse_failed: {e}"})
        return _apply_structural_rewrite_via_text(ir_text, strategy, safety)

    for edit in script.get("edits", []):
        typ = edit.get("type")
        if not edit.get("enabled"):
            all_skipped.append({"type": typ, "reason": "disabled_by_safety"})
            continue

        if typ == "replace_barrier_all_with_directional_sync":
            changes, skipped = _editor_replace_barrier_all(editor, edit)
        elif typ == "insert_sync_before_first_vector_op":
            changes, skipped = _editor_insert_sync_before_vector(editor, edit)
        elif typ == "hoist_invariant_q_load_from_simple_loop":
            changes, skipped = _editor_hoist_invariant_q_load(editor, edit)
        elif typ == "remove_adjacent_duplicate_sync_pairs":
            changes, skipped = _editor_remove_adjacent_duplicate_sync(editor, edit)
        elif typ == "remove_redundant_gm_roundtrip":
            changes, skipped = _editor_remove_redundant_gm_roundtrip(editor, edit)
        else:
            all_skipped.append({"type": typ, "reason": "unsupported_by_editor"})
            continue

        all_changes.extend(changes)
        all_skipped.extend(skipped)

    text = editor.export_to_string()
    return StructuralRewriteResult(text=text, changes=all_changes, skipped=all_skipped, edit_script=script)


def _editor_replace_barrier_all(editor: 'HivmOpsEditor', edit: Dict[str, Any]) -> Tuple[List[Dict], List[Dict]]:
    """Replace coarse PIPE_ALL barriers with directional set_flag/wait_flag pairs via HivmOpsEditor."""
    changes: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    max_edits = int(edit.get("max_edits", 1))

    # Collect all barrier ops
    barrier_ops = editor.collect_ops('hivm.hir.barrier')
    pipe_barrier_ops = editor.collect_ops('hivm.hir.pipe_barrier')
    all_barriers = barrier_ops + pipe_barrier_ops

    if not all_barriers:
        skipped.append({"type": edit.get("type"), "reason": "no_barrier_ops_found"})
        return changes, skipped

    count = 0
    for barrier_op in all_barriers:
        if count >= max_edits:
            break

        before_text = barrier_op.raw_text
        set_op, wait_op = editor.barrier_to_directional_sync(
            barrier_op,
            set_pipe=PipeAttr.PIPE_MTE2,
            wait_pipe=PipeAttr.PIPE_M,
            event_id=EventAttr.EVENT_ID0,
        )
        changes.append({
            "type": "replace_barrier_all_with_directional_sync",
            "line": barrier_op.line,
            "before": before_text,
            "after": [
                f"hivm.hir.set_flag {{pipe=\"MTE2\", event=\"EVENT_ID0\"}}",
                f"hivm.hir.wait_flag {{pipe=\"M\", event=\"EVENT_ID0\"}}",
            ],
            "structural_change": True,
            "editor_based": True,
        })
        count += 1

    if count == 0:
        skipped.append({"type": edit.get("type"), "reason": "no_barrier_ops_found"})
    return changes, skipped


def _editor_insert_sync_before_vector(editor: 'HivmOpsEditor', edit: Dict[str, Any]) -> Tuple[List[Dict], List[Dict]]:
    """Insert directional sync before the first vector op after cube/fixpipe via HivmOpsEditor."""
    changes: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    max_edits = int(edit.get("max_edits", 1))

    ops = editor.list_ops()
    cube_op = None
    vector_op = None

    # Find the last cube/fixpipe op before the first vector op
    for info in ops:
        name = info.qualified_name
        if any(x in name for x in ('mmad', 'mmadL1', 'matmul', 'fixpipe')):
            cube_op = info.op
        elif any(x in name for x in ('vadd', 'vsub', 'vmul', 'vdiv', 'vexp', 'vreduce', 'vrelu', 'vmax', 'vmin')):
            if vector_op is None:
                vector_op = info.op
                break

    if cube_op is None:
        skipped.append({"type": edit.get("type"), "reason": "no_cube_or_fixpipe_anchor_found"})
        return changes, skipped
    if vector_op is None:
        skipped.append({"type": edit.get("type"), "reason": "no_vector_anchor_found"})
        return changes, skipped

    # Check if sync already exists before the vector op
    for fn in editor._module.functions:
        for block in fn.body.blocks:
            for i, op in enumerate(block.operations):
                if op is vector_op and i > 0:
                    prev = block.operations[i - 1]
                    if prev.full_name in ('hivm.hir.set_flag', 'hivm.hir.wait_flag'):
                        skipped.append({"type": edit.get("type"), "reason": "sync_already_exists_before_vector"})
                        return changes, skipped

    inserted = 0
    if inserted < max_edits:
        editor.insert_cv_pipeline_sync(
            cube_op, vector_op,
            set_pipe=PipeAttr.PIPE_FIX,
            wait_pipe=PipeAttr.PIPE_V,
            event_id=EventAttr.EVENT_ID1,
        )
        changes.append({
            "type": "insert_sync_before_first_vector_op",
            "line": vector_op.line,
            "target": vector_op.full_name,
            "inserted": [
                "hivm.hir.set_flag {pipe=\"FIX\", event=\"EVENT_ID1\"}",
                "hivm.hir.wait_flag {pipe=\"V\", event=\"EVENT_ID1\"}",
            ],
            "structural_change": True,
            "editor_based": True,
        })
        inserted += 1

    if inserted == 0:
        skipped.append({"type": edit.get("type"), "reason": "no_vector_anchor_after_cube_or_already_synchronized"})
    return changes, skipped


def _editor_hoist_invariant_q_load(editor: 'HivmOpsEditor', edit: Dict[str, Any]) -> Tuple[List[Dict], List[Dict]]:
    """Hoist invariant Q load from scf.for loop via HivmOpsEditor."""
    changes: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    max_edits = int(edit.get("max_edits", 1))

    if max_edits <= 0:
        return changes, skipped

    # Find scf.for ops
    for_ops = editor.collect_ops('scf.for')
    if not for_ops:
        skipped.append({"type": edit.get("type"), "reason": "no_scf_for_loop_found"})
        return changes, skipped

    for for_op in for_ops:
        if not for_op.regions:
            continue
        for region in for_op.regions:
            for block in region.blocks:
                # Look for Q_gm load + nd2nz pattern inside the loop
                load_op = None
                nd2nz_op = None
                for op in block.operations:
                    if op.full_name == 'hivm.hir.load':
                        # Check if it references Q_gm or q_ub
                        raw = op.raw_text.lower()
                        if 'q_gm' in raw or ('q_' in raw and 'gm' in raw):
                            load_op = op
                    elif op.full_name == 'hivm.hir.nd2nz' and load_op is not None:
                        raw = op.raw_text.lower()
                        if 'q_' in raw:
                            nd2nz_op = op
                            break

                if load_op is None or nd2nz_op is None:
                    continue

                # Guard: check that hoisted lines don't use loop induction variable
                for_line = for_op.raw_text
                ind_match = re.search(r"scf\.for\s+(%[\w.$-]+)", for_line)
                ind_var = ind_match.group(1) if ind_match else None
                if ind_var:
                    if ind_var in load_op.raw_text or ind_var in nd2nz_op.raw_text:
                        skipped.append({
                            "type": edit.get("type"),
                            "reason": "candidate_uses_loop_induction_variable",
                        })
                        continue

                # Perform the hoist
                editor.hoist_q_load(load_op, nd2nz_op)
                changes.append({
                    "type": "hoist_invariant_q_load_from_simple_loop",
                    "loop_line": for_op.line,
                    "hoisted_ops": [load_op.full_name, nd2nz_op.full_name],
                    "structural_change": True,
                    "editor_based": True,
                })
                return changes, skipped

    skipped.append({"type": edit.get("type"), "reason": "no_Q_gm_load_nd2nz_pattern_in_loop_found"})
    return changes, skipped


def _editor_remove_adjacent_duplicate_sync(editor: 'HivmOpsEditor', edit: Dict[str, Any]) -> Tuple[List[Dict], List[Dict]]:
    """Remove adjacent duplicate set_flag/wait_flag pairs via HivmOpsEditor."""
    changes: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    max_edits = int(edit.get("max_edits", 1))

    if max_edits <= 0:
        return changes, skipped

    removed = 0
    for fn in editor._module.functions:
        for block in fn.body.blocks:
            i = 0
            while i < len(block.operations) - 1 and removed < max_edits:
                a = block.operations[i]
                b = block.operations[i + 1]
                if a.full_name in HIVM_SYNC_OPS and a.full_name == b.full_name:
                    # Check if the raw text is identical
                    if a.raw_text.strip() == b.raw_text.strip():
                        editor.delete_op(b)
                        changes.append({
                            "type": "remove_adjacent_duplicate_sync_pairs",
                            "line": b.line,
                            "removed": a.raw_text.strip(),
                            "structural_change": True,
                            "editor_based": True,
                        })
                        removed += 1
                        continue
                i += 1

    if removed == 0:
        skipped.append({"type": edit.get("type"), "reason": "no_adjacent_duplicate_sync_found"})
    return changes, skipped


def _editor_remove_redundant_gm_roundtrip(editor: 'HivmOpsEditor', edit: Dict[str, Any]) -> Tuple[List[Dict], List[Dict]]:
    """Remove redundant GM round-trip (load+store) pairs via HivmOpsEditor."""
    changes: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    # GM round-trip deletion is deferred until alias/dependency proof is available
    # This is a Phase-2E precheck-only edit; actual deletion is Phase-3C
    skipped.append({
        "type": edit.get("type"),
        "reason": "deferred_until_target_alias_dependency_check__phase3c",
        "note": "GM round-trip deletion requires alias/dependency proof; "
                "candidate detection is done but deletion is deferred to Phase-3C.",
    })

    # Still detect candidates for audit purposes
    max_pairs = int(edit.get("max_edits", 1))
    candidates = editor.delete_redundant_gm_trips(0)  # dry-run only
    if candidates:
        changes.append({
            "type": "remove_redundant_gm_roundtrip",
            "candidates_detected": candidates,
            "structural_change": False,
            "deferred": True,
            "editor_based": True,
        })

    return changes, skipped


def build_structural_rewrite_report(
    strategy: Dict[str, Any],
    result: StructuralRewriteResult,
    backend_status: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a dedicated structural rewrite report."""
    counts: Dict[str, int] = {}
    for c in result.changes:
        counts[c.get("type", "unknown")] = counts.get(c.get("type", "unknown"), 0) + 1
    return {
        "schema_version": "hivm_structural_rewrite_report_v1",
        "producer": "strategy_search_demo_v3.3.2_phase2c_vtriton_bridge_structural_rewrite",
        "strategy_id": strategy.get("strategy_id"),
        "backend": backend_status or {"mode": "python_fallback", "vtriton_binary_used": False},
        "official_rewrite_guidance": OFFICIAL_REWRITE_GUIDANCE,
        "edit_script_schema_validation": result.edit_script.get("schema_validation", {}),
        "structural_rewrite_performed": bool(result.changes),
        "changes_summary": {
            "total_changes": len(result.changes),
            "change_counts": counts,
        },
        "changes": result.changes,
        "skipped": result.skipped,
        "safety_contract": [
            "This pass changes operation sequence, not only attributes/hints.",
            "The Python fallback applies only explicit pattern-based edits and records every change.",
            "Official MLIR guidance is treated as the production target: all real mutation should move to PatternRewriter/RewriterBase or vTriton/HivmOpsEditor-style operation APIs.",
            "This is still not a full MLIR PatternRewriter/HivmOpsEditor proof; vTriton/Ascend parser and DES/trace validation must be run after rewrite.",
            "No compute op is deleted; no buffer is duplicated; no loop nest is generated in this first structural step.",
        ],
        "next_validation": [
            "Run tritonsim-hivm --npuir-file optimized.structural.hivm.mlir.",
            "Compare DES/trace before and after.",
            "Run correctness check on target compiler/runtime before claiming speedup.",
        ],
    }



_HIVM_OP_PATTERNS = {
    "barrier_all": re.compile(r"\bhivm\.(?:hir\.)?(?:pipe_barrier\[<PIPE_ALL>\]|barrier\b.*mode\s*=\s*\"ALL\")"),
    "set_flag": re.compile(r"\bhivm\.(?:hir\.)?set_flag\["),
    "wait_flag": re.compile(r"\bhivm\.(?:hir\.)?wait_flag\["),
    "load": re.compile(r"\bhivm\.(?:hir\.)?load\b"),
    "store": re.compile(r"\bhivm\.(?:hir\.)?store\b"),
    "cube": _CUBE_PAT,
    "fixpipe": _FIXPIPE_PAT,
    "vector": _VECTOR_PAT,
}


def count_structural_ops(ir_text: str) -> Dict[str, int]:
    """Count structural HIVM op families before/after rewrite.

    When the real MLIR/HIVM parser is available, uses the editor for accurate
    op counts. Otherwise falls back to regex-based counting.
    """
    if _HAS_REAL_PARSER:
        return _count_structural_ops_via_editor(ir_text)
    return _count_structural_ops_via_regex(ir_text)


def _count_structural_ops_via_regex(ir_text: str) -> Dict[str, int]:
    """Count structural HIVM op families using regex (legacy fallback)."""
    code_text = "\n".join(line for line in ir_text.splitlines() if not line.lstrip().startswith("//"))
    return {name: len(pat.findall(code_text)) for name, pat in _HIVM_OP_PATTERNS.items()}


def _count_structural_ops_via_editor(ir_text: str) -> Dict[str, int]:
    """Count structural HIVM op families using the real MLIR parser + HivmOpsEditor."""
    try:
        editor = HivmOpsEditor.load_from_text(ir_text)
        counts = editor.op_counts()
        # Map editor counts to the same keys as regex-based counting
        result = {
            "barrier_all": counts.get('hivm.hir.barrier', 0) + counts.get('hivm.hir.pipe_barrier', 0),
            "set_flag": counts.get('hivm.hir.set_flag', 0),
            "wait_flag": counts.get('hivm.hir.wait_flag', 0),
            "load": counts.get('hivm.hir.load', 0),
            "store": counts.get('hivm.hir.store', 0),
            "cube": sum(
                counts.get(name, 0) for name in ('hivm.hir.mmad', 'hivm.hir.mmadL1', 'hivm.hir.matmul')
            ),
            "fixpipe": counts.get('hivm.hir.fixpipe', 0),
            "vector": sum(
                counts.get(name, 0) for name in (
                    'hivm.hir.vadd', 'hivm.hir.vsub', 'hivm.hir.vmul', 'hivm.hir.vdiv',
                    'hivm.hir.vexp', 'hivm.hir.vreduce', 'hivm.hir.vmax', 'hivm.hir.vmin',
                    'hivm.hir.vrelu', 'hivm.hir.vsqrt', 'hivm.hir.vrec',
                )
            ),
        }
        return result
    except Exception:
        return _count_structural_ops_via_regex(ir_text)


def validate_python_structural_result(original_text: str, rewritten_text: str, result: StructuralRewriteResult) -> Dict[str, Any]:
    """Validate the Python fallback output using cheap but useful invariants.

    Official MLIR validation is still expected from vTriton/target MLIR context.
    These gates keep the demo honest: all claimed changes must be recorded, the
    output should not be empty, braces should stay roughly balanced, and op count
    deltas should match the expected direction for supported edits.
    """
    before = count_structural_ops(original_text)
    after = count_structural_ops(rewritten_text)
    errors: List[str] = []
    warnings: List[str] = []
    if not rewritten_text.strip():
        errors.append("rewritten IR is empty")
    if rewritten_text.count("{") != rewritten_text.count("}"):
        warnings.append("brace count changed or unbalanced; run target MLIR parser")
    if result.changes and original_text == rewritten_text:
        errors.append("changes were reported but IR text is identical")
    if not result.changes:
        warnings.append("no structural changes were applied; inspect skipped reasons")

    change_counts: Dict[str, int] = {}
    for ch in result.changes:
        typ = str(ch.get("type", "unknown"))
        change_counts[typ] = change_counts.get(typ, 0) + 1

    if change_counts.get("replace_barrier_all_with_directional_sync", 0) and after["barrier_all"] >= before["barrier_all"]:
        warnings.append("barrier replacement was reported but barrier_all count did not decrease")
    if change_counts.get("insert_sync_before_first_vector_op", 0) and (after["set_flag"] + after["wait_flag"] <= before["set_flag"] + before["wait_flag"]):
        warnings.append("CV sync insertion was reported but sync op count did not increase")

    return {
        "schema_version": "hivm_structural_python_fallback_validation_v1",
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "op_counts_before": before,
        "op_counts_after": after,
        "op_count_delta": {k: after.get(k, 0) - before.get(k, 0) for k in sorted(set(before) | set(after))},
        "change_counts": change_counts,
        "official_validation_required": [
            "Parse optimized.structural.hivm.mlir with the target vTriton/HIVM MLIR context.",
            "Run tritonsim-hivm or equivalent DES/trace generation before claiming performance impact.",
        ],
    }


def build_structural_validation_summary(
    original_ir_text: str,
    optimized_ir_text: str,
    rewrite_report: Optional[Dict[str, Any]] = None,
    legality_report: Optional[Dict[str, Any]] = None,
    tritonsim_validation_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a Phase-2F validation summary for structural rewrite outputs.

    This summary is deliberately parser-independent so it can run in CI without a
    local vTriton/LLVM build.  It does **not** prove semantic correctness; it
    checks that the actual optimized IR reflects the claimed structural edits and
    records what still requires target MLIR/vTriton validation.
    """
    rewrite_report = rewrite_report or {}
    legality_report = legality_report or {}
    before = count_structural_ops(original_ir_text)
    after = count_structural_ops(optimized_ir_text)
    keys = sorted(set(before) | set(after))
    delta = {k: after.get(k, 0) - before.get(k, 0) for k in keys}

    changes = rewrite_report.get("changes", []) if isinstance(rewrite_report, dict) else []
    claimed_counts: Dict[str, int] = {}
    if isinstance(rewrite_report.get("changes_summary"), dict):
        claimed_counts = dict((rewrite_report.get("changes_summary") or {}).get("change_counts", {}) or {})
    if not claimed_counts and isinstance(changes, list):
        for ch in changes:
            if isinstance(ch, dict):
                typ = str(ch.get("type", "unknown"))
                claimed_counts[typ] = claimed_counts.get(typ, 0) + 1

    errors: List[str] = []
    warnings: List[str] = []
    evidence: Dict[str, Any] = {}

    if not optimized_ir_text.strip():
        errors.append("optimized structural IR is empty")
    if original_ir_text == optimized_ir_text and sum(claimed_counts.values()) > 0:
        errors.append("rewrite report claims changes but optimized IR is text-identical to input")
    if optimized_ir_text.count("{") != optimized_ir_text.count("}"):
        warnings.append("optimized IR brace count is unbalanced; run target MLIR parser")

    barrier_rewrites = int(claimed_counts.get("replace_barrier_all_with_directional_sync", 0) or 0)
    cv_sync_insertions = int(claimed_counts.get("insert_sync_before_first_vector_op", 0) or 0)
    q_hoists = int(claimed_counts.get("hoist_invariant_q_load_from_simple_loop", 0) or 0)

    if barrier_rewrites:
        evidence["barrier_rewrite_expected"] = {
            "claimed": barrier_rewrites,
            "barrier_all_delta": delta.get("barrier_all", 0),
            "set_flag_delta": delta.get("set_flag", 0),
            "wait_flag_delta": delta.get("wait_flag", 0),
        }
        if delta.get("barrier_all", 0) > -barrier_rewrites:
            warnings.append("claimed barrier rewrites are not fully reflected by barrier_all count decrease")
        if delta.get("set_flag", 0) < barrier_rewrites or delta.get("wait_flag", 0) < barrier_rewrites:
            warnings.append("claimed barrier rewrites did not add expected directional set/wait count")

    if cv_sync_insertions:
        evidence["cv_sync_expected"] = {
            "claimed": cv_sync_insertions,
            "set_flag_delta": delta.get("set_flag", 0),
            "wait_flag_delta": delta.get("wait_flag", 0),
        }
        min_sync_delta = barrier_rewrites + cv_sync_insertions
        if delta.get("set_flag", 0) < min_sync_delta or delta.get("wait_flag", 0) < min_sync_delta:
            warnings.append("claimed CV sync insertion is not reflected in set/wait count delta")

    if q_hoists:
        # Hoisting should usually keep load count stable while changing location.
        evidence["q_hoist_expected"] = {
            "claimed": q_hoists,
            "load_delta": delta.get("load", 0),
            "store_delta": delta.get("store", 0),
        }
        if abs(delta.get("load", 0)) > 1:
            warnings.append("Q-load hoist changed load count unexpectedly; inspect rewrite diff")

    # Treat GM round-trip deletion specially: Phase-2E/F only detects/defer; any
    # GM load/store decrease is suspicious unless a future backend explicitly
    # reports a deletion edit.
    gm_delete_claimed = int(claimed_counts.get("remove_redundant_gm_roundtrip", 0) or 0)
    if not gm_delete_claimed and (delta.get("load", 0) < 0 or delta.get("store", 0) < 0):
        warnings.append("GM load/store count decreased without an approved GM round-trip deletion edit")

    local_legality = (legality_report or {}).get("summary", {}) if isinstance(legality_report, dict) else {}
    tritonsim_status = None
    if isinstance(tritonsim_validation_report, dict):
        tritonsim_status = {
            "input_ran": bool(((tritonsim_validation_report.get("input_ir") or {}).get("ran"))),
            "optimized_ran": bool(((tritonsim_validation_report.get("optimized_structural_ir") or {}).get("ran"))),
            "input_returncode": (tritonsim_validation_report.get("input_ir") or {}).get("returncode"),
            "optimized_returncode": (tritonsim_validation_report.get("optimized_structural_ir") or {}).get("returncode"),
        }

    return {
        "schema_version": "hivm_structural_validation_summary_v1",
        "producer": "strategy_search_demo_v3.3.2_phase2g_vtriton_adapter_manifest",
        "passed_local_validation": not errors,
        "errors": errors,
        "warnings": warnings,
        "op_counts_before": before,
        "op_counts_after": after,
        "op_count_delta": delta,
        "claimed_change_counts": claimed_counts,
        "evidence_checks": evidence,
        "local_legality_summary": local_legality,
        "tritonsim_validation_status": tritonsim_status,
        "interpretation": {
            "what_this_proves": "The emitted optimized.structural.hivm.mlir reflects the claimed local op-count changes under lightweight parser-independent checks.",
            "what_this_does_not_prove": "It does not prove target HIVM dialect parse success, dependency legality, buffer liveness, event live-range correctness, numerical correctness, or real hardware speedup.",
        },
        "required_next_validation": [
            "Parse optimized.structural.hivm.mlir in the target vTriton/HIVM MLIR context.",
            "Run tritonsim-hivm / DES / trace comparison for input and optimized IR.",
            "Run target compiler/runtime correctness validation before claiming performance.",
        ],
    }




def _sha256_file(path: Optional[str]) -> Optional[str]:
    """Return sha256 for a local binary/file when available."""
    if not path:
        return None
    exe = shutil.which(path) or path
    p = Path(exe)
    if not p.exists() or not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _backend_arg_prefix(binary: Optional[str]) -> List[str]:
    """Return a command prefix for invoking a backend binary.

    Python scripts are invoked via the current interpreter so they work
    even when the executable bit is lost after zip extraction on Windows / Linux.
    """
    if binary is None:
        return []
    if binary.endswith('.py'):
        return [sys.executable, binary]
    return [binary]


def try_query_strategy_rewriter_capabilities(rewriter_binary: Optional[str] = None) -> Dict[str, Any]:
    """Query capabilities of a vTriton-compatible hivm-strategy-rewrite binary.

    Phase-2G adds a stable handshake boundary.  The standalone C++ bridge
    supports ``--print-capabilities``.  Future vTriton/HivmOpsEditor backends
    should keep this command-line contract so the Python strategy searcher can
    decide whether to run an external backend, fall back, or fail fast.
    """
    if not rewriter_binary:
        return {"queried": False, "available": False, "reason": "no_binary_configured"}
    exe = shutil.which(rewriter_binary) or rewriter_binary
    if not Path(exe).exists() and shutil.which(rewriter_binary) is None:
        return {"queried": False, "available": False, "reason": f"binary_not_found: {rewriter_binary}"}
    try:
        proc = subprocess.run(_backend_arg_prefix(exe) + ["--print-capabilities"], text=True, capture_output=True, timeout=30)
    except Exception as exc:
        return {"queried": True, "available": False, "reason": f"capability_query_failed: {exc}"}
    out = (proc.stdout or "").strip()
    try:
        payload = json.loads(out) if out else {}
    except Exception as exc:
        return {
            "queried": True,
            "available": proc.returncode == 0,
            "returncode": proc.returncode,
            "reason": f"capability_json_parse_failed: {exc}",
            "stdout_tail": proc.stdout[-2000:],
            "stderr_tail": proc.stderr[-2000:],
        }
    payload.update({
        "queried": True,
        "available": proc.returncode == 0,
        "returncode": proc.returncode,
        "binary": exe,
        "binary_sha256": _sha256_file(exe),
        "stderr_tail": proc.stderr[-2000:],
    })
    return payload


def build_vtriton_adapter_manifest(
    backend_plan: Dict[str, Any],
    edit_script: Dict[str, Any],
    strategy_rewriter_binary: Optional[str],
    hivm_crud_binary: Optional[str],
    tritonsim_hivm: Optional[str],
    strategy: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the Phase-2G manifest for the vTriton/HivmOpsEditor boundary.

    The manifest is a small contract file for downstream backend owners.  It is
    intentionally more explicit than ``structural_backend_execution_plan``:
    that file says what this run selected; this manifest says what interface a
    production HivmOpsEditor/MLIR backend must satisfy.
    """
    capability_query = try_query_strategy_rewriter_capabilities(strategy_rewriter_binary)
    requested_edits = [e.get("type") for e in edit_script.get("edits", []) if e.get("enabled", True)]
    requested_unique = sorted({str(x) for x in requested_edits if x})
    supported = set(capability_query.get("supported_edits") or []) if isinstance(capability_query, dict) else set()
    coverage = {name: (name in supported if supported else None) for name in requested_unique}
    missing = [name for name, ok in coverage.items() if ok is False]
    return {
        "schema_version": "hivm_vtriton_adapter_manifest_v1",
        "producer": "strategy_search_demo_v3.3.2_phase2g_vtriton_adapter_manifest",
        "phase": "Phase-2G",
        "purpose": "Harden the Python strategy-search to vTriton/HivmOpsEditor structural rewrite interface before Phase-2 closure.",
        "strategy_id": strategy.get("strategy_id"),
        "backend_execution_plan": backend_plan,
        "external_strategy_rewriter_capabilities": capability_query,
        "requested_enabled_edit_types": requested_unique,
        "external_backend_coverage": {
            "coverage_by_edit_type": coverage,
            "missing_required_edits_in_external_backend": missing,
            "coverage_interpretation": "None values mean no capability manifest was available, so runtime execution/fallback decides.",
        },
        "interface_contract": {
            "required_cli": "hivm-strategy-rewrite --input in.mlir --edit-script structural_edit_script.json --output out.mlir --report report.json",
            "capability_cli": "hivm-strategy-rewrite --print-capabilities",
            "required_report_schema_fields": [
                "schema_version", "success", "backend_mode", "bridge_phase",
                "supported_edits", "applied_changes", "change_counts", "changes", "skipped"
            ],
            "required_runtime_guards": [
                "Parse input in target HIVM/NPUIR MLIR context before mutation.",
                "Apply mutations through HivmOpsEditor or PatternRewriter/RewriterBase-style APIs in production.",
                "Preserve a change list for every inserted/deleted/replaced op.",
                "Emit skipped/deferred reasons when legality gates are not proven.",
                "Run target parser or tritonsim-hivm after mutation before claiming performance."
            ],
        },
        "known_binaries": {
            "vtriton_strategy_rewriter": strategy_rewriter_binary,
            "vtriton_strategy_rewriter_sha256": _sha256_file(strategy_rewriter_binary),
            "vtriton_hivm_crud": hivm_crud_binary,
            "vtriton_hivm_crud_sha256": _sha256_file(hivm_crud_binary),
            "tritonsim_hivm": tritonsim_hivm,
            "tritonsim_hivm_sha256": _sha256_file(tritonsim_hivm),
        },
        "phase2g_boundary": {
            "completed_in_this_phase": [
                "Stable capability handshake for standalone/external HIVM strategy rewrite backends.",
                "Adapter manifest records requested edits, backend coverage, binary identity, and production interface contract.",
                "C++ strict bridge exposes --print-capabilities for CI and backend selection."
            ],
            "still_not_done": [
                "Full vTriton/HivmOpsEditor parser integration in this sandbox.",
                "Target dialect legality proof, buffer live range checker, event liveness checker.",
                "Real double-buffer, full CV overlap, and real tiling lowering."
            ],
        },
    }

def build_backend_execution_plan(
    backend: str,
    strategy_rewriter_binary: Optional[str],
    hivm_crud_binary: Optional[str],
    tritonsim_hivm: Optional[str],
) -> Dict[str, Any]:
    """Describe how structural rewrite will be executed in this environment."""
    backend = str(backend or "auto").lower()
    def _exists(x: Optional[str]) -> bool:
        if not x:
            return False
        return bool(shutil.which(x) or Path(x).exists())
    strategy_rewriter_found = _exists(strategy_rewriter_binary)
    crud_found = _exists(hivm_crud_binary)
    tritonsim_found = _exists(tritonsim_hivm)
    selected = backend
    reason = "user_selected"
    if backend == "auto":
        if strategy_rewriter_found:
            selected = "vtriton_strategy_rewriter"
            reason = "--vtriton-strategy-rewriter found"
        elif crud_found:
            selected = "vtriton_hivm_crud"
            reason = "--vtriton-hivm-crud found"
        else:
            selected = "python_fallback"
            reason = "no external vTriton rewrite binary found"
    elif backend == "vtriton":
        if strategy_rewriter_found:
            selected = "vtriton_strategy_rewriter"
            reason = "backend=vtriton requested and --vtriton-strategy-rewriter found"
        elif crud_found:
            selected = "vtriton_hivm_crud"
            reason = "backend=vtriton requested and --vtriton-hivm-crud found"
        else:
            selected = "dry_run_failed_no_backend"
            reason = "backend=vtriton requested but no vTriton binary was found"
    elif backend == "dry_run":
        selected = "dry_run"
        reason = "emit and validate edit script without mutating IR"
    return {
        "schema_version": "hivm_structural_backend_execution_plan_v1",
        "requested_backend": backend,
        "selected_backend": selected,
        "reason": reason,
        "binaries": {
            "vtriton_strategy_rewriter": strategy_rewriter_binary,
            "vtriton_strategy_rewriter_found": strategy_rewriter_found,
            "vtriton_hivm_crud": hivm_crud_binary,
            "vtriton_hivm_crud_found": crud_found,
            "tritonsim_hivm": tritonsim_hivm,
            "tritonsim_hivm_found": tritonsim_found,
        },
        "official_backend_target": "Phase-2G standalone C++ strict bridge exposes a capability handshake and supports barrier rewrite + CV boundary sync insertion; production target remains MLIR/vTriton Operation-level rewrite via HivmOpsEditor/PatternRewriter-style mutation APIs",
        "python_fallback_policy": "Allowed for auditable prototype and CI tests only; not the final production compiler pass.",
    }


def try_run_external_strategy_rewriter(
    input_path: Path,
    edit_script_path: Path,
    output_path: Path,
    report_path: Path,
    rewriter_binary: Optional[str],
) -> Dict[str, Any]:
    """Call a vTriton-compatible hivm-strategy-rewrite binary if present."""
    if not rewriter_binary:
        return {"mode": "not_run", "vtriton_strategy_rewriter_used": False, "reason": "no_binary_configured"}
    exe = shutil.which(rewriter_binary) or rewriter_binary
    if not Path(exe).exists() and shutil.which(rewriter_binary) is None:
        return {"mode": "not_run", "vtriton_strategy_rewriter_used": False, "reason": f"binary_not_found: {rewriter_binary}"}
    cmd = _backend_arg_prefix(exe) + ["--input", str(input_path), "--edit-script", str(edit_script_path), "--output", str(output_path), "--report", str(report_path)]
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=120)
    return {
        "mode": "external_vtriton_strategy_rewriter",
        "vtriton_strategy_rewriter_used": proc.returncode == 0,
        "returncode": proc.returncode,
        "cmd": cmd,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
        "output_exists": output_path.exists(),
        "report_exists": report_path.exists(),
    }


def try_run_tritonsim_validation(
    ir_path: Path,
    tritonsim_hivm: Optional[str],
    out_dir: Path,
    tag: str,
    des_graph_file: Optional[Path] = None,
    perfetto_trace_file: Optional[Path] = None,
) -> Dict[str, Any]:
    """Optionally run tritonsim-hivm and request DES/Perfetto artifacts.

    Phase-3E keeps this wrapper deliberately conservative: when the binary is
    missing, it emits a pending report; when it is present, it calls the common
    vTriton-style ``--npuir-file`` entry and, if paths are supplied, also passes
    ``--des-graph-file`` and ``--perfetto-trace-file``.  Some local vTriton
    builds may use slightly different flag spellings; in that case stdout/stderr
    and the non-zero return code become the audit evidence instead of silently
    claiming validation passed.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    if des_graph_file is None:
        des_graph_file = out_dir / f"{tag}_des_graph.json"
    if perfetto_trace_file is None:
        perfetto_trace_file = out_dir / f"{tag}_perfetto_trace.json"
    if not tritonsim_hivm:
        return {
            "tag": tag,
            "ran": False,
            "reason": "no_tritonsim_hivm_configured",
            "expected_des_graph_file": str(des_graph_file),
            "expected_perfetto_trace_file": str(perfetto_trace_file),
        }
    exe = shutil.which(tritonsim_hivm) or tritonsim_hivm
    if not Path(exe).exists() and shutil.which(tritonsim_hivm) is None:
        return {
            "tag": tag,
            "ran": False,
            "reason": f"binary_not_found: {tritonsim_hivm}",
            "expected_des_graph_file": str(des_graph_file),
            "expected_perfetto_trace_file": str(perfetto_trace_file),
        }
    cmd = _backend_arg_prefix(exe) + [
        "--npuir-file", str(ir_path),
        "--des-graph-file", str(des_graph_file),
        "--perfetto-trace-file", str(perfetto_trace_file),
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=180)
    (out_dir / f"{tag}_tritonsim_stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (out_dir / f"{tag}_tritonsim_stderr.txt").write_text(proc.stderr, encoding="utf-8")
    return {
        "tag": tag,
        "ran": True,
        "returncode": proc.returncode,
        "cmd": cmd,
        "stdout_file": str(out_dir / f"{tag}_tritonsim_stdout.txt"),
        "stderr_file": str(out_dir / f"{tag}_tritonsim_stderr.txt"),
        "des_graph_file": str(des_graph_file),
        "perfetto_trace_file": str(perfetto_trace_file),
        "des_graph_exists": des_graph_file.exists(),
        "perfetto_trace_exists": perfetto_trace_file.exists(),
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }

def try_run_external_vtriton_hivm_crud(
    input_path: Path,
    output_path: Path,
    crud_binary: Optional[str],
    mode: str = "roundtrip",
    remove_gm_trips: int = 0,
) -> Dict[str, Any]:
    """Optionally call an external vTriton hivm-crud binary.

    The demo does not require this. If ``crud_binary`` is missing, callers use
    the Python fallback above. When provided, this function executes the binary
    and reports stdout/stderr for audit.
    """
    if not crud_binary:
        return {"mode": "python_fallback", "vtriton_binary_used": False, "reason": "no_binary_configured"}
    exe = shutil.which(crud_binary) or crud_binary
    if not Path(exe).exists() and shutil.which(crud_binary) is None:
        return {"mode": "python_fallback", "vtriton_binary_used": False, "reason": f"binary_not_found: {crud_binary}"}
    cmd = _backend_arg_prefix(exe) + ["--input", str(input_path), "--output", str(output_path), "--mode", mode]
    if remove_gm_trips:
        cmd += ["--remove-gm-trips", str(remove_gm_trips)]
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=60)
    return {
        "mode": "external_vtriton_hivm_crud",
        "vtriton_binary_used": proc.returncode == 0,
        "returncode": proc.returncode,
        "cmd": cmd,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }


def build_phase2_closure_report(
    edit_script: Optional[Dict[str, Any]] = None,
    backend_plan: Optional[Dict[str, Any]] = None,
    adapter_manifest: Optional[Dict[str, Any]] = None,
    legality_report: Optional[Dict[str, Any]] = None,
    rewrite_report: Optional[Dict[str, Any]] = None,
    validation_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the Phase-2H closure/status report.

    Phase 2 is intentionally closed at the operation-level bridge boundary.  It
    standardizes edit-script generation, legality precheck, external backend
    capability handshake, lightweight validation, and a C++ strict bridge for two
    conservative mutations.  It does **not** include real double-buffer, full CV
    overlap, or tiling lowering; those require Phase 3+ dependency and liveness
    analysis.
    """
    edit_script = edit_script or {}
    backend_plan = backend_plan or {}
    adapter_manifest = adapter_manifest or {}
    legality_report = legality_report or {}
    rewrite_report = rewrite_report or {}
    validation_summary = validation_summary or {}

    claimed_counts = dict((rewrite_report.get("changes_summary") or {}).get("change_counts", {}) or {})
    coverage = (((adapter_manifest.get("external_backend_coverage") or {}).get("coverage_by_edit_type")) or {})
    requested_edits = [str(e.get("type")) for e in edit_script.get("edits", []) if isinstance(e, dict) and e.get("enabled", True)]

    phase2_matrix = [
        {
            "subphase": "Phase 2A",
            "name": "Backend boundary",
            "status": "completed",
            "evidence": ["structural_backend_execution_plan.json", "--structural-rewrite-backend auto|python|vtriton|dry_run"],
            "scope": "Separate Python strategy search from a future vTriton/HivmOpsEditor structural backend.",
        },
        {
            "subphase": "Phase 2B",
            "name": "Legality precheck",
            "status": "completed",
            "evidence": ["structural_legality_report.json"],
            "scope": "Local anchor detection and precheck/deferred decision for edit requests.",
        },
        {
            "subphase": "Phase 2C",
            "name": "C++ bridge barrier rewrite",
            "status": "completed",
            "evidence": ["vtriton_adapter/hivm_strategy_rewrite.cpp", "replace_barrier_all_with_directional_sync"],
            "scope": "Standalone C++ strict bridge can replace explicit barrier_ALL anchors with directional set/wait pairs.",
        },
        {
            "subphase": "Phase 2D",
            "name": "C++ bridge CV boundary sync",
            "status": "completed",
            "evidence": ["insert_sync_before_first_vector_op"],
            "scope": "Standalone C++ strict bridge can insert a minimal CV boundary set/wait pair before a vector stage anchor.",
        },
        {
            "subphase": "Phase 2E",
            "name": "GM round-trip precheck",
            "status": "completed_as_precheck_only",
            "evidence": ["remove_redundant_gm_roundtrip edit is generated and reported as deferred"],
            "scope": "Candidate detection/request only; deletion is intentionally deferred until target alias/dependency proof.",
        },
        {
            "subphase": "Phase 2F",
            "name": "Structural validation summary",
            "status": "completed",
            "evidence": ["structural_validation_summary.json"],
            "scope": "Parser-independent op-count delta audit for original vs optimized structural IR.",
        },
        {
            "subphase": "Phase 2G",
            "name": "Adapter manifest and capability handshake",
            "status": "completed",
            "evidence": ["vtriton_adapter_manifest.json", "hivm-strategy-rewrite --print-capabilities"],
            "scope": "External backend coverage, missing edit types, binary identity, and CLI/report contract are recorded.",
        },
        {
            "subphase": "Phase 2H",
            "name": "Closure and Phase-3 handoff",
            "status": "completed_in_this_version",
            "evidence": ["PHASE2_CLOSURE_AND_PHASE3_PLAN.md", "phase2_closure_report.json"],
            "scope": "Close Phase 2 as an operation-level rewrite bridge and define Phase 3 dependency/liveness roadmap.",
        },
    ]

    rewrite_capability_status = {
        "cxx_backend_mutation_supported": [
            "replace_barrier_all_with_directional_sync",
            "insert_sync_before_first_vector_op",
        ],
        "precheck_or_deferred": ["remove_redundant_gm_roundtrip"],
        "python_fallback_or_not_required_for_phase2_closure": [
            "hoist_invariant_q_load_from_simple_loop",
            "remove_adjacent_duplicate_sync_pairs",
        ],
        "explicitly_out_of_phase2_scope": [
            "real GM round-trip deletion",
            "real double-buffer ping-pong buffer duplication",
            "full cube/vector/store overlap scheduling",
            "real tiling loop lowering",
            "event reuse and sync motion",
        ],
    }

    phase3_plan = [
        {
            "phase": "Phase 3A",
            "task": "Dependency graph and event-liveness foundation",
            "goal": "Build producer-consumer, pipe dependency, barrier/set/wait, and event live-range summaries for HIVM op sequences.",
            "deliverables": ["dependency_graph_report.json", "event_liveness_report.json", "sync_dependency_report.json"],
            "difficulty": "High: requires target dialect-aware parsing or a reliable vTriton/HivmOpsEditor integration; text-level order is not enough for nested regions and SSA dataflow.",
        },
        {
            "phase": "Phase 3B",
            "task": "Buffer liveness and alias checker",
            "goal": "Prove whether UB/L1/GM values can be hoisted, reused, or removed without breaking semantics.",
            "deliverables": ["buffer_liveness_report.json", "gm_alias_report.json", "hoist_legality_report.json"],
            "difficulty": "High: same-GM-base proof, SSA aliasing, loop-carried uses, accumulator/output buffers, and intermediate writes are easy to misclassify.",
        },
        {
            "phase": "Phase 3C",
            "task": "Safe GM round-trip deletion",
            "goal": "Turn Phase-2E deferred candidates into actual deletion only when alias/dependency proof passes.",
            "deliverables": ["optimized.gm_cleanup.hivm.mlir", "gm_roundtrip_deletion_report.json"],
            "difficulty": "Medium-high: deletion affects observable memory behavior; candidate detection is much easier than proof.",
        },
        {
            "phase": "Phase 3D",
            "task": "Loop-invariant load hoist with legality proof",
            "goal": "Move invariant Q/metadata loads out of simple KV loops only when induction-variable independence and buffer lifetime are proven.",
            "deliverables": ["optimized.hoisted.hivm.mlir", "load_hoist_report.json"],
            "difficulty": "Medium-high: nesting, dynamic offsets, and hidden side effects can invalidate simple textual invariance.",
        },
        {
            "phase": "Phase 3E",
            "task": "tritonsim-hivm DES/trace validation integration",
            "goal": "Automatically compare original and optimized DES/trace outputs and feed deltas back to reports.",
            "deliverables": ["des_comparison_report.json", "trace_comparison_report.html", "vtriton_validation_report.json"],
            "difficulty": "Medium: depends on local vTriton build flags and stable output formats.",
        },
    ]

    return {
        "schema_version": "hivm_phase2_closure_report_v1",
        "producer": "strategy_search_demo_v3.3.2_phase2h_closure",
        "phase": "Phase-2H",
        "phase2_status": "closed",
        "phase2_definition": "Operation-level rewrite bridge and audit/validation boundary. Phase 2 does not attempt full compiler lowering.",
        "official_method_alignment": {
            "rewrite_model": "Strategy search emits structural_edit_script.json; production mutation should be performed by vTriton/HivmOpsEditor or MLIR PatternRewriter/RewriterBase-style operation APIs.",
            "legality_model": "Each edit carries a legality contract; local precheck may pass/defer, and target dialect proof is required for data movement deletion, buffer reuse, event reuse, or op motion.",
            "validation_model": "Parser-independent validation summary is a CI audit; target MLIR parse, DES/trace, and runtime correctness are still required before claiming speedup.",
        },
        "subphase_matrix": phase2_matrix,
        "runtime_evidence": {
            "requested_enabled_edits": sorted(set(requested_edits)),
            "external_backend_selected": backend_plan.get("selected_backend"),
            "external_backend_coverage": coverage,
            "claimed_change_counts": claimed_counts,
            "local_legality_summary": legality_report.get("summary", {}),
            "local_validation_passed": validation_summary.get("passed_local_validation"),
            "validation_warnings": validation_summary.get("warnings", []),
        },
        "rewrite_capability_status": rewrite_capability_status,
        "phase2_completion_criteria": {
            "edit_script_standardized": True,
            "legality_precheck_available": True,
            "external_backend_capability_handshake_available": True,
            "cxx_bridge_has_real_mutations": True,
            "parser_independent_validation_available": True,
            "target_vtriton_parser_required_for_production": True,
        },
        "phase3_plan": phase3_plan,
        "phase3_key_difficulties": [
            "HIVM/NPUIR dialect-aware parsing is needed; text-level rewrite cannot safely reason about nested regions, SSA use-def chains, or op attributes.",
            "Sync rewrites need event liveness and pipe dependency proof to avoid deadlock, stale read, or data race.",
            "GM round-trip deletion requires alias/dependency proof; same-looking load/store text is insufficient.",
            "Buffer hoist/reuse needs live-range and capacity checks, especially for accumulator/output/persistent buffers.",
            "tritonsim-hivm and msprof validation may differ from analytical cost model; calibration loop must remain explicit.",
        ],
        "recommended_next_entrypoint": "Phase 3A: dependency graph and event-liveness foundation",
    }
