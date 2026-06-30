# -*- coding: utf-8 -*-
from pathlib import Path
import json

from strategy_search.operation_rewrite.four_plan_operation_rewriter import run_four_plan_operation_rewrite


def test_v58_tiling_axis_slice_and_cvpipeline_schedule(tmp_path: Path):
    summary = run_four_plan_operation_rewrite(
        'sample_input/fa_best.hivm.mlir',
        'artifacts/latest_smoke_run/selected_plan.json',
        tmp_path,
        max_multibuffer_actions=4,
        max_cvpipeline_actions=2,
    )
    assert summary['four_plan_operation_rewrite_performed'] is True
    assert summary['portable_validation_passed'] is True
    assert summary['tiling_semantic_full_rewrite_performed'] is True
    assert summary['cvpipeline_semantic_schedule_performed'] is True
    text = Path(summary['optimized_ir']).read_text(encoding='utf-8')
    assert 'HIVM V5.8 tile-slice binding' in text
    assert 'HIVM V5.8 reduction binding' in text
    assert 'HIVM V5.8 CVPipeline semantic schedule begin' in text
    assert 'prologue/steady/epilogue' in text

    axis = json.loads(Path(summary['tiling_axis_binding']).read_text(encoding='utf-8'))
    assert axis['complete_for_sample_fa_pattern'] is True
    assert axis['axes']['M']['tile'] == 32
    assert axis['axes']['N']['tile'] == 64
    assert axis['axes']['K']['tile'] == 128

    graph = json.loads(Path(summary['cvpipeline_stage_graph']).read_text(encoding='utf-8'))
    assert graph['complete_minimal_pipeline_graph'] is True
    assert graph['stage_counts']['load'] >= 1
    assert graph['stage_counts']['compute'] >= 1
    assert graph['stage_counts']['store'] >= 1


def test_v58_operation_coverage_mentions_semantic_bindings(tmp_path: Path):
    run_four_plan_operation_rewrite(
        'sample_input/fa_best.hivm.mlir',
        'artifacts/latest_smoke_run/selected_plan.json',
        tmp_path,
        max_multibuffer_actions=1,
        max_cvpipeline_actions=1,
    )
    cov = Path(tmp_path / 'operation_parameter_coverage.json').read_text(encoding='utf-8')
    assert 'semantic_operation_v58_axis_slice_reduction_binding' in cov
    assert 'semantic_operation_v58_schedule_binding' in cov
    assert 'attach_tile_slice_binding_to_hivm_operation' in cov
