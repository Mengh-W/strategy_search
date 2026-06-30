from pathlib import Path

from scripts.prefill_a5_plan_only_validation import run


class Args:
    stage_labels = "profiles/prefill_a5/prefill_a5_stage_labels.json"
    kernel = "sample_input/chunk_kernel.npuir.mlir"
    hardware_config = "configs/ascend_910b.json"
    cost_model_config = "configs/cost_model_conservative.json"
    risk_mode = "conservative"
    artifact_des_graph = ["sample_product/prefill_des.json"]
    artifact_trace = ["sample_product/prefill_trace.json"]
    output_dir = "output_prefill_a5_plan_only_validation_test"


def test_plan_only_validation_scope_and_metrics():
    report = run(Args())
    summary = report["plan_only_summary"]
    assert summary["num_supported_transitions"] == 4
    assert summary["direction_hits"] == 2
    assert 0.49 < summary["direction_hit_rate"] < 0.51
    transitions = {f"{r['from']}->{r['to']}": r for r in report["plan_only_transition_rows"]}
    assert transitions["S1->S2"]["direction_hit"] is True
    assert transitions["S2->S3"]["direction_hit"] is False
    assert transitions["S5->S6"]["direction_hit"] is False
    assert Path(Args.output_dir, "prefill_a5_plan_only_validation_report.json").exists()


class CalibratedArgs(Args):
    cost_model_config = "configs/cost_model_prefill_a5_plan_calibrated.json"
    output_dir = "output_prefill_a5_plan_only_calibrated_test"


def test_plan_only_validation_after_prefill_a5_calibration():
    report = run(CalibratedArgs())
    summary = report["plan_only_summary"]
    assert summary["num_supported_transitions"] == 4
    assert summary["direction_hits"] == 4
    assert summary["direction_hit_rate"] == 1.0
    assert summary["mean_absolute_gain_error"] < 0.02
    transitions = {f"{r['from']}->{r['to']}": r for r in report["plan_only_transition_rows"]}
    assert transitions["S2->S3"]["direction_hit"] is True
    assert transitions["S5->S6"]["direction_hit"] is True
    assert Path(CalibratedArgs.output_dir, "prefill_a5_plan_only_validation_report.json").exists()
