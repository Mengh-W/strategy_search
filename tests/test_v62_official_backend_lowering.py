# -*- coding: utf-8 -*-
from __future__ import annotations
import json
from pathlib import Path

from strategy_search.operation_rewrite.official_backend_lowering_v62 import write_v62_official_backend_lowering_outputs
from strategy_search.operation_rewrite.four_plan_operation_rewriter import run_four_plan_operation_rewrite


def test_v62_lowering_removes_portable_textual_blockers(tmp_path: Path):
    src = '''module {
  func.func @f() {
    %q_ub_mb0_ping = memref.alloc() : memref<32x128xf16, #hivm.address_space<ub>>
    annotation.mark %q_ub_mb0_ping {hivm.multi_buffer_slot = "ping"} : memref<32x128xf16, #hivm.address_space<ub>>
    // restricted=true operation_movement=false loop_skewing=false
    hivm.hir.load ins(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub : memref<32x128xf16, #hivm.address_space<ub>>) {hivm.tile_offsets="['%m_outer', '%k_outer']", hivm.tile_shape="[32, 'D_tile']", hivm.tile_axes="['M', 'K']"}
    return
  }
}
'''
    p = tmp_path / 'in.hivm.mlir'
    p.write_text(src, encoding='utf-8')
    out = write_v62_official_backend_lowering_outputs(p, tmp_path)
    text = Path(out['v62_official_backend_lowered_ir']).read_text(encoding='utf-8')
    audit = out['official_backend_handoff_audit']
    assert audit['passed_v62_portable_official_handoff_audit']
    assert 'annotation.mark' not in text
    assert 'D_tile' not in text
    assert "['%" not in text
    assert 'operation_movement=false' not in text
    assert '%q_ub_mb0_ping' in text
    assert 'hivm.tile_offsets="m_outer,k_outer"' in text


def test_v62_full_pipeline_generates_official_backend_lowered_ir(tmp_path: Path):
    out_dir = tmp_path / 'run'
    summary = run_four_plan_operation_rewrite(
        'sample_input/fa_best.hivm.mlir',
        'artifacts/latest_smoke_run/selected_plan.json',
        out_dir,
    )
    lowered = Path(summary['v62_official_backend_lowered_ir'])
    assert lowered.exists()
    text = lowered.read_text(encoding='utf-8')
    assert summary['v62_official_backend_handoff_audit_passed'] is True
    assert summary['v62_official_backend_hard_blocker_count'] == 0
    assert 'annotation.mark' not in text
    assert 'D_tile' not in text
    assert 'propagate_from_input' not in text
    assert "hivm.tile_offsets=\"[" not in text
    assert (out_dir / 'linux_handoff' / 'inputs' / 'optimized.hivm.mlir').exists()
