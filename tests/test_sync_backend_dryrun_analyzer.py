# -*- coding: utf-8 -*-
from strategy_search.sync_backend_dryrun_analyzer import analyze_sync_backend_dryrun


def _contract():
    return {
        "schema_version": "hivm_sync_precision_contract_v1",
        "actions": [
            {
                "action_id": "sync_check_event_EVENT_ID0",
                "plan": "SyncPlan",
                "mutation_kind": "validate_existing_event_pair_liveness",
                "mode": "verify_or_dry_run_only",
                "mutation_allowed": False,
            }
        ],
    }


def test_fake_backend_sync_check_is_never_mutation_ready():
    dry = {
        "schema_version": "fake_hivm_dry_run_report_v2",
        "is_real_mlir_backend": False,
        "actions": [{"action_id": "sync_check_event_EVENT_ID0", "operation_found": True, "located": True}],
    }
    out = analyze_sync_backend_dryrun(_contract(), dry)
    assert out["overall_decision"] == "WAIT_FOR_REAL_BACKEND"
    assert out["actions"][0]["decision"] == "FAKE_BACKEND_CHECK_ONLY"


def test_real_backend_complete_sync_proofs_still_guarded():
    dry = {
        "schema_version": "hivm_operation_backend_dryrun_v2",
        "is_real_mlir_backend": True,
        "actions": [{
            "action_id": "sync_check_event_EVENT_ID0",
            "operation_found": True,
            "located": True,
            "checks": {
                "backend_parsed_event_operands": True,
                "event_pairs_reported": True,
                "event_liveness_passed": True,
                "no_deadlock_or_conflict_reported": True,
            },
        }],
    }
    out = analyze_sync_backend_dryrun(_contract(), dry)
    assert out["overall_decision"] == "REAL_BACKEND_SYNC_PROOFS_AVAILABLE_REVIEW_REQUIRED"
    assert out["actions"][0]["decision"] == "SYNC_DRY_RUN_PROOFS_COMPLETE_MUTATION_STILL_GUARDED"
