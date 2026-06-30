# -*- coding: utf-8 -*-
"""Official-document-guided HIVM op inventory and four-Plan rewrite planning.

This module is deliberately lightweight: it does **not** create a new IR and it
never mutates HIVM text.  It turns raw HIVM MLIR plus ``selected_plan.json`` into
an auditable ``rewrite_plan.json`` that a real vTriton/HivmOpsEditor backend can
consume later.

Design principle:
  selected_plan.json       = high-level optimization intent
  HIVM op inventory        = what the input IR actually contains
  rewrite_plan.json        = concrete backend mutation requests + gates
  HivmOpsEditor backend    = the component that performs real IR mutation
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


# Small official-doc-based subset.  We only model ops needed by the four Plan
# rewrite path instead of mirroring the whole HIVM dialect.
OFFICIAL_HIVM_OP_SCHEMA: Dict[str, Dict[str, Any]] = {
    "hivm.hir.load": {
        "syntax_family": "destination_style",
        "official_syntax_summary": "hivm.hir.load ins(%src : type) outs(%dst : type) attr-dict",
        "roles": ["gm_to_local_load", "cv_load_stage", "multibuffer_candidate"],
        "plan_consumers": ["MultiBufferPlan", "CVPipelinePlan"],
        "true_rewrite_boundary": "backend_required_for_operand_replacement_or_op_motion",
    },
    "hivm.hir.store": {
        "syntax_family": "destination_style",
        "official_syntax_summary": "hivm.hir.store ins(%src : type) outs(%dst : type) attr-dict",
        "roles": ["local_to_gm_store", "cv_store_stage", "gm_roundtrip_candidate"],
        "plan_consumers": ["CVPipelinePlan"],
        "true_rewrite_boundary": "backend_required_for_deletion_or_stage_reorder",
    },
    "hivm.hir.nd2nz": {
        "syntax_family": "destination_style",
        "official_syntax_summary": "destination-style layout transform; ins/outs operands are explicit",
        "roles": ["layout_transform", "cv_transform_stage"],
        "plan_consumers": ["CVPipelinePlan", "MultiBufferPlan"],
        "true_rewrite_boundary": "backend_required_for_op_motion",
    },
    "hivm.hir.copy": {
        "syntax_family": "destination_style",
        "roles": ["local_copy", "possible_stage_buffer_copy"],
        "plan_consumers": ["MultiBufferPlan", "CVPipelinePlan"],
        "true_rewrite_boundary": "backend_required_for_operand_replacement",
    },
    "hivm.hir.mmad": {
        "syntax_family": "destination_style",
        "roles": ["cube_compute_stage"],
        "plan_consumers": ["CVPipelinePlan", "TilingPlan"],
        "true_rewrite_boundary": "backend_required_for_tile_shape_or_schedule_change",
    },
    "hivm.hir.mmadL1": {
        "syntax_family": "destination_style",
        "roles": ["cube_compute_stage"],
        "plan_consumers": ["CVPipelinePlan", "TilingPlan"],
        "true_rewrite_boundary": "backend_required_for_tile_shape_or_schedule_change",
    },
    "hivm.hir.fixpipe": {
        "syntax_family": "destination_style",
        "roles": ["fixpipe_stage", "cv_boundary_candidate"],
        "plan_consumers": ["CVPipelinePlan", "SyncPlan"],
        "true_rewrite_boundary": "backend_required_for_stage_sync_insertion",
    },
    "hivm.hir.vreduce": {"syntax_family": "destination_style", "roles": ["vector_compute_stage"], "plan_consumers": ["CVPipelinePlan"]},
    "hivm.hir.vsub": {"syntax_family": "destination_style", "roles": ["vector_compute_stage"], "plan_consumers": ["CVPipelinePlan"]},
    "hivm.hir.vexp": {"syntax_family": "destination_style", "roles": ["vector_compute_stage"], "plan_consumers": ["CVPipelinePlan"]},
    "hivm.hir.vdiv": {"syntax_family": "destination_style", "roles": ["vector_compute_stage"], "plan_consumers": ["CVPipelinePlan"]},
    "hivm.hir.set_flag": {
        "syntax_family": "event_sync",
        "official_syntax_summary": "hivm.hir.set_flag [set_pipe, wait_pipe, event] attr-dict",
        "legacy_sample_syntax_readonly": "hivm.hir.set_flag {pipe=..., event=...}",
        "roles": ["sync_set"],
        "plan_consumers": ["SyncPlan", "CVPipelinePlan"],
        "true_rewrite_boundary": "backend_should_create_or_print_event_ops",
    },
    "hivm.hir.wait_flag": {
        "syntax_family": "event_sync",
        "official_syntax_summary": "hivm.hir.wait_flag [set_pipe, wait_pipe, event] attr-dict",
        "legacy_sample_syntax_readonly": "hivm.hir.wait_flag {pipe=..., event=...}",
        "roles": ["sync_wait"],
        "plan_consumers": ["SyncPlan", "CVPipelinePlan"],
        "true_rewrite_boundary": "backend_should_create_or_print_event_ops",
    },
    "hivm.hir.pipe_barrier": {
        "syntax_family": "pipe_barrier",
        "official_syntax_summary": "hivm.hir.pipe_barrier [pipe] attr-dict",
        "roles": ["coarse_or_pipe_sync_barrier"],
        "plan_consumers": ["SyncPlan"],
        "true_rewrite_boundary": "backend_required_for_barrier_to_event_rewrite",
    },
    # Some local samples use non-official/older barrier spellings.  They are
    # accepted as anchors but should not be generated by Python text code.
    "hivm.hir.barrier": {
        "syntax_family": "legacy_or_project_sample_barrier",
        "roles": ["coarse_sync_barrier"],
        "plan_consumers": ["SyncPlan"],
        "true_rewrite_boundary": "backend_required_for_barrier_to_event_rewrite",
    },
}



# Broader official-document-guided op coverage.  These entries are intentionally
# conservative: they classify known official HIVM ops so inventory reports do not
# treat them as unknown, but they do **not** authorize Python text-level mutation.
# True IR edits still require HivmOpsEditor / MLIR backend proof.
def _register_schema_defaults() -> None:
    def add(op: str, family: str, roles: list[str], consumers: list[str] | None = None, boundary: str | None = None) -> None:
        OFFICIAL_HIVM_OP_SCHEMA.setdefault(op, {
            "syntax_family": family,
            "official_syntax_summary": "see official AscendNPU-IR HIVM Dialect documentation",
            "roles": roles,
            "plan_consumers": consumers or [],
            "true_rewrite_boundary": boundary or "backend_required_for_any_true_mutation",
        })

    # Atomic / GM side-effect ops: important for alias and GM-memory SSA safety.
    for op in ["atomic_cas", "atomic_rmw", "atomic_xchg"]:
        add(f"hivm.hir.{op}", "destination_style_atomic", ["gm_atomic_side_effect", "alias_blocker"], ["SyncPlan"], "never_delete_or_move_without_backend_memory_effect_proof")

    # Cube / matmul family.
    for op in ["batchMmadL1", "matmul", "mix_group_matmul", "mix_matmul", "mmad", "mmadL1"]:
        add(f"hivm.hir.{op}", "destination_style_compute", ["cube_compute_stage", "tiling_compute_anchor"], ["CVPipelinePlan", "TilingPlan"], "backend_required_for_tile_shape_or_schedule_change")

    # Layout/view/cast family.
    add("hivm.hir.bitcast", "view_or_cast", ["view_like_or_type_cast", "no_data_copy_anchor"], ["MultiBufferPlan", "CVPipelinePlan"], "backend_required_for_use_def_preserving_rewrite")
    add("hivm.hir.convert_layout", "view_like_layout", ["layout_view", "no_data_copy_anchor"], ["CVPipelinePlan", "TilingPlan"], "backend_required_for_layout_sensitive_rewrite")
    add("hivm.hir.pointer_cast", "view_or_cast", ["pointer_cast", "alias_sensitive_anchor"], ["MultiBufferPlan"], "backend_required_for_alias_safe_rewrite")
    add("hivm.hir.nz2nd", "destination_style_layout", ["layout_transform", "cv_transform_stage"], ["CVPipelinePlan", "MultiBufferPlan"], "backend_required_for_op_motion")

    # Data movement / scalar / debug / system utility ops.
    add("hivm.hir.load_scalar", "scalar_load", ["scalar_load", "loop_or_index_anchor"], ["TilingPlan"], "backend_required_for_index_sensitive_rewrite")
    for op in ["get_block_idx", "get_block_num", "get_sub_block_idx", "get_sub_block_num", "get_sys_cnt"]:
        add(f"hivm.hir.{op}", "system_query", ["system_query", "do_not_move_across_control_boundary"], ["TilingPlan", "SyncPlan"], "backend_required_for_control_or_mapping_rewrite")
    for op in ["custom", "dcci", "debug", "finish_debug", "init_debug", "set_ffts_base_addr", "set_mask_norm"]:
        add(f"hivm.hir.{op}", "side_effect_or_debug", ["side_effect_or_debug_anchor", "mutation_blocker"], [], "do_not_rewrite_without_backend_specific_support")

    # Sync-block family.
    for op in ["create_sync_block_lock", "sync_block", "sync_block_lock", "sync_block_set", "sync_block_unlock", "sync_block_wait"]:
        add(f"hivm.hir.{op}", "sync_block", ["sync_block", "inter_or_intra_block_sync"], ["SyncPlan", "CVPipelinePlan"], "backend_required_for_sync_rewrite_and_deadlock_check")

    # Vector family.  These are compute-stage anchors for CVPipelinePlan, but
    # not mutation targets in the first guarded rewrite milestone.
    vector_ops = [
        "vabs", "vadd", "vand", "varange", "vbrc", "vcast", "vcmp", "vconcat", "vcos",
        "vcumprod", "vcumsum", "vdeinterleave", "vdiv", "verf", "vexp", "vflip", "vgather",
        "vinterleave", "vln", "vmax", "vmin", "vmod", "vmul", "vmulext", "vmulextended",
        "vnot", "vor", "vpad", "vpow", "vrec", "vreduce", "vrelu", "vrsqrt", "vsel",
        "vshl", "vshr", "vsin", "vsort", "vsqrt", "vsub", "vtanh", "vtranspose", "vxor",
    ]
    for op in vector_ops:
        add(f"hivm.hir.{op}", "destination_style_vector", ["vector_compute_stage"], ["CVPipelinePlan", "TilingPlan"], "backend_required_for_stage_reorder_or_tile_sensitive_rewrite")

_register_schema_defaults()


VECTOR_OPS = {op for op, meta in OFFICIAL_HIVM_OP_SCHEMA.items() if "vector_compute_stage" in meta.get("roles", [])}
CUBE_OPS = {op for op, meta in OFFICIAL_HIVM_OP_SCHEMA.items() if "cube_compute_stage" in meta.get("roles", [])}
LAYOUT_OPS = {op for op, meta in OFFICIAL_HIVM_OP_SCHEMA.items() if "layout_transform" in meta.get("roles", []) or "layout_view" in meta.get("roles", [])}
SYNC_OPS = {op for op, meta in OFFICIAL_HIVM_OP_SCHEMA.items() if any(role.startswith("sync") or "sync" in role for role in meta.get("roles", []))} | {"hivm.hir.set_flag", "hivm.hir.wait_flag", "hivm.hir.pipe_barrier", "hivm.hir.barrier"}
DATA_MOVE_OPS = {"hivm.hir.load", "hivm.hir.store", "hivm.hir.copy"}


@dataclass
class HivmOperationRecord:
    line: int
    op: str
    text: str
    known_by_schema: bool
    syntax_family: str
    roles: List[str]
    inputs: List[str]
    outputs: List[str]
    notes: List[str]


@dataclass
class HivmBufferRecord:
    line: int
    name: str
    space: str
    type_text: str
    text: str


_OP_RE = re.compile(r"\b(hivm\.hir\.[A-Za-z0-9_]+)\b")
_ALLOC_RE = re.compile(r"^\s*(%[\w.$-]+)\s*=\s*memref\.alloc\b.*?:\s*(memref<[^\n]+>)")
_SPACE_RE = re.compile(r"#hivm\.address_space<([^>]+)>")
_INOUT_RE = re.compile(r"\b(ins|outs)\s*\((.*?)\)", re.S)
_VALUE_RE = re.compile(r"%[A-Za-z_][\w.$-]*")
_SCF_FOR_RE = re.compile(r"\bscf\.for\b")


def _extract_values_from_group(group: str) -> List[str]:
    before_type = group.split(":", 1)[0]
    return _VALUE_RE.findall(before_type)


def _extract_ins_outs(line: str) -> Tuple[List[str], List[str]]:
    inputs: List[str] = []
    outputs: List[str] = []
    for kind, group in _INOUT_RE.findall(line):
        values = _extract_values_from_group(group)
        if kind == "ins":
            inputs.extend(values)
        else:
            outputs.extend(values)
    return inputs, outputs


def build_hivm_inventory(ir_text: str, source_name: str = "<memory>") -> Dict[str, Any]:
    """Parse a text-level HIVM inventory using official-doc-guided op roles.

    This is intentionally conservative.  It is not a replacement for the MLIR
    parser.  Unknown ops remain visible and automatically block true rewrite.
    """
    operations: List[HivmOperationRecord] = []
    buffers: List[HivmBufferRecord] = []
    loops: List[Dict[str, Any]] = []
    op_counts: Dict[str, int] = {}
    role_counts: Dict[str, int] = {}

    for line_no, line in enumerate(ir_text.splitlines(), 1):
        alloc_m = _ALLOC_RE.search(line)
        if alloc_m:
            type_text = alloc_m.group(2)
            space_m = _SPACE_RE.search(type_text)
            buffers.append(HivmBufferRecord(
                line=line_no,
                name=alloc_m.group(1),
                space=(space_m.group(1) if space_m else "unknown"),
                type_text=type_text,
                text=line.strip(),
            ))
        if _SCF_FOR_RE.search(line):
            loops.append({"line": line_no, "text": line.strip(), "kind": "scf.for"})
        for op_m in _OP_RE.finditer(line):
            op = op_m.group(1)
            schema = OFFICIAL_HIVM_OP_SCHEMA.get(op, {})
            inputs, outputs = _extract_ins_outs(line)
            roles = list(schema.get("roles", []))
            notes: List[str] = []
            if op in {"hivm.hir.set_flag", "hivm.hir.wait_flag"} and "{" in line and "[" not in line:
                notes.append("sample_or_legacy_event_syntax_seen; read-only anchor, let backend print official form")
            if not schema:
                notes.append("unknown_hivm_op_for_current_rewrite_schema; block true mutation involving this op")
            rec = HivmOperationRecord(
                line=line_no,
                op=op,
                text=line.strip(),
                known_by_schema=bool(schema),
                syntax_family=str(schema.get("syntax_family", "unknown")),
                roles=roles,
                inputs=inputs,
                outputs=outputs,
                notes=notes,
            )
            operations.append(rec)
            op_counts[op] = op_counts.get(op, 0) + 1
            for role in roles:
                role_counts[role] = role_counts.get(role, 0) + 1

    unknown = sorted({op for op in op_counts if op not in OFFICIAL_HIVM_OP_SCHEMA})
    by_category = {
        "data_move": sum(op_counts.get(op, 0) for op in DATA_MOVE_OPS),
        "layout": sum(op_counts.get(op, 0) for op in LAYOUT_OPS),
        "cube_compute": sum(op_counts.get(op, 0) for op in CUBE_OPS),
        "vector_compute": sum(op_counts.get(op, 0) for op in VECTOR_OPS),
        "sync": sum(op_counts.get(op, 0) for op in SYNC_OPS),
        "loops": len(loops),
        "buffers": len(buffers),
    }
    spaces: Dict[str, int] = {}
    for b in buffers:
        spaces[b.space] = spaces.get(b.space, 0) + 1

    return {
        "schema_version": "hivm_official_inventory_v1",
        "source": source_name,
        "doc_alignment": {
            "basis": "AscendNPU-IR HIVM Dialect official documentation subset",
            "note": "This inventory is text-level and conservative; the target backend must still parse/verify with the real MLIR/HIVM context.",
        },
        "summary": {
            "num_hivm_ops": len(operations),
            "num_buffers": len(buffers),
            "num_loops": len(loops),
            "op_counts": op_counts,
            "role_counts": role_counts,
            "by_category": by_category,
            "buffer_spaces": spaces,
            "unknown_hivm_ops": unknown,
        },
        "operations": [asdict(o) for o in operations],
        "buffers": [asdict(b) for b in buffers],
        "loops": loops,
    }


def _plan_knobs(selected_plan: Dict[str, Any], plan_name: str) -> Dict[str, Any]:
    return dict(selected_plan.get(plan_name, {}).get("controllable_knobs", {}) or {})


def _ops_with_role(inventory: Dict[str, Any], role: str) -> List[Dict[str, Any]]:
    return [op for op in inventory.get("operations", []) if role in op.get("roles", [])]


def _ops_named(inventory: Dict[str, Any], names: Iterable[str]) -> List[Dict[str, Any]]:
    names = set(names)
    return [op for op in inventory.get("operations", []) if op.get("op") in names]


def _local_buffers(inventory: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [b for b in inventory.get("buffers", []) if b.get("space") in {"ub", "cbuf", "l1", "l0a", "l0b", "l0c", "cc"}]


def build_four_plan_rewrite_plan(selected_plan: Dict[str, Any], inventory: Dict[str, Any]) -> Dict[str, Any]:
    """Translate selected four-Plan strategy into backend-oriented requests."""
    tiling_knobs = _plan_knobs(selected_plan, "tiling_plan")
    mb_knobs = _plan_knobs(selected_plan, "multibuffer_plan")
    cv_knobs = _plan_knobs(selected_plan, "cv_pipeline_plan")
    sync_knobs = _plan_knobs(selected_plan, "sync_plan")
    unknown_ops = inventory.get("summary", {}).get("unknown_hivm_ops", [])

    buffers = _local_buffers(inventory)
    loads = _ops_named(inventory, ["hivm.hir.load"])
    stores = _ops_named(inventory, ["hivm.hir.store"])
    layout = _ops_named(inventory, ["hivm.hir.nd2nz"])
    cube = _ops_named(inventory, CUBE_OPS)
    vector = _ops_named(inventory, VECTOR_OPS)
    sync = _ops_named(inventory, SYNC_OPS)
    loops = inventory.get("loops", [])

    request_status = "backend_required" if not unknown_ops else "blocked_or_dry_run_only_due_to_unknown_ops"

    tiling_req = {
        "plan": "TilingPlan",
        "selected_knobs": {
            "tile_m": tiling_knobs.get("tile_m"),
            "tile_n": tiling_knobs.get("tile_n"),
            "tile_k": tiling_knobs.get("tile_k"),
            "loop_order": tiling_knobs.get("loop_order"),
            "tail_strategy": tiling_knobs.get("tail_strategy"),
            "reduce_tile_policy": tiling_knobs.get("reduce_tile_policy"),
        },
        "candidate_anchors": {"loops": loops[:8], "cube_compute_ops": cube[:8]},
        "rewrite_actions": [
            "emit_tiling_hint_to_backend",
            "analyze_loop_split_legality",
            "defer_true_loop_index_slice_tailmask_rewrite_to_HivmOpsEditor_or_MLIR_pass",
        ],
        "minimum_gates": [
            "loop_bounds_identified",
            "load_store_slice_mapping_identified",
            "tail_mask_policy_defined",
            "capacity_after_tiling_passes",
            "backend_roundtrip_and_verify_pass",
        ],
        "status": "report_and_hint_only_v1" if loops else "no_loop_anchor_found",
    }

    target_buffer_names = sorted({b["name"] for b in buffers if any(tag in b["name"].lower() for tag in ["q", "k", "v", "ub", "l1"] )})[:16]
    mb_req = {
        "plan": "MultiBufferPlan",
        "selected_knobs": {
            "double_buffer": mb_knobs.get("double_buffer"),
            "template": mb_knobs.get("template"),
            "input_buffer_multiplier": mb_knobs.get("input_buffer_multiplier"),
            "stage_buffer_multiplier": mb_knobs.get("stage_buffer_multiplier"),
            "buffer_multipliers": mb_knobs.get("buffer_multipliers"),
            "stage_buffer_policy": mb_knobs.get("stage_buffer_policy"),
        },
        "candidate_anchors": {
            "local_buffers": [b for b in buffers if b["name"] in target_buffer_names],
            "load_ops": loads[:8],
            "layout_ops": layout[:8],
        },
        "rewrite_actions": [
            "select_cloneable_local_buffers",
            "create_backend_buffer_clone_requests",
            "replace_load_layout_compute_operands_by_iteration_or_stage_policy",
            "defer_actual_buffer_creation_and_use_replacement_to_HivmOpsEditor",
        ],
        "minimum_gates": [
            "target_buffer_has_known_address_space",
            "all_uses_are_known_or_backend_resolvable",
            "no_unknown_side_effect_op_between_producer_consumer",
            "capacity_recheck_passes_after_extra_buffer_slots",
            "buffer_liveness_no_overwrite",
            "backend_roundtrip_and_verify_pass",
        ],
        "status": request_status if mb_knobs.get("double_buffer") else "selected_plan_does_not_request_double_buffer",
    }

    cv_req = {
        "plan": "CVPipelinePlan",
        "selected_knobs": {
            "stage_num": cv_knobs.get("stage_num"),
            "template": cv_knobs.get("template"),
            "producer_consumer_distance": cv_knobs.get("producer_consumer_distance"),
            "enable_mixed_cv": cv_knobs.get("enable_mixed_cv"),
        },
        "candidate_anchors": {
            "load_ops": loads[:8],
            "layout_ops": layout[:8],
            "cube_ops": cube[:8],
            "vector_ops": vector[:8],
            "store_ops": stores[:8],
        },
        "rewrite_actions": [
            "classify_ops_into_load_transform_cube_vector_store_stages",
            "check_stage_dependency_is_linear",
            "require_MultiBufferPlan_pingpong_for_overlap",
            "insert_or_reuse_SyncPlan_directional_events_at_stage_boundaries",
            "defer_true_stage_reorder_to_HivmOpsEditor",
        ],
        "minimum_gates": [
            "stage_sequence_detected",
            "no_cross_tile_reduction_or_unknown_side_effect",
            "pingpong_or_stage_buffer_available",
            "event_liveness_passes",
            "prologue_steady_state_epilogue_defined",
            "backend_roundtrip_verify_DES_trace_pass",
        ],
        "status": request_status if int(cv_knobs.get("stage_num") or 1) > 1 else "selected_plan_single_stage",
    }

    sync_req = {
        "plan": "SyncPlan",
        "selected_knobs": {
            "policy": sync_knobs.get("policy"),
            "template": sync_knobs.get("template"),
            "barrier_level": sync_knobs.get("barrier_level"),
            "event_reuse": sync_knobs.get("event_reuse"),
            "event_id_policy": sync_knobs.get("event_id_policy"),
            "sync_motion": sync_knobs.get("sync_motion"),
            "remove_redundant_sync": sync_knobs.get("remove_redundant_sync"),
        },
        "candidate_anchors": {"sync_ops": sync[:16], "producer_ops": loads[:8] + cube[:8], "consumer_ops": cube[:8] + vector[:8] + stores[:8]},
        "rewrite_actions": [
            "detect_pipe_barrier_or_legacy_barrier_candidates",
            "derive_producer_consumer_pipe_pairs",
            "allocate_fresh_or_proven_reusable_event_ids",
            "ask_backend_to_create_set_flag_wait_flag_using_official_syntax",
            "defer_event_printing_to_HivmOpsEditor_because_sample_event_syntax_may_be_legacy",
        ],
        "minimum_gates": [
            "producer_consumer_pair_proven",
            "event_live_range_non_overlapping_or_fresh_event",
            "no_cross_iteration_dependency_removed",
            "deadlock_freedom_check_required",
            "backend_roundtrip_and_verify_pass",
        ],
        "status": request_status if sync_knobs.get("policy") in {"graph_sync_solver", "directional_event"} else "selected_plan_does_not_request_directional_sync",
    }

    return {
        "schema_version": "hivm_four_plan_rewrite_plan_v1",
        "producer": "strategy_search.hivm_official_rewrite_plan",
        "basis": {
            "official_docs": "AscendNPU-IR HIVM Dialect official documentation subset for load/store/set_flag/wait_flag/pipe_barrier and related ops",
            "important_rule": "Python emits rewrite intent only. True HIVM IR mutation must be done by HivmOpsEditor/MLIR backend and verified.",
        },
        "input_summary": inventory.get("summary", {}),
        "unknown_op_policy": "unknown HIVM ops block true mutation touching their region; dry-run/report is still allowed",
        "requests": [sync_req, mb_req, cv_req, tiling_req],
        "backend_contract": {
            "input_files": ["selected_plan.json", "hivm_ir_inventory.json", "rewrite_plan.json"],
            "required_backend_steps": ["inventory", "roundtrip", "verify-only", "dry-run", "mutate", "post-mutate verify", "optional DES/trace"],
            "do_not_claim": [
                "Do not claim real double-buffer if only hints were emitted.",
                "Do not claim CV overlap unless trace/DES shows expected stage overlap.",
                "Do not claim tiling rewrite unless loop/index/slice/tail-mask changed and verifier passed.",
                "Do not claim speedup without msprof or accepted simulator evidence.",
            ],
        },
    }


def build_reports(ir_path: Path, selected_plan_path: Path, output_dir: Path) -> Dict[str, Path]:
    ir_text = ir_path.read_text(encoding="utf-8")
    selected_plan = json.loads(selected_plan_path.read_text(encoding="utf-8"))
    inventory = build_hivm_inventory(ir_text, source_name=str(ir_path))
    rewrite_plan = build_four_plan_rewrite_plan(selected_plan, inventory)
    output_dir.mkdir(parents=True, exist_ok=True)
    inv_path = output_dir / "hivm_ir_inventory.official.json"
    plan_path = output_dir / "four_plan_rewrite_plan.json"
    schema_path = output_dir / "hivm_official_op_schema_subset.json"
    inv_path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    plan_path.write_text(json.dumps(rewrite_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    schema_path.write_text(json.dumps(OFFICIAL_HIVM_OP_SCHEMA, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"inventory": inv_path, "rewrite_plan": plan_path, "schema": schema_path}
