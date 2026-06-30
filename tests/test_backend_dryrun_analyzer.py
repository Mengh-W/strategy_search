# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from strategy_search.backend_dryrun_analyzer import analyze_backend_dryrun, select_guarded_mutation_action


def _contract():
    return {
        "schema_version": "test_contract",
        "actions": [
            {
                "action_id": "sync_001",
                "plan": "SyncPlan",
                "mutation_kind": "validate_existing_set_wait_events",
                "mode": "dry_run_or_verify_only",
            },
            {
                "action_id": "mb_001",
                "plan": "MultiBufferPlan",
                "mutation_kind": "clone_local_buffer_slots_and_replace_uses",
                "mode": "dry_run_first",
                "target": {
                    "target_buffer": "%k_ub",
                    "address_space": "ub",
                    "producer_ops": [{"text": "hivm.hir.load outs(%k_ub)"}],
                    "consumer_ops": [{"text": "hivm.hir.nd2nz ins(%k_ub)"}],
                    "candidate_score": 2,
                },
            },
        ],
    }


def test_fake_backend_is_never_mutation_candidate():
    dry = {
        "schema_version": "fake",
        "is_real_mlir_backend": False,
        "actions": [
            {"action_id": "mb_001", "located": True, "operation_found": True, "blockers": []}
        ],
    }
    report = analyze_backend_dryrun(_contract(), dry)
    assert report["overall_decision"] == "WAIT_FOR_REAL_BACKEND"
    assert any(a["decision"] == "BLOCKED_FAKE_BACKEND" for a in report["actions"] if a["action_id"] == "mb_001")


def test_real_backend_complete_proofs_selects_single_multibuffer_action():
    dry = {
        "schema_version": "realish",
        "is_real_mlir_backend": True,
        "actions": [
            {
                "action_id": "mb_001",
                "located": True,
                "operation_found": True,
                "use_def_resolution_ok": True,
                "all_uses_accounted_for": True,
                "capacity_recheck_passed": True,
                "buffer_liveness_passed": True,
                "post_mutate_verify_expected": True,
                "blockers": [],
            }
        ],
    }
    report = analyze_backend_dryrun(_contract(), dry)
    assert report["overall_decision"] == "HAS_GUARDED_MUTATION_CANDIDATE"
    sel = select_guarded_mutation_action(_contract(), report)
    assert sel["selected"] is True
    assert sel["selected_action_id"] == "mb_001"
    assert len(sel["single_action_contract"]["actions"]) == 1


def test_missing_proofs_blocks_real_backend_action():
    dry = {
        "schema_version": "realish",
        "is_real_mlir_backend": True,
        "actions": [{"action_id": "mb_001", "located": True, "operation_found": True, "blockers": []}],
    }
    report = analyze_backend_dryrun(_contract(), dry)
    mb = [a for a in report["actions"] if a["action_id"] == "mb_001"][0]
    assert mb["decision"] == "BLOCKED_DRY_RUN_PROOF_INCOMPLETE"
    assert "use_def_resolution_ok" in mb["missing_proofs"]
