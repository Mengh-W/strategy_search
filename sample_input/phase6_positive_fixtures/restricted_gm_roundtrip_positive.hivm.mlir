// Restricted Phase-6B positive fixture for GM round-trip deletion gate only.
// This is deliberately tiny and must still be verified by a real Operation backend.
module {
  func.func @restricted_gm_roundtrip_positive(%A_gm : memref<64x128xf16, #hivm.address_space<gm>>) {
    %tmp_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    %tmp2_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    hivm.hir.load ins(%A_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%tmp_ub : memref<64x128xf16, #hivm.address_space<ub>>)
    hivm.hir.store ins(%tmp_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%A_gm : memref<64x128xf16, #hivm.address_space<gm>>)
    hivm.hir.load ins(%A_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%tmp2_ub : memref<64x128xf16, #hivm.address_space<ub>>)
  }
}
