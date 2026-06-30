// Restricted Phase-6C positive fixture for true GM round-trip deletion.
// This is not a production kernel. It is deliberately tiny: the reload result
// is unused and the store writes back the same buffer loaded from the same GM.
module {
  func.func @restricted_gm_roundtrip_deletion_positive(%A_gm : memref<64x128xf16, #hivm.address_space<gm>>) {
    %tmp_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    %tmp2_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    hivm.hir.load ins(%A_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%tmp_ub : memref<64x128xf16, #hivm.address_space<ub>>)
    hivm.hir.store ins(%tmp_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%A_gm : memref<64x128xf16, #hivm.address_space<gm>>)
    hivm.hir.load ins(%A_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%tmp2_ub : memref<64x128xf16, #hivm.address_space<ub>>)
  }
}
