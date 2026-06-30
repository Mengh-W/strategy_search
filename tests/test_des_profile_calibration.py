# -*- coding: utf-8 -*-
from __future__ import annotations

from strategy_search.des_profile import (
    summarize_des_trace,
    build_single_trace_calibration,
    apply_single_trace_calibration_to_cost,
)


def test_des_profile_summary_from_prefill_example():
    s = summarize_des_trace("artifacts/optional_profiles/prefill_des.json", mlir_file="sample_input/kernel_001.npuir.mlir", sample_id="unit_prefill")
    assert s.sample_id == "unit_prefill"
    assert s.num_ops > 0
    assert s.makespan_cycles > 0
    assert s.total_duration_cycles >= s.makespan_cycles
    assert 0.0 <= s.observed_overlap_ratio < 1.0
    assert s.dominant_pipe
    assert s.sync_count >= s.barrier_count


def test_single_trace_calibration_scales_cost_and_records_audit():
    s = summarize_des_trace("artifacts/optional_profiles/prefill_des.json", sample_id="unit_prefill")
    calibration = build_single_trace_calibration(s, current_analytical_cycles=s.makespan_cycles / 2.0)
    assert calibration["enabled"] is True
    assert abs(calibration["global_scale"] - 2.0) < 1e-9

    cost = {
        "predicted_cycles": 100.0,
        "tau_load": 10.0,
        "tau_store": 10.0,
        "tau_cube": 20.0,
        "tau_vector": 20.0,
        "n_tiles": 1.0,
        "effective_parallelism": 1.0,
        "improvement_attribution": {
            "optimistic_savings_proxies_per_tile": {
                "load_overlap_saving": 1.0,
                "store_overlap_saving": 1.0,
                "cv_overlap_saving": 1.0,
            }
        },
        "cost_breakdown": {},
    }
    out = apply_single_trace_calibration_to_cost(cost, calibration)
    assert out["des_calibrated"] is True
    assert out["analytical_predicted_cycles_before_des_calibration"] == 100.0
    assert out["predicted_cycles"] >= 200.0
    assert out["des_calibration"]["sample_id"] == "unit_prefill"
