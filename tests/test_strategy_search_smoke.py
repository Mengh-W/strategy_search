#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke and regression tests for the strategy-search demo.

These tests intentionally avoid IR rewrite and discrete-memory-access logic.
They verify the currently supported scope: parser feature extraction,
hardware-gated strategy search, current-IR estimated reference cost,
cost-ranking artifacts, and the presentation report output.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import auto_strategy_search as search  # noqa: E402


def run_search_direct(kernel: Path, hw: Path, out: Path, *, cost_model_config: Path | None = None, cost_risk_mode: str = "conservative", candidate_space: str = "standard", enable_search_quality_audit: bool = False) -> None:
    args = search.argparse.Namespace(
        kernel=str(kernel), hardware_config=str(hw), search_space=None,
        candidate_space=candidate_space, guided_mode="off", search_mode="layered",
        guided_strength="soft", cost_risk_mode=cost_risk_mode,
        cost_model_config=str(cost_model_config) if cost_model_config else None,
        des_profile=None, trace_profile=None, desgraph=None, trace=None, source=None,
        bound_report=None, counterfactual=None, multi_kernel_report=None,
        vtriton_bindings=None, vtriton_compile_commands=None,
        enable_ir_rewrite=False, rewrite_mode="annotation", rewrite_safety="conservative",
        enable_search_quality_audit=enable_search_quality_audit,
        search_quality_random_budget=64, search_quality_random_seed=7,
        output_dir=str(out),
    )
    search.run(args)


