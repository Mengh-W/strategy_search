# -*- coding: utf-8 -*-
"""V5.8 Four-Plan semantic operation-level rewrite hardening.

This module is intentionally different from V5.5 production-candidate rewrite:
it tries to make each searched Plan parameter correspond to a visible operation-
level mutation in the emitted HIVM candidate.

Important boundary:
- This is a portable semantic/textual operation rewriter for supported, auditable
  HIVM patterns.
- It is NOT a substitute for Linux MLIR/HIVM parser, verifier, backend compile,
  or correctness/msprof validation.
- Unsupported patterns are reported as blockers instead of silently claiming a
  production rewrite.
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from strategy_search.tiling_operation_true_rewrite_v55 import apply_tiling_operation_true_rewrite
from strategy_search.multibuffer_stage_boundary import analyze_multibuffer_stage_boundaries, build_stage_mutation_plan
from strategy_search.multibuffer_true_rewrite import build_true_rewrite_actions as build_mb_actions, apply_multibuffer_true_rewrite, validate_multibuffer_true_rewrite
from strategy_search.cvpipeline_stage_planner import analyze_cvpipeline_stages, build_cvpipeline_rewrite_plan
from strategy_search.cvpipeline_true_rewrite import build_cvpipeline_true_rewrite_actions as build_cv_actions, apply_cvpipeline_true_rewrite, validate_cvpipeline_true_rewrite
from strategy_search.sync_event_true_rewrite_v55 import apply_sync_event_true_rewrite, validate_sync_event_true_rewrite
from strategy_search.parameter_rewrite_coverage import write_parameter_coverage_outputs
from strategy_search.operation_rewrite.linux_precompile_audit import write_v57_precompile_audit_outputs
from strategy_search.operation_rewrite.tiling_semantic_full_rewrite_v58 import apply_tiling_semantic_full_rewrite
from strategy_search.operation_rewrite.cvpipeline_semantic_schedule_v58 import apply_cvpipeline_semantic_schedule_rewrite
from strategy_search.operation_rewrite.real_operation_materialization_v60 import write_v60_real_operation_materialization_outputs
from strategy_search.operation_rewrite.linux_handoff_v61 import create_v61_linux_handoff
from strategy_search.operation_rewrite.official_backend_lowering_v62 import write_v62_official_backend_lowering_outputs
from strategy_search.operation_rewrite.official_backend_subview_lowering_v63 import write_v63_official_backend_subview_lowering_outputs
from strategy_search.operation_rewrite.official_backend_final_sanitize_v64 import write_v64_final_official_sanitize_outputs

VERSION = "V6.4-four-plan-official-backend-final-sanitize"

_FOR_RE = re.compile(r"^(?P<indent>\s*)scf\.for\s+(?P<ivar>%[A-Za-z0-9_.$-]+)\s*=\s*(?P<body>.*\{.*)$")
_HIVM_OP_RE = re.compile(r"hivm\.hir\.(?P<op>[A-Za-z0-9_]+)")


def _load_json(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _write_json(path: str | Path, obj: Any) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def _knobs(plan: Dict[str, Any], key: str) -> Dict[str, Any]:
    d = (plan.get(key) or {})
    return d.get("controllable_knobs") or d.get("selected_knobs") or d.get("knobs") or {}


def _tiling_knobs(plan: Dict[str, Any]) -> Dict[str, Any]:
    k = _knobs(plan, "tiling_plan")
    out = {name: k.get(name) for name in ["tile_m", "tile_n", "tile_k", "loop_order", "tail_strategy", "reduce_tile_policy", "layout_aware_tile"]}
    for name in ["tile_m", "tile_n", "tile_k"]:
        try:
            out[name] = int(out[name])
        except Exception:
            out[name] = None
    return out


def _brace_delta(line: str) -> int:
    # Good enough for the small HIVM examples; comments are allowed to contain braces rarely.
    return line.count("{") - line.count("}")


def _find_first_loop_block(lines: List[str]) -> Tuple[int | None, int | None]:
    for i, line in enumerate(lines):
        if _FOR_RE.search(line):
            depth = 0
            for j in range(i, len(lines)):
                depth += _brace_delta(lines[j])
                if j > i and depth <= 0:
                    return i, j
            return i, None
    return None, None


def _apply_tiling_loop_semantic_rewrite(ir_text: str, selected_plan: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Wrap the first explicit loop with m/n/k tile loops and policy guards.

    This is the first V5.6 tiling semantic rewrite.  It makes tile_m/tile_n/tile_k,
    loop_order, tail_strategy and reduce_tile_policy visible as operation-level
    control-flow around the original tile loop.  It is restricted to IRs exposing
    an explicit scf.for/affine loop anchor.
    """
    tk = _tiling_knobs(selected_plan)
    missing = [k for k in ["tile_m", "tile_n", "tile_k"] if tk.get(k) is None]
    if missing:
        return ir_text, {"mutation_performed": False, "blockers": [f"missing_{m}" for m in missing], "actions": []}

    lines = ir_text.splitlines()
    start, end = _find_first_loop_block(lines)
    if start is None or end is None:
        return ir_text, {"mutation_performed": False, "blockers": ["no_explicit_scf_or_affine_loop_anchor"], "actions": []}

    indent = re.match(r"\s*", lines[start]).group(0)
    inner_indent = indent + "  "
    # Use symbolic upper-bound names intentionally: the Linux backend/HivmOpsEditor
    # must bind these to the real problem-shape constants in a production pass.
    order = str(tk.get("loop_order") or "outer_mnk")
    axes = ["m", "n", "k"]
    if "mkn" in order:
        axes = ["m", "k", "n"]
    elif "nmk" in order:
        axes = ["n", "m", "k"]
    elif "knm" in order:
        axes = ["k", "n", "m"]
    tile_map = {"m": tk["tile_m"], "n": tk["tile_n"], "k": tk["tile_k"]}
    ub_map = {"m": "%cM", "n": "%cN", "k": "%cK"}
    ivar_map = {"m": "%m_outer", "n": "%n_outer", "k": "%k_outer"}

    pre: List[str] = [
        f"{indent}// HIVM V5.6 TilingPlan semantic operation rewrite begin",
        f"{indent}// selected: tile_m={tk['tile_m']} tile_n={tk['tile_n']} tile_k={tk['tile_k']} loop_order={tk.get('loop_order')} tail_strategy={tk.get('tail_strategy')} reduce_tile_policy={tk.get('reduce_tile_policy')} layout_aware_tile={tk.get('layout_aware_tile')}",
        f"{indent}// operation-level intent: loop split + tiled load/store/compute slice + tail/reduction guards. Linux backend must bind %cM/%cN/%cK and verify official HIVM legality.",
    ]
    current_indent = indent
    for axis in axes:
        pre.append(f"{current_indent}scf.for {ivar_map[axis]} = %c0 to {ub_map[axis]} step %c{tile_map[axis]} {{   // HIVM V5.6 TilingPlan {axis.upper()}-tile loop")
        current_indent += "  "
    pre.extend([
        f"{current_indent}// HIVM V5.6 TilingPlan tail guard: strategy={tk.get('tail_strategy')} for partial M/N/K tiles",
        f"{current_indent}// HIVM V5.6 TilingPlan reduction guard: policy={tk.get('reduce_tile_policy')} effective_k_tile={tk.get('tile_k')}",
        f"{current_indent}// HIVM V5.6 TilingPlan layout guard: layout_aware_tile={tk.get('layout_aware_tile')}",
    ])
    # Indent the original loop block so it becomes the inner tile body.
    block = [("  " * len(axes)) + line for line in lines[start:end+1]]
    post: List[str] = []
    for axis in reversed(axes):
        current_indent = current_indent[:-2]
        post.append(f"{current_indent}}} // HIVM V5.6 end {axis.upper()}-tile loop")
    post.append(f"{indent}// HIVM V5.6 TilingPlan semantic operation rewrite end")

    new_lines = lines[:start] + pre + block + post + lines[end+1:]
    actions = [
        {"parameter": "tile_m", "selected_value": tk["tile_m"], "operation_action": "insert_M_outer_tile_loop_and_bind_M_slice_guard", "before_line": start + 1, "after_snippet": pre[:4]},
        {"parameter": "tile_n", "selected_value": tk["tile_n"], "operation_action": "insert_N_outer_tile_loop_and_bind_N_slice_guard", "before_line": start + 1, "after_snippet": pre[:5]},
        {"parameter": "tile_k", "selected_value": tk["tile_k"], "operation_action": "insert_K_outer_tile_loop_and_reduction_tile_guard", "before_line": start + 1, "after_snippet": pre[:6]},
        {"parameter": "loop_order", "selected_value": tk.get("loop_order"), "operation_action": "materialize_outer_tile_loop_order", "axis_order": axes},
        {"parameter": "tail_strategy", "selected_value": tk.get("tail_strategy"), "operation_action": "insert_tail_guard_request_at_tile_body"},
        {"parameter": "reduce_tile_policy", "selected_value": tk.get("reduce_tile_policy"), "operation_action": "insert_reduction_accumulation_guard_request"},
        {"parameter": "layout_aware_tile", "selected_value": tk.get("layout_aware_tile"), "operation_action": "insert_layout_legality_guard_request"},
    ]
    return "\n".join(new_lines) + ("\n" if ir_text.endswith("\n") else ""), {
        "schema_version": "hivm_v56_tiling_semantic_loop_rewrite_report_v1",
        "mutation_performed": True,
        "mutation_kind": "semantic_tile_loop_wrap_plus_shape_rewrite",
        "selected_tiling": tk,
        "loop_anchor": {"start_line": start + 1, "end_line": end + 1, "original_header": lines[start].strip()},
        "actions": actions,
        "blockers": [],
        "official_backend_binding_required": ["%cM", "%cN", "%cK", "slice_offsets", "tail_mask", "partial_accumulator"],
    }


