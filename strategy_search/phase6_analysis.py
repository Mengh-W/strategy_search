# -*- coding: utf-8 -*-
"""Phase-6A real Operation-backend integration readiness reports.

Phase 6 starts the handoff from contracts/gates to a real MLIR/HivmOpsEditor
Operation-level backend.  This module still does not perform production mutation.
It audits whether the required external artifacts are available and whether a
backend is credible enough to be used for future positive-case validation.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .phase4_analysis import _which, _safe_load_json_file


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


def _probe_json_capabilities(binary: Optional[str]) -> Dict[str, Any]:
    resolved = _which(binary)
    if not resolved:
        return {
            "available": False,
            "requested_binary": binary,
            "resolved_binary": None,
            "supports_print_capabilities": False,
            "reason": "operation_backend_binary_not_configured_or_not_found",
        }
    try:
        proc = subprocess.run(
            _backend_arg_prefix(resolved) + ["--print-capabilities"],
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


def _cap_bool(caps: Optional[Dict[str, Any]], *names: str) -> bool:
    if not isinstance(caps, dict):
        return False
    for name in names:
        val = caps.get(name)
        if isinstance(val, bool) and val:
            return True
        if isinstance(val, dict) and (val.get("supported") or val.get("available") or val.get("enabled")):
            return True
    return False


def _probe_source_root(source_root: Optional[str]) -> Dict[str, Any]:
    if not source_root:
        return {
            "provided": False,
            "path": None,
            "exists": False,
            "looks_like_vtriton_repo": False,
            "reason": "vtriton_source_root_not_provided",
        }
    root = Path(source_root)
    markers = {
        "CMakeLists.txt": (root / "CMakeLists.txt").exists(),
        "tools_dir": (root / "tools").exists(),
        "hivm_crud_cpp": bool(list(root.glob("**/hivm-crud.cpp"))),
        "tritonsim_hivm_mentions": bool(list(root.glob("**/*tritonsim*hivm*"))),
    }
    return {
        "provided": True,
        "path": str(root),
        "exists": root.exists(),
        "markers": markers,
        "looks_like_vtriton_repo": root.exists() and (markers["CMakeLists.txt"] or markers["hivm_crud_cpp"]),
    }


def build_phase6a_real_backend_integration_report(
    *,
    out: Path,
    operation_backend_binary: Optional[str] = None,
    vtriton_source_root: Optional[str] = None,
    tritonsim_hivm: Optional[str] = None,
    mlir_opt_binary: Optional[str] = None,
) -> Dict[str, Any]:
    """Build Phase-6A report.

    This report is intentionally strict: a backend is not accepted as a real
    Operation-level mutation backend unless it explicitly declares real MLIR or
    HivmOpsEditor backing and supports the minimum modes needed by Phase 5.
    """
    backend = _probe_json_capabilities(operation_backend_binary)
    caps = backend.get("capabilities") if isinstance(backend, dict) else None
    source_root = _probe_source_root(vtriton_source_root)
    tritonsim = {"available": bool(_which(tritonsim_hivm)), "requested_binary": tritonsim_hivm, "resolved_binary": _which(tritonsim_hivm)}
    mlir_opt = {"available": bool(_which(mlir_opt_binary)), "requested_binary": mlir_opt_binary, "resolved_binary": _which(mlir_opt_binary)}

    identity_flags = {
        "declares_real_mlir_backend": _cap_bool(caps, "is_real_mlir_backend", "real_mlir_backend"),
        "declares_hivmopseditor_or_operation_walk": _cap_bool(caps, "uses_hivmopseditor", "uses_mlir_operation_walk", "operation_walk"),
        "declares_not_fake": bool(isinstance(caps, dict) and caps.get("backend_kind") not in {"fake", "fixture", "mock"}),
    }
    mode_flags = {
        "inventory": _cap_bool(caps, "inventory", "operation_inventory"),
        "roundtrip": _cap_bool(caps, "roundtrip"),
        "verify_only": _cap_bool(caps, "verify_only", "verifier"),
        "dry_run": _cap_bool(caps, "dry_run", "dry_run_edit_script"),
        "mutate_q_load_hoist": _cap_bool(caps, "mutate_q_load_hoist", "q_load_hoist_mutation"),
        "mutate_gm_roundtrip_deletion": _cap_bool(caps, "mutate_gm_roundtrip_deletion", "gm_roundtrip_deletion_mutation"),
    }

    blockers: List[str] = []
    if not backend.get("available"):
        blockers.append("real_operation_backend_binary_missing")
    if not backend.get("supports_print_capabilities"):
        blockers.append("backend_capability_handshake_missing")
    if not identity_flags["declares_real_mlir_backend"]:
        blockers.append("backend_does_not_declare_real_mlir_backend")
    if not identity_flags["declares_hivmopseditor_or_operation_walk"]:
        blockers.append("backend_does_not_declare_hivmopseditor_or_operation_walk")
    for mode, ok in mode_flags.items():
        if not ok:
            blockers.append(f"backend_mode_missing_{mode}")
    if not source_root.get("looks_like_vtriton_repo"):
        blockers.append("vtriton_source_root_missing_or_not_recognized")
    if not tritonsim.get("available"):
        blockers.append("real_tritonsim_hivm_binary_missing")

    accepted = not blockers
    required_inputs = {
        "must_provide_for_real_phase6_positive_case": [
            {
                "item": "vTriton source tree or internal HivmOpsEditor source tree",
                "why": "Needed to build/verify a real Operation-level backend instead of text scanner or fake fixture.",
                "cli": "--vtriton-source-root /path/to/vTriton",
            },
            {
                "item": "built HIVM Operation backend binary",
                "why": "Must support --print-capabilities, --inventory, --roundtrip, --verify-only, --dry-run, and guarded --mutate modes.",
                "cli": "--hivm-operation-backend /path/to/hivm-operation-backend",
            },
            {
                "item": "built tritonsim-hivm binary",
                "why": "Needed for real DES/trace validation after mutation.",
                "cli": "--tritonsim-hivm /path/to/tritonsim-hivm --run-vtriton-validation",
            },
            {
                "item": "one positive restricted HIVM fixture",
                "why": "Needed to prove one Q-load hoist or GM-deletion mutation end-to-end with verifier and DES/trace.",
                "example": "simple attention-like or matmul-like .hivm.mlir with explicit Q load in KV loop or same-offset GM round-trip.",
            },
            {
                "item": "expected parser/dialect version notes",
                "why": "Needed to diagnose MLIR dialect mismatch rather than treating parser failure as optimizer failure.",
            },
        ],
        "optional_but_useful": [
            "compile_commands.json or build directory for the backend",
            "real hardware run script and msprof command if Phase 6D/Phase 7 proceeds",
            "known-good original/optimized DES graph and Perfetto trace examples",
        ],
    }

    return {
        "schema_version": "hivm_phase6a_real_backend_integration_report_v1",
        "producer": "strategy_search_demo_v3.3.2_phase6a_real_backend_integration_readiness",
        "phase": "Phase-6A",
        "phase6a_status": "real_backend_accepted_for_positive_case" if accepted else "waiting_for_real_operation_backend_inputs",
        "plain_language_summary": "Phase 6A checks whether the project has a real MLIR/HivmOpsEditor Operation backend. Without that backend and real tritonsim-hivm, complex mutations remain locked even though earlier contracts and fake-backend tests are ready.",
        "backend_probe": backend,
        "source_root_probe": source_root,
        "tritonsim_probe": tritonsim,
        "mlir_opt_probe": mlir_opt,
        "identity_flags": identity_flags,
        "mode_flags": mode_flags,
        "accepted_for_phase6_positive_case": accepted,
        "production_mutation_allowed": False,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "required_inputs": required_inputs,
        "acceptance_rule": {
            "all_identity_flags_required": True,
            "all_mode_flags_required": True,
            "source_root_required": True,
            "real_tritonsim_required_before_claiming_DES_trace_validation": True,
            "fake_or_fixture_backend_rejected": True,
        },
    }


def build_phase6a_backend_acceptance_matrix(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": "hivm_phase6a_backend_acceptance_matrix_v1",
        "phase": "Phase-6A",
        "checks": [
            {"check": "backend capability handshake", "passed": bool((report.get("backend_probe") or {}).get("supports_print_capabilities"))},
            {"check": "declares real MLIR backend", "passed": bool((report.get("identity_flags") or {}).get("declares_real_mlir_backend"))},
            {"check": "declares HivmOpsEditor or MLIR Operation walk", "passed": bool((report.get("identity_flags") or {}).get("declares_hivmopseditor_or_operation_walk"))},
            {"check": "supports inventory", "passed": bool((report.get("mode_flags") or {}).get("inventory"))},
            {"check": "supports roundtrip", "passed": bool((report.get("mode_flags") or {}).get("roundtrip"))},
            {"check": "supports verify-only", "passed": bool((report.get("mode_flags") or {}).get("verify_only"))},
            {"check": "supports dry-run", "passed": bool((report.get("mode_flags") or {}).get("dry_run"))},
            {"check": "supports Q-load mutation", "passed": bool((report.get("mode_flags") or {}).get("mutate_q_load_hoist"))},
            {"check": "supports GM-deletion mutation", "passed": bool((report.get("mode_flags") or {}).get("mutate_gm_roundtrip_deletion"))},
            {"check": "vTriton/source root recognized", "passed": bool((report.get("source_root_probe") or {}).get("looks_like_vtriton_repo"))},
            {"check": "real tritonsim-hivm available", "passed": bool((report.get("tritonsim_probe") or {}).get("available"))},
        ],
        "accepted_for_phase6_positive_case": bool(report.get("accepted_for_phase6_positive_case")),
        "blockers": report.get("blockers") or [],
    }


def emit_phase6a_outputs(
    *,
    out: Path,
    operation_backend_binary: Optional[str] = None,
    vtriton_source_root: Optional[str] = None,
    tritonsim_hivm: Optional[str] = None,
    mlir_opt_binary: Optional[str] = None,
) -> Dict[str, Any]:
    report = build_phase6a_real_backend_integration_report(
        out=out,
        operation_backend_binary=operation_backend_binary,
        vtriton_source_root=vtriton_source_root,
        tritonsim_hivm=tritonsim_hivm,
        mlir_opt_binary=mlir_opt_binary,
    )
    matrix = build_phase6a_backend_acceptance_matrix(report)
    summary = {
        "schema_version": "hivm_phase6a_analysis_summary_v1",
        "producer": report.get("producer"),
        "phase": "Phase-6A",
        "status": report.get("phase6a_status"),
        "accepted_for_phase6_positive_case": bool(report.get("accepted_for_phase6_positive_case")),
        "production_mutation_allowed": False,
        "blocker_count": report.get("blocker_count"),
        "blockers": report.get("blockers"),
        "need_user_inputs": [item["item"] for item in (report.get("required_inputs") or {}).get("must_provide_for_real_phase6_positive_case", [])],
        "leadership_summary": "Phase 6A has prepared the real-backend integration checklist. To make substantive progress beyond gates/contracts, we now need the actual vTriton/HivmOpsEditor backend binary, source/build context, tritonsim-hivm, and a restricted positive HIVM fixture.",
    }
    _write_json(out / "phase6a_real_backend_integration_report.json", report)
    _write_json(out / "phase6a_backend_acceptance_matrix.json", matrix)
    _write_json(out / "phase6a_required_inputs.json", report.get("required_inputs") or {})
    _write_json(out / "phase6a_analysis_summary.json", summary)
    return summary


# ---------------------------------------------------------------------------
# Phase-6B: real-backend positive-case validation harness
# ---------------------------------------------------------------------------

def _split_fixture_paths(value: Optional[str]) -> List[str]:
    if not value:
        return []
    out: List[str] = []
    for chunk in str(value).split(','):
        c = chunk.strip()
        if c:
            out.append(c)
    return out


def _fixture_summary(path: str) -> Dict[str, Any]:
    p = Path(path)
    summary: Dict[str, Any] = {
        "path": str(p),
        "exists": p.exists(),
        "readable": False,
        "kind": "missing",
        "line_count": 0,
        "size_bytes": None,
        "counts": {},
        "candidate_signals": {},
        "readiness": "missing",
        "blockers": [],
    }
    if not p.exists():
        summary["blockers"].append("fixture_file_missing")
        return summary
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        summary["blockers"].append(f"fixture_unreadable:{exc}")
        return summary
    lines = text.splitlines()
    summary.update({
        "readable": True,
        "kind": "hivm_or_npuir_mlir" if ("hivm" in text or "npuir" in p.name) else "unknown_text",
        "line_count": len(lines),
        "size_bytes": p.stat().st_size,
    })
    counts = {
        "func": text.count("func.func"),
        "scf_for": text.count("scf.for"),
        "hivm_hir": text.count("hivm.hir."),
        "load": text.count("hivm.hir.load"),
        "store": text.count("hivm.hir.store"),
        "barrier": text.count("barrier"),
        "set_flag": text.count("set_flag"),
        "wait_flag": text.count("wait_flag"),
        "mmad_or_cube": text.count("mmad") + text.count("cube"),
        "vector_like": sum(text.count(k) for k in ["vadd", "vsub", "vmul", "vexp", "vreduce", "softmax"]),
        "gm_space": text.count("address_space<gm>"),
        "ub_space": text.count("address_space<ub>"),
        "l1_or_cbuf_space": text.count("address_space<cbuf>") + text.count("address_space<l1>"),
        "unsupported_warning": text.lower().count("warning:"),
    }
    summary["counts"] = counts
    load_lines = []
    q_like_load_lines = []
    loop_stack = 0
    load_in_loop = 0
    q_load_in_loop = 0
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if "scf.for" in stripped:
            loop_stack += 1
        if "hivm.hir.load" in stripped:
            item = {"line": idx, "in_loop_approx": loop_stack > 0, "text_preview": stripped[:240]}
            load_lines.append(item)
            if loop_stack > 0:
                load_in_loop += 1
            if any(tok in stripped.lower() for tok in ["%q", "q_gm", "query", "arg3"]):
                q_like_load_lines.append(item)
                if loop_stack > 0:
                    q_load_in_loop += 1
        # Conservative brace heuristic for simple fixture triage only.
        if "}" in stripped and loop_stack > 0:
            loop_stack -= stripped.count("}")
            if loop_stack < 0:
                loop_stack = 0
    candidate_signals = {
        "has_hivm_ops": counts["hivm_hir"] > 0,
        "has_loop": counts["scf_for"] > 0,
        "has_load_store": counts["load"] > 0 and counts["store"] > 0,
        "has_sync_ops": counts["set_flag"] > 0 or counts["wait_flag"] > 0 or counts["barrier"] > 0,
        "load_in_loop_count_approx": load_in_loop,
        "q_like_load_count": len(q_like_load_lines),
        "q_like_load_in_loop_count_approx": q_load_in_loop,
        "gm_roundtrip_possible_very_rough": counts["load"] > 0 and counts["store"] > 0 and counts["gm_space"] > 0,
        "q_load_hoist_positive_case_possible": q_load_in_loop > 0,
        "q_load_hoist_already_hoisted_or_no_loop_q_load": len(q_like_load_lines) > 0 and q_load_in_loop == 0,
    }
    summary["candidate_signals"] = candidate_signals
    summary["sample_load_lines"] = load_lines[:8]
    summary["sample_q_like_load_lines"] = q_like_load_lines[:8]
    blockers: List[str] = []
    if not candidate_signals["has_hivm_ops"]:
        blockers.append("no_hivm_hir_ops_seen")
    if counts["unsupported_warning"] > 0:
        blockers.append("contains_frontend_or_layout_warnings_needs_real_parser_check")
    if not candidate_signals["q_load_hoist_positive_case_possible"] and not candidate_signals["gm_roundtrip_possible_very_rough"]:
        blockers.append("no_obvious_q_hoist_or_gm_deletion_positive_signal")
    if blockers:
        readiness = "triage_only_needs_backend_or_better_positive_fixture"
    else:
        readiness = "candidate_positive_fixture_for_real_backend_validation"
    summary["blockers"] = blockers
    summary["readiness"] = readiness
    return summary


def _write_phase6b_command_script(
    *,
    out: Path,
    fixture_paths: List[str],
    operation_backend_binary: Optional[str],
    tritonsim_hivm: Optional[str],
    vtriton_source_root: Optional[str],
) -> str:
    script = out / "phase6b_real_backend_validation_commands.sh"
    lines: List[str] = []
    lines.append("#!/usr/bin/env bash")
    lines.append("set -euo pipefail")
    lines.append("")
    lines.append("# Phase-6B real backend validation script generated by strategy_search_demo.")
    lines.append("# It follows the vTriton README convention: tritonsim-hivm analyzes .npuir.mlir")
    lines.append("# and can emit DES graph / Perfetto trace artifacts.")
    lines.append("")
    lines.append(f"VTRITON_ROOT=\"{vtriton_source_root or '/path/to/vTriton'}\"")
    lines.append(f"HIVM_OPERATION_BACKEND=\"{operation_backend_binary or '/path/to/hivm-operation-backend'}\"")
    lines.append(f"TRITONSIM_HIVM=\"{tritonsim_hivm or '${VTRITON_ROOT}/build/bin/tritonsim-hivm'}\"")
    lines.append(f"OUT_DIR=\"{out}\"")
    lines.append("mkdir -p \"${OUT_DIR}/phase6b_real_backend_artifacts\"")
    lines.append("")
    lines.append("# Optional build reminder, copied from vTriton public README style:")
    lines.append("#   git submodule update --init thirdparty/triton-ascend")
    lines.append("#   ./scripts/apply_patches.sh")
    lines.append("#   ./scripts/build_llvm.sh")
    lines.append("#   mkdir -p build && cd build && cmake -G Ninja .. -DMLIR_DIR=../thirdparty/llvm-project/build/install/lib/cmake/mlir -DLLVM_DIR=../thirdparty/llvm-project/build/install/lib/cmake/llvm && ninja")
    lines.append("")
    lines.append("\"${HIVM_OPERATION_BACKEND}\" --print-capabilities || true")
    for i, fixture in enumerate(fixture_paths):
        stem = Path(fixture).name.replace(".", "_").replace("-", "_")
        prefix = f"${{OUT_DIR}}/phase6b_real_backend_artifacts/{i}_{stem}"
        lines.append("")
        lines.append(f"# Fixture {i}: {fixture}")
        lines.append(f"FIXTURE=\"{fixture}\"")
        lines.append(f"\"${{HIVM_OPERATION_BACKEND}}\" --inventory --input \"${{FIXTURE}}\" --report \"{prefix}_inventory.json\" || true")
        lines.append(f"\"${{HIVM_OPERATION_BACKEND}}\" --roundtrip --input \"${{FIXTURE}}\" --output \"{prefix}_roundtrip.mlir\" --report \"{prefix}_roundtrip_report.json\" || true")
        lines.append(f"\"${{HIVM_OPERATION_BACKEND}}\" --verify-only --input \"{prefix}_roundtrip.mlir\" --report \"{prefix}_verify_report.json\" || true")
        lines.append(f"\"${{TRITONSIM_HIVM}}\" --npuir-file \"${{FIXTURE}}\" --scheduler des --des-graph-file \"{prefix}_des_graph.json\" --perfetto-trace-file \"{prefix}_trace.json\" || true")
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        script.chmod(0o755)
    except Exception:
        pass
    return str(script)


def build_phase6b_positive_case_report(
    *,
    out: Path,
    fixture_paths: List[str],
    operation_backend_binary: Optional[str] = None,
    tritonsim_hivm: Optional[str] = None,
    vtriton_source_root: Optional[str] = None,
) -> Dict[str, Any]:
    backend = _probe_json_capabilities(operation_backend_binary)
    caps = backend.get("capabilities") if isinstance(backend, dict) else None
    real_backend = bool(
        backend.get("supports_print_capabilities")
        and _cap_bool(caps, "is_real_mlir_backend", "real_mlir_backend")
        and _cap_bool(caps, "uses_hivmopseditor", "uses_mlir_operation_walk", "operation_walk")
    )
    real_tritonsim = bool(_which(tritonsim_hivm))
    source_root = _probe_source_root(vtriton_source_root)
    fixtures = [_fixture_summary(p) for p in fixture_paths]
    candidate_fixtures = [f for f in fixtures if f.get("readiness") == "candidate_positive_fixture_for_real_backend_validation"]
    script = _write_phase6b_command_script(
        out=out,
        fixture_paths=[f.get("path") for f in fixtures if f.get("exists")],
        operation_backend_binary=operation_backend_binary,
        tritonsim_hivm=tritonsim_hivm,
        vtriton_source_root=vtriton_source_root,
    )
    blockers: List[str] = []
    if not fixture_paths:
        blockers.append("no_phase6_positive_fixtures_provided")
    if not candidate_fixtures:
        blockers.append("no_restricted_positive_fixture_identified_by_static_triage")
    if not real_backend:
        blockers.append("real_hivmopseditor_or_mlir_operation_backend_not_connected")
    if not real_tritonsim:
        blockers.append("real_tritonsim_hivm_not_connected")
    if not source_root.get("looks_like_vtriton_repo"):
        blockers.append("vtriton_source_root_missing_or_not_recognized")
    accepted = not blockers
    return {
        "schema_version": "hivm_phase6b_positive_case_report_v1",
        "producer": "strategy_search_demo_v3.3.2_phase6b_vtriton_positive_fixture_harness",
        "phase": "Phase-6B",
        "phase6b_status": "ready_to_run_real_positive_case" if accepted else "positive_case_harness_ready_but_waiting_for_real_backend_or_fixture",
        "official_alignment": {
            "vtriton_public_repo": "https://github.com/shane-kshongmo/vTriton",
            "uses_vtriton_documented_hivm_analysis_entry": "tritonsim-hivm --npuir-file <file> --des-graph-file <json> --perfetto-trace-file <json>",
            "uses_hivm_crud_design_reference": "tools/hivm-crud/hivm-crud.cpp wraps HivmOpsEditor; upper-level C++ should call HivmOpsEditor directly.",
            "no_text_region_motion": True,
            "fake_backend_results_rejected_for_production_mutation": True,
        },
        "backend_probe": backend,
        "real_backend_connected": real_backend,
        "tritonsim_probe": {"available": real_tritonsim, "requested_binary": tritonsim_hivm, "resolved_binary": _which(tritonsim_hivm)},
        "source_root_probe": source_root,
        "fixture_count": len(fixtures),
        "candidate_fixture_count": len(candidate_fixtures),
        "fixtures": fixtures,
        "validation_script": script,
        "accepted_for_phase6_positive_case_execution": accepted,
        "production_mutation_allowed": False,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "what_user_provided": [str(p) for p in fixture_paths],
        "what_is_still_needed": [
            "A real HivmOpsEditor/MLIR Operation backend binary, not fake_hivm_operation_backend.py.",
            "A built tritonsim-hivm binary from vTriton build/bin.",
            "A local vTriton source/build directory if backend compilation is expected in this project environment.",
            "At least one restricted positive fixture with a provable Q-load-in-loop or exact same-offset GM round-trip. Current static triage only suggests candidates; final proof must come from real backend/verifier/DES trace.",
        ],
    }


def emit_phase6b_outputs(
    *,
    out: Path,
    fixture_paths: Optional[List[str]] = None,
    operation_backend_binary: Optional[str] = None,
    tritonsim_hivm: Optional[str] = None,
    vtriton_source_root: Optional[str] = None,
) -> Dict[str, Any]:
    fixtures = fixture_paths or []
    report = build_phase6b_positive_case_report(
        out=out,
        fixture_paths=fixtures,
        operation_backend_binary=operation_backend_binary,
        tritonsim_hivm=tritonsim_hivm,
        vtriton_source_root=vtriton_source_root,
    )
    matrix = {
        "schema_version": "hivm_phase6b_fixture_acceptance_matrix_v1",
        "phase": "Phase-6B",
        "fixtures": [
            {
                "path": f.get("path"),
                "readiness": f.get("readiness"),
                "q_load_hoist_positive_case_possible": (f.get("candidate_signals") or {}).get("q_load_hoist_positive_case_possible"),
                "gm_roundtrip_possible_very_rough": (f.get("candidate_signals") or {}).get("gm_roundtrip_possible_very_rough"),
                "blockers": f.get("blockers"),
            }
            for f in report.get("fixtures", [])
        ],
        "accepted_for_phase6_positive_case_execution": report.get("accepted_for_phase6_positive_case_execution"),
        "global_blockers": report.get("blockers"),
    }
    summary = {
        "schema_version": "hivm_phase6b_analysis_summary_v1",
        "producer": report.get("producer"),
        "phase": "Phase-6B",
        "status": report.get("phase6b_status"),
        "fixture_count": report.get("fixture_count"),
        "candidate_fixture_count": report.get("candidate_fixture_count"),
        "real_backend_connected": report.get("real_backend_connected"),
        "tritonsim_available": (report.get("tritonsim_probe") or {}).get("available"),
        "accepted_for_phase6_positive_case_execution": report.get("accepted_for_phase6_positive_case_execution"),
        "production_mutation_allowed": False,
        "blocker_count": report.get("blocker_count"),
        "blockers": report.get("blockers"),
        "leadership_summary": "Phase 6B ingests the user-provided HIVM/NPUIR fixtures and creates the real vTriton/HivmOpsEditor positive-case validation harness. It can triage candidate fixtures and generate the real-backend command script, but it still refuses production mutation until a real Operation backend and real tritonsim-hivm are supplied.",
    }
    _write_json(out / "phase6b_positive_case_validation_report.json", report)
    _write_json(out / "phase6b_fixture_acceptance_matrix.json", matrix)
    _write_json(out / "phase6b_analysis_summary.json", summary)
    return summary

# ---------------------------------------------------------------------------
# Phase-6C: restricted true rewrite positive-case execution
# ---------------------------------------------------------------------------

def _restricted_rewriter_path() -> Optional[str]:
    p = Path(__file__).resolve().parents[1] / "tools" / "restricted_hivm_true_rewriter.py"
    return str(p) if p.exists() else None


def _run_restricted_true_rewrite(
    *,
    out: Path,
    fixture_path: str,
    mutation_kind: str,
    tag: str,
) -> Dict[str, Any]:
    tool = _restricted_rewriter_path()
    input_path = Path(fixture_path)
    output_path = out / f"optimized.phase6c.{tag}.{mutation_kind}.hivm.mlir"
    report_path = out / f"phase6c_{tag}_{mutation_kind}_restricted_true_rewrite_report.json"
    if not tool or not input_path.exists():
        return {
            "fixture": fixture_path,
            "mutation_kind": mutation_kind,
            "tool_available": bool(tool),
            "input_exists": input_path.exists(),
            "returncode": None,
            "mutation_performed": False,
            "output": str(output_path),
            "report": str(report_path),
            "blockers": ["restricted_true_rewriter_tool_or_fixture_missing"],
        }
    try:
        proc = subprocess.run(
            [
                sys.executable,
                tool,
                "--mutate",
                "--mutation-kind",
                mutation_kind,
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                "--report",
                str(report_path),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        rep = _safe_load_json_file(str(report_path)) or {}
        return {
            "fixture": str(input_path),
            "mutation_kind": mutation_kind,
            "tool": tool,
            "returncode": proc.returncode,
            "stdout_preview": proc.stdout[:2000],
            "stderr_preview": proc.stderr[:2000],
            "mutation_performed": bool(rep.get("mutation_performed")),
            "restricted_true_mutation": bool(rep.get("restricted_true_mutation")),
            "production_mutation": bool(rep.get("production_mutation")),
            "status": rep.get("status"),
            "output": str(output_path),
            "report": str(report_path),
            "backend_report": rep,
            "blockers": rep.get("blockers") or [],
        }
    except Exception as exc:
        return {
            "fixture": str(input_path),
            "mutation_kind": mutation_kind,
            "tool": tool,
            "returncode": None,
            "mutation_performed": False,
            "output": str(output_path),
            "report": str(report_path),
            "error": str(exc),
            "blockers": ["restricted_true_rewriter_execution_exception"],
        }


def build_phase6c_restricted_true_rewrite_report(
    *,
    out: Path,
    fixture_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run real file-level rewrites on explicit restricted positive fixtures.

    This stage deliberately does not claim production MLIR/HivmOpsEditor status.
    It proves that the pipeline can emit genuinely changed HIVM IR on tiny,
    auditable patterns while keeping complex kernels locked.
    """
    default_dir = Path(__file__).resolve().parents[1] / "sample_input" / "phase6_positive_fixtures"
    defaults = [
        default_dir / "restricted_q_load_hoist_mutation_positive.hivm.mlir",
        default_dir / "restricted_gm_roundtrip_deletion_positive.hivm.mlir",
    ]
    paths = [Path(p) for p in (fixture_paths or []) if str(p).strip()]
    if not paths:
        paths = defaults
    results: List[Dict[str, Any]] = []
    for p in paths:
        name = p.name
        tag = re.sub(r"[^A-Za-z0-9_]+", "_", p.stem) if 're' in globals() else p.stem.replace('.', '_')
        if "q_load" in name or "q_load_hoist" in name:
            results.append(_run_restricted_true_rewrite(out=out, fixture_path=str(p), mutation_kind="q_load_hoist", tag=tag))
        if "gm_roundtrip" in name or "gm" in name:
            results.append(_run_restricted_true_rewrite(out=out, fixture_path=str(p), mutation_kind="gm_roundtrip_deletion", tag=tag))
    mutated = [r for r in results if r.get("mutation_performed")]
    blockers: List[str] = []
    if not mutated:
        blockers.append("no_restricted_true_rewrite_positive_case_mutated")
    # In Phase 6C, successful restricted true mutation is useful, but still not production.
    return {
        "schema_version": "hivm_phase6c_restricted_true_rewrite_report_v1",
        "producer": "strategy_search_demo_v3.3.2_phase6c_restricted_true_rewrite",
        "phase": "Phase-6C",
        "phase6c_status": "restricted_true_rewrite_positive_case_completed" if mutated else "waiting_for_restricted_positive_case_or_tool",
        "plain_language_summary": "Phase 6C finally performs real file-level IR rewrites on tiny explicitly marked positive fixtures. This is more than attributes or dry-run, but it is still not a production MLIR/HivmOpsEditor backend.",
        "fixture_count": len(paths),
        "attempt_count": len(results),
        "restricted_true_mutation_count": len(mutated),
        "production_mutation_allowed": False,
        "production_mutation_unlocked": False,
        "results": results,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "scope": {
            "does_real_file_level_ir_mutation": bool(mutated),
            "does_not_require_msprof": True,
            "not_a_production_mlir_backend": True,
            "only_for_restricted_positive_fixtures": True,
            "complex_kernels_remain_locked": True,
        },
    }


