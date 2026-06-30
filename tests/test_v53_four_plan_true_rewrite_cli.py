# -*- coding: utf-8 -*-
import json
from pathlib import Path

from tools.run_four_plan_true_rewrite import run_four_plan_true_rewrite


def test_v53_four_plan_true_rewrite_pipeline(tmp_path):
    summary = run_four_plan_true_rewrite(
        'sample_input/original_repo_samples/chunk_kda_kernel_clean.npuir.mlir',
        'artifacts/latest_smoke_run/selected_plan.json',
        tmp_path,
        max_multibuffer_candidates=20,
        max_multibuffer_actions=1,
        max_cvpipeline_windows=10,
        max_cvpipeline_actions=1,
        max_sync_actions=3,
    )
    assert summary['four_plan_restricted_true_rewrite_performed'] is True
    assert summary['all_portable_validations_passed'] is True
    assert summary['all_controllable_parameters_rewritten_back_to_ir'] is True
    assert summary['all_controllable_parameters_semantic_operation_rewrite'] is False
    final_ir = Path(summary['optimized_ir']).read_text(encoding='utf-8')
    assert 'TilingPlan true rewrite' in final_ir
    assert 'MultiBufferPlan true rewrite' in final_ir
    assert 'CVPipelinePlan' in final_ir
    assert 'SyncPlan rewrite' in final_ir or 'set_flag' in final_ir
    assert 'hivm.param plan=tiling_plan key=tile_m' in final_ir
