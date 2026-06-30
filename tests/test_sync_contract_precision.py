# -*- coding: utf-8 -*-
import json
from pathlib import Path

from strategy_search.hivm_official_rewrite_plan import build_hivm_inventory
from strategy_search.sync_contract_precision import build_sync_precision_contract


def _selected_plan():
    return {
        "sync_plan": {
            "controllable_knobs": {
                "policy": "graph_sync_solver",
                "event_id_policy": "backend_allocator",
                "sync_motion": "local_move",
                "remove_redundant_sync": True,
            }
        },
        "multibuffer_plan": {"controllable_knobs": {"double_buffer": True, "input_buffer_multiplier": 2, "stage_buffer_multiplier": 2}},
        "cv_pipeline_plan": {"controllable_knobs": {"stage_num": 2}},
        "tiling_plan": {"controllable_knobs": {"tile_m": 32, "tile_n": 64, "tile_k": 128}},
    }


def test_sync_precision_contract_reads_legacy_events_in_fa_best():
    ir = Path("sample_input/fa_best.hivm.mlir").read_text(encoding="utf-8")
    inv = build_hivm_inventory(ir, "fa_best")
    contract = build_sync_precision_contract(_selected_plan(), inv)
    sync_inv = contract["normalized_sync_inventory"]
    assert contract["schema_version"] == "hivm_sync_precision_contract_v1"
    assert sync_inv["num_event_records"] >= 2
    assert sync_inv["num_event_pair_reports"] >= 1
    assert any(a["mutation_kind"] == "validate_existing_event_pair_liveness" for a in contract["actions"])
    assert contract["global_backend_policy"]["real_mutation_owner"] == "vTriton/HivmOpsEditor backend"


def test_sync_precision_contract_builds_barrier_actions():
    ir = """
module {
  %0 = hivm.hir.load ins(%gm : memref<128xf16>) outs(%ub : memref<128xf16>)
  hivm.hir.pipe_barrier [PIPE_MTE2]
  %1 = hivm.hir.vadd ins(%ub, %ub : memref<128xf16>, memref<128xf16>) outs(%out : memref<128xf16>)
}
"""
    inv = build_hivm_inventory(ir, "barrier_case")
    contract = build_sync_precision_contract(_selected_plan(), inv)
    assert contract["normalized_sync_inventory"]["num_barrier_records"] == 1
    barrier_actions = [a for a in contract["actions"] if a["mutation_kind"] == "barrier_to_directional_event_pair"]
    assert barrier_actions
    action = barrier_actions[0]
    assert action["mutation_allowed"] is False
    assert "target_op_index_or_operation_id" in action["required_backend_proofs"]
    assert "producer_consumer_pair_reported" in action["acceptance"]


def test_sync_precision_contract_classifies_sync_blocks_without_mutation():
    ir = """
module {
  hivm.hir.sync_block_wait [ALL]
  hivm.hir.sync_block_set [ALL]
}
"""
    inv = build_hivm_inventory(ir, "sync_block_case")
    contract = build_sync_precision_contract(_selected_plan(), inv)
    assert contract["normalized_sync_inventory"]["num_sync_block_records"] == 2
    assert all(a["mutation_allowed"] is False for a in contract["actions"])
    assert any(a["mutation_kind"] == "classify_sync_block_scope" for a in contract["actions"])
