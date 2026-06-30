module {
  func.func @fa(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>, %K_gm : memref<1024x128xf16, #hivm.address_space<gm>>, %V_gm : memref<1024x128xf16, #hivm.address_space<gm>>, %O_gm : memref<64x128xf16, #hivm.address_space<gm>>) {
    %q_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    %acc_ub = memref.alloc() : memref<64x128xf32, #hivm.address_space<ub>>
    %s_ub = memref.alloc() : memref<64x96xf16, #hivm.address_space<ub>>
    %p_ub = memref.alloc() : memref<64x96xf16, #hivm.address_space<ub>>
    %m_ub = memref.alloc() : memref<64x1xf32, #hivm.address_space<ub>>
    %l_ub = memref.alloc() : memref<64x1xf32, #hivm.address_space<ub>>
    %k_ub = memref.alloc() : memref<96x128xf16, #hivm.address_space<ub>>
    %v_ub = memref.alloc() : memref<96x128xf16, #hivm.address_space<ub>>
    %q_l1 = memref.alloc() : memref<64x128xf16, #hivm.address_space<cbuf>>
    %k_l1_ping = memref.alloc() : memref<96x128xf16, #hivm.address_space<cbuf>>
    %k_l1_pong = memref.alloc() : memref<96x128xf16, #hivm.address_space<cbuf>>
    %v_l1 = memref.alloc() : memref<96x128xf16, #hivm.address_space<cbuf>>
    %s_l0c = memref.alloc() : memref<64x96xf32, #hivm.address_space<cc>>
    hivm.hir.load ins(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>)
    hivm.hir.nd2nz ins(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%q_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>)
    scf.for %j = %c0 to %cE step %cB {   // @trip=10
      hivm.hir.load ins(%K_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%k_ub : memref<96x128xf16, #hivm.address_space<ub>>)
      hivm.hir.load ins(%V_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%v_ub : memref<96x128xf16, #hivm.address_space<ub>>)
      hivm.hir.nd2nz ins(%k_ub : memref<96x128xf16, #hivm.address_space<ub>>) outs(%k_l1_ping : memref<96x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.nd2nz ins(%v_ub : memref<96x128xf16, #hivm.address_space<ub>>) outs(%v_l1 : memref<96x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.copy ins(%K_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%k_l1_pong : memref<96x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.wait_flag {pipe="M",event="EVENT_ID0"}
      hivm.hir.mmad ins(%q_l1, %k_l1_ping : memref<64x128xf16, #hivm.address_space<cbuf>>, memref<96x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c : memref<64x96xf32, #hivm.address_space<cc>>)
      hivm.hir.fixpipe ins(%s_l0c : memref<64x96xf32, #hivm.address_space<cc>>) outs(%s_ub : memref<64x96xf16, #hivm.address_space<ub>>)
      hivm.hir.vreduce ins(%s_ub : memref<64x96xf16, #hivm.address_space<ub>>) outs(%m_ub : memref<64x1xf32, #hivm.address_space<ub>>) {reduce_op="max"}
      hivm.hir.vsub ins(%s_ub, %m_ub : memref<64x96xf16, #hivm.address_space<ub>>, memref<64x1xf32, #hivm.address_space<ub>>) outs(%p_ub : memref<64x96xf16, #hivm.address_space<ub>>)
      hivm.hir.vexp ins(%p_ub : memref<64x96xf16, #hivm.address_space<ub>>) outs(%p_ub : memref<64x96xf16, #hivm.address_space<ub>>)
      hivm.hir.vreduce ins(%p_ub : memref<64x96xf16, #hivm.address_space<ub>>) outs(%l_ub : memref<64x1xf32, #hivm.address_space<ub>>) {reduce_op="sum"}
      hivm.hir.nd2nz ins(%p_ub : memref<64x96xf16, #hivm.address_space<ub>>) outs(%v_l1 : memref<96x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.mmad ins(%p_ub, %v_l1 : memref<64x96xf16, #hivm.address_space<ub>>, memref<96x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c : memref<64x96xf32, #hivm.address_space<cc>>)
      hivm.hir.fixpipe ins(%s_l0c : memref<64x96xf32, #hivm.address_space<cc>>) outs(%acc_ub : memref<64x128xf32, #hivm.address_space<ub>>)
      hivm.hir.set_flag {pipe="FIX",event="EVENT_ID0"}
    }
    hivm.hir.vdiv ins(%acc_ub, %l_ub : memref<64x128xf32, #hivm.address_space<ub>>, memref<64x1xf32, #hivm.address_space<ub>>) outs(%acc_ub : memref<64x128xf32, #hivm.address_space<ub>>)
    hivm.hir.store ins(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%O_gm : memref<64x128xf16, #hivm.address_space<gm>>)
    return
  }
}