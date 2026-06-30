module {
  // HIVM V5.5 TilingPlan operation rewrite candidate begin
  // selected tile_m=32 tile_n=64 tile_k=128 loop_order=outer_mkn tail_strategy=mask_or_pad reduce_tile_policy=half_k
  // local memref operation/type shapes below are rewritten; Linux backend must still verify loop/index/tail/reduction legality
  // HIVM V5.5 TilingPlan operation rewrite candidate end
  func.func @fa(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>, %K_gm : memref<1024x128xf16, #hivm.address_space<gm>>, %V_gm : memref<1024x128xf16, #hivm.address_space<gm>>, %O_gm : memref<64x128xf16, #hivm.address_space<gm>>) {
    // HIVM V5.5 TilingPlan shape rewrite on line 3: %q_ub [64, 128] -> [32, 128]
    %q_ub = memref.alloc() : memref<32x128xf16, #hivm.address_space<ub>
    // HIVM V5.0 MultiBufferPlan true rewrite: ping slot for %q_ub (multibuffer_true_rewrite_action_0000)
    %q_ub_mb0_ping = memref.alloc() : memref<32x128xf16, #hivm.address_space<ub>
    annotation.mark %q_ub_mb0_ping {hivm.multi_buffer_slot = "ping", hivm.rewrite_action = "multibuffer_true_rewrite_action_0000"} : memref<32x128xf16, #hivm.address_space<ub>
    // HIVM V5.0 MultiBufferPlan true rewrite: pong slot for %q_ub (multibuffer_true_rewrite_action_0000)
    %q_ub_mb0_pong = memref.alloc() : memref<32x128xf16, #hivm.address_space<ub>
    annotation.mark %q_ub_mb0_pong {hivm.multi_buffer_slot = "pong", hivm.rewrite_action = "multibuffer_true_rewrite_action_0000"} : memref<32x128xf16, #hivm.address_space<ub>
    // HIVM V5.5 TilingPlan shape rewrite on line 4: %acc_ub [64, 128] -> [32, 128]
    %acc_ub = memref.alloc() : memref<32x128xf32, #hivm.address_space<ub>
    // HIVM V5.5 TilingPlan shape rewrite on line 5: %s_ub [64, 96] -> [32, 64]
    %s_ub = memref.alloc() : memref<32x64xf16, #hivm.address_space<ub>
    // HIVM V5.0 MultiBufferPlan true rewrite: ping slot for %s_ub (multibuffer_true_rewrite_action_0001)
    %s_ub_mb1_ping = memref.alloc() : memref<32x64xf16, #hivm.address_space<ub>
    annotation.mark %s_ub_mb1_ping {hivm.multi_buffer_slot = "ping", hivm.rewrite_action = "multibuffer_true_rewrite_action_0001"} : memref<32x64xf16, #hivm.address_space<ub>
    // HIVM V5.0 MultiBufferPlan true rewrite: pong slot for %s_ub (multibuffer_true_rewrite_action_0001)
    %s_ub_mb1_pong = memref.alloc() : memref<32x64xf16, #hivm.address_space<ub>
    annotation.mark %s_ub_mb1_pong {hivm.multi_buffer_slot = "pong", hivm.rewrite_action = "multibuffer_true_rewrite_action_0001"} : memref<32x64xf16, #hivm.address_space<ub>
    // HIVM V5.5 TilingPlan shape rewrite on line 6: %p_ub [64, 96] -> [32, 64]
    %p_ub = memref.alloc() : memref<32x64xf16, #hivm.address_space<ub>
    // HIVM V5.5 TilingPlan shape rewrite on line 7: %m_ub [64, 1] -> [32, 1]
    %m_ub = memref.alloc() : memref<32x1xf32, #hivm.address_space<ub>
    // HIVM V5.5 TilingPlan shape rewrite on line 8: %l_ub [64, 1] -> [32, 1]
    %l_ub = memref.alloc() : memref<32x1xf32, #hivm.address_space<ub>
    // HIVM V5.5 TilingPlan shape rewrite on line 9: %k_ub [96, 128] -> [64, 128]
    %k_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>
    // HIVM V5.0 MultiBufferPlan true rewrite: ping slot for %k_ub (multibuffer_true_rewrite_action_0002)
    %k_ub_mb2_ping = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>
    annotation.mark %k_ub_mb2_ping {hivm.multi_buffer_slot = "ping", hivm.rewrite_action = "multibuffer_true_rewrite_action_0002"} : memref<64x128xf16, #hivm.address_space<ub>
    // HIVM V5.0 MultiBufferPlan true rewrite: pong slot for %k_ub (multibuffer_true_rewrite_action_0002)
    %k_ub_mb2_pong = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>
    annotation.mark %k_ub_mb2_pong {hivm.multi_buffer_slot = "pong", hivm.rewrite_action = "multibuffer_true_rewrite_action_0002"} : memref<64x128xf16, #hivm.address_space<ub>
    // HIVM V5.5 TilingPlan shape rewrite on line 10: %v_ub [96, 128] -> [64, 128]
    %v_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>
    // HIVM V5.5 TilingPlan shape rewrite on line 11: %q_l1 [64, 128] -> [32, 128]
    %q_l1 = memref.alloc() : memref<32x128xf16, #hivm.address_space<cbuf>
    // HIVM V5.5 TilingPlan shape rewrite on line 12: %k_l1_ping [96, 128] -> [64, 128]
    %k_l1_ping = memref.alloc() : memref<64x128xf16, #hivm.address_space<cbuf>
    // HIVM V5.5 TilingPlan shape rewrite on line 13: %k_l1_pong [96, 128] -> [64, 128]
    %k_l1_pong = memref.alloc() : memref<64x128xf16, #hivm.address_space<cbuf>
    // HIVM V5.5 TilingPlan shape rewrite on line 14: %v_l1 [96, 128] -> [64, 128]
    %v_l1 = memref.alloc() : memref<64x128xf16, #hivm.address_space<cbuf>
    // HIVM V5.5 TilingPlan shape rewrite on line 15: %s_l0c [64, 96] -> [32, 64]
    %s_l0c = memref.alloc() : memref<32x64xf32, #hivm.address_space<cc>
    // HIVM V5.5 TilingPlan shape rewrite on line 16: %q_ub [64, 128] -> [32, 128]
    // HIVM V5.0 MultiBufferPlan use replacement: producer %q_ub -> %q_ub_mb0_ping (multibuffer_true_rewrite_action_0000)
    hivm.hir.load ins(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub_mb0_ping : memref<32x128xf16, #hivm.address_space<ub>)
    // HIVM V5.5 TilingPlan shape rewrite on line 17: %q_ub [64, 128] -> [32, 128]
    // HIVM V5.0 MultiBufferPlan use replacement: consumer %q_ub -> %q_ub_mb0_ping (multibuffer_true_rewrite_action_0000)
    hivm.hir.nd2nz ins(%q_ub_mb0_ping : memref<32x128xf16, #hivm.address_space<ub>) outs(%q_l1 : memref<32x128xf16, #hivm.address_space<cbuf>)
    scf.for %j = %c0 to %cE step %cB {   // @trip=10
      // HIVM V5.5 TilingPlan shape rewrite on line 19: %k_ub [96, 128] -> [64, 128]
      // HIVM V5.0 MultiBufferPlan use replacement: producer %k_ub -> %k_ub_mb2_ping (multibuffer_true_rewrite_action_0002)
      hivm.hir.load ins(%K_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%k_ub_mb2_ping : memref<64x128xf16, #hivm.address_space<ub>)
      // HIVM V5.5 TilingPlan shape rewrite on line 20: %v_ub [96, 128] -> [64, 128]
      hivm.hir.load ins(%V_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%v_ub : memref<64x128xf16, #hivm.address_space<ub>)
      // HIVM V5.5 TilingPlan shape rewrite on line 21: %k_l1_ping [96, 128] -> [64, 128]
      // HIVM V5.0 MultiBufferPlan use replacement: consumer %k_ub -> %k_ub_mb2_ping (multibuffer_true_rewrite_action_0002)
      hivm.hir.nd2nz ins(%k_ub_mb2_ping : memref<64x128xf16, #hivm.address_space<ub>) outs(%k_l1_ping : memref<64x128xf16, #hivm.address_space<cbuf>)
      // HIVM V5.5 TilingPlan shape rewrite on line 22: %v_l1 [96, 128] -> [64, 128]
      hivm.hir.nd2nz ins(%v_ub : memref<64x128xf16, #hivm.address_space<ub>) outs(%v_l1 : memref<64x128xf16, #hivm.address_space<cbuf>)
      // HIVM V5.5 TilingPlan shape rewrite on line 23: %k_l1_pong [96, 128] -> [64, 128]
      hivm.hir.copy ins(%K_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%k_l1_pong : memref<64x128xf16, #hivm.address_space<cbuf>)
      hivm.hir.wait_flag {pipe="M",event="EVENT_ID0"}
      // HIVM V5.5 TilingPlan shape rewrite on line 25: %k_l1_ping [96, 128] -> [64, 128]
      hivm.hir.mmad ins(%q_l1, %k_l1_ping : memref<32x128xf16, #hivm.address_space<cbuf>)
      // HIVM V5.5 TilingPlan shape rewrite on line 26: %s_l0c [64, 96] -> [32, 64]
      // HIVM V5.0 MultiBufferPlan use replacement: producer %s_ub -> %s_ub_mb1_ping (multibuffer_true_rewrite_action_0001)
      hivm.hir.fixpipe ins(%s_l0c : memref<32x64xf32, #hivm.address_space<cc>) outs(%s_ub_mb1_ping : memref<32x64xf16, #hivm.address_space<ub>)
      // HIVM V5.5 TilingPlan shape rewrite on line 27: %m_ub [64, 96] -> [32, 1]
      // HIVM V5.0 MultiBufferPlan use replacement: consumer %s_ub -> %s_ub_mb1_ping (multibuffer_true_rewrite_action_0001)
      hivm.hir.vreduce ins(%s_ub_mb1_ping : memref<32x64xf16, #hivm.address_space<ub>) {reduce_op="max"}
      // HIVM V5.5 TilingPlan shape rewrite on line 28: %p_ub [64, 96] -> [32, 64]
      hivm.hir.vsub ins(%s_ub, %m_ub : memref<32x64xf16, #hivm.address_space<ub>)
      // HIVM V5.5 TilingPlan shape rewrite on line 29: %p_ub [64, 96] -> [32, 64]
      hivm.hir.vexp ins(%p_ub : memref<32x64xf16, #hivm.address_space<ub>) outs(%p_ub : memref<32x64xf16, #hivm.address_space<ub>)
      // HIVM V5.5 TilingPlan shape rewrite on line 30: %p_ub [64, 96] -> [32, 64]
      hivm.hir.vreduce ins(%p_ub : memref<32x1xf16, #hivm.address_space<ub>) {reduce_op="sum"}
      // HIVM V5.5 TilingPlan shape rewrite on line 31: %p_ub [64, 96] -> [32, 64]
      hivm.hir.nd2nz ins(%p_ub : memref<64x128xf16, #hivm.address_space<ub>)
      // HIVM V5.5 TilingPlan shape rewrite on line 32: %s_l0c [64, 96] -> [32, 64]
      hivm.hir.mmad ins(%p_ub, %v_l1 : memref<64x128xf16, #hivm.address_space<ub>) outs(%s_l0c : memref<32x64xf32, #hivm.address_space<cc>)
      // HIVM V5.5 TilingPlan shape rewrite on line 33: %acc_ub [64, 96] -> [32, 128]
      hivm.hir.fixpipe ins(%s_l0c : memref<32x64xf32, #hivm.address_space<cc>)
      hivm.hir.set_flag {pipe="FIX",event="EVENT_ID0"}
    }
    // HIVM V5.5 TilingPlan shape rewrite on line 36: %acc_ub [64, 128] -> [32, 128]
    hivm.hir.vdiv ins(%acc_ub, %l_ub : memref<32x1xf32, #hivm.address_space<ub>) outs(%acc_ub : memref<32x128xf32, #hivm.address_space<ub>)
    // HIVM V5.5 TilingPlan shape rewrite on line 37: %q_ub [64, 128] -> [32, 128]
    hivm.hir.store ins(%q_ub : memref<32x128xf16, #hivm.address_space<ub>) outs(%O_gm : memref<64x128xf16, #hivm.address_space<gm>>)
    return
  }
}