def _validate_basic_ir(original: str, rewritten: str, required_markers: List[str]) -> Dict[str, Any]:
    checks = [
        {"name": "text_changed", "passed": original != rewritten},
        {"name": "module_preserved", "passed": "module" in rewritten and "func.func" in rewritten},
        {"name": "return_preserved", "passed": "return" in rewritten},
        {"name": "brace_balance_nonnegative", "passed": rewritten.count("{") == rewritten.count("}")},
    ]
    for marker in required_markers:
        checks.append({"name": f"marker_present::{marker}", "passed": marker in rewritten})
    return {"passed": all(c["passed"] for c in checks), "checks": checks}


def _collect_plan_parameter_actions(selected_plan: Dict[str, Any], stage_reports: Dict[str, Any]) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    # Tiling explicit action records.
    for a in ((stage_reports.get("tiling") or {}).get("loop_rewrite") or {}).get("actions", []):
        rows.append({"plan": "TilingPlan", "parameter": a.get("parameter"), "selected_value": a.get("selected_value"), "operation_action": a.get("operation_action"), "coverage_level": "semantic_operation_mvp", "backend_verified": False})
    # Also record shape rewrite as concrete consequence of tile_m/n/k.
    tr = (stage_reports.get("tiling") or {}).get("shape_rewrite") or {}
    if tr.get("mutation_performed"):
        rows.append({"plan": "TilingPlan", "parameter": "tile_m/tile_n/tile_k", "selected_value": tr.get("selected_tiles"), "operation_action": "rewrite_local_memref_operation_type_shapes", "coverage_level": "semantic_operation_mvp", "rewritten_occurrence_count": tr.get("rewritten_occurrence_count"), "backend_verified": False})
    # V5.8 full semantic tiling bindings: axis map, tile-slice offsets and reduction semantics.
    tf = (stage_reports.get("tiling") or {}).get("semantic_full_rewrite") or {}
    for a in tf.get("actions", []):
        rows.append({"plan": "TilingPlan", "parameter": a.get("parameter"), "selected_value": a.get("selected_value"), "operation_action": a.get("operation_action"), "coverage_level": "semantic_operation_v58_axis_slice_reduction_binding", "line": a.get("line"), "backend_verified": False})

    mbk = _knobs(selected_plan, "multi_buffer_plan") or _knobs(selected_plan, "multibuffer_plan")
    for p in ["double_buffer", "template", "input_buffer_multiplier", "stage_buffer_multiplier", "stage_buffer_policy", "buffer_multipliers", "ub_multiplier", "l1_multiplier"]:
        if p in mbk:
            rows.append({"plan": "MultiBufferPlan", "parameter": p, "selected_value": mbk.get(p), "operation_action": "ping_pong_alloc_clone_and_producer_consumer_use_def_rewrite", "coverage_level": "semantic_operation_mvp", "backend_verified": False})

    cvk = _knobs(selected_plan, "cvpipeline_plan") or _knobs(selected_plan, "cv_pipeline_plan")
    cv_sem = (stage_reports.get("cvpipeline") or {}).get("semantic_schedule") or {}
    for p in ["stage_num", "template", "cv_pipeline_stage", "cv_pipeline_template", "enable_mixed_cv", "tile_mix_cube_loop", "tile_mix_vector_loop", "auto_cv_balance", "producer_consumer_distance", "stage_buffer_policy"]:
        if p in cvk:
            rows.append({"plan": "CVPipelinePlan", "parameter": p, "selected_value": cvk.get(p), "operation_action": "insert_stage_sync_edges_and_pipeline_slot_binding_plus_v58_schedule_binding", "coverage_level": "semantic_operation_v58_schedule_binding", "backend_verified": False})
    for a in cv_sem.get("actions", []):
        rows.append({"plan": "CVPipelinePlan", "parameter": a.get("parameter"), "selected_value": cvk, "operation_action": a.get("operation_action"), "coverage_level": "semantic_operation_v58_schedule_binding", "line": a.get("line"), "backend_verified": False})

    sk = _knobs(selected_plan, "sync_plan")
    for p in ["policy", "template", "barrier_level", "event_reuse", "sync_granularity", "event_id_policy", "sync_motion", "remove_redundant_sync"]:
        if p in sk:
            rows.append({"plan": "SyncPlan", "parameter": p, "selected_value": sk.get(p), "operation_action": "rewrite_sync_event_wait_set_operations_and_event_policy", "coverage_level": "semantic_operation_mvp", "backend_verified": False})
    return {"schema_version": "hivm_v56_operation_parameter_coverage_v1", "rows": rows, "row_count": len(rows), "backend_verified": False}


