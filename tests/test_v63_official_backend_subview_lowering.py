from pathlib import Path
import json
from strategy_search.operation_rewrite.official_backend_subview_lowering_v63 import write_v63_official_backend_subview_lowering_outputs

ROOT = Path(__file__).resolve().parents[1]

def test_v63_subview_lowering_on_generated_v62(tmp_path):
    from strategy_search.operation_rewrite.four_plan_operation_rewriter import run_four_plan_operation_rewrite
    out = tmp_path / "run"
    summary = run_four_plan_operation_rewrite(ROOT / "sample_input/fa_best.hivm.mlir", ROOT / "artifacts/latest_smoke_run/selected_plan.json", out)
    p = Path(summary["recommended_linux_validation_ir"])
    text = p.read_text()
    assert "annotation.mark" not in text
    assert "memref.subview" in text
    audit = json.loads((out / "v63_official_compare_audit.json").read_text())
    assert audit["passed_v63_portable_official_compare_audit"] is True
    assert audit["counts_by_kind"].get("load_store_shape_mismatch_without_subview_or_pad", 0) == 0


def test_v63_direct_pass_removes_shape_mismatch(tmp_path):
    src = ROOT / "artifacts/latest_smoke_run/selected_plan.json"
    # use a tiny handcrafted snippet to check exact lowering behavior
    ir = tmp_path / "in.mlir"
    ir.write_text('''module {\n  func.func @f(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>, %O_gm : memref<64x128xf16, #hivm.address_space<gm>>) {\n    %c0 = arith.constant 0 : index\n    %q = memref.alloc() : memref<32x128xf16, #hivm.address_space<ub>>\n    hivm.hir.load ins(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q : memref<32x128xf16, #hivm.address_space<ub>>) {hivm.tile_offsets="m_outer,k_outer", hivm.tile_shape="32x128"}\n    hivm.hir.store ins(%q : memref<32x128xf16, #hivm.address_space<ub>>) outs(%O_gm : memref<64x128xf16, #hivm.address_space<gm>>) {hivm.tile_offsets="m_outer,k_outer", hivm.tile_shape="32x128"}\n    return\n  }\n}\n''')
    out = write_v63_official_backend_subview_lowering_outputs(ir, tmp_path)
    txt = Path(out["v63_official_backend_subview_lowered_ir"]).read_text()
    assert txt.count("memref.subview") == 2
    assert "hivm.tile_offsets" not in txt
    assert out["official_compare_audit"]["passed_v63_portable_official_compare_audit"] is True
