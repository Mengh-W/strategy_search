# -*- coding: utf-8 -*-
"""Schema and validation helpers for operation-level HIVM structural edits.

This module formalizes the boundary between the Python strategy searcher and a
future vTriton/HivmOpsEditor or MLIR PatternRewriter backend.  The Python side
may *plan* edits, but the long-term structural mutation should be implemented by
an operation-level rewriter that owns parser state and legality checks.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Tuple

SUPPORTED_EDIT_TYPES = {
    "remove_redundant_gm_roundtrip",
    "replace_barrier_all_with_directional_sync",
    "insert_cv_boundary_sync",
    "insert_sync_before_first_vector_op",  # backward-compatible alias used by the Python fallback
    "hoist_loop_invariant_q_load",
    "hoist_invariant_q_load_from_simple_loop",  # backward-compatible alias used by the Python fallback
    "remove_adjacent_duplicate_sync_pairs",
}

MUTATION_KINDS = {
    "remove_redundant_gm_roundtrip": ["erase_op"],
    "replace_barrier_all_with_directional_sync": ["replace_op", "create_op"],
    "insert_cv_boundary_sync": ["create_op"],
    "insert_sync_before_first_vector_op": ["create_op"],
    "hoist_loop_invariant_q_load": ["move_op"],
    "hoist_invariant_q_load_from_simple_loop": ["move_op"],
    "remove_adjacent_duplicate_sync_pairs": ["erase_op"],
}

OFFICIAL_REWRITE_GUIDANCE = {
    "mlir_pattern_rewriter": {
        "principle": "Operation-level IR mutations should be performed through PatternRewriter/RewriterBase inside matchAndRewrite or an equivalent pass-owned mutation API.",
        "project_rule": "Python text rewrite is kept only as an auditable fallback/prototype; production HIVM rewrite should use vTriton/HivmOpsEditor or a MLIR pass.",
    },
    "mlir_dialect_conversion": {
        "principle": "Use an explicit legality model: define which operations/patterns are legal after transformation and reject/skip unsafe partial rewrites.",
        "project_rule": "Every structural edit must report legality passed/failed/skipped and the evidence used by that decision.",
    },
    "mlir_operation_model": {
        "principle": "MLIR IR is made of Operations and Values; rewrite engineering should reason over op anchors, operands, results, regions, and effects rather than formatting text.",
        "project_rule": "Edit scripts name op-level anchors and mutation kinds, not arbitrary line numbers as the source of truth.",
    },
}


def structural_edit_schema() -> Dict[str, Any]:
    """Return the JSON schema-like contract used by this project.

    This is intentionally dependency-free.  It is not a full JSON Schema draft
    implementation; it is a stable machine-readable contract and is written to
    ``structural_edit_schema.json`` for downstream C++/vTriton backends.
    """
    return {
        "schema_version": "hivm_structural_edit_script_v1",
        "producer_contract": "strategy_search emits edit intent; vTriton/HivmOpsEditor or MLIR pass performs production mutation",
        "official_rewrite_guidance": OFFICIAL_REWRITE_GUIDANCE,
        "required_top_level_fields": [
            "schema_version",
            "producer",
            "backend_model",
            "rewrite_safety",
            "strategy_id",
            "selected_plan_summary",
            "edits",
            "guards",
            "legality_contract",
        ],
        "edit_fields": {
            "type": {"required": True, "allowed_values": sorted(SUPPORTED_EDIT_TYPES)},
            "enabled": {"required": True, "type": "bool"},
            "max_edits": {"required": False, "type": "integer>=0"},
            "anchor": {"required": False, "description": "Operation-level anchor/pattern to match in the backend."},
            "mutation_kinds": {"required": False, "description": "create_op/erase_op/replace_op/move_op/modify_attr."},
            "legality": {"required": True, "description": "Static safety gates required before applying the edit."},
            "reason": {"required": True, "description": "Why the selected strategy requests this edit."},
        },
        "supported_edit_types": sorted(SUPPORTED_EDIT_TYPES),
        "mutation_kinds_by_edit_type": deepcopy(MUTATION_KINDS),
        "safety_levels": {
            "conservative": "emit edit intent but apply only edits with explicit anchors and local legality evidence",
            "balanced": "apply first-batch low-risk local edits; recommended default for demo validation",
            "aggressive": "allow cleanup/reuse-style edits; requires stronger post-rewrite validation",
        },
        "hard_boundaries": [
            "No full tiling loop lowering in v1.",
            "No ping-pong buffer duplication in v1.",
            "No full CV overlap scheduling in v1.",
            "No event-id reuse or sync motion without dependency graph proof.",
        ],
    }


def legality_contract() -> Dict[str, Any]:
    """Return legality gates shared by generated edit scripts."""
    return {
        "version": "hivm_legality_contract_v1",
        "required_for_every_edit": [
            "explicit_op_anchor_found",
            "max_edit_bound_respected",
            "mutation_recorded_in_report",
            "fallback_reason_recorded_when_skipped",
        ],
        "sync_rewrite_gates": [
            "producer_consumer_pipe_pair_is_known",
            "fresh_event_id_or_non_overlapping_event_live_range",
            "no_cross_iteration_dependency_is_removed",
            "post_rewrite_parser_validation_required",
        ],
        "load_hoist_gates": [
            "candidate_uses_no_loop_induction_variable",
            "candidate_source_is_loop_invariant",
            "no_intermediate_write_to_same_buffer_or_gm_base",
            "hoisted_ops_dominate_original_consumers",
        ],
        "gm_roundtrip_gates": [
            "load_store_pair_targets_same_gm_base",
            "no_intermediate_consumer_requires_the_roundtrip",
            "no_intermediate_write_clobbers_the_value",
        ],
        "validation_after_rewrite": [
            "parse_with_vTriton_or_target_MLIR_context",
            "compare_DES_dependency_graph",
            "compare_trace_pipeline_utilization",
            "run_correctness_or_runtime_validation_before_claiming_speedup",
        ],
    }


def validate_structural_edit_script(script: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Lightweight dependency-free validation for generated edit scripts."""
    errors: List[str] = []
    schema = structural_edit_schema()
    for key in schema["required_top_level_fields"]:
        if key not in script:
            errors.append(f"missing top-level field: {key}")
    if script.get("schema_version") != schema["schema_version"]:
        errors.append(f"unsupported schema_version: {script.get('schema_version')}")
    edits = script.get("edits")
    if not isinstance(edits, list):
        errors.append("edits must be a list")
        return False, errors
    for i, edit in enumerate(edits):
        if not isinstance(edit, dict):
            errors.append(f"edits[{i}] must be an object")
            continue
        typ = edit.get("type")
        if typ not in SUPPORTED_EDIT_TYPES:
            errors.append(f"edits[{i}].type unsupported: {typ}")
        if "enabled" not in edit:
            errors.append(f"edits[{i}].enabled missing")
        if "legality" not in edit:
            errors.append(f"edits[{i}].legality missing")
        if "reason" not in edit:
            errors.append(f"edits[{i}].reason missing")
    return not errors, errors
