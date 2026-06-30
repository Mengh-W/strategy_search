module {
  func.func @fa_bad(%Q_gm : memref < 64 x128xf16 , #hivm.address_spacevm.address_space<gm> >, %K_gm : memref < 1024 x128xf16 , #hivm.address_spacevm.address_space<gm> >, %V_gm : memref < 1024 x128xf16 , #hivm.address_spacevm.address_space<gm> >, %O_gm : memref < 64 x128xf16 , #hivm.address_spacevm.address_space<gm> >) {
    %q_ub = memref.alloc outs(%q_ub)
    %acc_ub = memref.alloc outs(%acc_ub)
    %s_ub = memref.alloc outs(%s_ub)
    %p_ub = memref.alloc outs(%p_ub)
    %m_ub = memref.alloc outs(%m_ub)
    %l_ub = memref.alloc outs(%l_ub)
    %k_ub = memref.alloc outs(%k_ub)
    %v_ub = memref.alloc outs(%v_ub)
    %q_l1 = memref.alloc outs(%q_l1)
    %k_l1 = memref.alloc outs(%k_l1)
    %v_l1 = memref.alloc outs(%v_l1)
    %s_l0c = memref.alloc outs(%s_l0c)
    %o_ub = memref.alloc outs(%o_ub)
    scf.for
    hivm.hir.vdiv ins(%acc_ub, %l_ub)
    hivm.hir.cast ins(%acc_ub)
    hivm.hir.store ins(%o_ub)
    return
  }
}
