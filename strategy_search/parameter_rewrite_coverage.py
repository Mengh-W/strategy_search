# -*- coding: utf-8 -*-
"""V5.3 parameter-to-rewrite coverage utilities.

This module answers a very practical question: for every controllable knob in
selected_plan.json, is there a visible rewrite consumer in the generated HIVM?

We distinguish four levels:

* RESTRICTED_STRUCTURAL_REWRITE: the knob drives a visible portable IR mutation
  such as sync insertion, local symbol replacement, or slot creation. This is
  still not a verified production Operation rewrite.
* TRACE_METADATA_REWRITE: the knob is embedded back into IR as selected-plan
  metadata/annotations for traceability, but the portable path does not yet
  lower it into loop/index/use mutation.
* PRODUCTION_OPERATION_REWRITE: reserved for a future HivmOpsEditor/MLIR-verified
  rewrite. V5.3.1 intentionally emits zero rows at this level.
* EVIDENCE_ONLY: detected evidence/derived features, not a controllable rewrite knob.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

PARAM_COVERAGE_VERSION = "hivm_v531_parameter_rewrite_coverage_v2"

PLAN_KEYS = ["tiling_plan", "multibuffer_plan", "cv_pipeline_plan", "sync_plan"]

REWRITE_CONSUMER_MAP = {
    "tiling_plan": {
        "tile_m": "tiling_metadata_constants",
        "tile_n": "tiling_metadata_constants",
        "tile_k": "tiling_metadata_constants",
        "loop_order": "tiling_metadata_annotation",
        "tail_strategy": "tiling_metadata_annotation",
        "reduce_tile_policy": "tiling_metadata_annotation",
    },
    "multibuffer_plan": {
        "double_buffer": "ping_pong_slot_insertion",
        "input_buffer_multiplier": "ping_pong_slot_selection_or_metadata",
        "stage_buffer_multiplier": "ping_pong_slot_selection_or_metadata",
        "ub_multiplier": "scope_specific_multibuffer_metadata",
        "l1_multiplier": "scope_specific_multibuffer_metadata",
        "stage_buffer_policy": "producer_consumer_replacement_policy",
        "buffer_multipliers": "per_scope_buffer_multiplier_metadata",
        "buffer_multiplier_domain": "allowed_multiplier_domain_metadata",
        "detected_ping_pong_multibuffer": "existing_pingpong_evidence_metadata",
    },
    "cv_pipeline_plan": {
        "stage_num": "pipeline_group_and_sync_edge_count_metadata",
        "enable_mixed_cv": "mixed_cv_pipeline_policy_metadata",
        "tile_mix_cube_loop": "pipeline_window_selection_metadata",
        "tile_mix_vector_loop": "pipeline_window_selection_metadata",
        "auto_cv_balance": "pipeline_window_selection_metadata",
        "producer_consumer_distance": "load_compute_store_sync_edge_policy",
        "stage_buffer_policy": "pipeline_buffer_binding_policy",
    },
    "sync_plan": {
        "policy": "barrier_to_event_pair_rewrite_policy",
        "barrier_level": "barrier_candidate_selection_policy",
        "event_reuse": "event_id_allocation_policy",
        "sync_granularity": "sync_candidate_granularity_policy",
        "event_id_policy": "generated_event_id_policy",
        "sync_motion": "sync_motion_guard_metadata",
        "remove_redundant_sync": "sync_cleanup_guard_metadata",
        "sync_style_from_ir": "existing_sync_style_evidence_metadata",
    },
}

# Parameters that have visible operation-level / structural IR changes today.
RESTRICTED_STRUCTURAL = {
    ("tiling_plan", "tile_m"), ("tiling_plan", "tile_n"), ("tiling_plan", "tile_k"),
    ("multibuffer_plan", "double_buffer"), ("multibuffer_plan", "stage_buffer_policy"),
    ("cv_pipeline_plan", "producer_consumer_distance"), ("cv_pipeline_plan", "stage_buffer_policy"),
    ("sync_plan", "policy"), ("sync_plan", "barrier_level"), ("sync_plan", "event_id_policy"),
}


def _knobs(plan: Dict[str, Any], plan_name: str) -> Dict[str, Any]:
    node = plan.get(plan_name) or {}
    return node.get("controllable_knobs") or node.get("selected_knobs") or node.get("knobs") or {}


def flatten_controllable_parameters(selected_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for plan_name in PLAN_KEYS:
        knobs = _knobs(selected_plan, plan_name)
        for key, value in knobs.items():
            if key.endswith("_evidence") or key in {"generic_logical_axes_evidence"}:
                level = "EVIDENCE_ONLY"
            elif key in REWRITE_CONSUMER_MAP.get(plan_name, {}):
                level = "RESTRICTED_STRUCTURAL_REWRITE" if (plan_name, key) in RESTRICTED_STRUCTURAL else "TRACE_METADATA_REWRITE"
            else:
                level = "TRACE_METADATA_REWRITE"
            rows.append({
                "plan": plan_name,
                "parameter": key,
                "value": value,
                "coverage_level": level,
                "rewrite_consumer": REWRITE_CONSUMER_MAP.get(plan_name, {}).get(key, "selected_plan_metadata_block"),
                "rewritten_back_to_ir": level in {"RESTRICTED_STRUCTURAL_REWRITE", "TRACE_METADATA_REWRITE", "PRODUCTION_OPERATION_REWRITE"},
                "production_verified": False,
            })
    return rows


def build_parameter_rewrite_coverage(selected_plan: Dict[str, Any]) -> Dict[str, Any]:
    rows_all = flatten_controllable_parameters(selected_plan)
    # Evidence-only nested structures are useful diagnostics, but they are not selected knobs that must rewrite back.
    rows = [r for r in rows_all if r.get("coverage_level") != "EVIDENCE_ONLY"]
    evidence_rows = [r for r in rows_all if r.get("coverage_level") == "EVIDENCE_ONLY"]
    counts: Dict[str, int] = {}
    by_plan: Dict[str, Dict[str, int]] = {}
    for r in rows:
        counts[r["coverage_level"]] = counts.get(r["coverage_level"], 0) + 1
        by_plan.setdefault(r["plan"], {})[r["coverage_level"]] = by_plan.setdefault(r["plan"], {}).get(r["coverage_level"], 0) + 1
    rewrite_back = [r for r in rows if r["rewritten_back_to_ir"]]
    not_rewrite = [r for r in rows if not r["rewritten_back_to_ir"]]
    return {
        "schema_version": PARAM_COVERAGE_VERSION,
        "version": "V5.3-four-plan-true-rewrite-with-parameter-coverage",
        "parameter_count": len(rows),
        "rewritten_back_to_ir_count": len(rewrite_back),
        "not_rewritten_back_to_ir_count": len(not_rewrite),
        "coverage_counts": counts,
        "coverage_counts_by_plan": by_plan,
        "all_controllable_parameters_rewritten_back_to_ir": len(not_rewrite) == 0,
        "all_controllable_parameters_semantic_operation_rewrite": all(r["coverage_level"] == "PRODUCTION_OPERATION_REWRITE" for r in rows if r["coverage_level"] != "EVIDENCE_ONLY"),
        "important_boundary": "V5.3.1 embeds every controllable parameter back into IR metadata and applies restricted structural portable rewrites for supported parameters; zero parameters are claimed as production MLIR Operation rewrites until HivmOpsEditor/MLIR verifier/DES/msprof pass.",
        "evidence_only_parameters": evidence_rows,
        "parameters": rows,
    }


def _json_value(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def build_parameter_metadata_block(coverage: Dict[str, Any], indent: str = "  ") -> List[str]:
    lines = [
        f"{indent}// HIVM V5.3 Four-Plan selected-parameter rewrite metadata begin",
        f"{indent}//   This block makes every selected controllable knob traceable in the optimized IR.",
        f"{indent}//   RESTRICTED_STRUCTURAL_REWRITE = visible portable IR mutation; TRACE_METADATA_REWRITE = traceability metadata only; PRODUCTION_OPERATION_REWRITE is reserved for verified backend rewrites.",
    ]
    for r in coverage.get("parameters", []):
        if r.get("coverage_level") == "EVIDENCE_ONLY":
            continue
        value = _json_value(r.get("value"))
        lines.append(
            f"{indent}// hivm.param plan={r['plan']} key={r['parameter']} level={r['coverage_level']} consumer={r['rewrite_consumer']} value={value}"
        )
    lines.append(f"{indent}// HIVM V5.3 Four-Plan selected-parameter rewrite metadata end")
    return lines


def insert_parameter_metadata_block(ir_text: str, coverage: Dict[str, Any]) -> str:
    lines = ir_text.splitlines()
    insert_idx = 0
    indent = "  "
    for i, line in enumerate(lines):
        if "func.func" in line or "llvm.func" in line:
            insert_idx = i + 1
            # Use one indentation level inside function.
            indent = "  "
            break
    block = build_parameter_metadata_block(coverage, indent=indent)
    return "\n".join(lines[:insert_idx] + block + lines[insert_idx:]) + ("\n" if ir_text.endswith("\n") else "")


def write_parameter_coverage_outputs(selected_plan_path: str | Path, input_ir_path: str | Path, output_ir_path: str | Path, output_dir: str | Path) -> Dict[str, Any]:
    selected_plan = json.loads(Path(selected_plan_path).read_text(encoding="utf-8"))
    coverage = build_parameter_rewrite_coverage(selected_plan)
    original = Path(input_ir_path).read_text(encoding="utf-8", errors="ignore")
    rewritten = insert_parameter_metadata_block(original, coverage)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_ir_path = Path(output_ir_path)
    output_ir_path.write_text(rewritten, encoding="utf-8")
    (output_dir / "parameter_rewrite_coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "schema_version": "hivm_v53_parameter_rewrite_coverage_summary_v1",
        "version": coverage["version"],
        "parameter_count": coverage["parameter_count"],
        "rewritten_back_to_ir_count": coverage["rewritten_back_to_ir_count"],
        "not_rewritten_back_to_ir_count": coverage["not_rewritten_back_to_ir_count"],
        "coverage_counts": coverage["coverage_counts"],
        "all_controllable_parameters_rewritten_back_to_ir": coverage["all_controllable_parameters_rewritten_back_to_ir"],
        "all_controllable_parameters_semantic_operation_rewrite": coverage["all_controllable_parameters_semantic_operation_rewrite"],
        "optimized_ir": str(output_ir_path),
    }
    (output_dir / "parameter_rewrite_coverage_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"coverage": coverage, "summary": summary, "optimized_ir_path": str(output_ir_path)}
