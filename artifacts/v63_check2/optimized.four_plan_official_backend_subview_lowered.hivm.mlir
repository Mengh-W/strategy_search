module {
  // selected tile_m=32 tile_n=64 tile_k=128 loop_order=outer_mkn tail_strategy=mask_or_pad reduce_tile_policy=half_k
  func.func @fa(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>, %K_gm : memref<1024x128xf16, #hivm.address_space<gm>>, %V_gm : memref<1024x128xf16, #hivm.address_space<gm>>, %O_gm : memref<64x128xf16, #hivm.address_space<gm>>) {
    %c0 = arith.constant 0 : index
    %cB = arith.constant 64 : index
    %cE = arith.constant 1024 : index
    %cK = arith.constant 128 : index
    %cM = arith.constant 64 : index
    %cN = arith.constant 1024 : index
    %c32 = arith.constant 32 : index
    %c64 = arith.constant 64 : index
    %c128 = arith.constant 128 : index
    %q_ub = memref.alloc() : memref<32x128xf16, #hivm.address_space<ub>>
    %q_ub_mb0_ping = memref.alloc() {} : memref<32x128xf16, #hivm.address_space<ub>>
    %q_ub_mb0_pong = memref.alloc() {} : memref<32x128xf16, #hivm.address_space<ub>>
    %acc_ub_mb1_ping = memref.alloc() {} : memref<32x128xf32, #hivm.address_space<ub>>
    %acc_ub_mb1_pong = memref.alloc() {} : memref<32x128xf32, #hivm.address_space<ub>>
    %s_ub = memref.alloc() : memref<32x64xf16, #hivm.address_space<ub>>
    %s_ub_mb2_ping = memref.alloc() {} : memref<32x64xf16, #hivm.address_space<ub>>
    %s_ub_mb2_pong = memref.alloc() {} : memref<32x64xf16, #hivm.address_space<ub>>
    %p_ub = memref.alloc() : memref<32x64xf16, #hivm.address_space<ub>>
    %p_ub_mb3_ping = memref.alloc() {} : memref<32x64xf16, #hivm.address_space<ub>>
    %p_ub_mb3_pong = memref.alloc() {} : memref<32x64xf16, #hivm.address_space<ub>>
    %m_ub = memref.alloc() : memref<32x1xf32, #hivm.address_space<ub>>
    %l_ub = memref.alloc() : memref<32x1xf32, #hivm.address_space<ub>>
    %k_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    %v_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    %q_l1 = memref.alloc() : memref<32x128xf16, #hivm.address_space<cbuf>>
    %k_l1_ping = memref.alloc() : memref<64x128xf16, #hivm.address_space<cbuf>>
    %k_l1_pong = memref.alloc() : memref<64x128xf16, #hivm.address_space<cbuf>>
    %v_l1 = memref.alloc() : memref<64x128xf16, #hivm.address_space<cbuf>>
    %s_l0c = memref.alloc() : memref<32x64xf32, #hivm.address_space<cc>>
    hivm.hir.set_flag {pipe="MTE2", event="EVENT_ID_CVP_L2C_0", producer_pipe="MTE2", consumer_pipe="V"}
    %Q_gm_tile_v63_0 = memref.subview %Q_gm[%c0, %c0] [32, 128] [1, 1] : memref<64x128xf16, #hivm.address_space<gm>> to memref<32x128xf16, #hivm.address_space<gm>>
    hivm.hir.load ins(%Q_gm_tile_v63_0 : memref<32x128xf16, #hivm.address_space<gm>>) outs(%q_ub_mb0_ping : memref<32x128xf16, #hivm.address_space<ub>>)
    hivm.hir.nd2nz ins(%q_ub_mb0_ping : memref<32x128xf16, #hivm.address_space<ub>>) outs(%q_l1 : memref<32x128xf16, #hivm.address_space<cbuf>>)
    scf.for %m_outer = %c0 to %cM step %c32 {   // HIVM V5.6 TilingPlan M-tile loop
      scf.for %k_outer = %c0 to %cK step %c128 {   // HIVM V5.6 TilingPlan K-tile loop
        scf.for %n_outer = %c0 to %cN step %c64 {   // HIVM V5.6 TilingPlan N-tile loop
          scf.for %j = %c0 to %cE step %cB {   // @trip=10
            %K_gm_tile_v63_1 = memref.subview %K_gm[%n_outer, %k_outer] [64, 128] [1, 1] : memref<1024x128xf16, #hivm.address_space<gm>> to memref<64x128xf16, #hivm.address_space<gm>>
            hivm.hir.load ins(%K_gm_tile_v63_1 : memref<64x128xf16, #hivm.address_space<gm>>) outs(%k_ub : memref<64x128xf16, #hivm.address_space<ub>>)
            %V_gm_tile_v63_2 = memref.subview %V_gm[%n_outer, %c0] [64, 128] [1, 1] : memref<1024x128xf16, #hivm.address_space<gm>> to memref<64x128xf16, #hivm.address_space<gm>>
            hivm.hir.load ins(%V_gm_tile_v63_2 : memref<64x128xf16, #hivm.address_space<gm>>) outs(%v_ub : memref<64x128xf16, #hivm.address_space<ub>>)
            hivm.hir.nd2nz ins(%k_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%k_l1_ping : memref<64x128xf16, #hivm.address_space<cbuf>>)
            hivm.hir.nd2nz ins(%v_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%v_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>)
            hivm.hir.copy ins(%K_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%k_l1_pong : memref<64x128xf16, #hivm.address_space<cbuf>>)
            hivm.hir.wait_flag {pipe="M", event="EVENT_ID0", producer_pipe="M", consumer_pipe="M"}
    hivm.hir.wait_flag {pipe="V", event="EVENT_ID_CVP_L2C_0", producer_pipe="MTE2", consumer_pipe="V"}
            hivm.hir.mmad ins(%q_l1, %k_l1_ping  : memref<32x128xf16, #hivm.address_space<cbuf>>, memref<64x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c  : memref<32x64xf32, #hivm.address_space<cc>>)
    hivm.hir.set_flag {pipe="V", event="EVENT_ID_CVP_C2S_0", producer_pipe="V", consumer_pipe="MTE3"}
    hivm.hir.wait_flag {pipe="MTE3", event="EVENT_ID_CVP_C2S_0", producer_pipe="V", consumer_pipe="MTE3"}
            hivm.hir.fixpipe ins(%s_l0c : memref<32x64xf32, #hivm.address_space<cc>>) outs(%s_ub_mb2_ping : memref<32x64xf16, #hivm.address_space<ub>>)
            hivm.hir.vreduce ins(%s_ub_mb2_ping  : memref<32x64xf16, #hivm.address_space<ub>>) outs(%m_ub : memref<32x1xf32, #hivm.address_space<ub>>) {reduce_op="max"}
            hivm.hir.vsub ins(%s_ub_mb2_ping, %m_ub  : memref<32x64xf16, #hivm.address_space<ub>>, memref<32x1xf32, #hivm.address_space<ub>>) outs(%p_ub_mb3_ping  : memref<32x64xf16, #hivm.address_space<ub>>)
            hivm.hir.vexp ins(%p_ub_mb3_ping : memref<32x64xf16, #hivm.address_space<ub>>) outs(%p_ub_mb3_ping : memref<32x64xf16, #hivm.address_space<ub>>)
            hivm.hir.vreduce ins(%p_ub_mb3_ping  : memref<32x64xf16, #hivm.address_space<ub>>) outs(%l_ub : memref<32x1xf32, #hivm.address_space<ub>>) {reduce_op="sum"}
            hivm.hir.nd2nz ins(%p_ub_mb3_ping  : memref<32x64xf16, #hivm.address_space<ub>>) outs(%v_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>)
            hivm.hir.set_flag {pipe="MTE2", event="EVENT_ID_CVP_L2C_1", producer_pipe="MTE2", consumer_pipe="V"}
            hivm.hir.wait_flag {pipe="V", event="EVENT_ID_CVP_L2C_1", producer_pipe="MTE2", consumer_pipe="V"}
            hivm.hir.mmad ins(%p_ub_mb3_ping, %v_l1  : memref<32x64xf16, #hivm.address_space<ub>>, memref<64x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c  : memref<32x64xf32, #hivm.address_space<cc>>)
            hivm.hir.set_flag {pipe="V", event="EVENT_ID_CVP_C2S_1", producer_pipe="V", consumer_pipe="MTE3"}
            hivm.hir.wait_flag {pipe="MTE3", event="EVENT_ID_CVP_C2S_1", producer_pipe="V", consumer_pipe="MTE3"}
            hivm.hir.fixpipe ins(%s_l0c : memref<32x64xf32, #hivm.address_space<cc>>) outs(%acc_ub_mb1_ping  : memref<32x128xf32, #hivm.address_space<ub>>)
            hivm.hir.set_flag {pipe="FIX", event="EVENT_ID0", producer_pipe="FIX", consumer_pipe="FIX"}
          }
        } // HIVM V5.6 end N-tile loop
      } // HIVM V5.6 end K-tile loop
    } // HIVM V5.6 end M-tile loop
    hivm.hir.vdiv ins(%acc_ub_mb1_ping, %l_ub  : memref<32x128xf32, #hivm.address_space<ub>>, memref<32x1xf32, #hivm.address_space<ub>>) outs(%acc_ub_mb1_ping  : memref<32x128xf32, #hivm.address_space<ub>>)
    %O_gm_tile_v63_3 = memref.subview %O_gm[%c0, %c0] [32, 128] [1, 1] : memref<64x128xf16, #hivm.address_space<gm>> to memref<32x128xf16, #hivm.address_space<gm>>
    hivm.hir.store ins(%q_ub_mb0_ping : memref<32x128xf16, #hivm.address_space<ub>>) outs(%O_gm_tile_v63_3 : memref<32x128xf16, #hivm.address_space<gm>>)
    return
  }
}