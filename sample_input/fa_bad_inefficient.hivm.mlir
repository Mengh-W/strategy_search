// fa_bad_inefficient.hivm.mlir
// Purpose: deliberately inefficient HIVM/MLIR-style FlashAttention candidate for optimizer testing.
// Main defects:
//   1) Small BN=32 -> too many K/V loop blocks and poor tensor-core utilization.
//   2) score buffer uses f32 -> high UB pressure and extra bandwidth.
//   3) no P/S reuse -> allocates both s_ub and p_ub.
//   4) single L1 buffer -> no ping-pong prefetch overlap.
//   5) barrier synchronization -> coarse pipeline stall.
//   6) reloads Q inside the K/V loop -> redundant GM/UB/L1 traffic.

module {
  func.func @fa_bad(
      %Q_gm : memref<64x128xf16, #hivm.address_space<gm>>,
      %K_gm : memref<1024x128xf16, #hivm.address_space<gm>>,
      %V_gm : memref<1024x128xf16, #hivm.address_space<gm>>,
      %O_gm : memref<64x128xf16, #hivm.address_space<gm>>) {

    // Inefficient parameter vector:
    // BM=64, BN=32, D=128, seq=1024, dt_score=f32, dt_acc=f32,
    // reuse_p=0, nbuf_l1=1, sync=barrier.
    %q_ub   = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    %acc_ub = memref.alloc() : memref<64x128xf32, #hivm.address_space<ub>>
    %s_ub   = memref.alloc() : memref<64x32xf32,  #hivm.address_space<ub>>
    %p_ub   = memref.alloc() : memref<64x32xf32,  #hivm.address_space<ub>>
    %m_ub   = memref.alloc() : memref<64x1xf32,   #hivm.address_space<ub>>
    %l_ub   = memref.alloc() : memref<64x1xf32,   #hivm.address_space<ub>>
    %k_ub   = memref.alloc() : memref<32x128xf16, #hivm.address_space<ub>>
    %v_ub   = memref.alloc() : memref<32x128xf16, #hivm.address_space<ub>>
    %q_l1   = memref.alloc() : memref<64x128xf16, #hivm.address_space<cbuf>>
    %k_l1   = memref.alloc() : memref<32x128xf16, #hivm.address_space<cbuf>>
    %v_l1   = memref.alloc() : memref<32x128xf16, #hivm.address_space<cbuf>>
    %s_l0c  = memref.alloc() : memref<64x32xf32,  #hivm.address_space<cc>>
    %o_ub   = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>

    // Bad: Q load could be hoisted outside the loop, but here it is repeated.
    scf.for %j = %c0 to %c1024 step %c32 {   // @trip=32
      hivm.hir.load ins(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>)
      hivm.hir.nd2nz ins(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%q_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>)

      hivm.hir.load ins(%K_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%k_ub : memref<32x128xf16, #hivm.address_space<ub>>)
      hivm.hir.load ins(%V_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%v_ub : memref<32x128xf16, #hivm.address_space<ub>>)
      hivm.hir.nd2nz ins(%k_ub : memref<32x128xf16, #hivm.address_space<ub>>) outs(%k_l1 : memref<32x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.nd2nz ins(%v_ub : memref<32x128xf16, #hivm.address_space<ub>>) outs(%v_l1 : memref<32x128xf16, #hivm.address_space<cbuf>>)

      // Bad: global barrier serializes stages and prevents fine-grained overlap.
      hivm.hir.barrier {mode = "ALL"}

      hivm.hir.mmad ins(%q_l1, %k_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>, memref<32x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c : memref<64x32xf32, #hivm.address_space<cc>>)
      hivm.hir.fixpipe ins(%s_l0c : memref<64x32xf32, #hivm.address_space<cc>>) outs(%s_ub : memref<64x32xf32, #hivm.address_space<ub>>)
      hivm.hir.vreduce ins(%s_ub : memref<64x32xf32, #hivm.address_space<ub>>) outs(%m_ub : memref<64x1xf32, #hivm.address_space<ub>>) {reduce_op="max"}
      hivm.hir.vsub ins(%s_ub, %m_ub : memref<64x32xf32, #hivm.address_space<ub>>, memref<64x1xf32, #hivm.address_space<ub>>) outs(%p_ub : memref<64x32xf32, #hivm.address_space<ub>>)
      hivm.hir.vexp ins(%p_ub : memref<64x32xf32, #hivm.address_space<ub>>) outs(%p_ub : memref<64x32xf32, #hivm.address_space<ub>>)
      hivm.hir.vreduce ins(%p_ub : memref<64x32xf32, #hivm.address_space<ub>>) outs(%l_ub : memref<64x1xf32, #hivm.address_space<ub>>) {reduce_op="sum"}

      // P x V accumulation, intentionally kept with small BN and f32 P path.
      hivm.hir.mmad ins(%p_ub, %v_l1 : memref<64x32xf32, #hivm.address_space<ub>>, memref<32x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c : memref<64x32xf32, #hivm.address_space<cc>>)
      hivm.hir.fixpipe ins(%s_l0c : memref<64x32xf32, #hivm.address_space<cc>>) outs(%acc_ub : memref<64x128xf32, #hivm.address_space<ub>>)

      // Bad: another coarse barrier after compute.
      hivm.hir.barrier {mode = "ALL"}
    }

    hivm.hir.vdiv ins(%acc_ub, %l_ub : memref<64x128xf32, #hivm.address_space<ub>>, memref<64x1xf32, #hivm.address_space<ub>>) outs(%acc_ub : memref<64x128xf32, #hivm.address_space<ub>>)
    hivm.hir.cast ins(%acc_ub : memref<64x128xf32, #hivm.address_space<ub>>) outs(%o_ub : memref<64x128xf16, #hivm.address_space<ub>>)
    hivm.hir.store ins(%o_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%O_gm : memref<64x128xf16, #hivm.address_space<gm>>)
    return
  }
}
