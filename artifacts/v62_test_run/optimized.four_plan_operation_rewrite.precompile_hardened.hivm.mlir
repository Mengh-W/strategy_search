module {
  // HIVM V5.5 TilingPlan operation rewrite candidate begin
  // selected tile_m=32 tile_n=64 tile_k=128 loop_order=outer_mkn tail_strategy=mask_or_pad reduce_tile_policy=half_k
  // local memref operation/type shapes below are rewritten; Linux backend must still verify loop/index/tail/reduction legality
  // HIVM V5.5 TilingPlan operation rewrite candidate end
  func.func @fa(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>, %K_gm : memref<1024x128xf16, #hivm.address_space<gm>>, %V_gm : memref<1024x128xf16, #hivm.address_space<gm>>, %O_gm : memref<64x128xf16, #hivm.address_space<gm>>) {
    // HIVM V5.7 precompile hardening: materialized tiling/index constants
    %c0 = arith.constant 0 : index
    %cB = arith.constant 64 : index
    %cE = arith.constant 1024 : index
    %cK = arith.constant 128 : index
    %cM = arith.constant 64 : index
    %cN = arith.constant 1024 : index
    %c32 = arith.constant 32 : index
    %c64 = arith.constant 64 : index
    %c128 = arith.constant 128 : index
    // HIVM V5.5 TilingPlan shape rewrite on line 3: %q_ub [64, 128] -> [32, 128]
    // HIVM V5.1 CVPipelinePlan group begin: cvpipeline_true_rewrite_action_0000 window=cv_window_0000
    //   restricted=true operation_movement=false loop_skewing=false
    %q_ub = memref.alloc() : memref<32x128xf16, #hivm.address_space<ub>>
    // HIVM V5.0 MultiBufferPlan true rewrite: ping slot for %q_ub (multibuffer_true_rewrite_action_0000)
    %q_ub_mb0_ping = memref.alloc() : memref<32x128xf16, #hivm.address_space<ub>>
    annotation.mark %q_ub_mb0_ping {hivm.multi_buffer_slot = "ping", hivm.rewrite_action = "multibuffer_true_rewrite_action_0000"} : memref<32x128xf16, #hivm.address_space<ub>>
    // HIVM V5.0 MultiBufferPlan true rewrite: pong slot for %q_ub (multibuffer_true_rewrite_action_0000)
    %q_ub_mb0_pong = memref.alloc() : memref<32x128xf16, #hivm.address_space<ub>>
    annotation.mark %q_ub_mb0_pong {hivm.multi_buffer_slot = "pong", hivm.rewrite_action = "multibuffer_true_rewrite_action_0000"} : memref<32x128xf16, #hivm.address_space<ub>>
    // HIVM V5.5 TilingPlan shape rewrite on line 4: %acc_ub [64, 128] -> [32, 128]
    // HIVM V5.1 CVPipelinePlan slot binding: %acc_ub -> %acc_ub_mb1_ping (cvpipeline_true_rewrite_action_0000)
    %acc_ub_mb1_ping = memref.alloc() : memref<32x128xf32, #hivm.address_space<ub>>
    // HIVM V5.0 MultiBufferPlan true rewrite: ping slot for %acc_ub (multibuffer_true_rewrite_action_0001)
    // HIVM V5.7 precompile hardening: removed duplicate identical alloc for %acc_ub_mb1_ping
    annotation.mark %acc_ub_mb1_ping {hivm.multi_buffer_slot = "ping", hivm.rewrite_action = "multibuffer_true_rewrite_action_0001"} : memref<32x128xf32, #hivm.address_space<ub>>
    // HIVM V5.0 MultiBufferPlan true rewrite: pong slot for %acc_ub (multibuffer_true_rewrite_action_0001)
    // HIVM V5.1 CVPipelinePlan slot binding: %acc_ub -> %acc_ub_mb1_ping (cvpipeline_true_rewrite_action_0000)
    %acc_ub_mb1_pong = memref.alloc() : memref<32x128xf32, #hivm.address_space<ub>>
    annotation.mark %acc_ub_mb1_pong {hivm.multi_buffer_slot = "pong", hivm.rewrite_action = "multibuffer_true_rewrite_action_0001"} : memref<32x128xf32, #hivm.address_space<ub>>
    // HIVM V5.5 TilingPlan shape rewrite on line 5: %s_ub [64, 96] -> [32, 64]
    %s_ub = memref.alloc() : memref<32x64xf16, #hivm.address_space<ub>>
    // HIVM V5.0 MultiBufferPlan true rewrite: ping slot for %s_ub (multibuffer_true_rewrite_action_0002)
    %s_ub_mb2_ping = memref.alloc() : memref<32x64xf16, #hivm.address_space<ub>>
    annotation.mark %s_ub_mb2_ping {hivm.multi_buffer_slot = "ping", hivm.rewrite_action = "multibuffer_true_rewrite_action_0002"} : memref<32x64xf16, #hivm.address_space<ub>>
    // HIVM V5.0 MultiBufferPlan true rewrite: pong slot for %s_ub (multibuffer_true_rewrite_action_0002)
    %s_ub_mb2_pong = memref.alloc() : memref<32x64xf16, #hivm.address_space<ub>>
    annotation.mark %s_ub_mb2_pong {hivm.multi_buffer_slot = "pong", hivm.rewrite_action = "multibuffer_true_rewrite_action_0002"} : memref<32x64xf16, #hivm.address_space<ub>>
    // HIVM V5.5 TilingPlan shape rewrite on line 6: %p_ub [64, 96] -> [32, 64]
    %p_ub = memref.alloc() : memref<32x64xf16, #hivm.address_space<ub>>
    // HIVM V5.0 MultiBufferPlan true rewrite: ping slot for %p_ub (multibuffer_true_rewrite_action_0003)
    %p_ub_mb3_ping = memref.alloc() : memref<32x64xf16, #hivm.address_space<ub>>
    annotation.mark %p_ub_mb3_ping {hivm.multi_buffer_slot = "ping", hivm.rewrite_action = "multibuffer_true_rewrite_action_0003"} : memref<32x64xf16, #hivm.address_space<ub>>
    // HIVM V5.0 MultiBufferPlan true rewrite: pong slot for %p_ub (multibuffer_true_rewrite_action_0003)
    %p_ub_mb3_pong = memref.alloc() : memref<32x64xf16, #hivm.address_space<ub>>
    annotation.mark %p_ub_mb3_pong {hivm.multi_buffer_slot = "pong", hivm.rewrite_action = "multibuffer_true_rewrite_action_0003"} : memref<32x64xf16, #hivm.address_space<ub>>
    // HIVM V5.5 TilingPlan shape rewrite on line 7: %m_ub [64, 1] -> [32, 1]
    %m_ub = memref.alloc() : memref<32x1xf32, #hivm.address_space<ub>>
    // HIVM V5.5 TilingPlan shape rewrite on line 8: %l_ub [64, 1] -> [32, 1]
    %l_ub = memref.alloc() : memref<32x1xf32, #hivm.address_space<ub>>
    // HIVM V5.5 TilingPlan shape rewrite on line 9: %k_ub [96, 128] -> [64, 128]
    %k_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    // HIVM V5.5 TilingPlan shape rewrite on line 10: %v_ub [96, 128] -> [64, 128]
    %v_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    // HIVM V5.5 TilingPlan shape rewrite on line 11: %q_l1 [64, 128] -> [32, 128]
    %q_l1 = memref.alloc() : memref<32x128xf16, #hivm.address_space<cbuf>>
    // HIVM V5.5 TilingPlan shape rewrite on line 12: %k_l1_ping [96, 128] -> [64, 128]
    %k_l1_ping = memref.alloc() : memref<64x128xf16, #hivm.address_space<cbuf>>
    // HIVM V5.5 TilingPlan shape rewrite on line 13: %k_l1_pong [96, 128] -> [64, 128]
    %k_l1_pong = memref.alloc() : memref<64x128xf16, #hivm.address_space<cbuf>>
    // HIVM V5.5 TilingPlan shape rewrite on line 14: %v_l1 [96, 128] -> [64, 128]
    %v_l1 = memref.alloc() : memref<64x128xf16, #hivm.address_space<cbuf>>
    // HIVM V5.5 TilingPlan shape rewrite on line 15: %s_l0c [64, 96] -> [32, 64]
    %s_l0c = memref.alloc() : memref<32x64xf32, #hivm.address_space<cc>>
    // HIVM V5.1 CVPipelinePlan sync edge: load_to_compute (cvpipeline_true_rewrite_action_0000)
    // HIVM V5.8 CVPipeline stage binding: role=pipeline_sync_stage schedule=prologue/steady/epilogue distance=1
    hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_V>, EVENT_ID_CVP_L2C_0]
    // HIVM V5.5 TilingPlan shape rewrite on line 16: %q_ub [64, 128] -> [32, 128]
    // HIVM V5.8 tile-slice binding: role=Q_load_or_Q_stage offsets=['%m_outer', '%k_outer'] shape=[32, 128] axes=['M', 'K']
    // HIVM V5.0 MultiBufferPlan use replacement: producer %q_ub -> %q_ub_mb0_ping (multibuffer_true_rewrite_action_0000)
    // HIVM V5.8 CVPipeline stage binding: role=producer_load_stage schedule=prologue/steady/epilogue distance=1
    hivm.hir.load ins(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub_mb0_ping : memref<32x128xf16, #hivm.address_space<ub>>)
    // HIVM V5.5 TilingPlan shape rewrite on line 17: %q_ub [64, 128] -> [32, 128]
    // HIVM V5.8 tile-slice binding: role=layout_transform_tile offsets=['propagate_from_input'] shape=['propagate_from_input'] axes=['layout-aware']
    // HIVM V5.0 MultiBufferPlan use replacement: consumer %q_ub -> %q_ub_mb0_ping (multibuffer_true_rewrite_action_0000)
    hivm.hir.nd2nz ins(%q_ub_mb0_ping : memref<32x128xf16, #hivm.address_space<ub>>) outs(%q_l1 : memref<32x128xf16, #hivm.address_space<cbuf>>)
    // HIVM V5.6 TilingPlan semantic operation rewrite begin
    // selected: tile_m=32 tile_n=64 tile_k=128 loop_order=outer_mkn tail_strategy=mask_or_pad reduce_tile_policy=half_k layout_aware_tile=True
    // operation-level intent: loop split + tiled load/store/compute slice + tail/reduction guards. Linux backend must bind %cM/%cN/%cK and verify official HIVM legality.
    scf.for %m_outer = %c0 to %cM step %c32 {   // HIVM V5.6 TilingPlan M-tile loop
      scf.for %k_outer = %c0 to %cK step %c128 {   // HIVM V5.6 TilingPlan K-tile loop
        scf.for %n_outer = %c0 to %cN step %c64 {   // HIVM V5.6 TilingPlan N-tile loop
          // HIVM V5.8 TilingPlan semantic binding begin
          // axis-binding: M=%m_outer extent=64 tile=32; N=%n_outer extent=1024 tile=64; K=%k_outer extent=128 tile=128
          // tail-semantics: mask_or_pad => tile_end=min(axis_extent, outer+tile), mask/pad required for non-divisible tiles
          // reduction-semantics: half_k => explicit partial accumulator guards for score/output reductions
          // HIVM V5.8 TilingPlan semantic binding end
          // HIVM V5.8 CVPipeline semantic schedule begin
          // stage_num=2 template=P2_stage2_balanced producer_consumer_distance=1 stage_buffer_policy=none
          // prologue: prefetch/load tile[0] into multibuffer slot 0
          // steady: for tile[i], load tile[i+1] while compute/vector/store consumes tile[i] with slot=(i mod buffer_count)
          // epilogue: drain remaining compute/vector/store stages after final producer tile
          // HIVM V5.8 CVPipeline semantic schedule end
          // HIVM V5.6 TilingPlan tail guard: strategy=mask_or_pad for partial M/N/K tiles
          // HIVM V5.6 TilingPlan reduction guard: policy=half_k effective_k_tile=128
          // HIVM V5.6 TilingPlan layout guard: layout_aware_tile=True
          scf.for %j = %c0 to %cE step %cB {   // @trip=10
            // HIVM V5.5 TilingPlan shape rewrite on line 28: %k_ub [96, 128] -> [64, 128]
            // HIVM V5.8 tile-slice binding: role=K_load_or_K_stage offsets=['%n_outer', '%k_outer'] shape=[64, 128] axes=['N', 'K']
            // HIVM V5.8 CVPipeline stage binding: role=producer_load_stage schedule=prologue/steady/epilogue distance=1
            hivm.hir.load ins(%K_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%k_ub : memref<64x128xf16, #hivm.address_space<ub>>)
            // HIVM V5.5 TilingPlan shape rewrite on line 29: %v_ub [96, 128] -> [64, 128]
            // HIVM V5.8 tile-slice binding: role=V_load_or_V_stage offsets=['%n_outer', '%d_outer'] shape=[64, 'D_tile'] axes=['N', 'D']
            // HIVM V5.8 CVPipeline stage binding: role=producer_load_stage schedule=prologue/steady/epilogue distance=1
            hivm.hir.load ins(%V_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%v_ub : memref<64x128xf16, #hivm.address_space<ub>>)
            // HIVM V5.5 TilingPlan shape rewrite on line 30: %k_l1_ping [96, 128] -> [64, 128]
            // HIVM V5.8 tile-slice binding: role=layout_transform_tile offsets=['propagate_from_input'] shape=['propagate_from_input'] axes=['layout-aware']
            hivm.hir.nd2nz ins(%k_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%k_l1_ping : memref<64x128xf16, #hivm.address_space<cbuf>>)
            // HIVM V5.5 TilingPlan shape rewrite on line 31: %v_ub [96, 128] -> [64, 128]
            // HIVM V5.8 tile-slice binding: role=layout_transform_tile offsets=['propagate_from_input'] shape=['propagate_from_input'] axes=['layout-aware']
            hivm.hir.nd2nz ins(%v_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%v_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>)
            // HIVM V5.5 TilingPlan shape rewrite on line 32: %k_l1_pong [96, 128] -> [64, 128]
            // HIVM V5.8 tile-slice binding: role=K_load_or_K_stage offsets=['%n_outer', '%k_outer'] shape=[64, 128] axes=['N', 'K']
            // HIVM V5.8 CVPipeline stage binding: role=producer_load_stage schedule=prologue/steady/epilogue distance=1
            hivm.hir.copy ins(%K_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%k_l1_pong : memref<64x128xf16, #hivm.address_space<cbuf>>)
            // HIVM V5.8 CVPipeline stage binding: role=pipeline_sync_stage schedule=prologue/steady/epilogue distance=1
            // HIVM V5.5 SyncPlan operation rewrite: normalized wait_flag pipe/event attrs from line 113
            hivm.hir.wait_flag[<PIPE_M>, <PIPE_M>, EVENT_ID0]
            // HIVM V5.5 TilingPlan shape rewrite on line 34: %k_l1_ping [96, 128] -> [64, 128]
            // HIVM V5.8 tile-slice binding: role=QK_score_tile_compute offsets=['%m_outer', '%n_outer', '%k_outer'] shape=[32, 64, 128] axes=['M', 'N', 'K']
            // HIVM V5.8 reduction binding: partial_accumulate_over_K policy=half_k init/update/final-store guarded by outer tile indices
    // HIVM V5.1 CVPipelinePlan wait edge: load_to_compute (cvpipeline_true_rewrite_action_0000)
    // HIVM V5.8 CVPipeline stage binding: role=pipeline_sync_stage schedule=prologue/steady/epilogue distance=1
    hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_V>, EVENT_ID_CVP_L2C_0]
            // HIVM V5.8 CVPipeline stage binding: role=cube_compute_stage schedule=prologue/steady/epilogue distance=1
            hivm.hir.mmad ins(%q_l1, %k_l1_ping  : memref<32x128xf16, #hivm.address_space<cbuf>, memref<64x128xf16, #hivm.address_space<cbuf>) outs(%s_l0c  : memref<32x64xf32, #hivm.address_space<cc>)
    // HIVM V5.1 CVPipelinePlan sync edge: compute_to_store (cvpipeline_true_rewrite_action_0000)
    // HIVM V5.8 CVPipeline stage binding: role=pipeline_sync_stage schedule=prologue/steady/epilogue distance=1
    hivm.hir.set_flag[<PIPE_V>, <PIPE_MTE3>, EVENT_ID_CVP_C2S_0]
            // HIVM V5.5 TilingPlan shape rewrite on line 35: %s_l0c [64, 96] -> [32, 64]
            // HIVM V5.8 tile-slice binding: role=vector_postprocess_tile_fixpipe offsets=['%m_outer', '%n_outer'] shape=[32, 64] axes=['M', 'N']
            // HIVM V5.0 MultiBufferPlan use replacement: producer %s_ub -> %s_ub_mb2_ping (multibuffer_true_rewrite_action_0002)
    // HIVM V5.1 CVPipelinePlan wait edge: compute_to_store (cvpipeline_true_rewrite_action_0000)
    // HIVM V5.8 CVPipeline stage binding: role=pipeline_sync_stage schedule=prologue/steady/epilogue distance=1
    hivm.hir.wait_flag[<PIPE_V>, <PIPE_MTE3>, EVENT_ID_CVP_C2S_0]
            hivm.hir.fixpipe ins(%s_l0c : memref<32x64xf32, #hivm.address_space<cc>>) outs(%s_ub_mb2_ping : memref<32x64xf16, #hivm.address_space<ub>>)
    // HIVM V5.1 CVPipelinePlan group end: cvpipeline_true_rewrite_action_0000
            // HIVM V5.5 TilingPlan shape rewrite on line 36: %m_ub [64, 96] -> [32, 1]
            // HIVM V5.8 tile-slice binding: role=vector_postprocess_tile_vreduce offsets=['%m_outer', '%n_outer'] shape=[32, 64] axes=['M', 'N']
            // HIVM V5.0 MultiBufferPlan use replacement: consumer %s_ub -> %s_ub_mb2_ping (multibuffer_true_rewrite_action_0002)
            // HIVM V5.8 CVPipeline stage binding: role=vector_postprocess_stage schedule=prologue/steady/epilogue distance=1
            hivm.hir.vreduce ins(%s_ub_mb2_ping : memref<32x64xf16, #hivm.address_space<ub>>) outs(%m_ub  : memref<32x1xf32, #hivm.address_space<ub>) {reduce_op="max"}
            // HIVM V5.5 TilingPlan shape rewrite on line 37: %m_ub [64, 96] -> [32, 1]
            // HIVM V5.8 tile-slice binding: role=vector_postprocess_tile_vsub offsets=['%m_outer', '%n_outer'] shape=[32, 64] axes=['M', 'N']
            // HIVM V5.0 MultiBufferPlan use replacement: producer %p_ub -> %p_ub_mb3_ping (multibuffer_true_rewrite_action_0003)
            // HIVM V5.8 CVPipeline stage binding: role=vector_postprocess_stage schedule=prologue/steady/epilogue distance=1
            hivm.hir.vsub ins(%s_ub, %m_ub  : memref<32x64xf16, #hivm.address_space<ub>, memref<32x1xf32, #hivm.address_space<ub>) outs(%p_ub_mb3_ping : memref<32x64xf16, #hivm.address_space<ub>>)
            // HIVM V5.5 TilingPlan shape rewrite on line 38: %p_ub [64, 96] -> [32, 64]
            // HIVM V5.8 tile-slice binding: role=vector_postprocess_tile_vexp offsets=['%m_outer', '%n_outer'] shape=[32, 64] axes=['M', 'N']
            // HIVM V5.0 MultiBufferPlan use replacement: consumer %p_ub -> %p_ub_mb3_ping (multibuffer_true_rewrite_action_0003)
            // HIVM V5.8 CVPipeline stage binding: role=vector_postprocess_stage schedule=prologue/steady/epilogue distance=1
            hivm.hir.vexp ins(%p_ub_mb3_ping : memref<32x64xf16, #hivm.address_space<ub>>) outs(%p_ub_mb3_ping : memref<32x64xf16, #hivm.address_space<ub>>)
            // HIVM V5.5 TilingPlan shape rewrite on line 39: %p_ub [64, 96] -> [32, 64]
            // HIVM V5.8 tile-slice binding: role=vector_postprocess_tile_vreduce offsets=['%m_outer', '%n_outer'] shape=[32, 64] axes=['M', 'N']
            // HIVM V5.8 CVPipeline stage binding: role=vector_postprocess_stage schedule=prologue/steady/epilogue distance=1
            hivm.hir.vreduce ins(%p_ub  : memref<32x64xf16, #hivm.address_space<ub>) outs(%l_ub : memref<32x1xf32, #hivm.address_space<ub>>) {reduce_op="sum"}
            // HIVM V5.5 TilingPlan shape rewrite on line 40: %p_ub [64, 96] -> [32, 64]
            // HIVM V5.8 tile-slice binding: role=layout_transform_tile offsets=['propagate_from_input'] shape=['propagate_from_input'] axes=['layout-aware']
            // HIVM V5.1 CVPipelinePlan group begin: cvpipeline_true_rewrite_action_0001 window=cv_window_0003
            //   restricted=true operation_movement=false loop_skewing=false
            hivm.hir.nd2nz ins(%p_ub  : memref<32x64xf16, #hivm.address_space<ub>) outs(%v_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>)
            // HIVM V5.1 CVPipelinePlan sync edge: load_to_compute (cvpipeline_true_rewrite_action_0001)
            // HIVM V5.8 CVPipeline stage binding: role=pipeline_sync_stage schedule=prologue/steady/epilogue distance=1
            hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_V>, EVENT_ID_CVP_L2C_1]
            // HIVM V5.5 TilingPlan shape rewrite on line 41: %s_l0c [64, 96] -> [32, 64]
            // HIVM V5.8 tile-slice binding: role=PV_output_tile_compute offsets=['%m_outer', '%d_outer', '%n_outer'] shape=[32, 'D_tile', 64] axes=['M', 'D', 'N']
            // HIVM V5.8 reduction binding: partial_accumulate_over_N policy=half_k init/update/final-store guarded by outer tile indices
            // HIVM V5.1 CVPipelinePlan wait edge: load_to_compute (cvpipeline_true_rewrite_action_0001)
            // HIVM V5.8 CVPipeline stage binding: role=pipeline_sync_stage schedule=prologue/steady/epilogue distance=1
            hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_V>, EVENT_ID_CVP_L2C_1]
            // HIVM V5.8 CVPipeline stage binding: role=cube_compute_stage schedule=prologue/steady/epilogue distance=1
            hivm.hir.mmad ins(%p_ub, %v_l1  : memref<32x64xf16, #hivm.address_space<ub>, memref<64x128xf16, #hivm.address_space<cbuf>) outs(%s_l0c  : memref<32x64xf32, #hivm.address_space<cc>)
            // HIVM V5.1 CVPipelinePlan sync edge: compute_to_store (cvpipeline_true_rewrite_action_0001)
            // HIVM V5.8 CVPipeline stage binding: role=pipeline_sync_stage schedule=prologue/steady/epilogue distance=1
            hivm.hir.set_flag[<PIPE_V>, <PIPE_MTE3>, EVENT_ID_CVP_C2S_1]
            // HIVM V5.5 TilingPlan shape rewrite on line 42: %acc_ub [64, 96] -> [32, 128]
            // HIVM V5.8 tile-slice binding: role=vector_postprocess_tile_fixpipe offsets=['%m_outer', '%n_outer'] shape=[32, 64] axes=['M', 'N']
            // HIVM V5.0 MultiBufferPlan use replacement: producer %acc_ub -> %acc_ub_mb1_ping (multibuffer_true_rewrite_action_0001)
            // HIVM V5.1 CVPipelinePlan wait edge: compute_to_store (cvpipeline_true_rewrite_action_0001)
            // HIVM V5.8 CVPipeline stage binding: role=pipeline_sync_stage schedule=prologue/steady/epilogue distance=1
            hivm.hir.wait_flag[<PIPE_V>, <PIPE_MTE3>, EVENT_ID_CVP_C2S_1]
            hivm.hir.fixpipe ins(%s_l0c : memref<32x64xf32, #hivm.address_space<cc>>) outs(%acc_ub_mb1_ping  : memref<32x128xf32, #hivm.address_space<ub>)
            // HIVM V5.1 CVPipelinePlan group end: cvpipeline_true_rewrite_action_0001
            // HIVM V5.8 CVPipeline stage binding: role=pipeline_sync_stage schedule=prologue/steady/epilogue distance=1
            // HIVM V5.5 SyncPlan operation rewrite: normalized set_flag pipe/event attrs from line 180
            hivm.hir.set_flag[<PIPE_FIX>, <PIPE_FIX>, EVENT_ID0]
          }
        } // HIVM V5.6 end N-tile loop
      } // HIVM V5.6 end K-tile loop
    } // HIVM V5.6 end M-tile loop
    // HIVM V5.6 TilingPlan semantic operation rewrite end
    // HIVM V5.5 TilingPlan shape rewrite on line 49: %acc_ub [64, 128] -> [32, 128]
    // HIVM V5.8 tile-slice binding: role=vector_postprocess_tile_vdiv offsets=['%m_outer', '%n_outer'] shape=[32, 64] axes=['M', 'N']
    // HIVM V5.0 MultiBufferPlan use replacement: consumer %acc_ub -> %acc_ub_mb1_ping (multibuffer_true_rewrite_action_0001)
    // HIVM V5.8 CVPipeline stage binding: role=vector_postprocess_stage schedule=prologue/steady/epilogue distance=1
    hivm.hir.vdiv ins(%acc_ub_mb1_ping, %l_ub  : memref<32x128xf32, #hivm.address_space<ub>, memref<32x1xf32, #hivm.address_space<ub>) outs(%acc_ub_mb1_ping  : memref<32x128xf32, #hivm.address_space<ub>)
    // HIVM V5.5 TilingPlan shape rewrite on line 50: %q_ub [64, 128] -> [32, 128]
    // HIVM V5.8 tile-slice binding: role=O_store_tile offsets=['%m_outer', '%d_outer'] shape=[32, 'D_tile'] axes=['M', 'D']
    // HIVM V5.8 CVPipeline stage binding: role=consumer_store_stage schedule=prologue/steady/epilogue distance=1
    hivm.hir.store ins(%q_ub : memref<32x128xf16, #hivm.address_space<ub>>) outs(%O_gm : memref<64x128xf16, #hivm.address_space<gm>>)
    return
  }
}