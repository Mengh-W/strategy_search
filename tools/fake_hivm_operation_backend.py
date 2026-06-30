#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tiny fake Operation-level HIVM backend for local CI/demo only.

This fixture mimics the *CLI contract* expected by Phase-5A/5B.  It is not an
MLIR parser, not HivmOpsEditor, and not a production verifier.  It lets tests
exercise inventory/roundtrip/verify report plumbing before a real backend is
available.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List


def write_json(path: str | None, data: Any) -> None:
    if path:
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def inventory_text(text: str) -> Dict[str, Any]:
    ops: List[Dict[str, Any]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        m = re.search(r"\b([A-Za-z0-9_]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_\.]+|func\.func|scf\.for|return)\b", line)
        if not m:
            continue
        name = m.group(1)
        if name.startswith("hivm.") or name in {"func.func", "scf.for", "return"}:
            ops.append({
                "op_id": len(ops),
                "operation_name": name,
                "source_line": i,
                "text_preview": line.strip()[:240],
                "operand_count": line.count("%"),
                "result_count": 1 if line.strip().startswith("%") else 0,
                "region_path": [],
                "block_id": "fake_block_0",
            })
    return {
        "schema_version": "fake_hivm_operation_inventory_v1",
        "backend": "fake_hivm_operation_backend_ci_fixture",
        "is_real_mlir_backend": False,
        "op_count": len(ops),
        "operations": ops,
    }


def verify_text(text: str) -> tuple[bool, List[str]]:
    errors: List[str] = []
    if "module" not in text:
        errors.append("missing_module_keyword")
    if text.count("{") != text.count("}"):
        errors.append("brace_balance_mismatch")
    if "hivm." not in text:
        errors.append("no_hivm_ops_seen")
    return (not errors), errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--print-capabilities", action="store_true")
    ap.add_argument("--inventory", action="store_true")
    ap.add_argument("--roundtrip", action="store_true")
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument("--mutation-kind")
    ap.add_argument("--max-gm-pairs")
    ap.add_argument("--input")
    ap.add_argument("--output")
    ap.add_argument("--report")
    ap.add_argument("--edit-script")
    args = ap.parse_args()

    if args.print_capabilities:
        print(json.dumps({
            "backend": "fake_hivm_operation_backend_ci_fixture",
            "is_real_mlir_backend": False,
            "inventory": True,
            "roundtrip": True,
            "verify_only": True,
            "dry_run_edit_script": True,
            "production_mutation": False,
            "mutate_q_load_hoist": True,
            "mutation_contract_only": True,
        }, ensure_ascii=False))
        return 0

    text = Path(args.input).read_text(encoding="utf-8") if args.input else ""
    if args.inventory:
        write_json(args.report, inventory_text(text))
        return 0
    if args.roundtrip:
        if not args.output:
            return 2
        Path(args.output).write_text(text, encoding="utf-8")
        write_json(args.report, {
            "schema_version": "fake_hivm_roundtrip_report_v1",
            "backend": "fake_hivm_operation_backend_ci_fixture",
            "is_real_mlir_backend": False,
            "input": args.input,
            "output": args.output,
            "byte_identical": True,
            "status": "passed_fake_roundtrip",
        })
        return 0
    if args.verify_only:
        ok, errors = verify_text(text)
        write_json(args.report, {
            "schema_version": "fake_hivm_verifier_report_v1",
            "backend": "fake_hivm_operation_backend_ci_fixture",
            "is_real_mlir_backend": False,
            "input": args.input,
            "passed": ok,
            "errors": errors,
            "status": "passed_fake_verify" if ok else "failed_fake_verify",
        })
        return 0 if ok else 1
    if args.dry_run:
        edit = {}
        if args.edit_script and Path(args.edit_script).exists():
            try:
                edit = json.loads(Path(args.edit_script).read_text(encoding="utf-8"))
            except Exception:
                edit = {}
        actions = edit.get("actions") or []
        inv = inventory_text(text)
        per_action = []
        for idx, action in enumerate(actions if isinstance(actions, list) else []):
            if not isinstance(action, dict):
                continue
            target = action.get("target") if isinstance(action.get("target"), dict) else {}
            anchors = action.get("anchors") if isinstance(action.get("anchors"), dict) else {}
            target_line = (
                action.get("load_line")
                or target.get("alloc_line")
                or target.get("line")
            )
            # SyncPlan precision contracts often nest anchors deeper than the
            # generic four-plan contract.  This fake backend only does textual
            # location plumbing, but it should still exercise the same JSON
            # shape that the real HivmOpsEditor backend will consume.
            if not target_line and isinstance(target.get("anchor"), dict):
                target_line = target["anchor"].get("line")
            if not target_line and isinstance(target.get("target"), dict) and isinstance(target["target"].get("anchor"), dict):
                target_line = target["target"]["anchor"].get("line")
            if not target_line and isinstance(action.get("event_report"), dict):
                er = action["event_report"]
                for key in ("set_records", "wait_records"):
                    recs = er.get(key)
                    if isinstance(recs, list) and recs:
                        try:
                            target_line = recs[0].get("anchor", {}).get("line")
                            if target_line:
                                break
                        except Exception:
                            pass
            if not target_line and isinstance(action.get("target"), dict) and isinstance(action["target"].get("target"), dict):
                target_line = action["target"]["target"].get("line")
            if not target_line and anchors.get("existing_events"):
                try:
                    target_line = anchors["existing_events"][0].get("line")
                except Exception:
                    target_line = None
            candidate = None
            for op in inv.get("operations", []):
                if target_line and op.get("source_line") == target_line:
                    candidate = op
                    break
            if candidate is None and inv.get("operations"):
                candidate = inv.get("operations")[0]
            per_action.append({
                "action_id": action.get("action_id") or f"fake_action_{idx}",
                "candidate_id": action.get("candidate_id"),
                "target_line": target_line,
                "located": candidate is not None,
                "operation_found": candidate is not None,
                "operation": candidate,
                "dominance_ok": False,
                "region_motion_ok": False,
                "operation_found": candidate is not None,
                "located": candidate is not None,
                "checks": {
                    "backend_parsed_event_operands": False,
                    "event_pairs_reported": bool(action.get("event_report")),
                    "event_liveness_passed": False,
                    "no_deadlock_or_conflict_reported": False,
                    "target_barrier_located_by_backend": bool(target_line and candidate is not None),
                    "producer_consumer_pair_reported": False,
                    "fresh_or_safe_reused_event_reported": False,
                    "backend_can_print_official_set_wait_ops": False,
                    "event_liveness_passes_after_dry_run_plan": False,
                    "backend_reports_sync_block_mode_and_scope": False
                },
                "blockers": [
                    "fake_backend_cannot_prove_event_liveness",
                    "fake_backend_cannot_prove_deadlock_freedom",
                    "fake_backend_cannot_prove_dominance",
                    "fake_backend_cannot_prove_region_motion",
                ],
            })
        write_json(args.report, {
            "schema_version": "fake_hivm_dry_run_report_v2",
            "backend": "fake_hivm_operation_backend_ci_fixture",
            "is_real_mlir_backend": False,
            "input": args.input,
            "edit_script": args.edit_script,
            "production_mutation": False,
            "status": "dry_run_only_fake_backend_no_mutation",
            "action_count": len(actions) if isinstance(actions, list) else 0,
            "located_action_count": sum(1 for a in per_action if a.get("located")),
            "actions": per_action,
        })
        return 0

    if args.mutate:
        # This fixture intentionally refuses to perform a real compiler mutation.
        # It copies input to output so callers can test artifact plumbing, but the
        # report clearly marks the result as non-production and non-mutated.
        if not args.output:
            return 2
        Path(args.output).write_text(text, encoding="utf-8")
        edit = {}
        if args.edit_script and Path(args.edit_script).exists():
            try:
                edit = json.loads(Path(args.edit_script).read_text(encoding="utf-8"))
            except Exception:
                edit = {}
        common_blockers = [
            "fake_backend_is_not_real_mlir_or_hivmopseditor_backend",
            "fake_backend_does_not_perform_mutation",
            "fake_backend_does_not_run_mlir_verifier",
            "fake_backend_does_not_run_des_trace",
        ]
        if args.mutation_kind == "gm_roundtrip_deletion":
            common_blockers.extend([
                "fake_backend_cannot_prove_same_base_static_offset_slice",
                "fake_backend_cannot_prove_memory_effects_or_memoryssa",
                "fake_backend_cannot_prove_non_observable_gm_boundary",
            ])
        else:
            common_blockers.extend([
                "fake_backend_cannot_prove_dominance",
                "fake_backend_cannot_prove_region_motion",
            ])
        write_json(args.report, {
            "schema_version": "fake_hivm_mutation_report_v2",
            "backend": "fake_hivm_operation_backend_ci_fixture",
            "is_real_mlir_backend": False,
            "input": args.input,
            "output": args.output,
            "edit_script": args.edit_script,
            "mutation_kind": args.mutation_kind,
            "mutation_performed": False,
            "mutated": False,
            "deleted_pair_count": 0,
            "verifier_passed": False,
            "dominance_passed": False,
            "region_motion_passed": False,
            "alias_proof_passed": False,
            "same_base_static_offset_slice_passed": False,
            "memoryssa_passed": False,
            "observable_boundary_passed": False,
            "des_trace_after_passed": False,
            "status": "fake_backend_refused_production_mutation_and_copied_input",
            "summary": "Fixture validates the Phase-5D/5E CLI/report contract only. It is not a real MLIR/HivmOpsEditor backend and does not mutate IR.",
            "action_count": len(edit.get("actions") or []) if isinstance(edit, dict) else 0,
            "blockers": common_blockers,
        })
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