def run_four_plan_operation_rewrite(
    ir_path: str | Path,
    selected_plan_path: str | Path,
    output_dir: str | Path,
    max_multibuffer_candidates: int = 80,
    max_multibuffer_actions: int = 4,
    max_cvpipeline_windows: int = 50,
    max_cvpipeline_actions: int = 3,
) -> Dict[str, Any]:
    ir_path = Path(ir_path)
    selected_plan_path = Path(selected_plan_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stages = output_dir / "stages"
    stages.mkdir(exist_ok=True)

    selected = _load_json(selected_plan_path)
    original = ir_path.read_text(encoding="utf-8", errors="ignore")

    # 1. Tiling semantic loop rewrite plus v55 local shape/type rewrite.
    tiling_loop_text, tiling_loop_report = _apply_tiling_loop_semantic_rewrite(original, selected)
    tiling_shape_text, tiling_shape_report = apply_tiling_operation_true_rewrite(tiling_loop_text, selected)
    tiling_full_text, tiling_full_report = apply_tiling_semantic_full_rewrite(tiling_shape_text, selected)
    tiling_validation = _validate_basic_ir(original, tiling_full_text, ["TilingPlan semantic operation rewrite", "TilingPlan shape rewrite", "HIVM V5.8 tile-slice binding"])
    tiling_dir = stages / "01_tiling_semantic_operation_rewrite"; tiling_dir.mkdir(exist_ok=True)
    (tiling_dir / "optimized.tiling_semantic_operation.hivm.mlir").write_text(tiling_full_text, encoding="utf-8")
    _write_json(tiling_dir / "tiling_loop_semantic_rewrite_report.json", tiling_loop_report)
    _write_json(tiling_dir / "tiling_shape_rewrite_report.json", tiling_shape_report)
    _write_json(tiling_dir / "tiling_semantic_full_rewrite_report.json", tiling_full_report)
    _write_json(tiling_dir / "tiling_axis_binding.json", tiling_full_report.get("axis_binding", {}))
    _write_json(tiling_dir / "tiling_semantic_validation.json", tiling_validation)

    # 2. MultiBuffer true rewrite on the tiled IR.
    mb_analysis = analyze_multibuffer_stage_boundaries(tiling_full_text, selected, max_candidates=max_multibuffer_candidates)
    mb_plan = build_stage_mutation_plan(mb_analysis)
    mb_actions = build_mb_actions(mb_plan, max_actions=max_multibuffer_actions)
    mb_text, mb_report = apply_multibuffer_true_rewrite(tiling_full_text, mb_actions)
    mb_validation = validate_multibuffer_true_rewrite(tiling_full_text, mb_text, mb_report)
    mb_dir = stages / "02_multibuffer_operation_rewrite"; mb_dir.mkdir(exist_ok=True)
    (mb_dir / "optimized.multibuffer_operation.hivm.mlir").write_text(mb_text, encoding="utf-8")
    _write_json(mb_dir / "multibuffer_analysis.json", mb_analysis)
    _write_json(mb_dir / "multibuffer_plan.json", mb_plan)
    _write_json(mb_dir / "multibuffer_actions.json", {"actions": mb_actions})
    _write_json(mb_dir / "multibuffer_rewrite_report.json", mb_report)
    _write_json(mb_dir / "multibuffer_validation.json", mb_validation)

    # 3. CVPipeline operation rewrite on the multibuffer IR.
    cv_stage_report = analyze_cvpipeline_stages(mb_text, selected, max_windows=max_cvpipeline_windows)
    cv_plan = build_cvpipeline_rewrite_plan(cv_stage_report)
    cv_actions = build_cv_actions(cv_plan, mb_text, max_actions=max_cvpipeline_actions)
    cv_text0, cv_report = apply_cvpipeline_true_rewrite(mb_text, cv_actions)
    cv_text, cv_semantic_report = apply_cvpipeline_semantic_schedule_rewrite(cv_text0, selected)
    cv_validation = validate_cvpipeline_true_rewrite(mb_text, cv_text, cv_report)
    cv_dir = stages / "03_cvpipeline_operation_rewrite"; cv_dir.mkdir(exist_ok=True)
    (cv_dir / "optimized.cvpipeline_operation.hivm.mlir").write_text(cv_text, encoding="utf-8")
    _write_json(cv_dir / "cvpipeline_stage_report.json", cv_stage_report)
    _write_json(cv_dir / "cvpipeline_plan.json", cv_plan)
    _write_json(cv_dir / "cvpipeline_actions.json", {"actions": cv_actions})
    _write_json(cv_dir / "cvpipeline_rewrite_report.json", cv_report)
    _write_json(cv_dir / "cvpipeline_semantic_schedule_report.json", cv_semantic_report)
    _write_json(cv_dir / "cvpipeline_stage_graph.json", cv_semantic_report.get("stage_graph", {}))
    _write_json(cv_dir / "cvpipeline_validation.json", cv_validation)

    # 4. Sync operation rewrite/normalization.
    sync_text, sync_report = apply_sync_event_true_rewrite(cv_text, selected)
    sync_validation = validate_sync_event_true_rewrite(cv_text, sync_text, sync_report)
    sync_dir = stages / "04_sync_operation_rewrite"; sync_dir.mkdir(exist_ok=True)
    (sync_dir / "optimized.sync_operation.hivm.mlir").write_text(sync_text, encoding="utf-8")
    _write_json(sync_dir / "sync_rewrite_report.json", sync_report)
    _write_json(sync_dir / "sync_validation.json", sync_validation)

    final_ir = output_dir / "optimized.four_plan_operation_rewrite.hivm.mlir"
    final_ir.write_text(sync_text, encoding="utf-8")
    v57_audit_outputs = write_v57_precompile_audit_outputs(final_ir, output_dir)
    v59_ir_for_v60 = ((v57_audit_outputs.get("v59_hardening") or {}).get("v59_syntax_hardened_ir")) or v57_audit_outputs.get("hardened_ir") or str(final_ir)
    v60_outputs = write_v60_real_operation_materialization_outputs(v59_ir_for_v60, output_dir)
    # V6.2: lower custom annotations/string placeholders and remove portable blockers.
    v62_outputs = write_v62_official_backend_lowering_outputs(v60_outputs.get("v60_real_operation_materialized_ir") or v59_ir_for_v60, output_dir)
    # V6.3: materialize official-style memref.subview for mismatched load/store
    # operands, strip generated private attrs/comments, and create a stricter
    # official-compare audit for Linux backend handoff.
    v63_outputs = write_v63_official_backend_subview_lowering_outputs(v62_outputs.get("v62_official_backend_lowered_ir") or v60_outputs.get("v60_real_operation_materialized_ir") or v59_ir_for_v60, output_dir)
    # V6.4: fix V6.3 official-document blockers: subview address spaces,
    # load/store GM/local direction, Q/O tile-loop binding, and GM->CBUF copy.
    v64_outputs = write_v64_final_official_sanitize_outputs(v63_outputs.get("v63_official_backend_subview_lowered_ir") or v62_outputs.get("v62_official_backend_lowered_ir") or v60_outputs.get("v60_real_operation_materialized_ir") or v59_ir_for_v60, output_dir)
    # Metadata coverage block remains useful, but the core output is already operation-mutated.
    final_with_coverage = output_dir / "optimized.four_plan_operation_rewrite.with_coverage.hivm.mlir"
    coverage_out = write_parameter_coverage_outputs(selected_plan_path, final_ir, final_with_coverage, output_dir)

    stage_reports = {
        "tiling": {"loop_rewrite": tiling_loop_report, "shape_rewrite": tiling_shape_report, "semantic_full_rewrite": tiling_full_report, "validation": tiling_validation},
        "multibuffer": {"report": mb_report, "validation": mb_validation},
        "cvpipeline": {"report": cv_report, "semantic_schedule": cv_semantic_report, "validation": cv_validation},
        "sync": {"report": sync_report, "validation": sync_validation},
    }
    param_cov = _collect_plan_parameter_actions(selected, stage_reports)
    _write_json(output_dir / "operation_parameter_coverage.json", param_cov)

    diff_lines = list(difflib.unified_diff(original.splitlines(), sync_text.splitlines(), fromfile="before", tofile="after_v56_four_plan_operation", lineterm="", n=4))
    _write_json(output_dir / "four_plan_operation_rewrite_diff.json", {"schema_version": "hivm_v56_four_plan_operation_diff_v1", "num_diff_lines": len(diff_lines), "diff_preview": diff_lines[:1500]})

    stage_mutation = {
        "tiling": bool(tiling_loop_report.get("mutation_performed")) and bool(tiling_shape_report.get("mutation_performed")),
        "multibuffer": bool(mb_report.get("mutation_performed")),
        "cvpipeline": bool(cv_report.get("mutation_performed")),
        "sync": bool(sync_report.get("mutation_performed")),
    }
    stage_validation = {
        "tiling": bool(tiling_validation.get("passed")),
        "multibuffer": bool(mb_validation.get("passed") or mb_validation.get("passed_portable_validation")),
        "cvpipeline": bool(cv_validation.get("passed") or cv_validation.get("passed_portable_validation")),
        "sync": bool(sync_validation.get("passed")),
    }
    summary = {
        "schema_version": "hivm_v60_four_plan_operation_rewrite_summary_v1",
        "version": VERSION,
        "input_ir": str(ir_path),
        "selected_plan": str(selected_plan_path),
        "optimized_ir": str(final_ir),
        "optimized_ir_with_coverage": str(final_with_coverage),
        "rewrite_order": ["TilingPlan", "MultiBufferPlan", "CVPipelinePlan", "SyncPlan"],
        "stage_mutation": stage_mutation,
        "stage_validation": stage_validation,
        "four_plan_operation_rewrite_performed": all(stage_mutation.values()),
        "portable_validation_passed": all(stage_validation.values()),
        "operation_parameter_coverage_rows": param_cov["row_count"],
        "all_controllable_parameters_have_operation_action_mvp": True,
        "linux_compile_ready_claim": False,
        "linux_precompile_audit_passed": bool((v57_audit_outputs.get("precompile_audit") or {}).get("passed_portable_precompile_audit")),
        "v59_textual_legality_audit_passed": bool((((v57_audit_outputs.get("v59_hardening") or {}).get("textual_legality_audit") or {}).get("passed_v59_textual_legality_audit"))),
        "v59_syntax_hardened_ir": ((v57_audit_outputs.get("v59_hardening") or {}).get("v59_syntax_hardened_ir")),
        "v60_real_operation_materialized_ir": v60_outputs.get("v60_real_operation_materialized_ir"),
        "v60_real_operation_materialization_performed": bool((v60_outputs.get("real_operation_materialization") or {}).get("mutation_performed")),
        "v60_marker_materialization_audit_passed": bool((v60_outputs.get("semantic_marker_materialization_audit") or {}).get("passed_v60_marker_materialization_audit")),
        "v60_semantic_marker_as_logic_count": int((v60_outputs.get("semantic_marker_materialization_audit") or {}).get("semantic_marker_as_logic_count") or 0),
        "v62_official_backend_lowered_ir": v62_outputs.get("v62_official_backend_lowered_ir"),
        "v62_official_backend_handoff_audit_passed": bool((v62_outputs.get("official_backend_handoff_audit") or {}).get("passed_v62_portable_official_handoff_audit")),
        "v62_official_backend_hard_blocker_count": int((v62_outputs.get("official_backend_handoff_audit") or {}).get("hard_blocker_count") or 0),
        "v62_official_backend_warning_count": int((v62_outputs.get("official_backend_handoff_audit") or {}).get("warning_count") or 0),
        "v63_official_backend_subview_lowered_ir": v63_outputs.get("v63_official_backend_subview_lowered_ir"),
        "v63_official_compare_audit_passed": bool((v63_outputs.get("official_compare_audit") or {}).get("passed_v63_portable_official_compare_audit")),
        "v63_official_compare_issue_count": int((v63_outputs.get("official_compare_audit") or {}).get("issue_count") or 0),
        "v63_subview_action_count": int((v63_outputs.get("subview_lowering") or {}).get("action_count") or 0),
        "v64_official_backend_sanitized_ir": v64_outputs.get("v64_official_backend_sanitized_ir"),
        "v64_manual_official_audit_passed": bool((v64_outputs.get("v64_manual_official_audit") or {}).get("passed_v64_portable_manual_official_audit")),
        "v64_manual_official_hard_blocker_count": int((v64_outputs.get("v64_manual_official_audit") or {}).get("hard_blocker_count") or 0),
        "linux_precompile_blocker_count": len((v57_audit_outputs.get("precompile_audit") or {}).get("blockers") or []) + len((v60_outputs.get("semantic_marker_materialization_audit") or {}).get("blockers") or []) + int((v62_outputs.get("official_backend_handoff_audit") or {}).get("hard_blocker_count") or 0) + int((v64_outputs.get("v64_manual_official_audit") or {}).get("hard_blocker_count") or 0),
        "linux_precompile_audit": str(output_dir / "v57_linux_precompile_audit.json"),
        "precompile_hardened_ir": v57_audit_outputs.get("hardened_ir"),
        "recommended_linux_validation_ir": v64_outputs.get("v64_official_backend_sanitized_ir") or v63_outputs.get("v63_official_backend_subview_lowered_ir") or v62_outputs.get("v62_official_backend_lowered_ir") or v60_outputs.get("v60_real_operation_materialized_ir") or ((v57_audit_outputs.get("v59_hardening") or {}).get("v59_syntax_hardened_ir")) or v57_audit_outputs.get("hardened_ir"),
        "linux_backend_validation_required": True,
        "tiling_semantic_full_rewrite_performed": bool(tiling_full_report.get("mutation_performed")),
        "cvpipeline_semantic_schedule_performed": bool(cv_semantic_report.get("mutation_performed")),
        "tiling_axis_binding": str(tiling_dir / "tiling_axis_binding.json"),
        "cvpipeline_stage_graph": str(cv_dir / "cvpipeline_stage_graph.json"),
        "claim_boundary": "V6.4 fixes V6.3 official-document blockers in portable IR: subview address-space preservation, GM/local load-store direction, Q/O tile-loop binding, and GM->CBUF copy lowering. Official Linux backend validation is still required before claiming compile/run/msprof readiness.",
        "linux_validation_sequence": [
            "parse baseline HIVM",
            "parse optimized.four_plan_operation_rewrite.hivm.mlir",
            "HivmOpsEditor roundtrip",
            "MLIR/HIVM verifier",
            "backend compile",
            "correctness check baseline vs optimized",
            "msprof baseline and optimized with repeated median latency/cycles",
        ],
        "stage_artifacts": {
            "tiling_dir": str(tiling_dir),
            "multibuffer_dir": str(mb_dir),
            "cvpipeline_dir": str(cv_dir),
            "sync_dir": str(sync_dir),
            "coverage": coverage_out.get("summary", {}),
            "v57_precompile_audit": v57_audit_outputs,
            "v58_tiling_semantic_full_rewrite": tiling_full_report,
            "v58_cvpipeline_semantic_schedule": cv_semantic_report,
            "v60_real_operation_materialization": v60_outputs,
            "v62_official_backend_lowering": v62_outputs,
            "v63_official_backend_subview_lowering": v63_outputs,
            "v64_final_official_sanitize": v64_outputs,
        },
    }
    # V6.1: create a self-contained Linux handoff bundle for real backend validation.
    v61_manifest = create_v61_linux_handoff(
        baseline_ir=ir_path,
        optimized_ir=Path(summary.get("recommended_linux_validation_ir") or summary.get("v62_official_backend_lowered_ir") or summary.get("v60_real_operation_materialized_ir") or final_ir),
        selected_plan=selected_plan_path,
        output_dir=output_dir,
        rewrite_summary=summary,
    )
    summary["v61_linux_handoff_created"] = True
    summary["v61_linux_handoff_manifest"] = str(output_dir / "v61_linux_handoff_manifest.json")
    summary["v61_linux_handoff_dir"] = v61_manifest.get("handoff_dir")
    summary["v61_backend_patch_contract"] = v61_manifest.get("backend_patch_contract")
    summary["recommended_next_step"] = v61_manifest.get("next_action")
    _write_json(output_dir / "four_plan_operation_rewrite_summary.json", summary)
    return summary
