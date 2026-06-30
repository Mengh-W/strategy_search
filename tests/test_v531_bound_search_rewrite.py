# -*- coding: utf-8 -*-
from pathlib import Path

from tools.run_search_and_four_plan_rewrite import run_search_and_four_plan_rewrite


def test_v531_bound_search_rewrite_reports_honest_partial_failure(tmp_path):
    summary = run_search_and_four_plan_rewrite(
        kernel='sample_input/fa_bad_inefficient.hivm.mlir',
        hardware_config='configs/ascend_910b.json',
        cost_model_config='configs/cost_model_conservative.json',
        output_dir=tmp_path,
        cost_risk_mode='conservative',
        candidate_space='standard',
        max_multibuffer_candidates=20,
        max_multibuffer_actions=1,
        max_cvpipeline_windows=10,
        max_cvpipeline_actions=1,
        max_sync_actions=3,
    )
    assert summary['search_returncode'] == 0
    assert Path(summary['selected_plan']).exists()
    assert summary['selected_plan_bound_to_same_input'] is True

    # This smoke input intentionally exposes a currently unsupported SyncPlan closure:
    # the wrapper must not hide the failed rewrite subprocess behind a successful
    # stale-plan-avoidance check.
    assert summary['rewrite_returncode'] == 1
    assert summary['rewrite_process_succeeded'] is False
    assert summary['all_portable_validations_passed'] is False
    assert summary['end_to_end_passed'] is False
    assert summary['search_and_rewrite_bound_to_same_input'] is False
    assert summary['failure_reason'] == 'rewrite_process_failed'
    assert Path(summary['rewrite_optimized_ir']).exists()
