// 混合缺陷样例：defect_G_existing_pingpong_but_bad_sync_dtype
// 目的：一次性叠加多类低效因素，观察搜索器是否能同时调整 tile、缓冲、流水与同步策略。
// 明显缺陷说明：
// 1) 文件中已经出现双份 K 的局部缓冲，但其他问题仍然明显。
// 2) tile 不规整且 score 使用 f32。
// 3) 同步次数偏多，向量侧计算偏重。
// 4) 该样例用于检查优化器是否不会只因已有双份缓冲就停止优化。
// 注意：注释避免使用会被当前解析器误识别为实际结构的英文触发词。

module {
  func.func @defect_G_existing_pingpong_but_bad_sync_dtype(
      %Q_gm : memref<96x128xf16, #hivm.address_space<gm>>,
      %K_gm : memref<1024x128xf16, #hivm.address_space<gm>>,
      %V_gm : memref<1024x128xf16, #hivm.address_space<gm>>,
      %O_gm : memref<96x128xf16, #hivm.address_space<gm>>) {
    %q_ub   = memref.alloc() : memref<96x128xf16, #hivm.address_space<ub>>
    %acc_ub = memref.alloc() : memref<96x128xf32, #hivm.address_space<ub>>
    %s_ub   = memref.alloc() : memref<96x96xf32, #hivm.address_space<ub>>
    %p_ub   = memref.alloc() : memref<96x96xf32, #hivm.address_space<ub>>
    %tmp_ub_0 = memref.alloc() : memref<96x96xf32, #hivm.address_space<ub>>
    %m_ub   = memref.alloc() : memref<96x1xf32, #hivm.address_space<ub>>
    %l_ub   = memref.alloc() : memref<96x1xf32, #hivm.address_space<ub>>
    %k_ub   = memref.alloc() : memref<96x128xf16, #hivm.address_space<ub>>
    %v_ub   = memref.alloc() : memref<96x128xf16, #hivm.address_space<ub>>
    %q_l1   = memref.alloc() : memref<96x128xf16, #hivm.address_space<cbuf>>
    %k_l1_ping = memref.alloc() : memref<96x128xf16, #hivm.address_space<cbuf>>
    %k_l1_pong = memref.alloc() : memref<96x128xf16, #hivm.address_space<cbuf>>
    %v_l1   = memref.alloc() : memref<96x128xf16, #hivm.address_space<cbuf>>
    %s_l0c  = memref.alloc() : memref<96x96xf32, #hivm.address_space<cc>>
    %o_ub   = memref.alloc() : memref<96x128xf16, #hivm.address_space<ub>>

    hivm.hir.load ins(%Q_gm : memref<96x128xf16, #hivm.address_space<gm>>) outs(%q_ub : memref<96x128xf16, #hivm.address_space<ub>>)
    hivm.hir.nd2nz ins(%q_ub : memref<96x128xf16, #hivm.address_space<ub>>) outs(%q_l1 : memref<96x128xf16, #hivm.address_space<cbuf>>)
    scf.for %j = %c0 to %c1024 step %c96 {   // @trip=10
      hivm.hir.load ins(%K_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%k_ub : memref<96x128xf16, #hivm.address_space<ub>>)
      hivm.hir.load ins(%V_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%v_ub : memref<96x128xf16, #hivm.address_space<ub>>)
      hivm.hir.nd2nz ins(%k_ub : memref<96x128xf16, #hivm.address_space<ub>>) outs(%k_l1_ping : memref<96x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.nd2nz ins(%v_ub : memref<96x128xf16, #hivm.address_space<ub>>) outs(%v_l1 : memref<96x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.barrier {mode = "ALL"}
      hivm.hir.barrier {mode = "ALL"}
      hivm.hir.barrier {mode = "ALL"}
      hivm.hir.barrier {mode = "ALL"}
      hivm.hir.barrier {mode = "ALL"}
      hivm.hir.mmad ins(%q_l1, %k_l1_ping : memref<96x128xf16, #hivm.address_space<cbuf>>, memref<96x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c : memref<96x96xf32, #hivm.address_space<cc>>)
      hivm.hir.fixpipe ins(%s_l0c : memref<96x96xf32, #hivm.address_space<cc>>) outs(%s_ub : memref<96x96xf32, #hivm.address_space<ub>>)
      hivm.hir.vreduce ins(%s_ub : memref<96x96xf32, #hivm.address_space<ub>>) outs(%m_ub : memref<96x1xf32, #hivm.address_space<ub>>) {reduce_op="max"}
      hivm.hir.vsub ins(%s_ub, %m_ub : memref<96x96xf32, #hivm.address_space<ub>>, memref<96x1xf32, #hivm.address_space<ub>>) outs(%p_ub : memref<96x96xf32, #hivm.address_space<ub>>)
      hivm.hir.vexp ins(%p_ub : memref<96x96xf32, #hivm.address_space<ub>>) outs(%p_ub : memref<96x96xf32, #hivm.address_space<ub>>)
      hivm.hir.vmul ins(%p_ub, %p_ub : memref<96x96xf32, #hivm.address_space<ub>>, memref<96x96xf32, #hivm.address_space<ub>>) outs(%p_ub : memref<96x96xf32, #hivm.address_space<ub>>)
      hivm.hir.vmul ins(%p_ub, %p_ub : memref<96x96xf32, #hivm.address_space<ub>>, memref<96x96xf32, #hivm.address_space<ub>>) outs(%p_ub : memref<96x96xf32, #hivm.address_space<ub>>)
      hivm.hir.vreduce ins(%p_ub : memref<96x96xf32, #hivm.address_space<ub>>) outs(%l_ub : memref<96x1xf32, #hivm.address_space<ub>>) {reduce_op="sum"}
      hivm.hir.mmad ins(%p_ub, %v_l1 : memref<96x96xf32, #hivm.address_space<ub>>, memref<96x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c : memref<96x96xf32, #hivm.address_space<cc>>)
      hivm.hir.fixpipe ins(%s_l0c : memref<96x96xf32, #hivm.address_space<cc>>) outs(%acc_ub : memref<96x128xf32, #hivm.address_space<ub>>)
      hivm.hir.barrier {mode = "ALL"}
      hivm.hir.barrier {mode = "ALL"}
      hivm.hir.barrier {mode = "ALL"}
      hivm.hir.barrier {mode = "ALL"}
      hivm.hir.barrier {mode = "ALL"}
    }
    hivm.hir.vdiv ins(%acc_ub, %l_ub : memref<96x128xf32, #hivm.address_space<ub>>, memref<96x1xf32, #hivm.address_space<ub>>) outs(%acc_ub : memref<96x128xf32, #hivm.address_space<ub>>)
    hivm.hir.cast ins(%acc_ub : memref<96x128xf32, #hivm.address_space<ub>>) outs(%o_ub : memref<96x128xf16, #hivm.address_space<ub>>)
    hivm.hir.store ins(%o_ub : memref<96x128xf16, #hivm.address_space<ub>>) outs(%O_gm : memref<96x128xf16, #hivm.address_space<gm>>)
    return
  }
}