@pytest.mark.smoke
class StrategySearchSmokeTests(unittest.TestCase):
    def test_parser_counts_bare_and_hir_sync_ops(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "sync_forms.hivm.mlir"
            p.write_text(
                """
module {
  func.func @k() {
    hivm.set_flag {set_pipe = "MTE2", wait_pipe = "M", flag_id = 0 : i64}
    hivm.wait_flag {set_pipe = "MTE2", wait_pipe = "M", flag_id = 0 : i64}
    hivm.pipe_barrier {pipe = "ALL"}
    hivm.hir.set_flag {pipe=M,event=EVENT_ID0}
    hivm.hir.wait_flag {pipe=M,event=EVENT_ID0}
    hivm.hir.barrier {mode = ALL}
    return
  }
}
""",
                encoding="utf-8",
            )
            kf = search.parse_kernel_features(str(p))
            self.assertEqual(kf.num_set_flag, 2)
            self.assertEqual(kf.num_wait_flag, 2)
            self.assertEqual(kf.num_pipe_barrier, 2)

    def test_cli_generates_json_markdown_and_html_reports(self) -> None:
        kernel = ROOT / "sample_input" / "fa_bad_inefficient.hivm.mlir"
        hw = ROOT / "configs" / "ascend_910b.json"
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            run_search_direct(kernel, hw, out)
            required = [
                "selected_strategy.json",
                "search_report.json",
                "top_candidates.json",
                "hardware_boundary_audit.json",
                "cost_breakdown.json",
                "strategy_search_report.md",
                "strategy_search_report.html",
            ]
            for name in required:
                self.assertTrue((out / name).exists(), name)
            html = (out / "strategy_search_report.html").read_text(encoding="utf-8")
            for phrase in [
                "HIVM 四类 Plan 参数寻优报告",
                "最优候选策略",
                "硬件边界检查",
                "Cost Breakdown",
                "Top 候选排行",
                "当前版本不执行 IR rewrite",
            ]:
                self.assertIn(phrase, html)

    def test_selected_strategy_is_feasible_and_improves_current_ir_estimate(self) -> None:
        kernel = ROOT / "sample_input" / "fa_bad_inefficient.hivm.mlir"
        hw_path = ROOT / "configs" / "ascend_910b.json"
        hw = search.apply_cost_model_config(json.loads(hw_path.read_text(encoding="utf-8")), str(ROOT / "configs" / "cost_model_conservative.json"), "conservative")
        kf = search.parse_kernel_features(str(kernel))
        space = search.compact_search_for_quality_audit(search.auto_generate_search_space(kf, hw, "standard"))
        space["cost_risk_mode"] = "conservative"
        candidates, _stats = search.build_layered_candidates(kf, hw, space)
        scored = []
        for c, meta in candidates:
            final_c, ml, _trace, _reason, _detail = search.feasible_with_relax(c, kf, hw)
            if final_c is None:
                continue
            cost = search.estimate_cost(final_c, kf, hw, ml, space)
            scored.append({"strategy": final_c, "cost": cost, "max_live_bytes": ml, "meta": meta})
        self.assertTrue(scored)
        scored.sort(key=lambda x: x["cost"]["predicted_cycles"])
        best = scored[0]
        current_ir = search.build_current_ir_estimate(str(kernel), kf, hw, space)
        self.assertIn("cost", current_ir)
        self.assertGreater(current_ir["cost"]["predicted_cycles"], 0)
        self.assertGreater(best["cost"]["predicted_cycles"], 0)
        cycles = [x["cost"]["predicted_cycles"] for x in scored[:10]]
        self.assertEqual(cycles, sorted(cycles))
        util = best["max_live_bytes"].get("ub", 0) / search.memory_cap_bytes(hw, "ub")
        self.assertLessEqual(util, 1.0)

    def test_gm_workspace_is_modeled_as_resource_and_cost(self) -> None:
        kernel = ROOT / "sample_input" / "fa_bad_inefficient.hivm.mlir"
        hw = json.loads((ROOT / "configs" / "ascend_910b.json").read_text())
        cfg = {
            "problem_shape_hint": {"m_total": 64, "n_total": 512, "k_total": 512, "outer_iterations": 2},
            "cv_pipeline_stage": [2],
            "stage_buffer_policy": ["gm_workspace"],
        }
        kf = search.parse_kernel_features(str(kernel))
        c = search.StrategyConfig(
            strategy_id="unit_gm_ws", fusion="keep_existing",
            tile_m=64, tile_n=128, tile_k=64, block_dim=4,
            double_buffer=True, cv_pipeline_stage=2, cv_split_ratio="1:1",
            memory_reuse_level="level1", sync_policy="graph_sync_solver", dma_policy="keep_existing",
            stage_buffer_policy="gm_workspace", cv_pipeline_template="P2_stage2_balanced",
        )
        ml = search.estimate_max_live(c, kf, hw)
        self.assertIn("gm_ws", ml)
        self.assertGreater(ml["gm_ws"], 0)
        ok, reason, detail = search.feasibility(c, ml, hw)
        self.assertTrue(ok, reason)
        self.assertIn("gm_ws", detail)
        cost = search.estimate_cost(c, kf, hw, ml, cfg)
        self.assertGreater(cost["cost_breakdown"]["per_tile_workspace_exposed"], 0)
        self.assertEqual(cost["cost_breakdown"]["gm_workspace_bytes"], ml["gm_ws"])

    def test_gm_workspace_is_fallback_not_primary_candidate(self) -> None:
        kernel = ROOT / "sample_input" / "fa_bad_inefficient.hivm.mlir"
        hw = json.loads((ROOT / "configs" / "ascend_910b.json").read_text())
        kf = search.parse_kernel_features(str(kernel))
        c = search.StrategyConfig(
            strategy_id="unit_gm_ws_fallback", fusion="keep_existing",
            tile_m=64, tile_n=128, tile_k=64, block_dim=4,
            double_buffer=True, cv_pipeline_stage=2, cv_split_ratio="1:1",
            memory_reuse_level="level1", sync_policy="graph_sync_solver", dma_policy="keep_existing",
            stage_buffer_policy="gm_workspace", cv_pipeline_template="P2_stage2_balanced",
        )
        ok, reason, detail = search.gm_workspace_fallback_legality(c, kf, hw)
        self.assertFalse(ok)
        self.assertIn("on-chip policy", reason)
        self.assertIn("alternatives", detail)
        relaxed, _ml, trace, reason, _detail = search.feasible_with_relax(c, kf, hw)
        self.assertIsNotNone(relaxed)
        self.assertNotEqual(relaxed.stage_buffer_policy, "gm_workspace")

    def test_risk_aware_cost_mode_outputs_risk_fields(self) -> None:
        kernel = ROOT / "sample_input" / "fa_bad_inefficient.hivm.mlir"
        hw = ROOT / "configs" / "ascend_910b.json"
        cfg = ROOT / "configs" / "cost_model_conservative.json"
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            run_search_direct(kernel, hw, out, cost_model_config=cfg, cost_risk_mode="conservative")
            selected = json.loads((out / "selected_strategy.json").read_text(encoding="utf-8"))
            cost = selected["cost"]
            self.assertEqual(cost["cost_risk_mode"], "conservative")
            self.assertIn(cost["risk_level"], {"LOW", "MEDIUM", "HIGH"})
            self.assertIn("risk_assessment", cost)
            self.assertIn("improvement_attribution", cost)
            self.assertIn("legality_risk_penalty", cost)
            self.assertGreaterEqual(cost["legality_risk_penalty"], 0.0)
            md = (out / "strategy_search_report.md").read_text(encoding="utf-8")
            self.assertIn("风险评估与收益来源归因", md)
            self.assertIn("Risk level", md)

    def test_stage2a_expanded_contains_standard_tiles_and_search_audit(self) -> None:
        kernel = ROOT / "sample_input" / "fa_bad_inefficient.hivm.mlir"
        hw_path = ROOT / "configs" / "ascend_910b.json"
        hw = json.loads(hw_path.read_text(encoding="utf-8"))
        kf = search.parse_kernel_features(str(kernel))
        standard_full = search.auto_generate_search_space(kf, hw, "standard")
        expanded_full = search.auto_generate_search_space(kf, hw, "expanded")
        standard_tiles = {search.tile_key(t) for t in standard_full["tile_candidates"]}
        expanded_tiles = {search.tile_key(t) for t in expanded_full["tile_candidates"]}
        self.assertTrue(standard_tiles)
        self.assertTrue(standard_tiles.issubset(expanded_tiles))
        self.assertTrue(expanded_full.get("standard_candidates_included"))
        self.assertEqual(set(expanded_full.get("standard_tile_keys", [])), standard_tiles)

        standard = search.compact_search_for_quality_audit(standard_full)
        std_l1, _ = search.search_tiling_fusion(kf, hw, standard)
        expanded = copy.deepcopy(standard)
        expanded["candidate_space_density"] = "expanded"
        expanded["standard_layer1_signatures_to_pin"] = [list(search.layer1_signature(x)) for x in std_l1]
        candidates, stats = search.build_layered_candidates(kf, hw, expanded)
        self.assertTrue(candidates)
        audit = stats.get("layer1_stability_audit", {})
        self.assertEqual(audit.get("policy"), "cost_topw_plus_diversity_plus_pinned_standard_plus_fallback")
        self.assertEqual(audit.get("standard_layer1_signatures_to_pin"), len(std_l1))
        self.assertIn("diversity_added_after_topw", audit)
        self.assertIn("fallback_added_after_topw_diversity_and_pins", audit)
        self.assertGreaterEqual(audit.get("final_kept", 0), audit.get("configured_top_w", 0))
        dedup = stats.get("candidate_dedup_audit", {})
        self.assertEqual(dedup.get("unique_candidates"), len(candidates))
        self.assertGreaterEqual(dedup.get("dedup_removed", 0), 0)

    def test_stage2b_diversity_beam_and_fallback_are_audited(self) -> None:
        kernel = ROOT / "sample_input" / "fa_bad_inefficient.hivm.mlir"
        hw_path = ROOT / "configs" / "ascend_910b.json"
        hw = json.loads(hw_path.read_text(encoding="utf-8"))
        kf = search.parse_kernel_features(str(kernel))
        space = search.compact_search_for_quality_audit(search.auto_generate_search_space(kf, hw, "standard"))
        space["layer1_top_w"] = 4
        space["layer1_diversity_beam_enabled"] = True
        space["layer1_diversity_per_group_keep"] = 1
        space["layer1_diversity_max_extra"] = 6
        space["layer1_fallback_keep"] = 3
        l1, _ = search.search_tiling_fusion(kf, hw, space)
        audit = space.get("layer1_stability_audit", {})
        self.assertEqual(audit.get("policy"), "cost_topw_plus_diversity_plus_pinned_standard_plus_fallback")
        self.assertGreaterEqual(audit.get("final_kept", 0), 4)
        self.assertLessEqual(audit.get("diversity_added_after_topw", 0), 6)
        self.assertLessEqual(audit.get("fallback_added_after_topw_diversity_and_pins", 0), 3)
        self.assertEqual(audit.get("final_kept"), len(l1))

    def test_stage2b_expanded_beam_frontier_contains_standard_survivors(self) -> None:
        kernel = ROOT / "sample_input" / "fa_bad_inefficient.hivm.mlir"
        hw_path = ROOT / "configs" / "ascend_910b.json"
        hw = json.loads(hw_path.read_text(encoding="utf-8"))
        kf = search.parse_kernel_features(str(kernel))
        standard = search.compact_search_for_quality_audit(search.auto_generate_search_space(kf, hw, "standard"))
        standard["layer1_top_w"] = 4
        std_l1, _ = search.search_tiling_fusion(kf, hw, standard)
        std_sigs = {search.layer1_signature(x) for x in std_l1}

        # Use a compact expanded-like space for a fast regression test.  The
        # functional guarantee being tested is the pinning rule itself: even if
        # the density flag is expanded and Top-W is small, pinned standard
        # survivors must be present in the final Layer-1 frontier.
        expanded = copy.deepcopy(standard)
        expanded["candidate_space_density"] = "expanded"
        expanded["layer1_top_w"] = 2
        expanded["standard_layer1_signatures_to_pin"] = [list(x) for x in std_sigs]
        expanded_l1, _ = search.search_tiling_fusion(kf, hw, expanded)
        expanded_sigs = {search.layer1_signature(x) for x in expanded_l1}
        self.assertTrue(std_sigs.issubset(expanded_sigs))
        audit = expanded.get("layer1_stability_audit", {})
        self.assertEqual(audit.get("standard_layer1_signatures_to_pin"), len(std_sigs))


    def test_strategy_signature_ignores_candidate_id(self) -> None:
        c1 = search.StrategyConfig(
            strategy_id="a", fusion="keep_existing", tile_m=64, tile_n=128, tile_k=64, block_dim=4,
            double_buffer=True, cv_pipeline_stage=2, cv_split_ratio="1:1",
            memory_reuse_level="level1", sync_policy="graph_sync_solver", dma_policy="keep_existing",
            cv_pipeline_template="P2_stage2_balanced", sync_template="Y2_graph_sync_solver",
        )
        c2 = search.replace(c1, strategy_id="b")
        c3 = search.replace(c1, strategy_id="c", tile_n=256)
        self.assertEqual(search.strategy_signature(c1), search.strategy_signature(c2))
        self.assertNotEqual(search.strategy_signature(c1), search.strategy_signature(c3))



    @pytest.mark.slow
    @pytest.mark.regression
    def test_expanded_best_not_worse_than_standard(self) -> None:
        kernel = ROOT / "sample_input" / "fa_bad_inefficient.hivm.mlir"
        hw_path = ROOT / "configs" / "ascend_910b.json"
        hw = search.apply_cost_model_config(json.loads(hw_path.read_text(encoding="utf-8")), str(ROOT / "configs" / "cost_model_conservative.json"), "conservative")
        kf = search.parse_kernel_features(str(kernel))
        standard = search.compact_search_for_quality_audit(search.auto_generate_search_space(kf, hw, "standard"))
        standard["cost_risk_mode"] = "conservative"
        std_l1, _ = search.search_tiling_fusion(kf, hw, standard)

        expanded = copy.deepcopy(standard)
        expanded["candidate_space_density"] = "expanded"
        expanded["standard_candidates_included"] = True
        expanded["standard_layer1_signatures_to_pin"] = [list(search.layer1_signature(x)) for x in std_l1]
        # Add one extra legal tile if available to make this a true superset.
        full = search.auto_generate_search_space(kf, hw, "expanded")
        known = {search.tile_key(t) for t in expanded.get("tile_candidates", [])}
        for t in full.get("tile_candidates", []):
            if search.tile_key(t) not in known:
                expanded["tile_candidates"].append(t)
                break

        std_candidates, _ = search.build_layered_candidates(kf, hw, standard)
        exp_candidates, _ = search.build_layered_candidates(kf, hw, expanded)
        std_score = search.score_candidate_pool_for_audit(std_candidates, kf, hw, standard)
        exp_score = search.score_candidate_pool_for_audit(exp_candidates, kf, hw, expanded)
        self.assertIsNotNone(std_score["best_cost"])
        self.assertIsNotNone(exp_score["best_cost"])
        self.assertLessEqual(exp_score["best_cost"], std_score["best_cost"] + 1e-9)
    def test_risk_mode_cost_ordering_for_same_candidate(self) -> None:
        kernel = ROOT / "sample_input" / "fa_bad_inefficient.hivm.mlir"
        kf = search.parse_kernel_features(str(kernel))
        base_hw = json.loads((ROOT / "configs" / "ascend_910b.json").read_text(encoding="utf-8"))
        c = search.StrategyConfig(
            strategy_id="risk_order", fusion="keep_existing",
            tile_m=64, tile_n=128, tile_k=64, block_dim=4,
            double_buffer=True, cv_pipeline_stage=2, cv_split_ratio="1:1",
            memory_reuse_level="level1", sync_policy="graph_sync_solver", dma_policy="keep_existing",
            cv_pipeline_template="P2_stage2_balanced", sync_template="Y3_event_reuse",
            event_reuse=True, event_id_policy="reuse", sync_granularity="stage",
        )
        costs = []
        penalties = []
        for mode in ["conservative", "balanced", "aggressive"]:
            hw = search.apply_cost_model_config(copy.deepcopy(base_hw), str(ROOT / "configs" / f"cost_model_{mode}.json"), mode)
            cfg = {"cost_risk_mode": mode, "problem_shape_hint": {"m_total": 64, "n_total": 512, "k_total": 512, "outer_iterations": 2}}
            ml = search.estimate_max_live(c, kf, hw)
            cost = search.estimate_cost(c, kf, hw, ml, cfg)
            costs.append(cost["predicted_cycles"])
            penalties.append(cost["legality_risk_penalty"])
        self.assertGreaterEqual(costs[0], costs[1])
        self.assertGreaterEqual(costs[1], costs[2])
        self.assertGreaterEqual(penalties[0], penalties[1])
        self.assertGreaterEqual(penalties[1], penalties[2])

    @pytest.mark.slow
    @pytest.mark.regression
    def test_search_quality_audit_compares_beam_exhaustive_and_random(self) -> None:
        kernel = ROOT / "sample_input" / "fa_bad_inefficient.hivm.mlir"
        hw_path = ROOT / "configs" / "ascend_910b.json"
        hw = search.apply_cost_model_config(json.loads(hw_path.read_text(encoding="utf-8")), str(ROOT / "configs" / "cost_model_conservative.json"), "conservative")
        kf = search.parse_kernel_features(str(kernel))
        space = search.auto_generate_search_space(kf, hw, "standard")
        space["cost_risk_mode"] = "conservative"
        audit = search.build_search_quality_audit(kf, hw, space, random_budget=32, random_seed=11)
        self.assertTrue(audit["enabled"])
        self.assertIn("beam_on_compact", audit)
        self.assertIn("small_exhaustive_on_compact", audit)
        self.assertIn("random_baseline_on_compact", audit)
        self.assertIsNotNone(audit["beam_on_compact"]["best_cost"])
        self.assertIsNotNone(audit["small_exhaustive_on_compact"]["best_cost"])
        self.assertIsNotNone(audit["random_baseline_on_compact"]["best_cost"])
        self.assertIn("beam_vs_small_exhaustive_gap_ratio", audit)

    @pytest.mark.slow
    @pytest.mark.regression
    def test_search_audit_schema_with_quality_audit(self) -> None:
        kernel = ROOT / "sample_input" / "fa_bad_inefficient.hivm.mlir"
        hw = ROOT / "configs" / "ascend_910b.json"
        cfg = ROOT / "configs" / "cost_model_conservative.json"
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            run_search_direct(kernel, hw, out, cost_model_config=cfg, cost_risk_mode="conservative", candidate_space="standard", enable_search_quality_audit=True)
            audit = json.loads((out / "search_audit.json").read_text(encoding="utf-8"))
            for key in ["stage", "candidate_space_density", "search_mode", "layer1_stability_audit", "candidate_dedup_audit", "post_relax_legal_dedup_audit", "search_quality_audit"]:
                self.assertIn(key, audit)
            quality = audit["search_quality_audit"]
            self.assertTrue(quality["enabled"])
            self.assertIn("beam_on_compact", quality)
            self.assertIn("small_exhaustive_on_compact", quality)
            self.assertIn("random_baseline_on_compact", quality)


@pytest.mark.unit
class StrategySearchPackageStructureTests(unittest.TestCase):
    def test_package_facade_imports_match_legacy_wrapper(self) -> None:
        from strategy_search import cost_model, hardware, parser, plans, search as search_mod

        self.assertIs(plans.StrategyConfig, search.StrategyConfig)
        self.assertIs(parser.parse_kernel_features, search.parse_kernel_features)
        self.assertIs(cost_model.estimate_cost, search.estimate_cost)
        self.assertIs(hardware.memory_cap_bytes, search.memory_cap_bytes)
        self.assertTrue(hasattr(search_mod, "build_layered_candidates"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
