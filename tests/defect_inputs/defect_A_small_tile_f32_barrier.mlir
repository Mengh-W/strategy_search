// 缺陷注入样例：defect_A_small_tile_f32_barrier
// 目的：用于检验策略搜索器是否能识别低效结构，并给出更合理的候选策略。
// 明显缺陷说明：
// 1) N 方向切块过小，循环块数偏多。
// 2) score 使用 f32，局部缓冲与带宽压力偏高。
// 3) 概率矩阵单独分配，复用不足。
// 4) 使用粗粒度全局同步，容易造成流水停顿。
// 5) Q 数据在循环内重复搬运，存在冗余访存。
// 注意：这些说明刻意避免使用会被当前解析器误识别为实际结构的英文触发词。

module {
  func.func @defect_A_small_tile_f32_barrier(
      %Q_gm : memref<64x128xf16, #hivm.address_space<gm>>,
      %K_gm : memref<1024x128xf16, #hivm.address_space<gm>>,
      %V_gm : memref<1024x128xf16, #hivm.address_space<gm>>,
      %O_gm : memref<64x128xf16, #hivm.address_space<gm>>) {
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

    scf.for %j = %c0 to %c1024 step %c32 {   // @trip=32
      hivm.hir.load ins(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>)
      hivm.hir.nd2nz ins(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%q_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.load ins(%K_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%k_ub : memref<32x128xf16, #hivm.address_space<ub>>)
      hivm.hir.load ins(%V_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%v_ub : memref<32x128xf16, #hivm.address_space<ub>>)
      hivm.hir.nd2nz ins(%k_ub : memref<32x128xf16, #hivm.address_space<ub>>) outs(%k_l1 : memref<32x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.nd2nz ins(%v_ub : memref<32x128xf16, #hivm.address_space<ub>>) outs(%v_l1 : memref<32x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.barrier {mode = "ALL"}
      hivm.hir.mmad ins(%q_l1, %k_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>, memref<32x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c : memref<64x32xf32, #hivm.address_space<cc>>)
      hivm.hir.fixpipe ins(%s_l0c : memref<64x32xf32, #hivm.address_space<cc>>) outs(%s_ub : memref<64x32xf32, #hivm.address_space<ub>>)
      hivm.hir.vreduce ins(%s_ub : memref<64x32xf32, #hivm.address_space<ub>>) outs(%m_ub : memref<64x1xf32, #hivm.address_space<ub>>) {reduce_op="max"}
      hivm.hir.vsub ins(%s_ub, %m_ub : memref<64x32xf32, #hivm.address_space<ub>>, memref<64x1xf32, #hivm.address_space<ub>>) outs(%p_ub : memref<64x32xf32, #hivm.address_space<ub>>)
      hivm.hir.vexp ins(%p_ub : memref<64x32xf32, #hivm.address_space<ub>>) outs(%p_ub : memref<64x32xf32, #hivm.address_space<ub>>)
      hivm.hir.vreduce ins(%p_ub : memref<64x32xf32, #hivm.address_space<ub>>) outs(%l_ub : memref<64x1xf32, #hivm.address_space<ub>>) {reduce_op="sum"}
      hivm.hir.mmad ins(%p_ub, %v_l1 : memref<64x32xf32, #hivm.address_space<ub>>, memref<32x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c : memref<64x32xf32, #hivm.address_space<cc>>)
      hivm.hir.fixpipe ins(%s_l0c : memref<64x32xf32, #hivm.address_space<cc>>) outs(%acc_ub : memref<64x128xf32, #hivm.address_space<ub>>)
      hivm.hir.barrier {mode = "ALL"}
    }
    hivm.hir.vdiv ins(%acc_ub, %l_ub : memref<64x128xf32, #hivm.address_space<ub>>, memref<64x1xf32, #hivm.address_space<ub>>) outs(%acc_ub : memref<64x128xf32, #hivm.address_space<ub>>)
    hivm.hir.cast ins(%acc_ub : memref<64x128xf32, #hivm.address_space<ub>>) outs(%o_ub : memref<64x128xf16, #hivm.address_space<ub>>)
    hivm.hir.store ins(%o_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%O_gm : memref<64x128xf16, #hivm.address_space<gm>>)
    return
  }
}
