# -*- coding: utf-8 -*-
from pathlib import Path
import json

from strategy_search.operation_rewrite.four_plan_operation_rewriter import run_four_plan_operation_rewrite
from strategy_search.operation_rewrite.syntax_hardening_v59 import repair_memref_address_space_closures, normalize_bracket_event_ops, audit_v59_textual_legality

ROOT = Path(__file__).resolve().parents[1]


def test_v59_repairs_nested_memref_and_bracket_events():
    text = 'hivm.hir.mmad ins(%a : memref<32x64xf16, #hivm.address_space<ub>)\n  hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_V>, EVENT_ID0]\n'
    fixed, r1 = repair_memref_address_space_closures(text)
    fixed2, r2 = normalize_bracket_event_ops(fixed)
    audit = audit_v59_textual_legality(fixed2)
    assert r1['repair_count'] == 1
    assert r2['rewrite_count'] == 1
    assert 'memref<32x64xf16, #hivm.address_space<ub>>' in fixed2
    assert 'hivm.hir.wait_flag {' in fixed2
    assert audit['passed_v59_textual_legality_audit']


def test_v59_four_plan_output_has_syntax_hardened_ir(tmp_path):
    out = tmp_path / 'v59'
    summary = run_four_plan_operation_rewrite(
        ROOT / 'sample_input/fa_best.hivm.mlir',
        ROOT / 'artifacts/latest_smoke_run/selected_plan.json',
        out,
    )
    assert summary['four_plan_operation_rewrite_performed']
    assert summary['v59_textual_legality_audit_passed']
    rec = Path(summary['recommended_linux_validation_ir'])
    assert rec.exists()
    text = rec.read_text(encoding='utf-8')
    assert 'hivm.hir.wait_flag[' not in text
    assert 'hivm.hir.set_flag[' not in text
    audit = json.loads((out / 'v59_textual_legality_audit.json').read_text(encoding='utf-8'))
    assert audit['passed_v59_textual_legality_audit']
    consts = json.loads((out / 'v57_constant_materialization_report.json').read_text(encoding='utf-8'))
    assert consts['inserted_constants']['%cN'] == 1024
    assert consts['inserted_constants']['%cK'] == 128
    assert consts['inserted_constants']['%cB'] == 64
