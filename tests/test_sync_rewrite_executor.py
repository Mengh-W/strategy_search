# -*- coding: utf-8 -*-
from strategy_search.sync_rewrite_executor import apply_restricted_sync_rewrite, select_rewritable_sync_actions


def _contract():
    return {
        "schema_version": "hivm_sync_precision_contract_v1",
        "actions": [
            {
                "action_id": "sync_dryrun_barrier_001_line_3",
                "mutation_kind": "barrier_to_directional_event_pair",
                "target": {
                    "anchor": {"line": 3, "op": "hivm.hir.pipe_barrier"},
                    "normalized_barrier": {"set_pipe": "<PIPE_MTE2>"},
                },
            }
        ],
    }


def test_select_rewritable_barrier_action():
    actions = select_rewritable_sync_actions(_contract())
    assert len(actions) == 1
    assert actions[0]["_rewrite_line"] == 3
    assert actions[0]["_rewrite_pipe"] == "PIPE_MTE2"


def test_apply_restricted_sync_rewrite_replaces_pipe_barrier():
    text = "module {\n  func.func @k() {\n    hivm.hir.pipe_barrier[<PIPE_MTE2>]\n  }\n}\n"
    new_text, report = apply_restricted_sync_rewrite(text, _contract())
    assert "hivm.hir.pipe_barrier[<PIPE_MTE2>]" in new_text  # preserved in comment
    assert "hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_MTE2>, EVENT_ID_AUTO0]" in new_text
    assert "hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_MTE2>, EVENT_ID_AUTO0]" in new_text
    assert report["mutation_performed"] is True
    assert report["production_rewrite_claim_allowed"] is False


def test_pipe_all_is_skipped_by_default():
    contract = {
        "schema_version": "hivm_sync_precision_contract_v1",
        "actions": [{
            "action_id": "sync_dryrun_barrier_001_line_3",
            "mutation_kind": "barrier_to_directional_event_pair",
            "target": {"anchor": {"line": 3}, "normalized_barrier": {"set_pipe": "<PIPE_ALL>"}},
        }],
    }
    text = "module {\n  func.func @k() {\n    hivm.hir.pipe_barrier[<PIPE_ALL>]\n  }\n}\n"
    new_text, report = apply_restricted_sync_rewrite(text, contract)
    assert new_text == text
    assert report["mutation_performed"] is False
