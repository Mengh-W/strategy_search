#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fast unit tests for Plan-parameter sensitivity and hardware gates.

These tests are deliberately local and deterministic.  They do not run the full
layered search.  Their purpose is to catch the most dangerous regression for
this project: a Plan knob appears in the search space, but stops affecting the
hardware model or cost breakdown.
"""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import pytest

import auto_strategy_search as search

ROOT = Path(__file__).resolve().parents[1]


def make_candidate(**overrides) -> search.StrategyConfig:
    base = dict(
        strategy_id="unit_candidate",
        fusion="keep_existing",
        tile_m=64,
        tile_n=128,
        tile_k=64,
        block_dim=4,
        double_buffer=False,
        cv_pipeline_stage=1,
        cv_split_ratio="1:1",
        memory_reuse_level="level1",
        sync_policy="keep_existing",
        dma_policy="keep_existing",
        multibuffer_template="M0_no_multibuffer",
        cv_pipeline_template="P0_no_cv_pipeline",
        sync_template="Y0_keep_existing",
    )
    base.update(overrides)
    return search.StrategyConfig(**base)


@pytest.mark.unit
class CostModelUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.kf = search.parse_kernel_features(str(ROOT / "sample_input" / "fa_bad_inefficient.hivm.mlir"))
        base_hw = json.loads((ROOT / "configs" / "ascend_910b.json").read_text(encoding="utf-8"))
        cls.hw = search.apply_cost_model_config(base_hw, str(ROOT / "configs" / "cost_model_conservative.json"), "conservative")

    def setUp(self) -> None:
        self.space = {
            "cost_risk_mode": "conservative",
            "problem_shape_hint": {"m_total": 64, "n_total": 512, "k_total": 512, "outer_iterations": 2},
        }

    def score(self, c: search.StrategyConfig) -> tuple[dict, dict]:
        ml = search.estimate_max_live(c, self.kf, self.hw)
        return search.estimate_cost(c, self.kf, self.hw, ml, self.space), ml

    def test_tiling_plan_changes_tile_count_and_local_memory(self) -> None:
        large_tile = make_candidate(tile_m=64, tile_n=128, tile_k=64)
        small_tile = make_candidate(tile_m=32, tile_n=64, tile_k=64)
        large_cost, large_ml = self.score(large_tile)
        small_cost, small_ml = self.score(small_tile)

        self.assertGreater(small_cost["n_tiles"], large_cost["n_tiles"])
        self.assertLess(small_ml["ub"], large_ml["ub"])
        self.assertLess(small_ml["l0c"], large_ml["l0c"])

    def test_block_dim_changes_effective_parallelism_and_parallelized_cycles(self) -> None:
        low_parallel = make_candidate(block_dim=4)
        high_parallel = make_candidate(block_dim=16)
        low_cost, _ = self.score(low_parallel)
        high_cost, _ = self.score(high_parallel)

        self.assertGreater(high_cost["effective_parallelism"], low_cost["effective_parallelism"])
        self.assertLess(high_cost["cost_breakdown"]["parallelized_tile_cycles"], low_cost["cost_breakdown"]["parallelized_tile_cycles"])

    def test_multibuffer_plan_reduces_exposed_load_store_but_increases_live_memory(self) -> None:
        no_buffer = make_candidate(double_buffer=False, multibuffer_template="M0_no_multibuffer")
        double_buffer = make_candidate(double_buffer=True, multibuffer_template="M1_input_double_buffer")
        base_cost, base_ml = self.score(no_buffer)
        db_cost, db_ml = self.score(double_buffer)

        self.assertLess(db_cost["load_exposed"], base_cost["load_exposed"])
        self.assertLess(db_cost["store_exposed"], base_cost["store_exposed"])
        self.assertGreater(db_ml["ub"], base_ml["ub"])

    def test_cv_pipeline_plan_affects_cube_vector_time_and_risk_penalty(self) -> None:
        no_pipeline = make_candidate(cv_pipeline_stage=1, cv_pipeline_template="P0_no_cv_pipeline")
        stage2 = make_candidate(cv_pipeline_stage=2, cv_pipeline_template="P2_stage2_balanced")
        base_cost, _ = self.score(no_pipeline)
        cv_cost, _ = self.score(stage2)

        self.assertLess(cv_cost["cube_vector_time"], base_cost["cube_vector_time"])
        self.assertGreater(cv_cost["cv_estimated_penalty"], 0)
        self.assertIn("CVPipeline", " ".join(cv_cost["risk_assessment"].get("risk_reasons", [])))

    def test_sync_plan_changes_sync_cost_and_legality_risk(self) -> None:
        keep_existing = make_candidate(sync_policy="keep_existing", sync_template="Y0_keep_existing")
        graph_sync = make_candidate(sync_policy="graph_sync_solver", sync_template="Y2_graph_sync_solver")
        keep_cost, _ = self.score(keep_existing)
        graph_cost, _ = self.score(graph_sync)

        self.assertLess(graph_cost["sync_cost"], keep_cost["sync_cost"])
        self.assertGreater(graph_cost["sync_unknown_penalty"], 0)
        self.assertGreater(graph_cost["legality_risk_penalty"], keep_cost["legality_risk_penalty"])

    def test_event_reuse_changes_sync_cost_and_adds_explicit_risk(self) -> None:
        graph_sync = make_candidate(sync_policy="graph_sync_solver", sync_template="Y2_graph_sync_solver")
        event_reuse = make_candidate(
            sync_policy="graph_sync_solver",
            sync_template="Y3_event_reuse",
            event_reuse=True,
            event_id_policy="reuse",
            sync_granularity="stage",
        )
        graph_cost, _ = self.score(graph_sync)
        reuse_cost, _ = self.score(event_reuse)

        self.assertLess(reuse_cost["sync_cost"], graph_cost["sync_cost"])
        self.assertGreater(reuse_cost["event_reuse_penalty"], 0)
        self.assertIn(reuse_cost["risk_assessment"]["risk_level"], {"MEDIUM", "HIGH"})

    def test_hardware_gate_rejects_capacity_overflow_and_accepts_boundary_fit(self) -> None:
        c = make_candidate()
        hw = copy.deepcopy(self.hw)
        ub_cap = search.memory_cap_bytes(hw, "ub")
        boundary_live = {scope: 0 for scope in search.RESOURCE_SCOPES}
        boundary_live["ub"] = ub_cap
        overflow_live = dict(boundary_live)
        overflow_live["ub"] = ub_cap + 32

        ok, reason, _detail = search.feasibility(c, boundary_live, hw)
        self.assertTrue(ok, reason)
        ok, reason, detail = search.feasibility(c, overflow_live, hw)
        self.assertFalse(ok)
        self.assertEqual(reason, "UB overflow")
        self.assertGreater(detail["ub"]["required_kb"], detail["ub"]["available_kb"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
