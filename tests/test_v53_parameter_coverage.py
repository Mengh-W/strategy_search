# -*- coding: utf-8 -*-
import json
from pathlib import Path

from strategy_search.parameter_rewrite_coverage import build_parameter_rewrite_coverage, insert_parameter_metadata_block


def test_parameter_coverage_all_controllable_knobs_rewritten_back():
    plan = json.loads(Path('artifacts/latest_smoke_run/selected_plan.json').read_text(encoding='utf-8'))
    cov = build_parameter_rewrite_coverage(plan)
    assert cov['parameter_count'] >= 30
    assert cov['rewritten_back_to_ir_count'] == cov['parameter_count']
    assert cov['all_controllable_parameters_rewritten_back_to_ir'] is True
    assert cov['all_controllable_parameters_semantic_operation_rewrite'] is False
    assert any(r['coverage_level'] == 'RESTRICTED_STRUCTURAL_REWRITE' for r in cov['parameters'])
    assert any(r['coverage_level'] == 'TRACE_METADATA_REWRITE' for r in cov['parameters'])


def test_insert_parameter_metadata_block_mentions_all_core_plans():
    plan = json.loads(Path('artifacts/latest_smoke_run/selected_plan.json').read_text(encoding='utf-8'))
    cov = build_parameter_rewrite_coverage(plan)
    ir = 'module {\n  func.func @main() {\n    return\n  }\n}\n'
    rewritten = insert_parameter_metadata_block(ir, cov)
    assert 'HIVM V5.3 Four-Plan selected-parameter rewrite metadata begin' in rewritten
    assert 'plan=tiling_plan key=tile_m' in rewritten
    assert 'plan=multibuffer_plan key=double_buffer' in rewritten
    assert 'plan=cv_pipeline_plan key=stage_num' in rewritten
    assert 'plan=sync_plan key=policy' in rewritten
