# -*- coding: utf-8 -*-
from strategy_search.sync_rewrite_audit import build_sync_rewrite_audit
from strategy_search.sync_rewrite_executor import apply_restricted_sync_rewrite


def test_sync_rewrite_audit_reports_delta_and_migration_list():
    original = """func.func @k() {\n  hivm.hir.pipe_barrier[<PIPE_MTE2>]\n  hivm.hir.pipe_barrier[<PIPE_ALL>]\n}\n"""
    contract = {
        "schema_version": "hivm_sync_precision_contract_v1",
        "actions": [
            {
                "action_id": "a1",
                "mutation_kind": "barrier_to_directional_event_pair",
                "target": {"anchor": {"line": 2}, "normalized_barrier": {"pipe": "<PIPE_MTE2>"}},
            },
            {
                "action_id": "a2",
                "mutation_kind": "barrier_to_directional_event_pair",
                "target": {"anchor": {"line": 3}, "normalized_barrier": {"pipe": "<PIPE_ALL>"}},
            },
        ],
    }
    rewritten, rewrite = apply_restricted_sync_rewrite(original, contract, max_actions=10, allow_pipe_all=False)
    audit = build_sync_rewrite_audit(
        original,
        rewritten,
        contract,
        rewrite,
        {"passed_portable_validation": True},
        {},
        {"passed_portable_liveness": True},
    )
    assert audit["audit_decision"] == "PORTABLE_REWRITE_AUDITED_NOT_PRODUCTION"
    assert audit["structural_delta"]["pipe_barrier_delta"] == -1
    assert audit["structural_delta"]["set_flag_delta"] == 1
    assert audit["structural_delta"]["wait_flag_delta"] == 1
    assert audit["event_naming"]["all_generated_events_unique"] is True
    assert audit["risk_counts"]["BLOCKED"] == 1
    assert len(audit["hivmopseditor_migration_action_list"]) == 1


def test_sync_rewrite_audit_flags_dense_barrier_region():
    original = """func.func @k() {\n  hivm.hir.pipe_barrier[<PIPE_MTE2>]\n  hivm.hir.pipe_barrier[<PIPE_MTE2>]\n}\n"""
    contract = {
        "actions": [
            {"action_id": "a1", "mutation_kind": "barrier_to_directional_event_pair", "target": {"anchor": {"line": 2}, "normalized_barrier": {"pipe": "<PIPE_MTE2>"}}},
            {"action_id": "a2", "mutation_kind": "barrier_to_directional_event_pair", "target": {"anchor": {"line": 3}, "normalized_barrier": {"pipe": "<PIPE_MTE2>"}}},
        ]
    }
    rewritten, rewrite = apply_restricted_sync_rewrite(original, contract, max_actions=2)
    audit = build_sync_rewrite_audit(original, rewritten, contract, rewrite, {"passed_portable_validation": True}, {}, {"passed_portable_liveness": True})
    assert any("consecutive_or_dense_pipe_barrier_region" in a["warnings"] for a in audit["action_audit"])
