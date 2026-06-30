// Restricted Phase-6C positive fixture for true Q-load hoist mutation.
// This is not a production kernel. It is deliberately tiny: the Q buffer is
// loaded inside a simple loop, does not use the loop induction variable, and is
// not overwritten later in the loop body.
module {
  func.func @restricted_q_load_hoist_mutation_positive(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>, %O_gm : memref<64x128xf16, #hivm.address_space<gm>>) {
    %q_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    %q_l1 = memref.alloc() : memref<64x128xf16, #hivm.address_space<cbuf>>
    %acc_ub = memref.alloc() : memref<64x128xf32, #hivm.address_space<ub>>
    scf.for %j = %c0 to %c10 step %c1 {
      hivm.hir.load ins(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>)
      hivm.hir.nd2nz ins(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%q_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.vadd ins(%q_ub, %q_ub : memref<64x128xf16, #hivm.address_space<ub>>, memref<64x128xf16, #hivm.address_space<ub>>) outs(%acc_ub : memref<64x128xf32, #hivm.address_space<ub>>)
    }
    hivm.hir.store ins(%acc_ub : memref<64x128xf32, #hivm.address_space<ub>>) outs(%O_gm : memref<64x128xf16, #hivm.address_space<gm>>)
  }
}
