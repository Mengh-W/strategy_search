// 扩展缺陷注入样例：defect_M_tail_unfriendly_n176_no_overlap
// 目的：模仿既有 defect_A-I 的 MLIR 风格，测试 cost model 是否能识别新的低效方向。
// 明显缺陷说明：
// 1) 当前 tile / dtype / 同步 / buffer 组合刻意设置为低效或非法。
// 2) 该文件只用于解析式 cost model 与 hardware gate 回归，不代表可直接真实编译。
// 3) 注释避免使用英文结构触发词，避免影响当前文本解析器。

module {
  func.func @defect_M_tail_unfriendly_n176_no_overlap(
      %Q_gm : memref<64x128xf16, #hivm.address_space<gm>>,
      %K_gm : memref<1024x128xf16, #hivm.address_space<gm>>,
      %V_gm : memref<1024x128xf16, #hivm.address_space<gm>>,
      %O_gm : memref<64x128xf16, #hivm.address_space<gm>>) {
    %q_ub   = memref.alloc() : memref<32x128xf16, #hivm.address_space<ub>>
    %acc_ub = memref.alloc() : memref<32x128xf32, #hivm.address_space<ub>>
    %s_ub   = memref.alloc() : memref<32x176xf16, #hivm.address_space<ub>>
    %p_ub   = memref.alloc() : memref<32x176xf16, #hivm.address_space<ub>>
    %m_ub   = memref.alloc() : memref<32x1xf32, #hivm.address_space<ub>>
    %l_ub   = memref.alloc() : memref<32x1xf32, #hivm.address_space<ub>>
    %k_ub   = memref.alloc() : memref<176x128xf16, #hivm.address_space<ub>>
    %v_ub   = memref.alloc() : memref<176x128xf16, #hivm.address_space<ub>>
    %q_l1   = memref.alloc() : memref<32x128xf16, #hivm.address_space<cbuf>>
    %k_l1   = memref.alloc() : memref<176x128xf16, #hivm.address_space<cbuf>>
    %v_l1   = memref.alloc() : memref<176x128xf16, #hivm.address_space<cbuf>>
    %s_l0c  = memref.alloc() : memref<32x176xf32, #hivm.address_space<cc>>
    %extra0_ub = memref.alloc() : memref<32x176xf32, #hivm.address_space<ub>>
    scf.for %j = %c0 to %c1024 step %c176 {   // @trip=5
      hivm.hir.load ins(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub : memref<32x128xf16, #hivm.address_space<ub>>)
      hivm.hir.nd2nz ins(%q_ub : memref<32x128xf16, #hivm.address_space<ub>>) outs(%q_l1 : memref<32x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.load ins(%K_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%k_ub : memref<176x128xf16, #hivm.address_space<ub>>)
      hivm.hir.load ins(%V_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%v_ub : memref<176x128xf16, #hivm.address_space<ub>>)
      hivm.hir.nd2nz ins(%k_ub : memref<176x128xf16, #hivm.address_space<ub>>) outs(%k_l1 : memref<176x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.nd2nz ins(%v_ub : memref<176x128xf16, #hivm.address_space<ub>>) outs(%v_l1 : memref<176x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.barrier {mode = "ALL"}
      hivm.hir.barrier {mode = "ALL"}
      hivm.hir.barrier {mode = "ALL"}
      hivm.hir.barrier {mode = "ALL"}
      hivm.hir.mmad ins(%q_l1, %k_l1 : memref<32x128xf16, #hivm.address_space<cbuf>>, memref<176x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c : memref<32x176xf32, #hivm.address_space<cc>>)
      hivm.hir.fixpipe ins(%s_l0c : memref<32x176xf32, #hivm.address_space<cc>>) outs(%s_ub : memref<32x176xf16, #hivm.address_space<ub>>)
      hivm.hir.vreduce ins(%s_ub : memref<32x176xf16, #hivm.address_space<ub>>) outs(%m_ub : memref<32x1xf32, #hivm.address_space<ub>>) {reduce_op="max"}
      hivm.hir.vsub ins(%s_ub, %m_ub : memref<32x176xf16, #hivm.address_space<ub>>, memref<32x1xf32, #hivm.address_space<ub>>) outs(%p_ub : memref<32x176xf16, #hivm.address_space<ub>>)
      hivm.hir.vexp ins(%p_ub : memref<32x176xf16, #hivm.address_space<ub>>) outs(%p_ub : memref<32x176xf16, #hivm.address_space<ub>>)
      hivm.hir.vadd ins(%p_ub, %s_ub : memref<32x176xf16, #hivm.address_space<ub>>, memref<32x176xf16, #hivm.address_space<ub>>) outs(%p_ub : memref<32x176xf16, #hivm.address_space<ub>>)
      hivm.hir.vmul ins(%p_ub, %s_ub : memref<32x176xf16, #hivm.address_space<ub>>, memref<32x176xf16, #hivm.address_space<ub>>) outs(%p_ub : memref<32x176xf16, #hivm.address_space<ub>>)
      hivm.hir.vsel ins(%p_ub, %s_ub : memref<32x176xf16, #hivm.address_space<ub>>, memref<32x176xf16, #hivm.address_space<ub>>) outs(%p_ub : memref<32x176xf16, #hivm.address_space<ub>>)
      hivm.hir.vreduce ins(%p_ub : memref<32x176xf16, #hivm.address_space<ub>>) outs(%l_ub : memref<32x1xf32, #hivm.address_space<ub>>) {reduce_op="sum"}
      hivm.hir.mmad ins(%p_ub, %v_l1 : memref<32x176xf16, #hivm.address_space<ub>>, memref<176x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c : memref<32x176xf32, #hivm.address_space<cc>>)
      hivm.hir.fixpipe ins(%s_l0c : memref<32x176xf32, #hivm.address_space<cc>>) outs(%acc_ub : memref<32x128xf32, #hivm.address_space<ub>>)
    }
    hivm.hir.vdiv ins(%acc_ub, %l_ub : memref<32x128xf32, #hivm.address_space<ub>>, memref<32x1xf32, #hivm.address_space<ub>>) outs(%acc_ub : memref<32x128xf32, #hivm.address_space<ub>>)
    hivm.hir.store ins(%q_ub : memref<32x128xf16, #hivm.address_space<ub>>) outs(%O_gm : memref<64x128xf16, #hivm.address_space<gm>>)
    return
  }
}
