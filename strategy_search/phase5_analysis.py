# -*- coding: utf-8 -*-
"""Phase-5A Operation-backend readiness and inventory alignment reports.

Phase 5 starts the handoff from the standalone HIVM Rewrite Bridge toward a
real MLIR/HivmOpsEditor Operation-level backend.  This module deliberately does
not perform production mutation.  It audits whether a backend is available, what
kind of official MLIR-facing evidence is still missing, and whether the current
local scanner inventory can be aligned with a future Operation-walk inventory.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional

from .phase3_analysis import build_phase3a_analysis
from .phase4_analysis import _probe_capabilities, _which, _safe_load_json_file


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


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _local_operation_inventory(ir_text: str) -> Dict[str, Any]:
    """Return the current conservative inventory as a backend-alignment baseline."""
    phase3 = build_phase3a_analysis(ir_text or "") if (ir_text or "").strip() else {}
    inventory = phase3.get("inventory", {}) if isinstance(phase3, dict) else {}
    dependency = phase3.get("dependency_graph", {}) if isinstance(phase3, dict) else {}
    event = phase3.get("event_liveness", {}) if isinstance(phase3, dict) else {}
    return {
        "source": "local_conservative_scanner",
        "is_official_operation_backend": False,
        "inventory": inventory,
        "dependency_graph_brief": {
            "node_count": dependency.get("node_count", 0),
            "edge_count": dependency.get("edge_count", 0),
            "edge_counts": dependency.get("edge_counts", {}),
        },
        "event_liveness_brief": {
            "event_count": event.get("event_count", 0),
            "safe_pair_count": event.get("safe_pair_count", 0),
            "passed_local_event_liveness": event.get("passed_local_event_liveness", False),
        },
    }


def _probe_operation_backend(
    *,
    operation_backend_binary: Optional[str] = None,
    hivm_strategy_rewriter_binary: Optional[str] = None,
    hivm_crud_binary: Optional[str] = None,
    mlir_opt_binary: Optional[str] = None,
) -> Dict[str, Any]:
    """Probe available backend-like binaries without assuming they are official.

    A future real backend should support one or more explicit capability modes
    such as --print-capabilities, --inventory, --roundtrip and --verify-only.
    The current standalone bridge usually only supports --print-capabilities.
    """
    operation_backend_resolved = _which(operation_backend_binary)
    crud_resolved = _which(hivm_crud_binary)
    mlir_opt_resolved = _which(mlir_opt_binary)
    bridge_probe = _probe_capabilities(hivm_strategy_rewriter_binary)

    backend_probe: Dict[str, Any]
    if operation_backend_resolved:
        try:
            proc = subprocess.run(
                _backend_arg_prefix(operation_backend_resolved) + ["--print-capabilities"],
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
            backend_probe = {
                "available": True,
                "requested_binary": operation_backend_binary,
                "resolved_binary": operation_backend_resolved,
                "supports_print_capabilities": proc.returncode == 0 and isinstance(parsed, dict),
                "returncode": proc.returncode,
                "stdout_preview": proc.stdout[:2000],
                "stderr_preview": proc.stderr[:2000],
                "capabilities": parsed,
            }
        except Exception as exc:
            backend_probe = {
                "available": True,
                "requested_binary": operation_backend_binary,
                "resolved_binary": operation_backend_resolved,
                "supports_print_capabilities": False,
                "error": str(exc),
            }
    else:
        backend_probe = {
            "available": False,
            "requested_binary": operation_backend_binary,
            "resolved_binary": None,
            "supports_print_capabilities": False,
            "reason": "operation_backend_binary_not_configured_or_not_found",
        }

    return {
        "operation_backend": backend_probe,
        "standalone_hivm_rewrite_bridge": bridge_probe,
        "hivm_crud_binary": {
            "available": bool(crud_resolved),
            "requested_binary": hivm_crud_binary,
            "resolved_binary": crud_resolved,
            "role": "possible future HivmOpsEditor-backed reference tool; not required for current bridge mode",
        },
        "mlir_opt_binary": {
            "available": bool(mlir_opt_resolved),
            "requested_binary": mlir_opt_binary,
            "resolved_binary": mlir_opt_resolved,
            "role": "possible generic MLIR parser/verifier/pass runner; HIVM dialect availability still required",
        },
    }


def _backend_supports(capabilities: Optional[Dict[str, Any]], feature: str) -> bool:
    if not isinstance(capabilities, dict):
        return False
    raw = capabilities.get(feature)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, dict):
        return bool(raw.get("supported") or raw.get("available") or raw.get("enabled"))
    return False


def _build_backend_contract_requirements() -> Dict[str, Any]:
    """Official-docs-aligned contract for a real Operation-level backend."""
    return {
        "required_backend_modes": {
            "print_capabilities": {
                "required": True,
                "purpose": "Machine-readable handshake before Python dispatches edit scripts.",
                "expected_cli": "--print-capabilities",
            },
            "inventory": {
                "required": True,
                "purpose": "Walk MLIR Operations and emit op ids, names, blocks/regions, operands/results and attributes.",
                "expected_cli": "--inventory --input <ir> --report operation_inventory_backend.json",
            },
            "roundtrip": {
                "required": True,
                "purpose": "Parse and re-emit IR without mutation, then prove parser stability before any rewrite.",
                "expected_cli": "--roundtrip --input <ir> --output roundtrip.hivm.mlir --report mlir_roundtrip_report.json",
            },
            "verify_only": {
                "required": True,
                "purpose": "Run target MLIR verifier / dialect verifier on original, roundtrip and mutated IR.",
                "expected_cli": "--verify-only --input <ir> --report mlir_verifier_report.json",
            },
            "dry_run_edit_script": {
                "required": True,
                "purpose": "Locate candidate operations and insertion points without mutating IR.",
                "expected_cli": "--dry-run --input <ir> --edit-script <plan> --report operation_level_dry_run_report.json",
            },
        },
        "official_mlir_principles": {
            "operation_unit": "MLIR Operation is the unit to inspect and transform; text lines are not a safe transformation unit.",
            "rewriter_discipline": "Creates/replaces/erases/moves must go through rewriter/backend APIs that keep IR state and listeners coherent.",
            "dominance_region_policy": "Any cross-region or cross-loop motion requires dominance, region ownership and verifier checks.",
            "legality_policy": "No mutation is accepted solely because a pattern matches; explicit legality and blocker reasons are required.",
        },
    }


def build_phase5a_operation_backend_readiness_report(
    *,
    original_ir_text: str,
    optimized_ir_text: str,
    phase4_closure_report: Optional[Dict[str, Any]] = None,
    phase4d_dry_run_plan: Optional[Dict[str, Any]] = None,
    operation_backend_binary: Optional[str] = None,
    hivm_strategy_rewriter_binary: Optional[str] = None,
    hivm_crud_binary: Optional[str] = None,
    mlir_opt_binary: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the Phase-5A readiness report.

    This report starts Phase 5 with a strict boundary: it prepares for a real
    Operation-level backend but does not allow production mutation.  If no such
    backend is configured, the report remains useful by showing exactly what is
    missing and by emitting the local inventory baseline for future comparison.
    """
    probes = _probe_operation_backend(
        operation_backend_binary=operation_backend_binary,
        hivm_strategy_rewriter_binary=hivm_strategy_rewriter_binary,
        hivm_crud_binary=hivm_crud_binary,
        mlir_opt_binary=mlir_opt_binary,
    )
    contract = _build_backend_contract_requirements()
    original_local = _local_operation_inventory(original_ir_text)
    optimized_local = _local_operation_inventory(optimized_ir_text)

    op_backend_caps = probes.get("operation_backend", {}).get("capabilities")
    supported_modes = {
        "print_capabilities": bool(probes.get("operation_backend", {}).get("supports_print_capabilities")),
        "inventory": _backend_supports(op_backend_caps, "inventory") or _backend_supports(op_backend_caps, "operation_inventory"),
        "roundtrip": _backend_supports(op_backend_caps, "roundtrip"),
        "verify_only": _backend_supports(op_backend_caps, "verify_only") or _backend_supports(op_backend_caps, "verifier"),
        "dry_run_edit_script": _backend_supports(op_backend_caps, "dry_run_edit_script") or _backend_supports(op_backend_caps, "dry_run"),
    }

    blockers: List[str] = []
    if not probes.get("operation_backend", {}).get("available"):
        blockers.append("real_operation_backend_binary_not_configured_or_not_found")
    if not supported_modes["inventory"]:
        blockers.append("operation_backend_inventory_mode_missing")
    if not supported_modes["roundtrip"]:
        blockers.append("operation_backend_roundtrip_mode_missing")
    if not supported_modes["verify_only"]:
        blockers.append("operation_backend_verify_only_mode_missing")
    if not supported_modes["dry_run_edit_script"]:
        blockers.append("operation_backend_dry_run_edit_script_mode_missing")

    actions = phase4d_dry_run_plan.get("actions", []) if isinstance(phase4d_dry_run_plan, dict) else []
    if not actions:
        blockers.append("no_phase4d_operation_dry_run_actions_available")

    backend_status = "not_connected"
    if probes.get("operation_backend", {}).get("available"):
        if all(supported_modes.values()):
            backend_status = "operation_backend_capability_complete_not_yet_executed"
        else:
            backend_status = "operation_backend_partial_capability"
    elif probes.get("standalone_hivm_rewrite_bridge", {}).get("supports_print_capabilities"):
        backend_status = "standalone_bridge_only_no_operation_backend"

    return {
        "schema_version": "hivm_phase5a_operation_backend_readiness_v1",
        "producer": "strategy_search_demo_v3.3.2_phase5a_operation_backend_readiness",
        "phase": "Phase-5A",
        "phase_goal": "Start real Operation-level backend integration by auditing capabilities, inventory baselines and official MLIR contract requirements.",
        "backend_status": backend_status,
        "official_docs_contract": contract,
        "binary_probes": probes,
        "supported_backend_modes": supported_modes,
        "local_inventory_baseline": {
            "original": original_local,
            "optimized": optimized_local,
            "note": "This is still the project-local conservative scanner baseline. It is emitted for future comparison with a real Operation-walk backend, not as a replacement for MLIR parsing.",
        },
        "phase4_context": {
            "phase4_status": (phase4_closure_report or {}).get("phase4_status"),
            "remaining_blockers": (phase4_closure_report or {}).get("remaining_blockers", []),
            "phase4d_action_count": len(actions),
        },
        "phase5a_blockers": blockers,
        "readiness": {
            "can_run_operation_inventory_backend": bool(supported_modes["inventory"]),
            "can_run_roundtrip_backend": bool(supported_modes["roundtrip"]),
            "can_run_verify_only_backend": bool(supported_modes["verify_only"]),
            "can_run_operation_level_dry_run_backend": bool(supported_modes["dry_run_edit_script"] and actions),
            "production_mutation_allowed": False,
            "reason_production_mutation_locked": "Phase-5A is readiness/inventory/roundtrip planning only; no mutation until real backend inventory, roundtrip, verifier, dry-run and DES/trace all pass.",
        },
        "next_actions": [
            "Build or locate the real HivmOpsEditor / MLIR Operation-level backend.",
            "Add backend CLI modes: --inventory, --roundtrip, --verify-only and --dry-run.",
            "Compare backend Operation inventory with this local baseline before any mutation.",
            "Run no-op roundtrip and target verifier before Q-load hoist or GM deletion prototypes.",
        ],
    }


