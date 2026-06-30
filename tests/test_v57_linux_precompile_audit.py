# -*- coding: utf-8 -*-
from pathlib import Path
import json

from strategy_search.operation_rewrite.four_plan_operation_rewriter import run_four_plan_operation_rewrite
from strategy_search.operation_rewrite.linux_precompile_audit import audit_linux_precompile_candidate, materialize_missing_index_constants


def test_v57_materializes_tiling_constants():
    text = 'module {\n  func.func @f(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>, %K_gm : memref<1024x128xf16, #hivm.address_space<gm>>, %O_gm : memref<64x128xf16, #hivm.address_space<gm>>) {\n    scf.for %m_outer = %c0 to %cM step %c32 {\n    }\n    return\n  }\n}\n'
    out, report = materialize_missing_index_constants(text)
    assert report['mutation_performed'] is True
    assert '%cM = arith.constant 64 : index' in out
    assert '%c32 = arith.constant 32 : index' in out


def test_v57_audit_detects_duplicate_and_undefined():
    text = 'module {\n  func.func @f() {\n    %x = memref.alloc() : memref<1xf16>\n    %x = memref.alloc() : memref<1xf16>\n    scf.for %i = %c0 to %cM step %c32 {\n    }\n    return\n  }\n}\n'
    audit = audit_linux_precompile_candidate(text)
    kinds = {b['kind'] for b in audit['blockers']}
    assert 'duplicate_ssa_definition' in kinds
    assert 'undefined_ssa_or_symbol' in kinds
    assert audit['passed_portable_precompile_audit'] is False


def test_v57_four_plan_rewrite_emits_precompile_audit(tmp_path: Path):
    summary = run_four_plan_operation_rewrite(
        'sample_input/fa_best.hivm.mlir',
        'artifacts/latest_smoke_run/selected_plan.json',
        tmp_path,
        max_multibuffer_actions=4,
        max_cvpipeline_actions=2,
    )
    assert summary['four_plan_operation_rewrite_performed'] is True
    assert 'linux_precompile_audit_passed' in summary
    assert Path(summary['precompile_hardened_ir']).exists()
    audit_path = Path(summary['linux_precompile_audit'])
    assert audit_path.exists()
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    assert audit['schema_version'] == 'hivm_v57_linux_precompile_audit_v1'
    assert audit['passed_portable_precompile_audit'] is True
    assert audit['duplicate_ssa_definition_count'] == 0
    assert audit['undefined_symbol_count'] == 0
    assert audit['memref_type_mismatch_count'] == 0
    hardened = Path(summary['precompile_hardened_ir']).read_text(encoding='utf-8')
    assert 'HIVM V5.7 precompile hardening' in hardened
