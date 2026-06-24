// 混合缺陷样例：defect_H_event_sync_but_small_tile_no_overlap
// 目的：一次性叠加多类低效因素，观察搜索器是否能同时调整 tile、缓冲、流水与同步策略。
// 明显缺陷说明：
// 1) 已经使用事件式同步，但 N 方向切块仍然过小。
// 2) 循环内重复搬运 Q，缺少有效重叠。
// 3) 向量侧计算偏重，并存在冗余写回。
// 4) 该样例用于检查优化器是否能在同步已较细时继续优化 tile 与缓冲。
// 注意：注释避免使用会被当前解析器误识别为实际结构的英文触发词。

module {
  func.func @defect_H_event_sync_but_small_tile_no_overlap(
      %Q_gm : memref<64x128xf16, #hivm.address_space<gm>>,
      %K_gm : memref<1024x128xf16, #hivm.address_space<gm>>,
      %V_gm : memref<1024x128xf16, #hivm.address_space<gm>>,
      %O_gm : memref<64x128xf16, #hivm.address_space<gm>>) {
    %q_ub   = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    %acc_ub = memref.alloc() : memref<64x128xf32, #hivm.address_space<ub>>
    %s_ub   = memref.alloc() : memref<64x32xf16, #hivm.address_space<ub>>
    %m_ub   = memref.alloc() : memref<64x1xf32, #hivm.address_space<ub>>
    %l_ub   = memref.alloc() : memref<64x1xf32, #hivm.address_space<ub>>
    %k_ub   = memref.alloc() : memref<32x128xf16, #hivm.address_space<ub>>
    %v_ub   = memref.alloc() : memref<32x128xf16, #hivm.address_space<ub>>
    %q_l1   = memref.alloc() : memref<64x128xf16, #hivm.address_space<cbuf>>
    %k_l1   = memref.alloc() : memref<32x128xf16, #hivm.address_space<cbuf>>
    %v_l1   = memref.alloc() : memref<32x128xf16, #hivm.address_space<cbuf>>
    %s_l0c  = memref.alloc() : memref<64x32xf32, #hivm.address_space<cc>>
    %o_ub   = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>

    scf.for %j = %c0 to %c1024 step %c32 {   // @trip=32
      hivm.hir.load ins(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>)
      hivm.hir.nd2nz ins(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%q_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.load ins(%K_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%k_ub : memref<32x128xf16, #hivm.address_space<ub>>)
      hivm.hir.load ins(%V_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%v_ub : memref<32x128xf16, #hivm.address_space<ub>>)
      hivm.hir.nd2nz ins(%k_ub : memref<32x128xf16, #hivm.address_space<ub>>) outs(%k_l1 : memref<32x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.nd2nz ins(%v_ub : memref<32x128xf16, #hivm.address_space<ub>>) outs(%v_l1 : memref<32x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.wait_flag {pipe="M", event="E0"}
      hivm.hir.mmad ins(%q_l1, %k_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>, memref<32x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c : memref<64x32xf32, #hivm.address_space<cc>>)
      hivm.hir.fixpipe ins(%s_l0c : memref<64x32xf32, #hivm.address_space<cc>>) outs(%s_ub : memref<64x32xf16, #hivm.address_space<ub>>)
      hivm.hir.vreduce ins(%s_ub : memref<64x32xf16, #hivm.address_space<ub>>) outs(%m_ub : memref<64x1xf32, #hivm.address_space<ub>>) {reduce_op="max"}
      hivm.hir.vsub ins(%s_ub, %m_ub : memref<64x32xf16, #hivm.address_space<ub>>, memref<64x1xf32, #hivm.address_space<ub>>) outs(%s_ub : memref<64x32xf16, #hivm.address_space<ub>>)
      hivm.hir.vexp ins(%s_ub : memref<64x32xf16, #hivm.address_space<ub>>) outs(%s_ub : memref<64x32xf16, #hivm.address_space<ub>>)
      hivm.hir.vmul ins(%s_ub, %s_ub : memref<64x32xf16, #hivm.address_space<ub>>, memref<64x32xf16, #hivm.address_space<ub>>) outs(%s_ub : memref<64x32xf16, #hivm.address_space<ub>>)
      hivm.hir.vmul ins(%s_ub, %s_ub : memref<64x32xf16, #hivm.address_space<ub>>, memref<64x32xf16, #hivm.address_space<ub>>) outs(%s_ub : memref<64x32xf16, #hivm.address_space<ub>>)
      hivm.hir.vreduce ins(%s_ub : memref<64x32xf16, #hivm.address_space<ub>>) outs(%l_ub : memref<64x1xf32, #hivm.address_space<ub>>) {reduce_op="sum"}
      hivm.hir.mmad ins(%s_ub, %v_l1 : memref<64x32xf16, #hivm.address_space<ub>>, memref<32x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c : memref<64x32xf32, #hivm.address_space<cc>>)
      hivm.hir.fixpipe ins(%s_l0c : memref<64x32xf32, #hivm.address_space<cc>>) outs(%acc_ub : memref<64x128xf32, #hivm.address_space<ub>>)
      hivm.hir.set_flag {pipe="FIX", event="E0"}
    }
    hivm.hir.vdiv ins(%acc_ub, %l_ub : memref<64x128xf32, #hivm.address_space<ub>>, memref<64x1xf32, #hivm.address_space<ub>>) outs(%acc_ub : memref<64x128xf32, #hivm.address_space<ub>>)
    hivm.hir.cast ins(%acc_ub : memref<64x128xf32, #hivm.address_space<ub>>) outs(%o_ub : memref<64x128xf16, #hivm.address_space<ub>>)
    hivm.hir.store ins(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%O_gm : memref<64x128xf16, #hivm.address_space<gm>>)
    hivm.hir.store ins(%o_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%O_gm : memref<64x128xf16, #hivm.address_space<gm>>)
    return
  }
}