def build_phase5a_inventory_alignment_report(readiness_report: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize how close we are to comparing local and Operation backend inventories."""
    original_inv = ((readiness_report.get("local_inventory_baseline") or {}).get("original") or {}).get("inventory", {})
    optimized_inv = ((readiness_report.get("local_inventory_baseline") or {}).get("optimized") or {}).get("inventory", {})
    op_backend_ready = bool((readiness_report.get("readiness") or {}).get("can_run_operation_inventory_backend"))
    return {
        "schema_version": "hivm_phase5a_inventory_alignment_v1",
        "producer": readiness_report.get("producer"),
        "phase": "Phase-5A",
        "operation_backend_inventory_available": op_backend_ready,
        "alignment_status": "pending_real_operation_backend_inventory" if not op_backend_ready else "ready_to_compare_with_backend_inventory",
        "local_original_inventory_brief": {
            "op_count": original_inv.get("op_count", 0),
            "unknown_op_count": original_inv.get("unknown_op_count", 0),
            "role_counts": original_inv.get("role_counts", {}),
        },
        "local_optimized_inventory_brief": {
            "op_count": optimized_inv.get("op_count", 0),
            "unknown_op_count": optimized_inv.get("unknown_op_count", 0),
            "role_counts": optimized_inv.get("role_counts", {}),
        },
        "required_backend_fields": [
            "op_id",
            "operation_name",
            "block_id",
            "region_path",
            "parent_operation",
            "operand_count",
            "result_count",
            "attributes",
            "source_location_or_line_if_available",
        ],
        "comparison_policy": "The local scanner is a baseline only. Mismatches with the Operation backend must be treated as blockers until explained.",
    }


def emit_phase5a_outputs(
    *,
    out: Path,
    original_ir_text: str,
    optimized_ir_text: str,
    operation_backend_binary: Optional[str] = None,
    hivm_strategy_rewriter_binary: Optional[str] = None,
    hivm_crud_binary: Optional[str] = None,
    mlir_opt_binary: Optional[str] = None,
) -> Dict[str, Any]:
    """Emit Phase-5A Operation backend readiness artifacts."""
    phase4_closure = _safe_load_json_file(str(out / "phase4_closure_report.json")) or {}
    phase4d_plan = _safe_load_json_file(str(out / "phase4d_hivmopseditor_dry_run_plan.json")) or {}
    report = build_phase5a_operation_backend_readiness_report(
        original_ir_text=original_ir_text,
        optimized_ir_text=optimized_ir_text,
        phase4_closure_report=phase4_closure,
        phase4d_dry_run_plan=phase4d_plan,
        operation_backend_binary=operation_backend_binary,
        hivm_strategy_rewriter_binary=hivm_strategy_rewriter_binary,
        hivm_crud_binary=hivm_crud_binary,
        mlir_opt_binary=mlir_opt_binary,
    )
    alignment = build_phase5a_inventory_alignment_report(report)
    summary = {
        "schema_version": "hivm_phase5a_analysis_summary_v1",
        "producer": report.get("producer"),
        "phase": "Phase-5A",
        "backend_status": report.get("backend_status"),
        "blocker_count": len(report.get("phase5a_blockers") or []),
        "phase5a_blockers": report.get("phase5a_blockers") or [],
        "production_mutation_allowed": False,
        "readiness": report.get("readiness"),
        "leadership_summary": "Phase 5A starts the real Operation-level backend integration path. The current project can emit a local inventory baseline and backend contract, but production mutation remains locked until a real HivmOpsEditor/MLIR backend provides inventory, roundtrip, verifier and dry-run evidence.",
    }
    _write_json(out / "phase5a_operation_backend_readiness_report.json", report)
    _write_json(out / "phase5a_inventory_alignment_report.json", alignment)
    _write_json(out / "phase5a_analysis_summary.json", summary)
    return summary



def _sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> Optional[str]:
    try:
        if not path.exists():
            return None
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _run_backend_command(cmd: List[str], *, timeout: int = 20) -> Dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return {
            "command": cmd,
            "ran": True,
            "returncode": proc.returncode,
            "ok": proc.returncode == 0,
            "stdout_preview": proc.stdout[:4000],
            "stderr_preview": proc.stderr[:4000],
        }
    except Exception as exc:
        return {
            "command": cmd,
            "ran": False,
            "returncode": None,
            "ok": False,
            "error": str(exc),
        }


def _load_json_optional(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if path.exists():
            obj = json.loads(path.read_text(encoding="utf-8"))
            return obj if isinstance(obj, dict) else {"value": obj}
    except Exception as exc:
        return {"parse_error": str(exc)}
    return None


def _build_local_roundtrip_check(original_text: str, roundtrip_text: str) -> Dict[str, Any]:
    orig_inv = _local_operation_inventory(original_text).get("inventory", {})
    rt_inv = _local_operation_inventory(roundtrip_text).get("inventory", {})
    return {
        "mode": "local_conservative_roundtrip_check",
        "original_sha256": _sha256_text(original_text),
        "roundtrip_sha256": _sha256_text(roundtrip_text),
        "byte_identical": _sha256_text(original_text) == _sha256_text(roundtrip_text),
        "original_op_count": orig_inv.get("op_count", 0),
        "roundtrip_op_count": rt_inv.get("op_count", 0),
        "op_count_delta": int(rt_inv.get("op_count", 0) or 0) - int(orig_inv.get("op_count", 0) or 0),
        "original_unknown_op_count": orig_inv.get("unknown_op_count", 0),
        "roundtrip_unknown_op_count": rt_inv.get("unknown_op_count", 0),
        "role_counts_equal": orig_inv.get("role_counts", {}) == rt_inv.get("role_counts", {}),
        "note": "This is a local sanity check only. Passing it is not equivalent to MLIR verifier success.",
    }


def _run_phase5b_for_one_ir(
    *,
    tag: str,
    ir_text: str,
    out: Path,
    operation_backend_binary: Optional[str],
    mlir_opt_binary: Optional[str] = None,
) -> Dict[str, Any]:
    """Run Phase-5B inventory/roundtrip/verify gates for one IR file when possible."""
    backend = _which(operation_backend_binary)
    input_path = out / f"phase5b_{tag}_input.hivm.mlir"
    inventory_report_path = out / f"phase5b_{tag}_operation_inventory_backend.json"
    roundtrip_path = out / f"phase5b_{tag}_roundtrip.hivm.mlir"
    roundtrip_report_path = out / f"phase5b_{tag}_roundtrip_backend_report.json"
    verifier_report_path = out / f"phase5b_{tag}_verifier_backend_report.json"
    mlir_opt_report_path = out / f"phase5b_{tag}_mlir_opt_probe_report.json"
    input_path.write_text(ir_text or "", encoding="utf-8")

    planned_commands = {
        "inventory": _backend_arg_prefix(backend) + ["--inventory", "--input", str(input_path), "--report", str(inventory_report_path)],
        "roundtrip": _backend_arg_prefix(backend) + ["--roundtrip", "--input", str(input_path), "--output", str(roundtrip_path), "--report", str(roundtrip_report_path)],
        "verify_only": _backend_arg_prefix(backend) + ["--verify-only", "--input", str(roundtrip_path if roundtrip_path.exists() else input_path), "--report", str(verifier_report_path)],
    }

    if not backend:
        return {
            "tag": tag,
            "backend_available": False,
            "status": "pending_operation_backend_not_configured",
            "input_path": str(input_path),
            "planned_commands": planned_commands,
            "inventory": {"ran": False, "ok": False, "reason": "operation_backend_missing"},
            "roundtrip": {"ran": False, "ok": False, "reason": "operation_backend_missing"},
            "verify_only": {"ran": False, "ok": False, "reason": "operation_backend_missing"},
            "local_roundtrip_check": None,
        }

    inventory_run = _run_backend_command(planned_commands["inventory"])
    roundtrip_run = _run_backend_command(planned_commands["roundtrip"])
    roundtrip_text = roundtrip_path.read_text(encoding="utf-8") if roundtrip_path.exists() else ""
    verify_input = roundtrip_path if roundtrip_path.exists() else input_path
    verify_cmd = _backend_arg_prefix(backend) + ["--verify-only", "--input", str(verify_input), "--report", str(verifier_report_path)]
    verify_run = _run_backend_command(verify_cmd)

    mlir_opt_resolved = _which(mlir_opt_binary)
    mlir_opt_probe: Dict[str, Any]
    if mlir_opt_resolved:
        # Generic mlir-opt may not have the HIVM dialect registered. Treat failure as diagnostic, not as official pass/fail.
        mlir_cmd = [mlir_opt_resolved, str(verify_input)]
        mlir_opt_probe = _run_backend_command(mlir_cmd)
        _write_json(mlir_opt_report_path, mlir_opt_probe)
    else:
        mlir_opt_probe = {"ran": False, "ok": False, "reason": "mlir_opt_not_configured"}

    local_check = _build_local_roundtrip_check(ir_text, roundtrip_text) if roundtrip_path.exists() else None
    return {
        "tag": tag,
        "backend_available": True,
        "status": "roundtrip_and_verify_executed" if (roundtrip_run.get("ran") and verify_run.get("ran")) else "backend_execution_incomplete",
        "input_path": str(input_path),
        "planned_commands": planned_commands,
        "inventory": {
            **inventory_run,
            "report_path": str(inventory_report_path),
            "report_exists": inventory_report_path.exists(),
            "report_json": _load_json_optional(inventory_report_path),
        },
        "roundtrip": {
            **roundtrip_run,
            "output_path": str(roundtrip_path),
            "output_exists": roundtrip_path.exists(),
            "output_sha256": _sha256_file(roundtrip_path),
            "report_path": str(roundtrip_report_path),
            "report_exists": roundtrip_report_path.exists(),
            "report_json": _load_json_optional(roundtrip_report_path),
        },
        "verify_only": {
            **verify_run,
            "verified_input": str(verify_input),
            "report_path": str(verifier_report_path),
            "report_exists": verifier_report_path.exists(),
            "report_json": _load_json_optional(verifier_report_path),
        },
        "mlir_opt_probe": mlir_opt_probe,
        "local_roundtrip_check": local_check,
    }


def build_phase5b_roundtrip_verifier_gate_report(
    *,
    out: Path,
    original_ir_text: str,
    optimized_ir_text: str,
    phase5a_summary: Optional[Dict[str, Any]] = None,
    operation_backend_binary: Optional[str] = None,
    mlir_opt_binary: Optional[str] = None,
) -> Dict[str, Any]:
    """Build and, if possible, execute the no-op roundtrip/verifier gate.

    Phase 5B is still not a mutation phase.  It follows the official MLIR-style
    discipline that a backend must first prove it can parse, emit and verify IR
    without changing semantics before it is allowed to perform transformations.
    """
    original_result = _run_phase5b_for_one_ir(
        tag="original",
        ir_text=original_ir_text,
        out=out,
        operation_backend_binary=operation_backend_binary,
        mlir_opt_binary=mlir_opt_binary,
    )
    optimized_result = _run_phase5b_for_one_ir(
        tag="optimized",
        ir_text=optimized_ir_text,
        out=out,
        operation_backend_binary=operation_backend_binary,
        mlir_opt_binary=mlir_opt_binary,
    )

    def passed_one(res: Dict[str, Any]) -> bool:
        return bool(
            res.get("backend_available")
            and (res.get("roundtrip") or {}).get("ok")
            and (res.get("roundtrip") or {}).get("output_exists")
            and (res.get("verify_only") or {}).get("ok")
        )

    blockers: List[str] = []
    if not _which(operation_backend_binary):
        blockers.append("operation_backend_not_connected")
    if not passed_one(original_result):
        blockers.append("original_ir_roundtrip_or_verify_not_passed")
    if not passed_one(optimized_result):
        blockers.append("optimized_ir_roundtrip_or_verify_not_passed")

    status = "passed_noop_roundtrip_and_verify_gate" if not blockers else "pending_or_failed_noop_roundtrip_and_verify_gate"
    return {
        "schema_version": "hivm_phase5b_roundtrip_verifier_gate_v1",
        "producer": "strategy_search_demo_v3.3.2_phase5b_roundtrip_verifier_gate",
        "phase": "Phase-5B",
        "phase_goal": "Prove the future Operation backend can parse, no-op roundtrip and verify original/optimized IR before any production mutation.",
        "status": status,
        "passed_noop_roundtrip_and_verify_gate": not blockers,
        "production_mutation_allowed": False,
        "reason_production_mutation_locked": "Phase-5B only validates no-op backend stability. Even if this gate passes, mutation still requires operation-level dry-run, dominance/region-motion proof and DES/trace/msprof validation.",
        "official_docs_discipline": {
            "no_text_region_motion": True,
            "no_mutation_in_phase5b": True,
            "operation_backend_required": True,
            "verifier_required_before_mutation": True,
            "summary": "A transformation backend must first demonstrate stable parse/emit/verify behavior. Text-level movement remains forbidden for region/loop transformations.",
        },
        "phase5a_context": phase5a_summary or {},
        "original": original_result,
        "optimized": optimized_result,
        "blockers": blockers,
        "next_actions": [
            "Connect a real HivmOpsEditor/MLIR Operation backend if this report is pending.",
            "Make --roundtrip produce an IR that can be parsed and verified again.",
            "Only after original and optimized no-op roundtrip/verify pass should Phase-5C attempt operation-level dry-run on Q-load hoist candidates.",
        ],
    }


def build_phase5b_backend_execution_plan(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": "hivm_phase5b_backend_execution_plan_v1",
        "producer": report.get("producer"),
        "phase": "Phase-5B",
        "status": report.get("status"),
        "commands": {
            "original": (report.get("original") or {}).get("planned_commands", {}),
            "optimized": (report.get("optimized") or {}).get("planned_commands", {}),
        },
        "required_success_criteria": [
            "operation backend binary exists",
            "--roundtrip returns 0 for original and optimized IR",
            "roundtrip output files exist",
            "--verify-only returns 0 for original and optimized roundtrip IR",
            "backend reports are machine-readable JSON where supported",
        ],
        "note": "This plan is intentionally no-op. It is the last gate before operation-level dry-run/mutation attempts.",
    }


def emit_phase5b_outputs(
    *,
    out: Path,
    original_ir_text: str,
    optimized_ir_text: str,
    operation_backend_binary: Optional[str] = None,
    mlir_opt_binary: Optional[str] = None,
) -> Dict[str, Any]:
    phase5a_summary = _safe_load_json_file(str(out / "phase5a_analysis_summary.json")) or {}
    report = build_phase5b_roundtrip_verifier_gate_report(
        out=out,
        original_ir_text=original_ir_text,
        optimized_ir_text=optimized_ir_text,
        phase5a_summary=phase5a_summary,
        operation_backend_binary=operation_backend_binary,
        mlir_opt_binary=mlir_opt_binary,
    )
    plan = build_phase5b_backend_execution_plan(report)
    summary = {
        "schema_version": "hivm_phase5b_analysis_summary_v1",
        "producer": report.get("producer"),
        "phase": "Phase-5B",
        "status": report.get("status"),
        "passed_noop_roundtrip_and_verify_gate": report.get("passed_noop_roundtrip_and_verify_gate", False),
        "blocker_count": len(report.get("blockers") or []),
        "blockers": report.get("blockers") or [],
        "production_mutation_allowed": False,
        "leadership_summary": "Phase 5B checks whether a future Operation-level backend can do a no-op read/write/verify loop. It does not perform real optimization yet; it is the safety gate before any operation-level mutation.",
    }
    _write_json(out / "phase5b_roundtrip_verifier_gate_report.json", report)
    _write_json(out / "phase5b_backend_execution_plan.json", plan)
    _write_json(out / "phase5b_analysis_summary.json", summary)
    return summary

# ---------------------------------------------------------------------------
# Phase-5C: Operation-level dry-run execution gate
# ---------------------------------------------------------------------------

def _extract_phase4d_actions(plan: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(plan, dict):
        return []
    return [a for a in (plan.get("actions") or []) if isinstance(a, dict)]


def _run_phase5c_backend_dry_run(
    *,
    out: Path,
    optimized_ir_text: str,
    operation_backend_binary: Optional[str] = None,
    dry_run_plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute the backend dry-run command, if a backend is available.

    Phase 5C is deliberately dry-run only.  The backend is asked to locate the
    candidate operation(s) and target insertion point(s) described by the Phase-4D
    plan, then return evidence.  It must not mutate IR or emit optimized output.
    """
    backend = _which(operation_backend_binary)
    input_path = out / "phase5c_optimized_input.hivm.mlir"
    plan_path = out / "phase5c_operation_dry_run_input_plan.json"
    backend_report_path = out / "phase5c_operation_level_dry_run_backend_report.json"
    input_path.write_text(optimized_ir_text or "", encoding="utf-8")
    _write_json(plan_path, dry_run_plan or {})
    planned_command = (
        _backend_arg_prefix(backend) + [
            "--dry-run",
            "--input",
            str(input_path),
            "--edit-script",
            str(plan_path),
            "--report",
            str(backend_report_path),
        ]
    )
    if not backend:
        return {
            "backend_available": False,
            "ran": False,
            "ok": False,
            "status": "pending_operation_backend_not_configured",
            "input_path": str(input_path),
            "plan_path": str(plan_path),
            "planned_command": planned_command,
            "report_path": str(backend_report_path),
            "report_exists": False,
            "report_json": None,
        }
    run = _run_backend_command(planned_command)
    return {
        "backend_available": True,
        **run,
        "status": "operation_dry_run_executed" if run.get("ran") else "operation_dry_run_not_executed",
        "input_path": str(input_path),
        "plan_path": str(plan_path),
        "planned_command": planned_command,
        "report_path": str(backend_report_path),
        "report_exists": backend_report_path.exists(),
        "report_json": _load_json_optional(backend_report_path),
    }


def _summarize_backend_dry_run_evidence(backend_result: Dict[str, Any], actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    report = backend_result.get("report_json") if isinstance(backend_result, dict) else None
    report = report if isinstance(report, dict) else {}
    backend_is_real = bool(report.get("is_real_mlir_backend"))
    raw_results = report.get("actions") or report.get("dry_run_actions") or report.get("results") or []
    raw_results = raw_results if isinstance(raw_results, list) else []
    located_count = 0
    dominance_passed_count = 0
    region_motion_passed_count = 0
    blockers: List[str] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        if item.get("located") or item.get("candidate_located") or item.get("operation_found"):
            located_count += 1
        if item.get("dominance_ok") or item.get("dominance_precheck_passed"):
            dominance_passed_count += 1
        if item.get("region_motion_ok") or item.get("region_motion_precheck_passed"):
            region_motion_passed_count += 1
        for b in item.get("blockers") or []:
            if isinstance(b, str):
                blockers.append(b)
    if backend_result.get("ran") and backend_result.get("ok") and not raw_results:
        # Some fixture/backends only confirm command execution.  Treat that as
        # interface readiness, not as candidate proof.
        blockers.append("backend_dry_run_report_has_no_per_action_operation_evidence")
    if not backend_is_real:
        blockers.append("dry_run_backend_is_not_real_mlir_or_hivmopseditor_backend")
    return {
        "backend_is_real_mlir_backend": backend_is_real,
        "input_action_count": len(actions),
        "backend_action_result_count": len(raw_results),
        "candidate_located_count": located_count,
        "dominance_passed_count": dominance_passed_count,
        "region_motion_passed_count": region_motion_passed_count,
        "blockers": sorted(set(blockers)),
        "raw_backend_status": report.get("status"),
    }


def build_phase5c_operation_dry_run_execution_report(
    *,
    out: Path,
    optimized_ir_text: str,
    phase5b_summary: Optional[Dict[str, Any]] = None,
    operation_backend_binary: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the Phase-5C Operation-level dry-run execution gate.

    This stage asks the future Operation backend to consume the Phase-4D plan and
    locate candidate operations without mutating IR.  It follows official MLIR
    rewrite discipline: no production mutation is allowed until dry-run evidence,
    dominance/region checks, verifier, DES/trace and later msprof validation pass.
    """
    phase5b_summary = phase5b_summary or {}
    plan = _safe_load_json_file(str(out / "phase4d_hivmopseditor_dry_run_plan.json")) or {}
    actions = _extract_phase4d_actions(plan)
    backend_result = _run_phase5c_backend_dry_run(
        out=out,
        optimized_ir_text=optimized_ir_text,
        operation_backend_binary=operation_backend_binary,
        dry_run_plan=plan,
    )
    evidence = _summarize_backend_dry_run_evidence(backend_result, actions)

    blockers: List[str] = []
    if not actions:
        blockers.append("phase4d_dry_run_plan_has_no_actions")
    if not bool(phase5b_summary.get("passed_noop_roundtrip_and_verify_gate")):
        blockers.append("phase5b_noop_roundtrip_verify_gate_not_passed")
    if not backend_result.get("backend_available"):
        blockers.append("operation_backend_not_connected")
    if not backend_result.get("ok"):
        blockers.append("operation_backend_dry_run_command_failed_or_not_run")
    if not backend_result.get("report_exists"):
        blockers.append("operation_backend_dry_run_report_missing")
    blockers.extend(evidence.get("blockers") or [])
    if evidence.get("candidate_located_count", 0) < len(actions):
        blockers.append("not_all_candidates_located_by_operation_backend")
    if evidence.get("dominance_passed_count", 0) < len(actions):
        blockers.append("dominance_precheck_not_passed_for_all_candidates")
    if evidence.get("region_motion_passed_count", 0) < len(actions):
        blockers.append("region_motion_precheck_not_passed_for_all_candidates")

    passed_dry_run_gate = not blockers
    return {
        "schema_version": "hivm_phase5c_operation_level_dry_run_execution_v1",
        "producer": "strategy_search_demo_v3.3.2_phase5c_operation_dry_run_execution",
        "phase": "Phase-5C",
        "phase_goal": "Execute Operation-level dry-run on Phase-4D candidate plan without mutating HIVM IR.",
        "status": "passed_operation_level_dry_run_gate" if passed_dry_run_gate else "pending_or_failed_operation_level_dry_run_gate",
        "passed_operation_level_dry_run_gate": passed_dry_run_gate,
        "production_mutation_allowed": False,
        "reason_production_mutation_locked": "Phase-5C is dry-run only. Real mutation still requires a real MLIR/HivmOpsEditor backend, verified dominance/region-motion proof, verifier, DES/trace and msprof validation.",
        "official_docs_discipline": {
            "no_text_region_motion": True,
            "no_production_mutation_in_phase5c": True,
            "backend_must_locate_operations_not_lines": True,
            "dominance_and_region_motion_required_before_move": True,
            "summary": "Candidate movement must be proven at Operation/Region/Block level; dry-run evidence is separate from mutation.",
        },
        "phase5b_context": phase5b_summary,
        "input_plan": {
            "plan_path": str(out / "phase4d_hivmopseditor_dry_run_plan.json"),
            "action_count": len(actions),
            "actions": actions,
        },
        "backend_dry_run": backend_result,
        "evidence_summary": evidence,
        "blockers": sorted(set(blockers)),
        "next_actions": [
            "Connect a real HivmOpsEditor/MLIR Operation backend if the current backend is only a fixture.",
            "Make backend dry-run return per-action candidate location, dominance and region-motion evidence.",
            "Only after Phase-5C passes should Phase-5D attempt guarded Operation-level Q-load hoist mutation on a restricted sample.",
        ],
    }


def build_phase5c_dominance_precheck_report(report: Dict[str, Any]) -> Dict[str, Any]:
    evidence = report.get("evidence_summary") or {}
    action_count = (report.get("input_plan") or {}).get("action_count", 0)
    return {
        "schema_version": "hivm_phase5c_dominance_precheck_v1",
        "producer": report.get("producer"),
        "phase": "Phase-5C",
        "action_count": action_count,
        "dominance_passed_count": evidence.get("dominance_passed_count", 0),
        "passed": bool(action_count and evidence.get("dominance_passed_count", 0) >= action_count and evidence.get("backend_is_real_mlir_backend")),
        "reason_if_not_passed": "Dominance precheck requires real Operation-level backend evidence for every action.",
        "production_mutation_allowed": False,
    }


def build_phase5c_region_motion_precheck_report(report: Dict[str, Any]) -> Dict[str, Any]:
    evidence = report.get("evidence_summary") or {}
    action_count = (report.get("input_plan") or {}).get("action_count", 0)
    return {
        "schema_version": "hivm_phase5c_region_motion_precheck_v1",
        "producer": report.get("producer"),
        "phase": "Phase-5C",
        "action_count": action_count,
        "region_motion_passed_count": evidence.get("region_motion_passed_count", 0),
        "passed": bool(action_count and evidence.get("region_motion_passed_count", 0) >= action_count and evidence.get("backend_is_real_mlir_backend")),
        "reason_if_not_passed": "Region-motion precheck requires real Operation/Block/Region ownership evidence for every action.",
        "production_mutation_allowed": False,
    }


def emit_phase5c_outputs(
    *,
    out: Path,
    optimized_ir_text: str,
    operation_backend_binary: Optional[str] = None,
) -> Dict[str, Any]:
    phase5b_summary = _safe_load_json_file(str(out / "phase5b_analysis_summary.json")) or {}
    report = build_phase5c_operation_dry_run_execution_report(
        out=out,
        optimized_ir_text=optimized_ir_text,
        phase5b_summary=phase5b_summary,
        operation_backend_binary=operation_backend_binary,
    )
    dominance = build_phase5c_dominance_precheck_report(report)
    region = build_phase5c_region_motion_precheck_report(report)
    summary = {
        "schema_version": "hivm_phase5c_analysis_summary_v1",
        "producer": report.get("producer"),
        "phase": "Phase-5C",
        "status": report.get("status"),
        "passed_operation_level_dry_run_gate": report.get("passed_operation_level_dry_run_gate", False),
        "candidate_action_count": (report.get("input_plan") or {}).get("action_count", 0),
        "candidate_located_count": (report.get("evidence_summary") or {}).get("candidate_located_count", 0),
        "blocker_count": len(report.get("blockers") or []),
        "blockers": report.get("blockers") or [],
        "production_mutation_allowed": False,
        "leadership_summary": "Phase 5C asks the future Operation backend to locate candidate operations and check dominance/region-motion in dry-run mode. It still performs no real IR mutation.",
    }
    _write_json(out / "phase5c_operation_level_dry_run_report.json", report)
    _write_json(out / "phase5c_dominance_precheck_report.json", dominance)
    _write_json(out / "phase5c_region_motion_precheck_report.json", region)
    _write_json(out / "phase5c_analysis_summary.json", summary)
    return summary


# ---------------------------------------------------------------------------
# Phase-5D: Guarded Operation-level mutation execution gate
# ---------------------------------------------------------------------------

def _run_phase5d_backend_mutation(
    *,
    out: Path,
    optimized_ir_text: str,
    operation_backend_binary: Optional[str] = None,
    mutation_plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ask a future Operation backend to perform a guarded mutation prototype.

    Phase 5D is the first stage that defines the *execution contract* for a real
    mutation backend.  The project itself still does not perform text-level
    region motion.  If the supplied backend is a fixture or cannot prove it is a
    real MLIR/HivmOpsEditor backend, the report must keep production mutation
    locked.
    """
    backend = _which(operation_backend_binary)
    input_path = out / "phase5d_optimized_input.hivm.mlir"
    plan_path = out / "phase5d_q_load_hoist_mutation_input_plan.json"
    output_path = out / "optimized.phase5d.q_load_hoist_candidate.hivm.mlir"
    backend_report_path = out / "phase5d_q_load_hoist_backend_mutation_report.json"
    input_path.write_text(optimized_ir_text or "", encoding="utf-8")
    _write_json(plan_path, mutation_plan or {})
    planned_command = (
        _backend_arg_prefix(backend) + [
            "--mutate",
            "--mutation-kind", "q_load_hoist",
            "--input", str(input_path),
            "--edit-script", str(plan_path),
            "--output", str(output_path),
            "--report", str(backend_report_path),
        ]
    )
    if not backend:
        return {
            "backend_available": False,
            "ran": False,
            "ok": False,
            "status": "pending_operation_backend_not_configured",
            "planned_command": planned_command,
            "input_path": str(input_path),
            "plan_path": str(plan_path),
            "output_path": str(output_path),
            "report_path": str(backend_report_path),
            "output_exists": False,
            "report_exists": False,
            "report_json": None,
        }
    run = _run_backend_command(planned_command, timeout=30)
    return {
        "backend_available": True,
        **run,
        "status": "mutation_backend_command_ran" if run.get("ran") else "mutation_backend_command_not_executed",
        "input_path": str(input_path),
        "plan_path": str(plan_path),
        "output_path": str(output_path),
        "report_path": str(backend_report_path),
        "output_exists": output_path.exists(),
        "output_sha256": _sha256_file(output_path),
        "report_exists": backend_report_path.exists(),
        "report_json": _load_json_optional(backend_report_path),
    }


def _summarize_phase5d_mutation_evidence(result: Dict[str, Any], actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    report = result.get("report_json") if isinstance(result, dict) else None
    report = report if isinstance(report, dict) else {}
    backend_is_real = bool(report.get("is_real_mlir_backend"))
    mutation_performed = bool(report.get("mutation_performed") or report.get("mutated"))
    verifier_passed = bool(report.get("verifier_passed") or report.get("mlir_verifier_passed"))
    dominance_passed = bool(report.get("dominance_passed") or report.get("dominance_proof_passed"))
    region_motion_passed = bool(report.get("region_motion_passed") or report.get("region_motion_proof_passed"))
    des_trace_after_passed = bool(report.get("des_trace_after_passed") or report.get("des_trace_validation_passed"))
    blockers: List[str] = []
    for b in report.get("blockers") or []:
        if isinstance(b, str):
            blockers.append(b)
    if not backend_is_real:
        blockers.append("mutation_backend_is_not_real_mlir_or_hivmopseditor_backend")
    if not dominance_passed:
        blockers.append("dominance_proof_not_passed")
    if not region_motion_passed:
        blockers.append("region_motion_proof_not_passed")
    if not verifier_passed:
        blockers.append("mlir_verifier_after_mutation_not_passed")
    if not des_trace_after_passed:
        blockers.append("des_trace_after_mutation_not_passed")
    if not mutation_performed:
        blockers.append("backend_did_not_perform_mutation")
    if len(actions) == 0:
        blockers.append("no_mutation_actions_available")
    return {
        "backend_is_real_mlir_backend": backend_is_real,
        "input_action_count": len(actions),
        "mutation_performed": mutation_performed,
        "dominance_passed": dominance_passed,
        "region_motion_passed": region_motion_passed,
        "verifier_passed": verifier_passed,
        "des_trace_after_passed": des_trace_after_passed,
        "blockers": sorted(set(blockers)),
        "raw_backend_status": report.get("status"),
        "raw_backend_summary": report.get("summary") or report.get("message"),
    }


def build_phase5d_guarded_mutation_execution_report(
    *,
    out: Path,
    optimized_ir_text: str,
    phase5b_summary: Optional[Dict[str, Any]] = None,
    phase5c_summary: Optional[Dict[str, Any]] = None,
    operation_backend_binary: Optional[str] = None,
) -> Dict[str, Any]:
    """Build Phase-5D guarded mutation execution gate for Q-load hoist.

    This stage defines and optionally invokes a future Operation-level mutation
    backend.  It is intentionally strict: a mutation only becomes production-
    allowed if the backend proves it is a real MLIR/HivmOpsEditor backend, the
    Phase-5B/5C gates passed, dominance/region-motion/verifier/DES-trace checks
    pass, and an output IR is emitted.
    """
    phase5b_summary = phase5b_summary or {}
    phase5c_summary = phase5c_summary or {}
    plan = _safe_load_json_file(str(out / "phase4d_hivmopseditor_dry_run_plan.json")) or {}
    actions = _extract_phase4d_actions(plan)
    mutation_request = {
        "schema_version": "hivm_phase5d_q_load_hoist_mutation_request_v1",
        "producer": "strategy_search_demo_v3.3.2_phase5d_guarded_mutation_execution",
        "mutation_kind": "q_load_hoist",
        "source_plan": str(out / "phase4d_hivmopseditor_dry_run_plan.json"),
        "actions": actions,
        "required_preconditions": {
            "phase5b_noop_roundtrip_and_verify_gate": True,
            "phase5c_operation_level_dry_run_gate": True,
            "real_mlir_or_hivmopseditor_backend": True,
            "dominance_and_region_motion_proof": True,
            "mlir_verifier_after_mutation": True,
            "des_trace_after_mutation": True,
            "no_python_text_region_motion": True,
        },
        "mutation_policy": "Backend may mutate only through Operation-level APIs. Text-level loop/region motion is forbidden.",
    }
    backend_result = _run_phase5d_backend_mutation(
        out=out,
        optimized_ir_text=optimized_ir_text,
        operation_backend_binary=operation_backend_binary,
        mutation_plan=mutation_request,
    )
    evidence = _summarize_phase5d_mutation_evidence(backend_result, actions)

    blockers: List[str] = []
    if not bool(phase5b_summary.get("passed_noop_roundtrip_and_verify_gate")):
        blockers.append("phase5b_noop_roundtrip_verify_gate_not_passed")
    if not bool(phase5c_summary.get("passed_operation_level_dry_run_gate")):
        blockers.append("phase5c_operation_dry_run_gate_not_passed")
    if not backend_result.get("backend_available"):
        blockers.append("operation_backend_not_connected")
    if not backend_result.get("ok"):
        blockers.append("operation_backend_mutation_command_failed_or_not_run")
    if not backend_result.get("report_exists"):
        blockers.append("operation_backend_mutation_report_missing")
    if not backend_result.get("output_exists"):
        blockers.append("operation_backend_mutation_output_missing")
    blockers.extend(evidence.get("blockers") or [])

    production_allowed = not blockers
    return {
        "schema_version": "hivm_phase5d_guarded_q_load_hoist_mutation_gate_v1",
        "producer": "strategy_search_demo_v3.3.2_phase5d_guarded_mutation_execution",
        "phase": "Phase-5D",
        "phase_goal": "Define and optionally execute a guarded Operation-level Q-load hoist mutation contract without allowing fake/text-level mutation to pass as production.",
        "status": "passed_guarded_mutation_gate" if production_allowed else "pending_or_failed_guarded_mutation_gate",
        "production_mutation_allowed": production_allowed,
        "mutation_kind": "q_load_hoist",
        "mutation_request": mutation_request,
        "backend_mutation": backend_result,
        "evidence_summary": evidence,
        "blockers": sorted(set(blockers)),
        "official_docs_discipline": {
            "no_python_text_region_motion": True,
            "mutation_must_be_operation_level": True,
            "dominance_region_verifier_required": True,
            "des_trace_and_later_msprof_required": True,
        },
        "reason_if_locked": None if production_allowed else "The gate is intentionally strict. A fake backend or standalone bridge cannot pass production mutation; a real MLIR/HivmOpsEditor backend must prove Operation-level mutation correctness first.",
        "next_actions": [
            "Connect a real HivmOpsEditor/MLIR Operation-level backend that supports --mutate for q_load_hoist.",
            "Make the backend emit dominance, region-motion, verifier and DES/trace evidence in its mutation report.",
            "Only after this gate passes on a restricted sample should optimized.phase5d.q_load_hoisted.hivm.mlir be treated as a real compiler rewrite result.",
        ],
    }


def build_phase5d_mutation_safety_report(report: Dict[str, Any]) -> Dict[str, Any]:
    evidence = report.get("evidence_summary") or {}
    blockers = report.get("blockers") or []
    return {
        "schema_version": "hivm_phase5d_mutation_safety_report_v1",
        "producer": report.get("producer"),
        "phase": "Phase-5D",
        "mutation_kind": report.get("mutation_kind"),
        "production_mutation_allowed": bool(report.get("production_mutation_allowed")),
        "backend_is_real_mlir_backend": bool(evidence.get("backend_is_real_mlir_backend")),
        "mutation_performed": bool(evidence.get("mutation_performed")),
        "required_evidence": {
            "phase5b_noop_roundtrip_verify_gate": "must pass before mutation",
            "phase5c_operation_dry_run_gate": "must pass before mutation",
            "dominance_proof": evidence.get("dominance_passed", False),
            "region_motion_proof": evidence.get("region_motion_passed", False),
            "mlir_verifier_after_mutation": evidence.get("verifier_passed", False),
            "des_trace_after_mutation": evidence.get("des_trace_after_passed", False),
        },
        "blockers": blockers,
        "safety_conclusion": "safe_to_treat_as_real_mutation" if report.get("production_mutation_allowed") else "not_safe_to_treat_as_real_mutation",
    }


def emit_phase5d_outputs(
    *,
    out: Path,
    optimized_ir_text: str,
    operation_backend_binary: Optional[str] = None,
) -> Dict[str, Any]:
    phase5b_summary = _safe_load_json_file(str(out / "phase5b_analysis_summary.json")) or {}
    phase5c_summary = _safe_load_json_file(str(out / "phase5c_analysis_summary.json")) or {}
    report = build_phase5d_guarded_mutation_execution_report(
        out=out,
        optimized_ir_text=optimized_ir_text,
        phase5b_summary=phase5b_summary,
        phase5c_summary=phase5c_summary,
        operation_backend_binary=operation_backend_binary,
    )
    safety = build_phase5d_mutation_safety_report(report)
    summary = {
        "schema_version": "hivm_phase5d_analysis_summary_v1",
        "producer": report.get("producer"),
        "phase": "Phase-5D",
        "status": report.get("status"),
        "mutation_kind": report.get("mutation_kind"),
        "production_mutation_allowed": bool(report.get("production_mutation_allowed")),
        "mutation_performed": bool((report.get("evidence_summary") or {}).get("mutation_performed")),
        "blocker_count": len(report.get("blockers") or []),
        "blockers": report.get("blockers") or [],
        "leadership_summary": "Phase 5D defines and executes the guarded mutation gate for Q-load hoist. A fake or non-MLIR backend is rejected, so no result is marketed as real compiler mutation until Operation-level proof and verifier/DES evidence pass.",
    }
    _write_json(out / "phase5d_guarded_mutation_execution_report.json", report)
    _write_json(out / "phase5d_mutation_safety_report.json", safety)
    _write_json(out / "phase5d_analysis_summary.json", summary)
    return summary



# ---------------------------------------------------------------------------
# Phase-5E: Limited GM round-trip deletion guarded gate
# ---------------------------------------------------------------------------

def _extract_phase3c_gm_deletion_candidates(out: Path) -> List[Dict[str, Any]]:
    """Extract Phase-3C GM deletion decisions as Phase-5E backend actions."""
    decision = _safe_load_json_file(str(out / "gm_roundtrip_deletion_decision.json")) or {}
    actions: List[Dict[str, Any]] = []
    for idx, d in enumerate(decision.get("decisions") or []):
        if not isinstance(d, dict):
            continue
        gates = d.get("gates") if isinstance(d.get("gates"), dict) else {}
        actions.append({
            "action_id": f"gm_roundtrip_delete_candidate_{idx}",
            "candidate_id": f"gm_{d.get('store_op_id')}_to_{d.get('load_op_id')}",
            "edit_type": "remove_redundant_gm_roundtrip",
            "gm_var": d.get("gm_var"),
            "store_op_id": d.get("store_op_id"),
            "store_line": d.get("store_line"),
            "load_op_id": d.get("load_op_id"),
            "load_line": d.get("load_line"),
            "phase3c_delete_permission": bool(d.get("delete_permission")),
            "phase3c_decision": d.get("decision"),
            "phase3c_reason": d.get("reason"),
            "phase3c_gates": gates,
            "required_operation_backend_proofs": {
                "same_base_static_offset_slice": True,
                "memoryssa_unique_reaching_def": True,
                "no_intervening_unknown_gm_side_effect": True,
                "not_observable_output_or_boundary": True,
                "mlir_verifier_after_deletion": True,
                "des_trace_after_deletion": True,
            },
        })
    return actions


def _run_phase5e_backend_gm_deletion_mutation(
    *,
    out: Path,
    optimized_ir_text: str,
    operation_backend_binary: Optional[str] = None,
    mutation_plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ask a future Operation backend to attempt guarded GM round-trip deletion.

    The project itself never performs text-level GM deletion.  A real backend must
    prove alias, memory-effect and observable-boundary conditions and must emit a
    verifier/DES-trace-backed report before any deletion is accepted.
    """
    backend = _which(operation_backend_binary)
    input_path = out / "phase5e_optimized_input.hivm.mlir"
    plan_path = out / "phase5e_gm_roundtrip_deletion_input_plan.json"
    output_path = out / "optimized.phase5e.gm_roundtrip_removed_candidate.hivm.mlir"
    backend_report_path = out / "phase5e_gm_roundtrip_deletion_backend_report.json"
    input_path.write_text(optimized_ir_text or "", encoding="utf-8")
    _write_json(plan_path, mutation_plan or {})
    planned_command = (
        _backend_arg_prefix(backend) + [
            "--mutate",
            "--mutation-kind", "gm_roundtrip_deletion",
            "--input", str(input_path),
            "--edit-script", str(plan_path),
            "--output", str(output_path),
            "--report", str(backend_report_path),
        ]
    )
    if not backend or not ((mutation_plan or {}).get("actions") or []):
        return {
            "backend_available": bool(backend),
            "ran": False,
            "ok": False,
            "status": "pending_operation_backend_or_no_gm_deletion_actions",
            "planned_command": planned_command,
            "input_path": str(input_path),
            "plan_path": str(plan_path),
            "output_path": str(output_path),
            "report_path": str(backend_report_path),
            "output_exists": False,
            "report_exists": False,
            "report_json": None,
        }
    run = _run_backend_command(planned_command, timeout=30)
    return {
        "backend_available": True,
        **run,
        "status": "gm_deletion_backend_command_ran" if run.get("ran") else "gm_deletion_backend_command_not_executed",
        "input_path": str(input_path),
        "plan_path": str(plan_path),
        "output_path": str(output_path),
        "report_path": str(backend_report_path),
        "output_exists": output_path.exists(),
        "output_sha256": _sha256_file(output_path),
        "report_exists": backend_report_path.exists(),
        "report_json": _load_json_optional(backend_report_path),
    }


def _summarize_phase5e_gm_deletion_evidence(result: Dict[str, Any], actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    report = result.get("report_json") if isinstance(result, dict) else None
    report = report if isinstance(report, dict) else {}
    backend_is_real = bool(report.get("is_real_mlir_backend"))
    mutation_performed = bool(report.get("mutation_performed") or report.get("mutated"))
    verifier_passed = bool(report.get("verifier_passed") or report.get("mlir_verifier_passed"))
    alias_passed = bool(report.get("alias_proof_passed") or report.get("same_base_static_offset_slice_passed"))
    memoryssa_passed = bool(report.get("memoryssa_passed") or report.get("memory_effect_proof_passed"))
    observable_passed = bool(report.get("observable_boundary_passed") or report.get("not_observable_boundary_passed"))
    des_trace_after_passed = bool(report.get("des_trace_after_passed") or report.get("des_trace_validation_passed"))
    deleted_pair_count = int(report.get("deleted_pair_count") or report.get("deleted_count") or 0)
    blockers: List[str] = []
    for b in report.get("blockers") or []:
        if isinstance(b, str):
            blockers.append(b)
    if not actions:
        blockers.append("no_gm_roundtrip_deletion_actions_available")
    else:
        if not backend_is_real:
            blockers.append("gm_deletion_backend_is_not_real_mlir_or_hivmopseditor_backend")
        if not alias_passed:
            blockers.append("same_base_static_offset_slice_alias_proof_not_passed")
        if not memoryssa_passed:
            blockers.append("operation_level_memoryssa_or_memory_effect_proof_not_passed")
        if not observable_passed:
            blockers.append("observable_boundary_proof_not_passed")
        if not verifier_passed:
            blockers.append("mlir_verifier_after_gm_deletion_not_passed")
        if not des_trace_after_passed:
            blockers.append("des_trace_after_gm_deletion_not_passed")
        if not mutation_performed or deleted_pair_count <= 0:
            blockers.append("backend_did_not_delete_any_gm_roundtrip_pair")
    return {
        "backend_is_real_mlir_backend": backend_is_real,
        "input_action_count": len(actions),
        "mutation_performed": mutation_performed,
        "deleted_pair_count": deleted_pair_count,
        "alias_passed": alias_passed,
        "memoryssa_passed": memoryssa_passed,
        "observable_boundary_passed": observable_passed,
        "verifier_passed": verifier_passed,
        "des_trace_after_passed": des_trace_after_passed,
        "blockers": sorted(set(blockers)),
        "raw_backend_status": report.get("status"),
        "raw_backend_summary": report.get("summary") or report.get("message"),
    }


def build_phase5e_limited_gm_roundtrip_deletion_report(
    *,
    out: Path,
    optimized_ir_text: str,
    phase5b_summary: Optional[Dict[str, Any]] = None,
    operation_backend_binary: Optional[str] = None,
) -> Dict[str, Any]:
    """Build Phase-5E limited GM round-trip deletion guarded gate.

    This gate is intentionally stricter than Q-load hoist because deleting GM
    traffic can remove externally visible memory effects.  The project only
    prepares candidate actions and validates backend evidence; it never deletes
    GM stores/loads by text replacement.
    """
    phase5b_summary = phase5b_summary or {}
    actions_all = _extract_phase3c_gm_deletion_candidates(out)
    # Only Phase-3C-allowed candidates are sent as executable mutation actions.
    # Deferred candidates are reported but not dispatched to the mutation backend.
    executable_actions = [a for a in actions_all if a.get("phase3c_delete_permission")]
    mutation_request = {
        "schema_version": "hivm_phase5e_gm_roundtrip_deletion_mutation_request_v1",
        "producer": "strategy_search_demo_v3.3.2_phase5e_limited_gm_roundtrip_deletion_gate",
        "mutation_kind": "gm_roundtrip_deletion",
        "source_decision_report": str(out / "gm_roundtrip_deletion_decision.json"),
        "candidate_action_count_total": len(actions_all),
        "executable_action_count": len(executable_actions),
        "actions": executable_actions,
        "deferred_actions": [a for a in actions_all if not a.get("phase3c_delete_permission")],
        "required_preconditions": {
            "phase5b_noop_roundtrip_and_verify_gate": True,
            "real_mlir_or_hivmopseditor_backend": True,
            "same_base_static_offset_slice_proof": True,
            "memoryssa_or_memory_effect_proof": True,
            "not_observable_boundary_proof": True,
            "mlir_verifier_after_deletion": True,
            "des_trace_after_deletion": True,
            "no_python_text_gm_deletion": True,
        },
        "mutation_policy": "Delete GM traffic only through a real Operation-level backend after alias, memory-effect and observable-boundary proof. Text-level deletion is forbidden.",
    }
    backend_result = _run_phase5e_backend_gm_deletion_mutation(
        out=out,
        optimized_ir_text=optimized_ir_text,
        operation_backend_binary=operation_backend_binary,
        mutation_plan=mutation_request,
    )
    evidence = _summarize_phase5e_gm_deletion_evidence(backend_result, executable_actions)
    blockers: List[str] = []
    if not bool(phase5b_summary.get("passed_noop_roundtrip_and_verify_gate")):
        blockers.append("phase5b_noop_roundtrip_verify_gate_not_passed")
    if not actions_all:
        blockers.append("no_gm_roundtrip_candidates_from_phase3c")
    if actions_all and not executable_actions:
        blockers.append("all_gm_roundtrip_candidates_deferred_by_phase3c_gate")
    if not backend_result.get("backend_available"):
        blockers.append("operation_backend_not_connected")
    if executable_actions and not backend_result.get("ok"):
        blockers.append("operation_backend_gm_deletion_command_failed_or_not_run")
    if executable_actions and not backend_result.get("report_exists"):
        blockers.append("operation_backend_gm_deletion_report_missing")
    if executable_actions and not backend_result.get("output_exists"):
        blockers.append("operation_backend_gm_deletion_output_missing")
    blockers.extend(evidence.get("blockers") or [])
    production_allowed = not blockers
    return {
        "schema_version": "hivm_phase5e_limited_gm_roundtrip_deletion_gate_v1",
        "producer": "strategy_search_demo_v3.3.2_phase5e_limited_gm_roundtrip_deletion_gate",
        "phase": "Phase-5E",
        "phase_goal": "Prepare and optionally execute a very limited Operation-level GM round-trip deletion gate without allowing text-level memory deletion.",
        "status": "passed_limited_gm_roundtrip_deletion_gate" if production_allowed else "pending_or_failed_limited_gm_roundtrip_deletion_gate",
        "production_mutation_allowed": production_allowed,
        "mutation_kind": "gm_roundtrip_deletion",
        "candidate_count_total": len(actions_all),
        "executable_action_count": len(executable_actions),
        "mutation_request": mutation_request,
        "backend_mutation": backend_result,
        "evidence_summary": evidence,
        "blockers": sorted(set(blockers)),
        "official_docs_discipline": {
            "no_python_text_gm_deletion": True,
            "mutation_must_be_operation_level": True,
            "alias_memory_effect_observable_boundary_required": True,
            "verifier_and_des_trace_required": True,
        },
        "notes": [
            "GM traffic deletion is more dangerous than sync replacement because it can remove externally visible memory effects.",
            "Same textual GM SSA value is not enough; target backend must prove same base/offset/slice and no intervening side effect.",
            "Deferred Phase-3C candidates are not sent to backend mutation execution.",
        ],
    }


def build_phase5e_gm_deletion_safety_report(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": "hivm_phase5e_gm_deletion_safety_report_v1",
        "producer": report.get("producer"),
        "phase": "Phase-5E",
        "mutation_kind": report.get("mutation_kind"),
        "status": report.get("status"),
        "production_mutation_allowed": bool(report.get("production_mutation_allowed")),
        "candidate_count_total": report.get("candidate_count_total"),
        "executable_action_count": report.get("executable_action_count"),
        "safety_requirements": {
            "phase5b_noop_roundtrip_verify_gate": "must pass before deletion",
            "phase3c_gm_deletion_decision_gate": "must allow candidate before backend execution",
            "real_operation_backend": "must prove it is MLIR/HivmOpsEditor-backed",
            "alias_proof": "same base, same static offset/slice/layout",
            "memory_effect_proof": "unique reaching def/use and no unknown GM side effect",
            "observable_boundary_proof": "must not delete output or externally visible GM traffic",
            "verifier_des_trace": "must pass after deletion",
        },
        "blockers": report.get("blockers") or [],
        "leadership_summary": "Phase 5E prepares the first guarded GM deletion gate, but it refuses to delete any GM traffic unless Phase-3C and a real Operation backend prove alias, memory effects, observable boundary, verifier and DES/trace safety.",
    }


def emit_phase5e_outputs(
    *,
    out: Path,
    optimized_ir_text: str,
    operation_backend_binary: Optional[str] = None,
) -> Dict[str, Any]:
    phase5b_summary = _safe_load_json_file(str(out / "phase5b_analysis_summary.json")) or {}
    report = build_phase5e_limited_gm_roundtrip_deletion_report(
        out=out,
        optimized_ir_text=optimized_ir_text,
        phase5b_summary=phase5b_summary,
        operation_backend_binary=operation_backend_binary,
    )
    safety = build_phase5e_gm_deletion_safety_report(report)
    summary = {
        "schema_version": "hivm_phase5e_analysis_summary_v1",
        "producer": report.get("producer"),
        "phase": "Phase-5E",
        "status": report.get("status"),
        "mutation_kind": report.get("mutation_kind"),
        "candidate_count_total": report.get("candidate_count_total"),
        "executable_action_count": report.get("executable_action_count"),
        "production_mutation_allowed": bool(report.get("production_mutation_allowed")),
        "mutation_performed": bool((report.get("evidence_summary") or {}).get("mutation_performed")),
        "deleted_pair_count": int((report.get("evidence_summary") or {}).get("deleted_pair_count") or 0),
        "blocker_count": len(report.get("blockers") or []),
        "blockers": report.get("blockers") or [],
        "leadership_summary": "Phase 5E adds a limited GM round-trip deletion gate. It does not text-delete GM traffic; candidates must first pass Phase-3C and then a real Operation backend must prove alias/memory/observable-boundary/verifier/DES evidence.",
    }
    _write_json(out / "phase5e_limited_gm_roundtrip_deletion_report.json", report)
    _write_json(out / "phase5e_gm_deletion_safety_report.json", safety)
    _write_json(out / "phase5e_analysis_summary.json", summary)
    return summary



def _load_phase_summary(out: Path, filename: str) -> Dict[str, Any]:
    data = _safe_load_json_file(str(out / filename))
    return data if isinstance(data, dict) else {}


def build_phase5f_closure_report(*, out: Path) -> Dict[str, Any]:
    """Close Phase 5 and produce a conservative Phase-6 handoff matrix.

    Phase 5 deliberately does not unlock production mutations unless a real
    MLIR/HivmOpsEditor Operation backend provides no-op roundtrip, verifier,
    dominance/region-motion, post-mutation verifier and DES/trace evidence.
    The closure report makes that state explicit for engineering and leadership.
    """
    phase5a = _load_phase_summary(out, "phase5a_analysis_summary.json")
    phase5b = _load_phase_summary(out, "phase5b_analysis_summary.json")
    phase5c = _load_phase_summary(out, "phase5c_analysis_summary.json")
    phase5d = _load_phase_summary(out, "phase5d_analysis_summary.json")
    phase5e = _load_phase_summary(out, "phase5e_analysis_summary.json")
    phase4e = _load_phase_summary(out, "phase4e_analysis_summary.json")

    production_unlocks = {
        "q_load_hoist": bool(phase5d.get("production_mutation_allowed") and phase5d.get("mutation_performed")),
        "gm_roundtrip_deletion": bool(phase5e.get("production_mutation_allowed") and phase5e.get("mutation_performed")),
        "real_double_buffer": False,
        "full_cv_overlap": False,
        "real_tiling_loop_lowering": False,
    }

    gates = {
        "operation_backend_readiness": phase5a.get("backend_status") or phase5a.get("status"),
        "noop_roundtrip_verify": phase5b.get("status"),
        "operation_dry_run": phase5c.get("status"),
        "q_load_mutation_gate": phase5d.get("status"),
        "gm_deletion_gate": phase5e.get("status"),
    }

    remaining_blockers: List[str] = []
    if not bool(phase5b.get("passed_noop_roundtrip_and_verify_gate")):
        remaining_blockers.append("real_noop_roundtrip_and_verify_gate_not_passed")
    if not bool(phase5c.get("passed_operation_level_dry_run_gate")):
        remaining_blockers.append("real_operation_level_dry_run_gate_not_passed")
    if not production_unlocks["q_load_hoist"]:
        remaining_blockers.append("q_load_hoist_not_production_unlocked")
    if not production_unlocks["gm_roundtrip_deletion"]:
        remaining_blockers.append("gm_roundtrip_deletion_not_production_unlocked")
    remaining_blockers.extend([
        "real_hivmopseditor_or_mlir_operation_backend_still_required",
        "real_mlir_verifier_required_after_any_mutation",
        "real_tritonsim_des_trace_required_after_any_mutation",
        "real_msprof_validation_not_started",
    ])
    remaining_blockers = sorted(set(remaining_blockers))

    phase6_plan = {
        "recommended_phase6_name": "Real Operation Backend Integration and Positive-case Validation",
        "do_next": [
            {
                "stage": "Phase-6A",
                "name": "Connect real HivmOpsEditor / MLIR Operation backend",
                "goal": "Replace fake backend/scanner evidence with real Operation inventory, roundtrip and verifier evidence.",
                "exit_criteria": "operation_inventory_backend.json, roundtrip report and verifier report pass on original and optimized IR.",
            },
            {
                "stage": "Phase-6B",
                "name": "Positive Q-load hoist sample",
                "goal": "Run one restricted Q-load hoist mutation with real dominance, region-motion, verifier and DES/trace evidence.",
                "exit_criteria": "optimized.q_load_hoisted.hivm.mlir is produced by real backend and passes verifier + DES/trace gate.",
            },
            {
                "stage": "Phase-6C",
                "name": "Positive GM deletion sample",
                "goal": "Use a deliberately simple same-base/same-offset GM round-trip fixture to validate the deletion gate end to end.",
                "exit_criteria": "GM deletion is performed only on an allowed candidate and passes verifier + DES/trace gate.",
            },
            {
                "stage": "Phase-6D",
                "name": "msprof readiness pack",
                "goal": "Prepare original/optimized artifacts and measurement protocol for real hardware comparison.",
                "exit_criteria": "A reproducible msprof runbook exists, but real hardware validation may be a separate phase if the compile/run chain is not available.",
            },
        ],
        "explicitly_not_recommended_yet": [
            "real_double_buffer_pingpong",
            "full_cv_pipeline_overlap",
            "real_tiling_loop_lowering",
        ],
        "reason": "These require stronger real-backend mutation evidence and at least one positive verifier/DES/trace validated mutation before changing larger memory scheduling structures.",
    }

    return {
        "schema_version": "hivm_phase5f_closure_report_v1",
        "producer": "strategy_search_demo_v3.3.2_phase5f_closure_phase6_plan",
        "phase": "Phase-5F",
        "phase5_status": "closed_contract_and_gate_phase_no_production_complex_mutation",
        "plain_language_summary": "Phase 5 completed the contracts and gates for a future real Operation-level backend. It can call/assess no-op roundtrip, dry-run, Q-load mutation and GM deletion contracts, but without a real MLIR/HivmOpsEditor backend it correctly keeps complex production mutations locked.",
        "what_is_really_implemented": {
            "strategy_search": True,
            "annotation_and_hint_rewrite": True,
            "small_sync_op_sequence_rewrite": True,
            "q_load_hoist_candidate_and_mutation_contract": True,
            "gm_deletion_candidate_and_mutation_contract": True,
            "fake_backend_rejection": True,
        },
        "what_is_not_yet_implemented": {
            "real_operation_level_backend": False,
            "production_q_load_hoist": production_unlocks["q_load_hoist"],
            "production_gm_roundtrip_deletion": production_unlocks["gm_roundtrip_deletion"],
            "real_double_buffer": False,
            "full_cv_overlap": False,
            "real_tiling_lowering": False,
            "real_msprof_speedup_proof": False,
        },
        "phase5_gate_status": gates,
        "production_mutations_unlocked": production_unlocks,
        "remaining_blocker_count": len(remaining_blockers),
        "remaining_blockers": remaining_blockers,
        "phase4_handoff_context": phase4e,
        "phase5_stage_summaries": {
            "phase5a": phase5a,
            "phase5b": phase5b,
            "phase5c": phase5c,
            "phase5d": phase5d,
            "phase5e": phase5e,
        },
        "phase6_plan": phase6_plan,
        "official_docs_policy": {
            "no_text_level_region_motion": True,
            "no_text_level_gm_deletion": True,
            "operation_level_backend_required_for_complex_mutation": True,
            "verifier_and_des_trace_required_after_mutation": True,
            "fake_backend_never_counts_as_production_evidence": True,
        },
    }


def build_phase5f_leadership_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": "hivm_phase5f_leadership_summary_v1",
        "phase": "Phase-5F",
        "headline": "Phase 5 closes the backend-contract stage: the project is ready to connect a real Operation-level backend, but complex production mutations remain locked.",
        "three_bullets": [
            "The project already searches strategies, writes them back to HIVM, and performs small real sync/barrier op-sequence rewrites.",
            "Phase 5 added backend contracts for no-op roundtrip, verifier, operation dry-run, Q-load hoist mutation and GM deletion mutation, while rejecting fake/non-MLIR evidence.",
            "The next real milestone is connecting HivmOpsEditor/MLIR Operation backend and validating one positive Q-load or GM-deletion example before moving to larger optimizations.",
        ],
        "do_not_overclaim": [
            "Do not claim production Q-load hoist is implemented.",
            "Do not claim GM traffic is really deleted.",
            "Do not claim full vTriton/HivmOpsEditor backend is connected.",
            "Do not claim msprof speedup is proven.",
        ],
        "phase6_focus": (report.get("phase6_plan") or {}).get("recommended_phase6_name"),
        "remaining_blockers": report.get("remaining_blockers") or [],
    }


def emit_phase5f_outputs(*, out: Path) -> Dict[str, Any]:
    report = build_phase5f_closure_report(out=out)
    leadership = build_phase5f_leadership_summary(report)
    summary = {
        "schema_version": "hivm_phase5f_analysis_summary_v1",
        "producer": report.get("producer"),
        "phase": "Phase-5F",
        "phase5_status": report.get("phase5_status"),
        "production_mutations_unlocked": report.get("production_mutations_unlocked"),
        "remaining_blocker_count": report.get("remaining_blocker_count"),
        "remaining_blockers": report.get("remaining_blockers"),
        "phase6_recommended_name": (report.get("phase6_plan") or {}).get("recommended_phase6_name"),
        "leadership_summary": leadership.get("headline"),
    }
    _write_json(out / "phase5_closure_report.json", report)
    _write_json(out / "phase5f_leadership_summary.json", leadership)
    _write_json(out / "phase5f_analysis_summary.json", summary)
    return summary
