# -*- coding: utf-8 -*-
"""Prefill-A5 S0-S9 多阶段实测数据的 benchmark/校准测试。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.prefill_a5_stage_benchmark import run


ROOT = Path(__file__).resolve().parents[1]


def test_prefill_a5_stage_labels_are_complete():
    labels = json.loads((ROOT / "profiles/prefill_a5/prefill_a5_stage_labels.json").read_text(encoding="utf-8"))
    assert [x["stage"] for x in labels] == [f"S{i}" for i in range(10)]
    assert labels[0]["latency_us"] == 5800
    assert labels[-1]["latency_us"] == 3573
    assert labels[2]["BLOCK_SBS"] == 256
    assert labels[2]["multibuffer"] is False
    assert labels[7]["shared_kv_nope_ssa"] is True


def test_prefill_a5_benchmark_outputs_metrics(tmp_path):
    args = argparse.Namespace(
        stage_labels=str(ROOT / "profiles/prefill_a5/prefill_a5_stage_labels.json"),
        kernel=str(ROOT / "sample_input/chunk_kernel.npuir.mlir"),
        hardware_config=str(ROOT / "configs/ascend_910b.json"),
        cost_model_config=str(ROOT / "configs/cost_model_conservative.json"),
        risk_mode="conservative",
        artifact_des_graph=[str(ROOT / "sample_product/prefill_des.json")],
        artifact_trace=[str(ROOT / "sample_product/prefill_trace.json")],
        output_dir=str(tmp_path),
    )
    report = run(args)
    assert report["metrics"]["raw_project_anchor_scaled"]["spearman_rank_correlation"] < 0.8
    assert report["metrics"]["hybrid_calibrated"]["spearman_rank_correlation"] > 0.85
    assert report["metrics"]["hybrid_calibrated"]["top1_hit"] is True
    assert (tmp_path / "prefill_a5_stage_benchmark_report.json").exists()
    assert (tmp_path / "prefill_a5_cost_calibration_priors.json").exists()