def emit_phase6c_outputs(
    *,
    out: Path,
    fixture_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    report = build_phase6c_restricted_true_rewrite_report(out=out, fixture_paths=fixture_paths)
    summary = {
        "schema_version": "hivm_phase6c_analysis_summary_v1",
        "phase": "Phase-6C",
        "status": report.get("phase6c_status"),
        "restricted_true_mutation_count": report.get("restricted_true_mutation_count"),
        "production_mutation_allowed": False,
        "blocker_count": report.get("blocker_count"),
        "blockers": report.get("blockers") or [],
    }
    leadership = {
        "schema_version": "hivm_phase6c_leadership_summary_v1",
        "title": "Phase 6C：受限正例上的真正 IR 改写",
        "one_sentence": "这一版终于不只是 dry-run：系统会在明确标记的受限样例上真正生成改写后的 HIVM IR 文件，但仍不把它包装成生产级 MLIR 后端。",
        "what_changed": [
            "Q-load hoist 受限正例：可以把 loop 内的 Q load + nd2nz 移到 loop 外。",
            "GM round-trip 受限正例：可以删除一个被证明为局部冗余的 store/reload pair。",
            "真实复杂 kernel 仍然锁住，不会用这个受限 rewriter 乱改。",
        ],
        "important_boundary": "这是 restricted true rewrite，不是 full compiler lowering；它证明项目具备真实改写链路，但生产级复杂改写仍需 HivmOpsEditor/MLIR 后端。",
    }
    _write_json(out / "phase6c_restricted_true_rewrite_report.json", report)
    _write_json(out / "phase6c_analysis_summary.json", summary)
    _write_json(out / "phase6c_leadership_summary.json", leadership)
    return summary

# ---------------------------------------------------------------------------
# Phase-6D: vTriton-source-aware HivmOpsEditor backend adapter skeleton
# ---------------------------------------------------------------------------

def _read_text_preview(path: Path, limit: int = 200000) -> str:
    try:
        data = path.read_text(encoding="utf-8", errors="ignore")
        return data[:limit]
    except Exception:
        return ""


def _find_first(root: Path, name: str) -> Optional[Path]:
    try:
        matches = list(root.glob(f"**/{name}"))
        return matches[0] if matches else None
    except Exception:
        return None


def build_phase6d_vtriton_source_integration_report(
    *,
    out: Path,
    vtriton_source_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Inspect the supplied vTriton source tree and describe the generated adapter.

    Phase 6D is the first stage that is actually source-aware.  It does not
    build vTriton inside this sandbox, but it generates a concrete adapter that
    includes the real HivmOpsEditor header and follows the observed API.
    """
    root = Path(vtriton_source_root) if vtriton_source_root else None
    source_probe = _probe_source_root(vtriton_source_root)
    h_header = _find_first(root, "HivmOpsEditor.h") if root and root.exists() else None
    h_impl = _find_first(root, "HivmOpsEditor.cpp") if root and root.exists() else None
    crud = _find_first(root, "hivm-crud.cpp") if root and root.exists() else None
    tritonsim = _find_first(root, "tritonsim-hivm.cpp") if root and root.exists() else None
    header_text = _read_text_preview(h_header) if h_header else ""
    impl_text = _read_text_preview(h_impl) if h_impl else ""
    crud_text = _read_text_preview(crud) if crud else ""

    observed_api = {
        "loadFromFile": "loadFromFile" in header_text or "loadFromFile" in impl_text,
        "exportToFile": "exportToFile" in header_text or "exportToFile" in impl_text,
        "exportToString": "exportToString" in header_text or "exportToString" in impl_text,
        "listOps": "listOps" in header_text or "listOps" in impl_text,
        "opCounts": "opCounts" in header_text or "opCounts" in impl_text,
        "deleteOp": "deleteOp" in header_text or "deleteOp" in impl_text,
        "replaceOpWith": "replaceOpWith" in header_text or "replaceOpWith" in impl_text,
        "addSetFlagWaitFlagBefore": "addSetFlagWaitFlagBefore" in header_text or "addSetFlagWaitFlagBefore" in impl_text,
        "removeRedundantLoadStorePair": "removeRedundantLoadStorePair" in header_text or "removeRedundantLoadStorePair" in impl_text,
        "removeRedundantGMTrips": "deleteRedundantGMTrips" in header_text or "deleteRedundantGMTrips" in impl_text,
        "hivm_crud_says_call_editor_directly": "Upper-level C++ code should call HivmOpsEditor directly" in crud_text,
    }
    adapter_dir = Path(__file__).resolve().parents[1] / "vtriton_hivm_operation_backend"
    generated_files = []
    if adapter_dir.exists():
        for p in sorted(adapter_dir.glob("**/*")):
            if p.is_file():
                generated_files.append({"path": str(p), "size_bytes": p.stat().st_size})
    blockers: List[str] = []
    if not source_probe.get("looks_like_vtriton_repo"):
        blockers.append("vtriton_source_root_missing_or_not_recognized")
    if not h_header:
        blockers.append("HivmOpsEditor_header_not_found")
    if not h_impl:
        blockers.append("HivmOpsEditor_impl_not_found")
    if not crud:
        blockers.append("hivm_crud_reference_not_found")
    if not observed_api.get("loadFromFile") or not observed_api.get("listOps"):
        blockers.append("HivmOpsEditor_minimum_read_inventory_api_not_confirmed")
    if not observed_api.get("exportToFile"):
        blockers.append("HivmOpsEditor_roundtrip_export_api_not_confirmed")
    adapter_ready = not blockers and bool(generated_files)
    return {
        "schema_version": "hivm_phase6d_vtriton_source_integration_report_v1",
        "producer": "strategy_search_demo_v3.3.2_phase6d_vtriton_source_aware_adapter",
        "phase": "Phase-6D",
        "phase6d_status": "vtriton_source_aware_adapter_generated" if adapter_ready else "waiting_for_complete_vtriton_source_or_adapter_files",
        "plain_language_summary": "Phase 6D uses the supplied vTriton source tree to generate a real HivmOpsEditor-oriented backend adapter skeleton. This is no longer a purely invented interface: the adapter includes the observed HivmOpsEditor header/API names from the provided source.",
        "source_root_probe": source_probe,
        "located_files": {
            "HivmOpsEditor.h": str(h_header) if h_header else None,
            "HivmOpsEditor.cpp": str(h_impl) if h_impl else None,
            "hivm-crud.cpp": str(crud) if crud else None,
            "tritonsim-hivm.cpp": str(tritonsim) if tritonsim else None,
        },
        "observed_hivmopseditor_api": observed_api,
        "generated_adapter": {
            "directory": str(adapter_dir),
            "files": generated_files,
            "install_script": str(Path(__file__).resolve().parents[1] / "scripts" / "phase6d_install_backend_adapter.sh"),
            "intended_vtriton_location": "<vTriton>/tools/hivm-operation-backend/",
            "primary_cpp": str(adapter_dir / "hivm_operation_backend.cpp"),
            "cmake": str(adapter_dir / "CMakeLists.txt"),
        },
        "capability_contract": {
            "implemented_in_adapter_skeleton": [
                "--print-capabilities",
                "--inventory",
                "--roundtrip",
                "--verify-only",
                "--dry-run",
                "--mutate --mutation-kind gm_roundtrip_deletion --max-gm-pairs N",
            ],
            "intentionally_rejected_until_algorithm_added": [
                "--mutate --mutation-kind q_load_hoist"
            ],
            "why_q_load_hoist_is_rejected": "The supplied HivmOpsEditor exposes CRUD and creation helpers, but a production Q-load hoist still needs a dominance/region-motion algorithm. The generated adapter refuses to perform text-level region motion.",
        },
        "official_discipline": {
            "uses_HivmOpsEditor_API": True,
            "requires_MLIR_context_and_registered_dialects": True,
            "rejects_fake_backend_for_production": True,
            "does_not_use_python_text_region_motion": True,
            "broad_production_mutation_still_requires_build_verifier_DES_trace": True,
        },
        "adapter_ready_for_user_local_build": adapter_ready,
        "production_mutation_allowed_in_this_sandbox": False,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "next_steps_for_user_local_environment": [
            "Run scripts/phase6d_install_backend_adapter.sh /path/to/vTriton",
            "Add add_subdirectory(hivm-operation-backend) to vTriton/tools/CMakeLists.txt if needed",
            "Rebuild vTriton with HIVM/BishengIR support enabled",
            "Run hivm-operation-backend --print-capabilities and check is_real_mlir_backend=true",
            "Run --inventory/--roundtrip/--verify-only on kernel.npuir.mlir and fa_best.hivm.mlir",
            "Only then consider guarded GM deletion or future Q-load hoist implementation",
        ],
    }


def emit_phase6d_outputs(
    *,
    out: Path,
    vtriton_source_root: Optional[str] = None,
) -> Dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    report = build_phase6d_vtriton_source_integration_report(out=out, vtriton_source_root=vtriton_source_root)
    summary = {
        "schema_version": "hivm_phase6d_analysis_summary_v1",
        "phase": "Phase-6D",
        "status": report.get("phase6d_status"),
        "adapter_ready_for_user_local_build": report.get("adapter_ready_for_user_local_build"),
        "production_mutation_allowed": False,
        "blocker_count": report.get("blocker_count"),
        "blockers": report.get("blockers"),
        "leadership_summary": "Phase 6D consumes the provided vTriton source tree and generates a source-aware HivmOpsEditor backend adapter skeleton. The adapter is designed to be built inside vTriton and can support inventory, roundtrip, verify-only, dry-run, and limited GM deletion through the real HivmOpsEditor API. Q-load hoist remains disabled until a real dominance/region-motion implementation is added.",
    }
    manifest = {
        "schema_version": "hivm_phase6d_generated_backend_files_manifest_v1",
        "phase": "Phase-6D",
        "files": (report.get("generated_adapter") or {}).get("files") or [],
        "install_script": (report.get("generated_adapter") or {}).get("install_script"),
        "intended_vtriton_location": (report.get("generated_adapter") or {}).get("intended_vtriton_location"),
    }
    plan = {
        "schema_version": "hivm_phase6d_hivmopseditor_backend_adapter_plan_v1",
        "phase": "Phase-6D",
        "build_location": "<vTriton>/tools/hivm-operation-backend/",
        "requires": [
            "vTriton source tree",
            "TRITONSIM_HAS_BISHENGIR_HIVM enabled if HIVM dialect is external",
            "MLIR/LLVM build targets used by vTriton",
            "AscendModelTransforms and AscendModelIR libraries",
        ],
        "modes": (report.get("capability_contract") or {}).get("implemented_in_adapter_skeleton") or [],
        "disabled_modes": (report.get("capability_contract") or {}).get("intentionally_rejected_until_algorithm_added") or [],
    }
    _write_json(out / "phase6d_vtriton_source_integration_report.json", report)
    _write_json(out / "phase6d_generated_backend_files_manifest.json", manifest)
    _write_json(out / "phase6d_hivmopseditor_backend_adapter_plan.json", plan)
    _write_json(out / "phase6d_analysis_summary.json", summary)
    return summary


# ---------------------------------------------------------------------------
# Phase-6E: local vTriton integration/build harness for real backend adapter
# ---------------------------------------------------------------------------

def _phase6e_script_paths() -> Dict[str, str]:
    root = Path(__file__).resolve().parents[1]
    return {
        "apply_patch_script": str(root / "scripts" / "phase6e_apply_vtriton_backend_patch.py"),
        "build_script": str(root / "scripts" / "phase6e_build_hivm_operation_backend.sh"),
        "smoke_script": str(root / "scripts" / "phase6e_smoke_test_backend.sh"),
        "adapter_dir": str(root / "vtriton_hivm_operation_backend"),
    }


def build_phase6e_vtriton_local_integration_report(
    *,
    out: Path,
    vtriton_source_root: Optional[str] = None,
    operation_backend_binary: Optional[str] = None,
    tritonsim_hivm: Optional[str] = None,
) -> Dict[str, Any]:
    """Build Phase-6E local integration/build report.

    Phase 6E is the build handoff after Phase 6D generated the source-aware
    HivmOpsEditor adapter skeleton.  It does not claim that the backend has
    compiled in this sandbox unless a real binary is provided and passes
    capability probing.  It emits concrete scripts for installing/building the
    adapter inside the user's vTriton tree.
    """
    source_root = _probe_source_root(vtriton_source_root)
    backend = _probe_json_capabilities(operation_backend_binary)
    caps = backend.get("capabilities") if isinstance(backend, dict) else None
    tritonsim = {
        "available": bool(_which(tritonsim_hivm)),
        "requested_binary": tritonsim_hivm,
        "resolved_binary": _which(tritonsim_hivm),
    }
    scripts = _phase6e_script_paths()
    adapter_dir = Path(scripts["adapter_dir"])
    adapter_files = []
    if adapter_dir.exists():
        for f in sorted(adapter_dir.glob("**/*")):
            if f.is_file():
                adapter_files.append({"path": str(f), "size_bytes": f.stat().st_size})

    tools_cmake = None
    existing_backend_dir = None
    if vtriton_source_root:
        root = Path(vtriton_source_root)
        tools_cmake = root / "tools" / "CMakeLists.txt"
        existing_backend_dir = root / "tools" / "hivm-operation-backend"

    backend_is_real = bool(
        backend.get("supports_print_capabilities")
        and _cap_bool(caps, "is_real_mlir_backend", "real_mlir_backend")
        and _cap_bool(caps, "uses_hivmopseditor", "uses_mlir_operation_walk", "operation_walk")
    )
    mode_flags = {
        "inventory": _cap_bool(caps, "inventory", "operation_inventory"),
        "roundtrip": _cap_bool(caps, "roundtrip"),
        "verify_only": _cap_bool(caps, "verify_only", "verifier"),
        "dry_run": _cap_bool(caps, "dry_run", "dry_run_edit_script"),
        "mutate_gm_roundtrip_deletion": _cap_bool(caps, "mutate_gm_roundtrip_deletion", "gm_roundtrip_deletion_mutation"),
        "mutate_q_load_hoist": _cap_bool(caps, "mutate_q_load_hoist", "q_load_hoist_mutation"),
    }
    blockers: List[str] = []
    if not source_root.get("looks_like_vtriton_repo"):
        blockers.append("vtriton_source_root_missing_or_not_recognized")
    if not adapter_files:
        blockers.append("generated_hivm_operation_backend_adapter_files_missing")
    if tools_cmake is not None and not tools_cmake.exists():
        blockers.append("vtriton_tools_cmakelists_missing")
    if not backend.get("available"):
        blockers.append("compiled_hivm_operation_backend_binary_not_provided_yet")
    elif not backend_is_real:
        blockers.append("provided_backend_binary_did_not_prove_real_hivmopseditor_mlir_identity")
    for mode, ok in mode_flags.items():
        if mode != "mutate_q_load_hoist" and backend.get("available") and not ok:
            blockers.append(f"provided_backend_missing_mode_{mode}")
    if not tritonsim.get("available"):
        blockers.append("real_tritonsim_hivm_binary_not_provided_yet")

    status = "phase6e_backend_compiled_and_accepted" if backend_is_real and tritonsim.get("available") else "phase6e_integration_pack_ready_waiting_for_local_vtriton_build"
    return {
        "schema_version": "hivm_phase6e_vtriton_local_integration_report_v1",
        "producer": "strategy_search_demo_v3.3.2_phase6e_vtriton_build_integration_pack",
        "phase": "Phase-6E",
        "phase6e_status": status,
        "plain_language_summary": "Phase 6E turns the source-aware adapter skeleton into a local vTriton integration/build pack. It can install the adapter into a real vTriton tree, patch tools/CMakeLists.txt, and generate build/smoke-test commands. It only accepts production mutation after a real compiled backend proves its HivmOpsEditor/MLIR identity and modes.",
        "source_root_probe": source_root,
        "adapter_files": adapter_files,
        "vtriton_expected_locations": {
            "tools_cmakelists": str(tools_cmake) if tools_cmake else None,
            "backend_dir_after_install": str(existing_backend_dir) if existing_backend_dir else None,
        },
        "scripts": scripts,
        "backend_probe": backend,
        "backend_is_real_hivmopseditor_mlir": backend_is_real,
        "backend_mode_flags": mode_flags,
        "tritonsim_probe": tritonsim,
        "ready_to_run_local_install_script": bool(source_root.get("looks_like_vtriton_repo") and adapter_files),
        "compiled_backend_accepted": bool(backend_is_real),
        "des_trace_ready": bool(tritonsim.get("available")),
        "production_mutation_allowed": False,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "local_commands": {
            "install_adapter": f"python {scripts['apply_patch_script']} --vtriton-root {vtriton_source_root or '/path/to/vTriton'} --adapter-dir {scripts['adapter_dir']} --apply",
            "configure_or_reconfigure": "cmake -S /path/to/vTriton -B /path/to/vTriton/build <your existing vTriton CMake options>",
            "build_backend": "cmake --build /path/to/vTriton/build --target hivm-operation-backend -j$(nproc)",
            "smoke_test": f"bash {scripts['smoke_script']} /path/to/vTriton/build/bin/hivm-operation-backend sample_input/phase6_positive_fixtures/restricted_gm_roundtrip_positive.hivm.mlir",
        },
        "acceptance_rule": {
            "must_build_inside_vtriton_or_equivalent_mlir_env": True,
            "must_pass_print_capabilities": True,
            "must_declare_is_real_mlir_backend": True,
            "must_declare_uses_hivmopseditor_or_operation_walk": True,
            "must_pass_inventory_roundtrip_verify_on_at_least_one_fixture_before_mutation": True,
            "q_load_hoist_remains_disabled_until_dominance_region_motion_algorithm_exists": True,
            "msprof_is_not_required_for_phase6e": True,
        },
    }


def emit_phase6e_outputs(
    *,
    out: Path,
    vtriton_source_root: Optional[str] = None,
    operation_backend_binary: Optional[str] = None,
    tritonsim_hivm: Optional[str] = None,
) -> Dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    report = build_phase6e_vtriton_local_integration_report(
        out=out,
        vtriton_source_root=vtriton_source_root,
        operation_backend_binary=operation_backend_binary,
        tritonsim_hivm=tritonsim_hivm,
    )
    build_plan = {
        "schema_version": "hivm_phase6e_backend_build_plan_v1",
        "phase": "Phase-6E",
        "steps": [
            {"step": 1, "action": "Install adapter into <vTriton>/tools/hivm-operation-backend", "script": report["scripts"]["apply_patch_script"]},
            {"step": 2, "action": "Patch <vTriton>/tools/CMakeLists.txt with add_subdirectory(hivm-operation-backend) if absent"},
            {"step": 3, "action": "Reconfigure vTriton with its existing MLIR/BishengIR options"},
            {"step": 4, "action": "Build target hivm-operation-backend"},
            {"step": 5, "action": "Run --print-capabilities and require real MLIR/HivmOpsEditor identity"},
            {"step": 6, "action": "Run inventory/roundtrip/verify-only on restricted positive fixtures"},
            {"step": 7, "action": "Only then run guarded GM round-trip deletion mutation on restricted positive fixture"},
        ],
        "q_load_hoist_status": "disabled_until_dominance_region_motion_algorithm_is_implemented",
        "gm_roundtrip_status": "first_real_mutation_candidate_after_backend_build_and_verify",
    }
    summary = {
        "schema_version": "hivm_phase6e_analysis_summary_v1",
        "phase": "Phase-6E",
        "status": report.get("phase6e_status"),
        "ready_to_run_local_install_script": report.get("ready_to_run_local_install_script"),
        "compiled_backend_accepted": report.get("compiled_backend_accepted"),
        "des_trace_ready": report.get("des_trace_ready"),
        "production_mutation_allowed": False,
        "blocker_count": report.get("blocker_count"),
        "blockers": report.get("blockers"),
        "leadership_summary": "Phase 6E produces the concrete vTriton local integration/build pack for the HivmOpsEditor backend adapter. The next real milestone is no longer another report: it is compiling hivm-operation-backend inside the user's vTriton environment and running inventory/roundtrip/verify on a fixture.",
    }
    _write_json(out / "phase6e_vtriton_local_integration_report.json", report)
    _write_json(out / "phase6e_backend_build_plan.json", build_plan)
    _write_json(out / "phase6e_analysis_summary.json", summary)
    return summary


# ---------------------------------------------------------------------------
# Phase-6F: compiled backend acceptance + Phase-6 closure gate
# ---------------------------------------------------------------------------

def _run_backend_cmd(cmd: List[str], *, timeout: int = 20) -> Dict[str, Any]:
    """Run a backend command and return a compact, machine-readable result."""
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        parsed_stdout = None
        if proc.stdout.strip():
            try:
                parsed_stdout = json.loads(proc.stdout)
            except Exception:
                parsed_stdout = None
        return {
            "cmd": cmd,
            "returncode": proc.returncode,
            "ok": proc.returncode == 0,
            "stdout_preview": proc.stdout[:4000],
            "stderr_preview": proc.stderr[:4000],
            "parsed_stdout_is_json": isinstance(parsed_stdout, dict),
            "parsed_stdout": parsed_stdout,
        }
    except Exception as exc:
        return {"cmd": cmd, "returncode": None, "ok": False, "error": str(exc)}


def _fixture_dicts_for_phase6f(fixture_paths: Optional[List[str]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for raw in fixture_paths or []:
        path = Path(raw)
        if not path.exists():
            out.append({"path": str(path), "exists": False, "kind": "missing", "eligible_for_acceptance": False})
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")[:200000]
        lower = path.name.lower()
        kind = "npuir" if ".npuir" in lower else "hivm" if ".hivm" in lower else "mlir"
        has_q_hoist_marker = "phase6c_positive_q_load_hoist" in text or "restricted_q_load" in lower
        has_gm_roundtrip_marker = "phase6c_positive_gm_roundtrip" in text or "restricted_gm_roundtrip" in lower
        out.append({
            "path": str(path),
            "exists": True,
            "kind": kind,
            "size_bytes": path.stat().st_size,
            "contains_hivm_load": "hivm.hir.load" in text,
            "contains_hivm_store": "hivm.hir.store" in text,
            "contains_scf_for": "scf.for" in text,
            "has_q_hoist_positive_marker": has_q_hoist_marker,
            "has_gm_roundtrip_positive_marker": has_gm_roundtrip_marker,
            "eligible_for_acceptance": kind in {"hivm", "npuir", "mlir"} and ("hivm.hir." in text or "npuir" in text.lower()),
        })
    return out


def build_phase6f_backend_acceptance_report(
    *,
    out: Path,
    fixture_paths: Optional[List[str]] = None,
    operation_backend_binary: Optional[str] = None,
    tritonsim_hivm: Optional[str] = None,
) -> Dict[str, Any]:
    """Build Phase-6F acceptance report for a compiled real Operation backend.

    Phase 6F is intentionally binary-facing.  It is the first closure stage that
    tries to *accept* a compiled hivm-operation-backend if one is supplied.  It
    still refuses to claim production mutation unless the binary proves real
    HivmOpsEditor/MLIR identity and passes inventory/roundtrip/verify smoke
    tests on at least one fixture.
    """
    out.mkdir(parents=True, exist_ok=True)
    backend = _probe_json_capabilities(operation_backend_binary)
    caps = backend.get("capabilities") if isinstance(backend, dict) else None
    binary = backend.get("resolved_binary") if backend.get("available") else None
    tritonsim = {
        "available": bool(_which(tritonsim_hivm)),
        "requested_binary": tritonsim_hivm,
        "resolved_binary": _which(tritonsim_hivm),
    }
    fixtures = _fixture_dicts_for_phase6f(fixture_paths)
    eligible = [f for f in fixtures if f.get("eligible_for_acceptance")]
    smoke_dir = out / "phase6f_backend_smoke"
    smoke_dir.mkdir(parents=True, exist_ok=True)

    identity_flags = {
        "capabilities_json_ok": bool(backend.get("supports_print_capabilities")),
        "declares_real_mlir_backend": _cap_bool(caps, "is_real_mlir_backend", "real_mlir_backend"),
        "declares_hivmopseditor_or_operation_walk": _cap_bool(caps, "uses_hivmopseditor", "uses_mlir_operation_walk", "operation_walk"),
        "not_fake_backend": bool(isinstance(caps, dict) and caps.get("backend_kind") not in {"fake", "fixture", "mock"}),
    }
    required_modes = {
        "inventory": _cap_bool(caps, "inventory", "operation_inventory"),
        "roundtrip": _cap_bool(caps, "roundtrip"),
        "verify_only": _cap_bool(caps, "verify_only", "verifier"),
        "dry_run": _cap_bool(caps, "dry_run", "dry_run_edit_script"),
        "mutate_gm_roundtrip_deletion": _cap_bool(caps, "mutate_gm_roundtrip_deletion", "gm_roundtrip_deletion_mutation"),
    }

    smoke_results: List[Dict[str, Any]] = []
    if binary and all(identity_flags.values()):
        for idx, fixture in enumerate(eligible[:3]):
            fpath = fixture["path"]
            stem = Path(fpath).name.replace(".", "_")
            inv_report = smoke_dir / f"{idx}_{stem}.inventory.json"
            rt_out = smoke_dir / f"{idx}_{stem}.roundtrip.mlir"
            rt_report = smoke_dir / f"{idx}_{stem}.roundtrip.json"
            verify_report = smoke_dir / f"{idx}_{stem}.verify.json"
            one = {"fixture": fixture, "commands": {}}
            one["commands"]["inventory"] = _run_backend_cmd(_backend_arg_prefix(binary) + ["--inventory", "--input", fpath, "--report", str(inv_report)])
            one["commands"]["roundtrip"] = _run_backend_cmd(_backend_arg_prefix(binary) + ["--roundtrip", "--input", fpath, "--output", str(rt_out), "--report", str(rt_report)])
            verify_input = str(rt_out) if rt_out.exists() else fpath
            one["commands"]["verify_only"] = _run_backend_cmd(_backend_arg_prefix(binary) + ["--verify-only", "--input", verify_input, "--report", str(verify_report)])
            one["artifacts"] = {
                "inventory_report_exists": inv_report.exists(),
                "roundtrip_output_exists": rt_out.exists(),
                "roundtrip_report_exists": rt_report.exists(),
                "verify_report_exists": verify_report.exists(),
            }
            one["passed_basic_smoke"] = all(cmd.get("ok") for cmd in one["commands"].values()) and all(one["artifacts"].values())
            smoke_results.append(one)

    passed_smoke_count = sum(1 for r in smoke_results if r.get("passed_basic_smoke"))
    accepted_backend = bool(binary and all(identity_flags.values()) and all(required_modes.values()) and passed_smoke_count > 0)
    blockers: List[str] = []
    if not backend.get("available"):
        blockers.append("compiled_hivm_operation_backend_binary_not_provided")
    if not backend.get("supports_print_capabilities"):
        blockers.append("backend_capability_handshake_not_passed")
    for name, ok in identity_flags.items():
        if not ok:
            blockers.append(f"identity_check_failed_{name}")
    for name, ok in required_modes.items():
        if not ok:
            blockers.append(f"required_mode_missing_{name}")
    if not eligible:
        blockers.append("no_eligible_hivm_or_npuir_fixture_for_backend_acceptance")
    if binary and all(identity_flags.values()) and passed_smoke_count == 0:
        blockers.append("backend_inventory_roundtrip_verify_smoke_not_passed")
    if not tritonsim.get("available"):
        blockers.append("real_tritonsim_hivm_not_available_des_trace_deferred")

    status = "phase6f_backend_accepted_for_restricted_mutation_trials" if accepted_backend else "phase6f_waiting_for_compiled_real_backend_acceptance"
    return {
        "schema_version": "hivm_phase6f_backend_acceptance_report_v1",
        "producer": "strategy_search_demo_v3.3.2_phase6f_backend_acceptance_closure",
        "phase": "Phase-6F",
        "phase6f_status": status,
        "plain_language_summary": "Phase 6F accepts a compiled real HivmOpsEditor/MLIR backend only if it proves identity, supports required modes, and passes inventory/roundtrip/verify smoke tests on a fixture. Without that, restricted Python true rewrites remain separate prototypes and production complex mutation stays locked.",
        "backend_probe": backend,
        "identity_flags": identity_flags,
        "required_mode_flags": required_modes,
        "tritonsim_probe": tritonsim,
        "fixture_count": len(fixtures),
        "eligible_fixture_count": len(eligible),
        "fixtures": fixtures,
        "smoke_dir": str(smoke_dir),
        "smoke_results": smoke_results,
        "passed_smoke_count": passed_smoke_count,
        "accepted_backend_for_restricted_mutation_trials": accepted_backend,
        "production_mutation_allowed": False,
        "des_trace_deferred_without_real_tritonsim": not tritonsim.get("available"),
        "blocker_count": len(blockers),
        "blockers": blockers,
        "acceptance_rule": {
            "must_provide_compiled_backend_binary": True,
            "must_pass_print_capabilities": True,
            "must_declare_real_mlir_or_hivmopseditor_identity": True,
            "must_support_inventory_roundtrip_verify_dry_run_and_limited_gm_mutation": True,
            "must_pass_basic_inventory_roundtrip_verify_on_fixture": True,
            "q_load_hoist_still_requires_dominance_region_motion_algorithm": True,
            "msprof_not_required_for_phase6f": True,
        },
    }


def build_phase6f_closure_report(acceptance_report: Dict[str, Any]) -> Dict[str, Any]:
    accepted = bool(acceptance_report.get("accepted_backend_for_restricted_mutation_trials"))
    return {
        "schema_version": "hivm_phase6f_closure_report_v1",
        "phase": "Phase-6F",
        "phase6_status": "closed_waiting_for_real_backend_binary" if not accepted else "closed_backend_acceptance_passed_for_restricted_trials",
        "what_is_done": [
            "restricted true IR rewrite positive cases are implemented in a narrow Python tool",
            "vTriton source-aware HivmOpsEditor backend adapter skeleton is generated",
            "local vTriton build integration scripts are generated",
            "compiled backend acceptance gate is implemented",
        ],
        "what_is_not_done": [
            "broad production Q-load hoist on real kernels",
            "broad production GM round-trip deletion on real kernels",
            "real double-buffer rewrite",
            "full CVPipeline overlap rewrite",
            "real tiling loop lowering",
            "msprof validation",
        ],
        "next_phase_recommendation": "Phase-7 should start only after a compiled real hivm-operation-backend binary passes Phase-6F acceptance. If accepted, start with one restricted GM deletion trial; keep Q-load hoist locked until dominance/region-motion is implemented in the real backend.",
        "phase7_entry_conditions": [
            "hivm-operation-backend binary provided",
            "--print-capabilities declares real MLIR/HivmOpsEditor backend",
            "inventory/roundtrip/verify smoke tests pass on at least one fixture",
            "limited GM deletion mode is available",
            "tritonsim-hivm available before claiming DES/trace validation",
        ],
        "production_mutations_unlocked": {
            "q_load_hoist": False,
            "gm_roundtrip_deletion_broad": False,
            "restricted_gm_roundtrip_deletion_trial": bool(accepted),
            "real_double_buffer": False,
            "full_cv_overlap": False,
            "real_tiling_loop_lowering": False,
        },
    }


def emit_phase6f_outputs(
    *,
    out: Path,
    fixture_paths: Optional[List[str]] = None,
    operation_backend_binary: Optional[str] = None,
    tritonsim_hivm: Optional[str] = None,
) -> Dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    acceptance = build_phase6f_backend_acceptance_report(
        out=out,
        fixture_paths=fixture_paths,
        operation_backend_binary=operation_backend_binary,
        tritonsim_hivm=tritonsim_hivm,
    )
    closure = build_phase6f_closure_report(acceptance)
    smoke_commands = {
        "schema_version": "hivm_phase6f_smoke_command_matrix_v1",
        "phase": "Phase-6F",
        "commands": {
            "print_capabilities": "hivm-operation-backend --print-capabilities",
            "inventory": "hivm-operation-backend --inventory --input <fixture.hivm.mlir> --report inventory.json",
            "roundtrip": "hivm-operation-backend --roundtrip --input <fixture.hivm.mlir> --output roundtrip.hivm.mlir --report roundtrip.json",
            "verify_only": "hivm-operation-backend --verify-only --input roundtrip.hivm.mlir --report verify.json",
            "restricted_gm_mutation_trial": "hivm-operation-backend --mutate --mutation-kind gm_roundtrip_deletion --max-gm-pairs 1 --input <restricted_gm_fixture.hivm.mlir> --output optimized.gm_removed.hivm.mlir --report gm_mutation.json",
        },
        "q_load_hoist_note": "Do not run production q_load_hoist until the real backend implements dominance and region-motion proof.",
    }
    summary = {
        "schema_version": "hivm_phase6f_analysis_summary_v1",
        "phase": "Phase-6F",
        "status": acceptance.get("phase6f_status"),
        "accepted_backend_for_restricted_mutation_trials": acceptance.get("accepted_backend_for_restricted_mutation_trials"),
        "passed_smoke_count": acceptance.get("passed_smoke_count"),
        "production_mutation_allowed": False,
        "blocker_count": acceptance.get("blocker_count"),
        "blockers": acceptance.get("blockers"),
        "leadership_summary": "Phase 6F implements the compiled-backend acceptance gate. The project can now distinguish restricted Python true rewrites, generated vTriton adapter source, and an actually compiled real HivmOpsEditor backend. Without a compiled backend binary passing smoke tests, broad production mutation remains locked.",
    }
    _write_json(out / "phase6f_backend_acceptance_report.json", acceptance)
    _write_json(out / "phase6_closure_report.json", closure)
    _write_json(out / "phase6f_smoke_command_matrix.json", smoke_commands)
    _write_json(out / "phase6f_analysis_summary.json", summary)
    return summary
