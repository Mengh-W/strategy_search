# -*- coding: utf-8 -*-
"""Phase-4A target-parser / HIVM Bridge hardening reports.

Phase 4 deliberately does not add new risky mutations.  It audits whether the
current standalone HIVM Rewrite Bridge is ready to be replaced by, or connected
with, a target parser / HivmOpsEditor / vTriton-style Operation-level backend.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .phase3_analysis import build_phase3a_analysis, _des_graph_brief, _trace_artifact_brief


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _read_text_safe(path: Optional[Path]) -> str:
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""




def _safe_load_json_file(path: Optional[str]) -> Optional[Any]:
    if not path:
        return None
    p = Path(path)
    if not p.exists() or not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def _which(path_or_name: Optional[str]) -> Optional[str]:
    if not path_or_name:
        return None
    p = Path(str(path_or_name))
    if p.exists():
        return str(p)
    found = shutil.which(str(path_or_name))
    return found


def _probe_capabilities(binary: Optional[str]) -> Dict[str, Any]:
    """Probe a bridge binary's capability handshake without requiring vTriton."""
    resolved = _which(binary)
    if not resolved:
        return {
            "available": False,
            "requested_binary": binary,
            "resolved_binary": None,
            "supports_print_capabilities": False,
            "reason": "binary_not_found",
        }
    try:
        proc = subprocess.run(
            [resolved, "--print-capabilities"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
        parsed = None
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
            except Exception:
                parsed = None
        return {
            "available": True,
            "requested_binary": binary,
            "resolved_binary": resolved,
            "supports_print_capabilities": proc.returncode == 0 and isinstance(parsed, dict),
            "returncode": proc.returncode,
            "stdout_preview": proc.stdout[:2000],
            "stderr_preview": proc.stderr[:2000],
            "capabilities": parsed,
        }
    except Exception as exc:
        return {
            "available": True,
            "requested_binary": binary,
            "resolved_binary": resolved,
            "supports_print_capabilities": False,
            "error": str(exc),
        }


def _local_parse_sanity(ir_text: str) -> Dict[str, Any]:
    """Cheap local sanity checks; not a replacement for MLIR parsing."""
    phase3a = build_phase3a_analysis(ir_text) if ir_text.strip() else {}
    inventory = phase3a.get("inventory", {}) if isinstance(phase3a, dict) else {}
    return {
        "text_available": bool(ir_text.strip()),
        "brace_balance": int(ir_text.count("{") - ir_text.count("}")),
        "brace_balanced": ir_text.count("{") == ir_text.count("}"),
        "has_module_keyword": "module" in ir_text,
        "has_func_keyword": "func.func" in ir_text,
        "op_count": inventory.get("op_count", 0),
        "unknown_op_count": inventory.get("unknown_op_count", 0),
        "role_counts": inventory.get("role_counts", {}),
        "interpretation": "local_text_sanity_only_not_target_parser_proof",
    }


def _extract_requested_edit_types(edit_script: Optional[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    if not isinstance(edit_script, dict):
        return out
    for edit in edit_script.get("edits", []) or []:
        if isinstance(edit, dict) and edit.get("enabled", True):
            typ = str(edit.get("type", ""))
            if typ and typ not in out:
                out.append(typ)
    return out


def _extract_manifest_capability_map(manifest: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(manifest, dict):
        return {}
    for key in ["external_backend_capabilities", "backend_capabilities", "capability_handshake"]:
        val = manifest.get(key)
        if isinstance(val, dict):
            caps = val.get("capabilities") if isinstance(val.get("capabilities"), dict) else val
            if isinstance(caps, dict):
                return caps
    # Some reports expose coverage directly rather than raw capabilities.
    if isinstance(manifest.get("coverage_by_edit_type"), dict):
        return {k: v for k, v in manifest.get("coverage_by_edit_type", {}).items()}
    return {}


def build_phase4a_target_parser_validation_report(
    *,
    original_ir_text: str,
    optimized_ir_text: str,
    edit_script: Optional[Dict[str, Any]] = None,
    bridge_manifest: Optional[Dict[str, Any]] = None,
    backend_plan: Optional[Dict[str, Any]] = None,
    strategy_rewriter_binary: Optional[str] = None,
    hivm_crud_binary: Optional[str] = None,
    tritonsim_hivm: Optional[str] = None,
    tritonsim_validation_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the Phase-4A report.

    The report is intentionally honest: a missing target parser is not treated as
    a failure of local generation, but it keeps production mutations locked.
    """
    backend_plan = backend_plan or {}
    bridge_manifest = bridge_manifest or {}
    requested_edits = _extract_requested_edit_types(edit_script)
    capability_probe = _probe_capabilities(strategy_rewriter_binary)
    crud_available = bool(_which(hivm_crud_binary)) if hivm_crud_binary else False
    tritonsim_available = bool(_which(tritonsim_hivm)) if tritonsim_hivm else False
    original_sanity = _local_parse_sanity(original_ir_text)
    optimized_sanity = _local_parse_sanity(optimized_ir_text)

    capabilities = _extract_manifest_capability_map(bridge_manifest)
    coverage: Dict[str, Any] = {}
    for typ in requested_edits:
        cap = None
        if isinstance(capabilities, dict):
            cap = capabilities.get(typ)
        coverage[typ] = {
            "requested": True,
            "manifest_entry": cap,
            "covered_by_current_bridge": bool(cap) if not isinstance(cap, dict) else bool(cap.get("mutation_supported") or cap.get("covered") or cap.get("supported")),
        }

    triton = tritonsim_validation_report or {}
    tri_input = triton.get("input_ir", {}) if isinstance(triton.get("input_ir"), dict) else {}
    tri_opt = triton.get("optimized_structural_ir", {}) if isinstance(triton.get("optimized_structural_ir"), dict) else {}
    tritonsim_ran_both = bool(tri_input.get("ran")) and bool(tri_opt.get("ran"))
    tritonsim_ok_both = tritonsim_ran_both and int(tri_input.get("returncode", -1)) == 0 and int(tri_opt.get("returncode", -1)) == 0

    blockers: List[str] = []
    if not capability_probe.get("supports_print_capabilities"):
        blockers.append("hivm_bridge_capability_handshake_missing_or_unavailable")
    if not (crud_available or tritonsim_available or tritonsim_ok_both):
        blockers.append("target_parser_or_tritonsim_not_connected")
    if optimized_sanity.get("unknown_op_count", 0):
        blockers.append("optimized_ir_contains_unknown_hivm_ops_under_local_registry")
    if not optimized_sanity.get("brace_balanced"):
        blockers.append("optimized_ir_failed_local_brace_balance")

    production_parser_status = "not_connected"
    if tritonsim_ok_both:
        production_parser_status = "tritonsim_des_trace_ran_both"
    elif tritonsim_available or crud_available:
        production_parser_status = "binary_available_but_not_validated_in_this_run"
    elif capability_probe.get("supports_print_capabilities"):
        production_parser_status = "bridge_handshake_only_no_target_parser"

    return {
        "schema_version": "hivm_phase4a_target_parser_validation_v1",
        "producer": "strategy_search_demo_v3.3.2_phase4a_bridge_hardening",
        "phase": "Phase-4A",
        "phase_goal": "Harden the HIVM Rewrite Bridge boundary before enabling riskier production mutations.",
        "naming_scope": {
            "preferred_backend_name": "HIVM Rewrite Bridge",
            "legacy_alias": "vTriton adapter",
            "current_scope": "standalone bridge plus optional external validation hooks; not fully HivmOpsEditor-backed yet",
        },
        "backend_plan": backend_plan,
        "binary_probes": {
            "hivm_strategy_rewriter": capability_probe,
            "hivm_crud_available": crud_available,
            "tritonsim_hivm_available": tritonsim_available,
        },
        "local_ir_sanity": {
            "original": original_sanity,
            "optimized": optimized_sanity,
        },
        "requested_edit_types": requested_edits,
        "bridge_coverage_by_edit_type": coverage,
        "target_parser_status": production_parser_status,
        "tritonsim_validation_reused": {
            "available": isinstance(tritonsim_validation_report, dict),
            "ran_both": tritonsim_ran_both,
            "ok_both": tritonsim_ok_both,
        },
        "phase4a_blockers": blockers,
        "readiness": {
            "can_start_phase4b_des_trace": tritonsim_available or tritonsim_ok_both,
            "can_start_guarded_q_load_hoist_prototype": production_parser_status in {"tritonsim_des_trace_ran_both"},
            "can_start_guarded_gm_deletion_prototype": False,
            "reason_gm_deletion_locked": "GM deletion still requires target alias/dependency proof plus DES/trace/msprof validation.",
        },
        "next_actions": [
            "Build or locate vTriton/HivmOpsEditor/tritonsim-hivm in the target environment.",
            "Run Phase-4A with real parser binaries and confirm original/optimized IR roundtrip.",
            "Only after parser and DES/trace validation, enable guarded Q-load hoist or limited GM deletion prototypes.",
        ],
    }


def emit_phase4a_outputs(
    *,
    out: Path,
    original_ir_text: str,
    optimized_ir_text: str,
    edit_script: Optional[Dict[str, Any]] = None,
    bridge_manifest: Optional[Dict[str, Any]] = None,
    backend_plan: Optional[Dict[str, Any]] = None,
    strategy_rewriter_binary: Optional[str] = None,
    hivm_crud_binary: Optional[str] = None,
    tritonsim_hivm: Optional[str] = None,
    tritonsim_validation_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    report = build_phase4a_target_parser_validation_report(
        original_ir_text=original_ir_text,
        optimized_ir_text=optimized_ir_text,
        edit_script=edit_script,
        bridge_manifest=bridge_manifest,
        backend_plan=backend_plan,
        strategy_rewriter_binary=strategy_rewriter_binary,
        hivm_crud_binary=hivm_crud_binary,
        tritonsim_hivm=tritonsim_hivm,
        tritonsim_validation_report=tritonsim_validation_report,
    )
    summary = {
        "schema_version": "hivm_phase4a_analysis_summary_v1",
        "producer": report["producer"],
        "phase": "Phase-4A",
        "target_parser_status": report.get("target_parser_status"),
        "blocker_count": len(report.get("phase4a_blockers", []) or []),
        "phase4a_blockers": report.get("phase4a_blockers", []),
        "readiness": report.get("readiness", {}),
    }
    _write_json(out / "target_parser_validation_report.json", report)
    _write_json(out / "phase4a_analysis_summary.json", summary)
    return summary



def _phase4b_run_brief(run: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalize one tritonsim-hivm invocation record."""
    run = run or {}
    ran = bool(run.get("ran"))
    returncode = run.get("returncode")
    ok = ran and int(returncode if returncode is not None else -1) == 0
    des_path = run.get("des_graph_file") or run.get("expected_des_graph_file")
    trace_path = run.get("perfetto_trace_file") or run.get("expected_perfetto_trace_file")
    des = _des_graph_brief(des_path)
    trace = _trace_artifact_brief(trace_path)
    return {
        "tag": run.get("tag"),
        "ran": ran,
        "returncode": returncode,
        "returncode_ok": ok,
        "reason": run.get("reason"),
        "cmd": run.get("cmd"),
        "stdout_file": run.get("stdout_file"),
        "stderr_file": run.get("stderr_file"),
        "stdout_tail": run.get("stdout_tail"),
        "stderr_tail": run.get("stderr_tail"),
        "des_graph": des,
        "perfetto_trace": trace,
        "artifact_pair_available": bool(des.get("exists") and trace.get("exists")),
        "artifact_pair_json_parse_ok": bool(des.get("json_parse_ok") and trace.get("json_parse_ok")),
    }


def _build_phase4b_command_script(
    *,
    tritonsim_hivm: Optional[str],
    original_ir_path: Optional[str],
    optimized_ir_path: Optional[str],
) -> str:
    exe = tritonsim_hivm or "/path/to/tritonsim-hivm"
    original = original_ir_path or "original.hivm.mlir"
    optimized = optimized_ir_path or "optimized.structural.hivm.mlir"
    return f"""#!/usr/bin/env bash
set -euo pipefail

# Phase-4B DES/trace validation command template.
# Replace the executable path with the real vTriton build artifact when needed.
TRITONSIM_HIVM=\"{exe}\"
ORIGINAL_IR=\"{original}\"
OPTIMIZED_IR=\"{optimized}\"
OUT_DIR=\"${{1:-phase4b_des_trace}}\"
mkdir -p \"$OUT_DIR\"

\"$TRITONSIM_HIVM\" \\
  --npuir-file \"$ORIGINAL_IR\" \\
  --des-graph-file \"$OUT_DIR/original_des_graph.json\" \\
  --perfetto-trace-file \"$OUT_DIR/original_perfetto_trace.json\"

\"$TRITONSIM_HIVM\" \\
  --npuir-file \"$OPTIMIZED_IR\" \\
  --des-graph-file \"$OUT_DIR/optimized_des_graph.json\" \\
  --perfetto-trace-file \"$OUT_DIR/optimized_perfetto_trace.json\"
"""


def build_phase4b_des_trace_execution_report(
    *,
    tritonsim_validation_report: Optional[Dict[str, Any]] = None,
    phase4a_summary: Optional[Dict[str, Any]] = None,
    tritonsim_hivm: Optional[str] = None,
    original_ir_path: Optional[str] = None,
    optimized_ir_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a stricter Phase-4B DES/trace execution report.

    Phase 3E introduced a generic wrapper. Phase 4B turns that wrapper into an
    explicit execution gate: both original and optimized IR must be run, both
    return codes must be zero, and both DES/Perfetto artifacts must exist and be
    parseable before any higher-risk Phase-4 prototype can claim external
    validation readiness.
    """
    tr = tritonsim_validation_report or {}
    original = _phase4b_run_brief(tr.get("input_ir") if isinstance(tr, dict) else None)
    optimized = _phase4b_run_brief(tr.get("optimized_structural_ir") if isinstance(tr, dict) else None)

    ran_both = bool(original.get("ran") and optimized.get("ran"))
    returncode_ok_both = bool(original.get("returncode_ok") and optimized.get("returncode_ok"))
    artifacts_exist_both = bool(original.get("artifact_pair_available") and optimized.get("artifact_pair_available"))
    artifacts_parse_ok_both = bool(original.get("artifact_pair_json_parse_ok") and optimized.get("artifact_pair_json_parse_ok"))
    passed = bool(ran_both and returncode_ok_both and artifacts_exist_both and artifacts_parse_ok_both)

    reasons: List[str] = []
    if not ran_both:
        reasons.append("tritonsim-hivm did not run for both original and optimized IR")
    if ran_both and not returncode_ok_both:
        reasons.append("tritonsim-hivm returned non-zero for original or optimized IR")
    if ran_both and not artifacts_exist_both:
        reasons.append("DES/Perfetto artifacts are missing for original or optimized IR")
    if ran_both and artifacts_exist_both and not artifacts_parse_ok_both:
        reasons.append("DES/Perfetto artifacts exist but at least one JSON artifact could not be parsed")
    if not tritonsim_hivm:
        reasons.append("no tritonsim-hivm path configured; use --run-vtriton-validation --tritonsim-hivm /path/to/tritonsim-hivm")

    des_delta = None
    trace_delta = None
    if original.get("des_graph", {}).get("node_count") is not None and optimized.get("des_graph", {}).get("node_count") is not None:
        des_delta = {
            "node_count_delta": optimized["des_graph"].get("node_count") - original["des_graph"].get("node_count"),
            "edge_count_delta": (optimized["des_graph"].get("edge_count") or 0) - (original["des_graph"].get("edge_count") or 0),
        }
    if original.get("perfetto_trace", {}).get("event_count") is not None and optimized.get("perfetto_trace", {}).get("event_count") is not None:
        trace_delta = {
            "event_count_delta": optimized["perfetto_trace"].get("event_count") - original["perfetto_trace"].get("event_count"),
        }

    status = "passed_des_trace_execution" if passed else "pending_or_failed_des_trace_execution"
    return {
        "schema_version": "hivm_phase4b_des_trace_execution_v1",
        "producer": "strategy_search_demo_v3.3.2_phase4b_des_trace_execution_gate",
        "phase": "Phase-4B",
        "phase_goal": "Run or strictly audit tritonsim-hivm DES/Perfetto trace validation for original and optimized HIVM IR.",
        "status": status,
        "passed_external_des_trace_gate": passed,
        "reasons": reasons,
        "phase4a_context": phase4a_summary or {},
        "runs": {
            "original": original,
            "optimized": optimized,
        },
        "artifact_comparison": {
            "des_graph_delta": des_delta,
            "perfetto_trace_delta": trace_delta,
            "note": "Schema-agnostic comparison only; exact counters depend on the local vTriton/tritonsim-hivm artifact schema.",
        },
        "mutation_readiness": {
            "can_start_guarded_q_load_hoist_prototype": passed,
            "can_start_limited_gm_roundtrip_deletion_prototype": False,
            "can_start_real_double_buffer": False,
            "can_start_full_cv_overlap": False,
            "can_start_real_tiling_lowering": False,
            "reason": "DES/trace pass is necessary but not sufficient; GM deletion/double-buffer/CV/tiling still require stronger alias, liveness, parser, and later msprof validation.",
        },
        "command_template_file": "phase4b_validation_commands.sh",
    }


def emit_phase4b_outputs(
    *,
    out: Path,
    tritonsim_validation_report: Optional[Dict[str, Any]] = None,
    phase4a_summary: Optional[Dict[str, Any]] = None,
    tritonsim_hivm: Optional[str] = None,
    original_ir_path: Optional[str] = None,
    optimized_ir_path: Optional[str] = None,
) -> Dict[str, Any]:
    report = build_phase4b_des_trace_execution_report(
        tritonsim_validation_report=tritonsim_validation_report,
        phase4a_summary=phase4a_summary,
        tritonsim_hivm=tritonsim_hivm,
        original_ir_path=original_ir_path,
        optimized_ir_path=optimized_ir_path,
    )
    summary = {
        "schema_version": "hivm_phase4b_analysis_summary_v1",
        "producer": report["producer"],
        "phase": "Phase-4B",
        "status": report.get("status"),
        "passed_external_des_trace_gate": report.get("passed_external_des_trace_gate"),
        "reason_count": len(report.get("reasons") or []),
        "reasons": report.get("reasons") or [],
        "mutation_readiness": report.get("mutation_readiness") or {},
    }
    _write_json(out / "phase4b_des_trace_execution_report.json", report)
    _write_json(out / "phase4b_analysis_summary.json", summary)
    script = _build_phase4b_command_script(
        tritonsim_hivm=tritonsim_hivm,
        original_ir_path=original_ir_path,
        optimized_ir_path=optimized_ir_path,
    )
    script_path = out / "phase4b_validation_commands.sh"
    script_path.write_text(script, encoding="utf-8")
    try:
        script_path.chmod(0o755)
    except Exception:
        pass
    return summary


# ---------------------------------------------------------------------------
# Phase-4C: guarded Q-load hoist prototype gate
# ---------------------------------------------------------------------------

def _decision_gate_bool(decision: Dict[str, Any], key: str) -> bool:
    gates = decision.get("gates") if isinstance(decision, dict) else {}
    if isinstance(gates, dict) and key in gates:
        return bool(gates.get(key))
    return False


def build_phase4c_q_load_hoist_prototype_report(
    *,
    q_load_hoist_decision: Optional[Dict[str, Any]] = None,
    loop_invariant_load_hoist_report: Optional[Dict[str, Any]] = None,
    phase4a_summary: Optional[Dict[str, Any]] = None,
    phase4b_summary: Optional[Dict[str, Any]] = None,
    buffer_liveness_report: Optional[Dict[str, Any]] = None,
    event_liveness_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a guarded Q-load hoist prototype decision report.

    Phase-4C is intentionally conservative.  It does not perform text-level
    region motion by default.  It promotes locally-proven Phase-3D candidates
    into a target-backend worklist only when the bridge/parser/trace gates are
    also clean.  Actual production mutation remains locked until a target
    parser / HivmOpsEditor can prove dominance and region-motion correctness.
    """
    q_load_hoist_decision = q_load_hoist_decision or {}
    loop_invariant_load_hoist_report = loop_invariant_load_hoist_report or {}
    phase4a_summary = phase4a_summary or {}
    phase4b_summary = phase4b_summary or {}
    buffer_liveness_report = buffer_liveness_report or {}
    event_liveness_report = event_liveness_report or {}

    target_parser_status = phase4a_summary.get("target_parser_status")
    phase4a_blockers = list(phase4a_summary.get("phase4a_blockers") or [])
    phase4b_passed = bool(phase4b_summary.get("passed_external_des_trace_gate"))
    capacity_ok = bool((buffer_liveness_report.get("capacity_recheck") or {}).get("passed_conservative_capacity_recheck"))
    event_ok = bool(event_liveness_report.get("passed_local_event_liveness"))
    target_parser_gate = target_parser_status == "tritonsim_des_trace_ran_both" and not phase4a_blockers

    candidates_by_id = {
        c.get("candidate_id"): c for c in loop_invariant_load_hoist_report.get("candidates") or []
    }
    decisions = []
    worklist = []
    dry_run_ready = 0
    mutation_allowed = 0
    for d in q_load_hoist_decision.get("decisions") or []:
        cid = d.get("candidate_id")
        source = candidates_by_id.get(cid, {})
        gates = {
            "phase3d_local_proof_passed": bool(d.get("local_proof_passed")),
            "phase4a_target_parser_gate": bool(target_parser_gate),
            "phase4b_des_trace_gate": bool(phase4b_passed),
            "event_liveness_ok": bool(event_ok),
            "capacity_recheck_ok": bool(capacity_ok),
            "target_region_motion_proof": _decision_gate_bool(d, "target_parser_region_motion_proof"),
        }
        # Phase-4C allows a candidate to enter the backend prototype worklist if
        # all guard rails except actual region-motion proof are clean.  It does
        # not allow mutation until the final region-motion gate is true.
        worklist_ready = all(v for k, v in gates.items() if k != "target_region_motion_proof")
        production_mutation_allowed = worklist_ready and gates["target_region_motion_proof"]
        if worklist_ready:
            dry_run_ready += 1
            worklist.append({
                "candidate_id": cid,
                "edit_type": "hoist_loop_invariant_q_load",
                "load_op_id": d.get("load_op_id"),
                "load_line": d.get("load_line"),
                "parent_loop": source.get("parent_loop"),
                "destination_buffers": source.get("destination_buffers"),
                "required_backend": "HivmOpsEditor_or_MLIR_Operation_region_motion",
                "apply_by_default": False,
                "reason": "ready for guarded backend dry-run; production mutation still requires target_region_motion_proof",
            })
        if production_mutation_allowed:
            mutation_allowed += 1
        missing = [k for k, v in gates.items() if not v]
        decisions.append({
            "candidate_id": cid,
            "load_op_id": d.get("load_op_id"),
            "load_line": d.get("load_line"),
            "phase4c_status": "backend_dry_run_worklist" if worklist_ready and not production_mutation_allowed else ("production_mutation_allowed" if production_mutation_allowed else "deferred"),
            "worklist_ready": worklist_ready,
            "production_mutation_allowed": production_mutation_allowed,
            "gates": gates,
            "missing_gates": missing,
            "reason": "all gates passed" if production_mutation_allowed else ("missing gate(s): " + ", ".join(missing) if missing else "ready for backend dry-run"),
        })

    blockers = []
    if not target_parser_gate:
        blockers.append("target parser / bridge validation is not strong enough for region motion")
    if not phase4b_passed:
        blockers.append("DES/trace execution gate did not pass")
    if not event_ok:
        blockers.append("local event liveness did not pass")
    if not capacity_ok:
        blockers.append("conservative capacity recheck did not pass")
    if not decisions:
        blockers.append("no Q-load hoist candidates were nominated by Phase-3D")
    if dry_run_ready and not mutation_allowed:
        blockers.append("candidate(s) are ready for backend dry-run, but production mutation remains blocked by missing target region-motion proof")

    return {
        "schema_version": "hivm_phase4c_q_load_hoist_prototype_v1",
        "producer": "strategy_search_demo_v3.3.2_phase4c_guarded_q_load_hoist",
        "phase": "Phase-4C",
        "phase_goal": "Promote locally-proven loop-invariant Q-load hoist candidates into a guarded backend dry-run worklist without enabling unsafe text-level region motion.",
        "candidate_count": len(decisions),
        "backend_dry_run_ready_count": dry_run_ready,
        "production_mutation_allowed_count": mutation_allowed,
        "production_mutation_unlocked": mutation_allowed > 0,
        "blockers": blockers,
        "context": {
            "phase4a_target_parser_status": target_parser_status,
            "phase4a_blockers": phase4a_blockers,
            "phase4b_passed_external_des_trace_gate": phase4b_passed,
            "event_liveness_ok": event_ok,
            "capacity_recheck_ok": capacity_ok,
        },
        "decisions": decisions,
        "backend_dry_run_worklist": worklist,
        "safety_policy": "Do not move load ops with text rewriting. Emit a backend worklist and require HivmOpsEditor/MLIR Operation-level region-motion proof before mutation.",
    }


def build_phase4c_q_load_hoist_candidate_script(report: Dict[str, Any]) -> Dict[str, Any]:
    """Build a sidecar edit script for a future HivmOpsEditor-backed dry-run."""
    worklist = report.get("backend_dry_run_worklist") or []
    return {
        "schema_version": "hivm_phase4c_q_load_hoist_candidate_script_v1",
        "producer": report.get("producer"),
        "apply_by_default": False,
        "script_mode": "backend_dry_run_only",
        "reason": "Phase-4C does not perform unsafe text-level region motion. This script is for a future target-parser/HivmOpsEditor backend dry-run.",
        "edits": [
            {
                "type": "hoist_loop_invariant_q_load",
                "candidate_id": item.get("candidate_id"),
                "load_op_id": item.get("load_op_id"),
                "load_line": item.get("load_line"),
                "required_backend": item.get("required_backend"),
                "enabled": False,
                "safety": "guarded_prototype_dry_run",
            }
            for item in worklist
        ],
    }


def emit_phase4c_outputs(
    *,
    out: Path,
    phase4a_summary: Optional[Dict[str, Any]] = None,
    phase4b_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Emit Phase-4C guarded Q-load hoist prototype artifacts.

    The detailed Phase-3 reports are read from the output directory because the
    rewrite pipeline already emitted them before Phase-4C runs.
    """
    q_decision = _safe_load_json_file(str(out / "q_load_hoist_decision.json")) or {}
    hoist_report = _safe_load_json_file(str(out / "loop_invariant_load_hoist_report.json")) or {}
    buffer_liveness = _safe_load_json_file(str(out / "buffer_liveness_report.json")) or {}
    event_liveness = _safe_load_json_file(str(out / "event_liveness_report.json")) or {}
    report = build_phase4c_q_load_hoist_prototype_report(
        q_load_hoist_decision=q_decision,
        loop_invariant_load_hoist_report=hoist_report,
        phase4a_summary=phase4a_summary,
        phase4b_summary=phase4b_summary,
        buffer_liveness_report=buffer_liveness,
        event_liveness_report=event_liveness,
    )
    script = build_phase4c_q_load_hoist_candidate_script(report)
    summary = {
        "schema_version": "hivm_phase4c_analysis_summary_v1",
        "producer": report.get("producer"),
        "phase": "Phase-4C",
        "candidate_count": report.get("candidate_count"),
        "backend_dry_run_ready_count": report.get("backend_dry_run_ready_count"),
        "production_mutation_allowed_count": report.get("production_mutation_allowed_count"),
        "production_mutation_unlocked": report.get("production_mutation_unlocked"),
        "blocker_count": len(report.get("blockers") or []),
        "blockers": report.get("blockers") or [],
        "next_step": "Implement HivmOpsEditor/MLIR region-motion dry-run for candidate worklist; keep production mutation disabled until target_region_motion_proof passes.",
    }
    _write_json(out / "phase4c_q_load_hoist_prototype_report.json", report)
    _write_json(out / "phase4c_q_load_hoist_candidate_script.json", script)
    _write_json(out / "phase4c_analysis_summary.json", summary)
    return summary


# ---------------------------------------------------------------------------
# Phase-4D: official-docs-aligned Operation-level dry-run contract
# ---------------------------------------------------------------------------

def build_phase4d_operation_rewrite_dry_run_report(
    *,
    phase4c_candidate_script: Optional[Dict[str, Any]] = None,
    phase4a_summary: Optional[Dict[str, Any]] = None,
    phase4b_summary: Optional[Dict[str, Any]] = None,
    phase4c_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build an official-docs-aligned dry-run contract for future Operation-level rewrite.

    Phase-4D still performs no production mutation.  It converts Phase-4C's
    candidate worklist into a stricter dry-run contract that a future
    HivmOpsEditor/MLIR backend can consume.  The contract follows MLIR's official
    rewrite discipline: mutation must be performed through a rewriter/backend,
    legality must be explicit, and region motion must have target-parser evidence.
    """
    phase4c_candidate_script = phase4c_candidate_script or {}
    phase4a_summary = phase4a_summary or {}
    phase4b_summary = phase4b_summary or {}
    phase4c_summary = phase4c_summary or {}

    edits = [e for e in (phase4c_candidate_script.get("edits") or []) if isinstance(e, dict)]
    phase4a_ok = phase4a_summary.get("target_parser_status") == "tritonsim_des_trace_ran_both" and not (phase4a_summary.get("phase4a_blockers") or [])
    phase4b_ok = bool(phase4b_summary.get("passed_external_des_trace_gate"))
    phase4c_ready = int(phase4c_summary.get("backend_dry_run_ready_count") or 0) > 0

    official_requirements = [
        {
            "requirement_id": "mlir_rewriter_owns_mutation",
            "source": "MLIR PatternRewriter official documentation",
            "rule": "IR mutations in a rewrite must be performed through the rewriter/backend API rather than ad-hoc textual edits.",
            "project_enforcement": "Phase-4D emits dry-run actions only; apply_by_default is false and no Python text-level region motion is performed.",
            "satisfied_by_this_phase": True,
        },
        {
            "requirement_id": "explicit_legality_contract",
            "source": "MLIR Dialect Conversion official documentation",
            "rule": "Rewrites should have explicit legality/capability conditions before transformation is accepted.",
            "project_enforcement": "Each dry-run action carries required_preconditions and locked production mutation status.",
            "satisfied_by_this_phase": True,
        },
        {
            "requirement_id": "operation_level_region_motion_only",
            "source": "MLIR Operation API documentation",
            "rule": "Moving operations across blocks/regions is an Operation-level action and must preserve dominance/region semantics.",
            "project_enforcement": "Future backend must prove dominance, region motion, event liveness and buffer capacity before enabling mutation.",
            "satisfied_by_this_phase": False,
            "reason": "Target HivmOpsEditor/MLIR backend is not connected in this package.",
        },
    ]

    actions: List[Dict[str, Any]] = []
    for idx, e in enumerate(edits):
        actions.append({
            "action_id": f"phase4d_dryrun_{idx}",
            "type": e.get("type"),
            "candidate_id": e.get("candidate_id"),
            "load_op_id": e.get("load_op_id"),
            "load_line": e.get("load_line"),
            "official_backend_required": "HivmOpsEditor_or_MLIR_Operation_backend",
            "allowed_to_mutate_now": False,
            "dry_run_only": True,
            "apply_by_default": False,
            "required_preconditions": {
                "phase4a_target_parser_gate": bool(phase4a_ok),
                "phase4b_des_trace_gate": bool(phase4b_ok),
                "phase4c_candidate_ready": bool(phase4c_ready),
                "operation_level_dominance_proof": False,
                "operation_level_region_motion_proof": False,
                "mlir_verifier_after_rewrite": False,
                "des_trace_after_real_backend_rewrite": False,
            },
            "next_backend_steps": [
                "Load the HIVM module with the target parser/HivmOpsEditor.",
                "Resolve candidate load_op_id to a concrete Operation* or equivalent handle.",
                "Check dominance and region ownership before any move.",
                "Use backend/rewriter APIs for move/clone/erase; do not use text rewrite.",
                "Run verifier plus DES/trace after dry-run output is produced.",
            ],
        })

    blockers: List[str] = []
    if not phase4a_ok:
        blockers.append("phase4a_target_parser_gate_not_clean")
    if not phase4b_ok:
        blockers.append("phase4b_des_trace_gate_not_passed")
    if not phase4c_ready:
        blockers.append("no_phase4c_backend_dry_run_candidates")
    blockers.append("operation_level_dominance_and_region_motion_backend_not_connected")

    return {
        "schema_version": "hivm_phase4d_operation_rewrite_dry_run_v1",
        "producer": "strategy_search_demo_v3.3.2_phase4d_official_dry_run_contract",
        "phase": "Phase-4D",
        "phase_goal": "Translate guarded Q-load hoist candidates into an official-docs-aligned Operation-level dry-run contract without enabling production mutation.",
        "official_alignment": official_requirements,
        "input_candidate_count": len(edits),
        "dry_run_action_count": len(actions),
        "production_mutation_allowed_count": 0,
        "production_mutation_unlocked": False,
        "blockers": blockers,
        "actions": actions,
        "safety_policy": "No text-level region motion. No production mutation until HivmOpsEditor/MLIR Operation-level dominance, region-motion, verifier and DES/trace checks all pass.",
    }


def build_phase4d_hivmopseditor_dry_run_plan(report: Dict[str, Any]) -> Dict[str, Any]:
    """Build a future-backend plan file from the Phase-4D dry-run report."""
    return {
        "schema_version": "hivm_phase4d_hivmopseditor_dry_run_plan_v1",
        "producer": report.get("producer"),
        "apply_by_default": False,
        "backend_required": "HivmOpsEditor_or_MLIR_Operation_backend",
        "mode": "dry_run_only",
        "official_docs_policy": {
            "mutation_api": "Use backend/rewriter APIs for create/move/erase/replace; no raw text mutation for region motion.",
            "legality": "Reject if target legality, dominance, region-motion, event-liveness, buffer-capacity or verifier checks fail.",
        },
        "actions": report.get("actions") or [],
    }


def emit_phase4d_outputs(
    *,
    out: Path,
    phase4a_summary: Optional[Dict[str, Any]] = None,
    phase4b_summary: Optional[Dict[str, Any]] = None,
    phase4c_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Emit Phase-4D Operation-level dry-run contract artifacts."""
    candidate_script = _safe_load_json_file(str(out / "phase4c_q_load_hoist_candidate_script.json")) or {}
    report = build_phase4d_operation_rewrite_dry_run_report(
        phase4c_candidate_script=candidate_script,
        phase4a_summary=phase4a_summary,
        phase4b_summary=phase4b_summary,
        phase4c_summary=phase4c_summary,
    )
    plan = build_phase4d_hivmopseditor_dry_run_plan(report)
    official_report = {
        "schema_version": "hivm_phase4d_official_mlir_compliance_v1",
        "producer": report.get("producer"),
        "phase": "Phase-4D",
        "official_alignment": report.get("official_alignment"),
        "compliance_summary": {
            "text_level_region_motion_disabled": True,
            "production_mutation_unlocked": False,
            "requires_backend_rewriter_api": True,
            "requires_explicit_legality_gate": True,
            "requires_operation_level_dominance_and_region_motion_proof": True,
        },
        "note": "This file records design compliance with official MLIR rewrite discipline; it is not a substitute for running a real MLIR verifier in a target backend.",
    }
    summary = {
        "schema_version": "hivm_phase4d_analysis_summary_v1",
        "producer": report.get("producer"),
        "phase": "Phase-4D",
        "dry_run_action_count": report.get("dry_run_action_count"),
        "production_mutation_allowed_count": report.get("production_mutation_allowed_count"),
        "production_mutation_unlocked": report.get("production_mutation_unlocked"),
        "blocker_count": len(report.get("blockers") or []),
        "blockers": report.get("blockers") or [],
        "next_step": "Connect a real HivmOpsEditor/MLIR Operation-level backend and run dominance/region-motion/verifier checks before any production mutation.",
    }
    _write_json(out / "phase4d_operation_rewrite_dry_run_report.json", report)
    _write_json(out / "phase4d_hivmopseditor_dry_run_plan.json", plan)
    _write_json(out / "phase4d_official_mlir_compliance_report.json", official_report)
    _write_json(out / "phase4d_analysis_summary.json", summary)
    return summary

# ---------------------------------------------------------------------------
# Phase-4E: Phase-4 closure and Phase-5 handoff
# ---------------------------------------------------------------------------

def build_phase4e_closure_report(
    *,
    phase4a_summary: Optional[Dict[str, Any]] = None,
    phase4b_summary: Optional[Dict[str, Any]] = None,
    phase4c_summary: Optional[Dict[str, Any]] = None,
    phase4d_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Close Phase 4 without enabling risky mutations.

    Phase-4E is a management and engineering gate.  It summarizes how far the
    current HIVM Rewrite Bridge has progressed toward an official Operation-level
    backend, and it records exactly which blockers remain before any real
    region-motion or memory-deletion mutation can be enabled.
    """
    phase4a_summary = phase4a_summary or {}
    phase4b_summary = phase4b_summary or {}
    phase4c_summary = phase4c_summary or {}
    phase4d_summary = phase4d_summary or {}

    phase4a_clean = not (phase4a_summary.get("phase4a_blockers") or [])
    phase4b_passed = bool(phase4b_summary.get("passed_external_des_trace_gate"))
    phase4c_has_worklist = int(phase4c_summary.get("backend_dry_run_ready_count") or 0) > 0
    phase4d_has_contract = int(phase4d_summary.get("dry_run_action_count") or 0) > 0

    blockers: List[str] = []
    if not phase4a_clean:
        blockers.append("phase4a_target_parser_or_bridge_readiness_not_clean")
    if not phase4b_passed:
        blockers.append("phase4b_real_des_trace_gate_not_passed")
    if not phase4c_has_worklist:
        blockers.append("phase4c_no_guarded_q_load_worklist_ready")
    if not phase4d_has_contract:
        blockers.append("phase4d_no_operation_level_dry_run_contract")
    blockers.append("real_hivmopseditor_or_mlir_operation_backend_not_connected")
    blockers.append("real_mlir_verifier_not_run_on_backend_mutation")
    blockers.append("real_msprof_validation_not_started")

    phase5_entry_gates = {
        "real_hivmopseditor_or_mlir_operation_backend_connected": False,
        "operation_level_dominance_region_motion_proof_available": False,
        "real_mlir_verifier_after_mutation_available": False,
        "real_tritonsim_des_trace_ran_on_backend_mutated_ir": False,
        "msprof_validation_available": False,
    }

    capability_matrix = {
        "sync_rewrite_audit_and_refinement": {
            "phase4_status": "eligible_for_controlled_prototype",
            "reason": "Current bridge can mutate simple sync patterns and local evidence exists.",
            "phase5_condition": "Run through real target parser / verifier / DES trace before broadening scope.",
        },
        "guarded_q_load_hoist": {
            "phase4_status": "dry_run_contract_ready" if phase4d_has_contract else "candidate_gate_only",
            "reason": "Candidate/worklist can be emitted, but real region motion requires Operation-level dominance proof.",
            "phase5_condition": "Connect HivmOpsEditor/MLIR backend and verify dominance, region ownership, liveness, capacity, verifier and DES/trace.",
        },
        "gm_roundtrip_deletion": {
            "phase4_status": "locked",
            "reason": "Alias / observable-boundary proof remains insufficient for real deletion.",
            "phase5_condition": "Require same-address proof, MemorySSA-like reaching def, no unknown side effects, verifier, DES/trace and later msprof.",
        },
        "real_double_buffer_pingpong": {
            "phase4_status": "locked",
            "reason": "Needs buffer cloning, live-range extension, sync scheduling and capacity proof.",
            "phase5_condition": "Prototype only after Operation-level backend and trace validation are real, not fixture-only.",
        },
        "full_cv_pipeline_overlap": {
            "phase4_status": "locked",
            "reason": "Requires real stage graph, event allocation, buffer lifetime and schedule transformation.",
            "phase5_condition": "Start with stage graph validation before any schedule mutation.",
        },
        "real_tiling_loop_lowering": {
            "phase4_status": "locked",
            "reason": "Highest-risk rewrite: changes loops, indexes, tail handling, reductions and memory offsets.",
            "phase5_condition": "Defer until parser/verifier/DES/msprof chain is stable on smaller rewrites.",
        },
    }

    return {
        "schema_version": "hivm_phase4e_closure_v1",
        "producer": "strategy_search_demo_v3.3.2_phase4e_closure_phase5_handoff",
        "phase": "Phase-4E",
        "phase4_status": "closed_bridge_validation_and_dry_run_contract",
        "phase_goal": "Close Phase 4 by summarizing bridge hardening, DES/trace gate, guarded Q-load worklist and official Operation-level dry-run contract.",
        "official_docs_alignment": {
            "mlir_pattern_rewriter_policy": "Real IR mutation must be delegated to a rewriter/backend API; no Python text-level region motion.",
            "mlir_dialect_conversion_policy": "Transformation acceptance requires explicit legality conditions, not just a pattern match.",
            "mlir_operation_motion_policy": "Moving operations is an Operation-level action that must preserve dominance and region semantics.",
        },
        "phase4_summaries": {
            "phase4a": phase4a_summary,
            "phase4b": phase4b_summary,
            "phase4c": phase4c_summary,
            "phase4d": phase4d_summary,
        },
        "capability_matrix": capability_matrix,
        "phase5_entry_gates": phase5_entry_gates,
        "production_mutations_unlocked": {
            "q_load_hoist": False,
            "gm_roundtrip_deletion": False,
            "real_double_buffer": False,
            "full_cv_overlap": False,
            "real_tiling_loop_lowering": False,
        },
        "remaining_blockers": blockers,
        "recommended_phase5_order": [
            "Phase-5A: connect real HivmOpsEditor / MLIR Operation-level backend",
            "Phase-5B: run real verifier and tritonsim-hivm on original and backend-mutated IR",
            "Phase-5C: enable Q-load hoist only as guarded dry-run-to-mutation prototype",
            "Phase-5D: add limited GM round-trip deletion only for exact same-address toy/simple patterns",
            "Phase-5E: decide whether to move toward msprof validation before double-buffer/CV overlap",
        ],
        "leadership_summary": "Phase 4 completed the bridge validation and official dry-run contract layer. The project can now identify guarded optimization candidates and produce backend-ready dry-run plans, but production mutations remain locked until a real Operation-level backend, verifier, DES/trace and later msprof validation are connected.",
    }


def emit_phase4e_outputs(
    *,
    out: Path,
    phase4a_summary: Optional[Dict[str, Any]] = None,
    phase4b_summary: Optional[Dict[str, Any]] = None,
    phase4c_summary: Optional[Dict[str, Any]] = None,
    phase4d_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Emit Phase-4 closure and Phase-5 handoff artifacts."""
    report = build_phase4e_closure_report(
        phase4a_summary=phase4a_summary,
        phase4b_summary=phase4b_summary,
        phase4c_summary=phase4c_summary,
        phase4d_summary=phase4d_summary,
    )
    summary = {
        "schema_version": "hivm_phase4e_analysis_summary_v1",
        "producer": report.get("producer"),
        "phase": "Phase-4E",
        "phase4_status": report.get("phase4_status"),
        "remaining_blocker_count": len(report.get("remaining_blockers") or []),
        "remaining_blockers": report.get("remaining_blockers") or [],
        "production_mutations_unlocked": report.get("production_mutations_unlocked"),
        "recommended_phase5_order": report.get("recommended_phase5_order"),
    }
    _write_json(out / "phase4_closure_report.json", report)
    _write_json(out / "phase4e_analysis_summary.json", summary)
    return summary
