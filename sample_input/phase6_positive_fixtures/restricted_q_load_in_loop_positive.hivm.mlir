// Restricted Phase-6B positive fixture for Q-load hoist gate only.
// This is not a production kernel.  It exists so that a real MLIR/HivmOpsEditor
// backend can prove or reject loop-invariant Q-load motion under a tiny pattern.
module {
  func.func @restricted_q_load_in_loop_positive(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>, %O_gm : memref<64x128xf16, #hivm.address_space<gm>>) {
    %q_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    %q_l1 = memref.alloc() : memref<64x128xf16, #hivm.address_space<cbuf>>
    %acc_ub = memref.alloc() : memref<64x128xf32, #hivm.address_space<ub>>
    scf.for %j = %c0 to %c10 step %c1 {
      hivm.hir.load ins(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>)
      hivm.hir.nd2nz ins(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%q_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.vadd ins(%q_ub, %q_ub : memref<64x128xf16, #hivm.address_space<ub>>, memref<64x128xf16, #hivm.address_space<ub>>) outs(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>)
    }
    hivm.hir.store ins(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%O_gm : memref<64x128xf16, #hivm.address_space<gm>>)
  }
}
