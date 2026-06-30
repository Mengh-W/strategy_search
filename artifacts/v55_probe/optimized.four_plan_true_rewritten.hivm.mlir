module {
// HIVM V5.2 TilingPlan true rewrite begin: tiling_true_rewrite_action_0000
//   metadata-level rewrite only; loop/index/memref-shape mutation is intentionally disabled
%hivm_tile_m_v52 = arith.constant 32 : index
%hivm_tile_n_v52 = arith.constant 64 : index
%hivm_tile_k_v52 = arith.constant 128 : index
annotation.mark %hivm_tile_m_v52 {hivm.tiling.axis = "m", hivm.tiling.value = 32, hivm.rewrite_action = "tiling_true_rewrite_action_0000"} : index
annotation.mark %hivm_tile_n_v52 {hivm.tiling.axis = "n", hivm.tiling.value = 64, hivm.rewrite_action = "tiling_true_rewrite_action_0000"} : index
annotation.mark %hivm_tile_k_v52 {hivm.tiling.axis = "k", hivm.tiling.value = 128, hivm.rewrite_action = "tiling_true_rewrite_action_0000"} : index
// HIVM V5.2 TilingPlan metadata: loop_order=outer_mkn tail_strategy=mask_or_pad reduce_tile_policy=half_k
// HIVM V5.2 TilingPlan true rewrite end: tiling_true_rewrite_action_0000
  func.func @fa(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>, %K_gm : memref<1024x128xf16, #hivm.address_space<gm>>, %V_gm : memref<1024x128xf16, #hivm.address_space<gm>>, %O_gm : memref<64x128xf16, #hivm.address_space<gm>>) {
  // HIVM V5.3 Four-Plan selected-parameter rewrite metadata begin
  //   This block makes every selected controllable knob traceable in the optimized IR.
  //   RESTRICTED_STRUCTURAL_REWRITE = visible portable IR mutation; TRACE_METADATA_REWRITE = traceability metadata only; PRODUCTION_OPERATION_REWRITE is reserved for verified backend rewrites.
  // hivm.param plan=tiling_plan key=tile_m level=RESTRICTED_STRUCTURAL_REWRITE consumer=tiling_metadata_constants value=32
  // hivm.param plan=tiling_plan key=tile_n level=RESTRICTED_STRUCTURAL_REWRITE consumer=tiling_metadata_constants value=64
  // hivm.param plan=tiling_plan key=tile_k level=RESTRICTED_STRUCTURAL_REWRITE consumer=tiling_metadata_constants value=128
  // hivm.param plan=tiling_plan key=logical_axes level=TRACE_METADATA_REWRITE consumer=selected_plan_metadata_block value=["axis_m", "axis_n", "axis_k"]
  // hivm.param plan=tiling_plan key=loop_order level=TRACE_METADATA_REWRITE consumer=tiling_metadata_annotation value="outer_mkn"
  // hivm.param plan=tiling_plan key=tail_strategy level=TRACE_METADATA_REWRITE consumer=tiling_metadata_annotation value="mask_or_pad"
  // hivm.param plan=tiling_plan key=reduce_tile_policy level=TRACE_METADATA_REWRITE consumer=tiling_metadata_annotation value="half_k"
  // hivm.param plan=tiling_plan key=layout_aware_tile level=TRACE_METADATA_REWRITE consumer=selected_plan_metadata_block value=true
  // hivm.param plan=multibuffer_plan key=double_buffer level=RESTRICTED_STRUCTURAL_REWRITE consumer=ping_pong_slot_insertion value=true
  // hivm.param plan=multibuffer_plan key=template level=TRACE_METADATA_REWRITE consumer=selected_plan_metadata_block value="M1_input_double_buffer"
  // hivm.param plan=multibuffer_plan key=input_buffer_multiplier level=TRACE_METADATA_REWRITE consumer=ping_pong_slot_selection_or_metadata value=2
  // hivm.param plan=multibuffer_plan key=stage_buffer_multiplier level=TRACE_METADATA_REWRITE consumer=ping_pong_slot_selection_or_metadata value=2
  // hivm.param plan=multibuffer_plan key=ub_multiplier level=TRACE_METADATA_REWRITE consumer=scope_specific_multibuffer_metadata value=1
  // hivm.param plan=multibuffer_plan key=l1_multiplier level=TRACE_METADATA_REWRITE consumer=scope_specific_multibuffer_metadata value=1
  // hivm.param plan=multibuffer_plan key=stage_buffer_policy level=RESTRICTED_STRUCTURAL_REWRITE consumer=producer_consumer_replacement_policy value="none"
  // hivm.param plan=multibuffer_plan key=buffer_multipliers level=TRACE_METADATA_REWRITE consumer=per_scope_buffer_multiplier_metadata value={"k_l1": 1, "q_l1": 1, "q_ub": 1, "v_l1": 1}
  // hivm.param plan=multibuffer_plan key=buffer_multiplier_domain level=TRACE_METADATA_REWRITE consumer=allowed_multiplier_domain_metadata value={"k_l1": [1, 2], "q_l1": [1, 2], "q_ub": [1, 2], "v_l1": [1, 2]}
  // hivm.param plan=multibuffer_plan key=detected_ping_pong_multibuffer level=TRACE_METADATA_REWRITE consumer=existing_pingpong_evidence_metadata value=false
  // hivm.param plan=cv_pipeline_plan key=stage_num level=TRACE_METADATA_REWRITE consumer=pipeline_group_and_sync_edge_count_metadata value=2
  // hivm.param plan=cv_pipeline_plan key=template level=TRACE_METADATA_REWRITE consumer=selected_plan_metadata_block value="P2_stage2_balanced"
  // hivm.param plan=cv_pipeline_plan key=enable_mixed_cv level=TRACE_METADATA_REWRITE consumer=mixed_cv_pipeline_policy_metadata value=false
  // hivm.param plan=cv_pipeline_plan key=tile_mix_cube_loop level=TRACE_METADATA_REWRITE consumer=pipeline_window_selection_metadata value=1
  // hivm.param plan=cv_pipeline_plan key=tile_mix_vector_loop level=TRACE_METADATA_REWRITE consumer=pipeline_window_selection_metadata value=1
  // hivm.param plan=cv_pipeline_plan key=auto_cv_balance level=TRACE_METADATA_REWRITE consumer=pipeline_window_selection_metadata value=true
  // hivm.param plan=cv_pipeline_plan key=producer_consumer_distance level=RESTRICTED_STRUCTURAL_REWRITE consumer=load_compute_store_sync_edge_policy value=1
  // hivm.param plan=cv_pipeline_plan key=stage_buffer_policy level=RESTRICTED_STRUCTURAL_REWRITE consumer=pipeline_buffer_binding_policy value="none"
  // hivm.param plan=sync_plan key=policy level=RESTRICTED_STRUCTURAL_REWRITE consumer=barrier_to_event_pair_rewrite_policy value="graph_sync_solver"
  // hivm.param plan=sync_plan key=template level=TRACE_METADATA_REWRITE consumer=selected_plan_metadata_block value="Y3_event_reuse"
  // hivm.param plan=sync_plan key=barrier_level level=RESTRICTED_STRUCTURAL_REWRITE consumer=barrier_candidate_selection_policy value="low"
  // hivm.param plan=sync_plan key=event_reuse level=TRACE_METADATA_REWRITE consumer=event_id_allocation_policy value=true
  // hivm.param plan=sync_plan key=sync_granularity level=TRACE_METADATA_REWRITE consumer=sync_candidate_granularity_policy value="stage"
  // hivm.param plan=sync_plan key=event_id_policy level=RESTRICTED_STRUCTURAL_REWRITE consumer=generated_event_id_policy value="reuse"
  // hivm.param plan=sync_plan key=sync_motion level=TRACE_METADATA_REWRITE consumer=sync_motion_guard_metadata value="local_move"
  // hivm.param plan=sync_plan key=remove_redundant_sync level=TRACE_METADATA_REWRITE consumer=sync_cleanup_guard_metadata value=true
  // hivm.param plan=sync_plan key=sync_style_from_ir level=TRACE_METADATA_REWRITE consumer=existing_sync_style_evidence_metadata value="barrier"
  // HIVM V5.3 Four-Plan selected-parameter rewrite metadata end
    // HIVM V5.1 CVPipelinePlan group begin: cvpipeline_true_rewrite_action_0000 window=cv_window_0000
    //   restricted=true operation_movement=false loop_skewing=false
    %q_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    // HIVM V5.0 MultiBufferPlan true rewrite: ping slot for %q_ub (multibuffer_true_rewrite_action_0000)
    %q_ub_mb0_ping = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    annotation.mark %q_ub_mb0_ping {hivm.multi_buffer_slot = "ping", hivm.rewrite_action = "multibuffer_true_rewrite_action_0000"} : memref<64x128xf16, #hivm.address_space<ub>>
    // HIVM V5.0 MultiBufferPlan true rewrite: pong slot for %q_ub (multibuffer_true_rewrite_action_0000)
    %q_ub_mb0_pong = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
    annotation.mark %q_ub_mb0_pong {hivm.multi_buffer_slot = "pong", hivm.rewrite_action = "multibuffer_true_rewrite_action_0000"} : memref<64x128xf16, #hivm.address_space<ub>>
    // HIVM V5.1 CVPipelinePlan slot binding: %acc_ub -> %acc_ub_mb1_ping (cvpipeline_true_rewrite_action_0000)
    %acc_ub_mb1_ping = memref.alloc() : memref<64x128xf32, #hivm.address_space<ub>>
    // HIVM V5.0 MultiBufferPlan true rewrite: ping slot for %acc_ub (multibuffer_true_rewrite_action_0001)
    %acc_ub_mb1_ping = memref.alloc() : memref<64x128xf32, #hivm.address_space<ub>>
    annotation.mark %acc_ub_mb1_ping {hivm.multi_buffer_slot = "ping", hivm.rewrite_action = "multibuffer_true_rewrite_action_0001"} : memref<64x128xf32, #hivm.address_space<ub>>
    // HIVM V5.0 MultiBufferPlan true rewrite: pong slot for %acc_ub (multibuffer_true_rewrite_action_0001)
    // HIVM V5.1 CVPipelinePlan slot binding: %acc_ub -> %acc_ub_mb1_ping (cvpipeline_true_rewrite_action_0000)
    %acc_ub_mb1_pong = memref.alloc() : memref<64x128xf32, #hivm.address_space<ub>>
    annotation.mark %acc_ub_mb1_pong {hivm.multi_buffer_slot = "pong", hivm.rewrite_action = "multibuffer_true_rewrite_action_0001"} : memref<64x128xf32, #hivm.address_space<ub>>
    %s_ub = memref.alloc() : memref<64x96xf16, #hivm.address_space<ub>>
    // HIVM V5.0 MultiBufferPlan true rewrite: ping slot for %s_ub (multibuffer_true_rewrite_action_0002)
    %s_ub_mb2_ping = memref.alloc() : memref<64x96xf16, #hivm.address_space<ub>>
    annotation.mark %s_ub_mb2_ping {hivm.multi_buffer_slot = "ping", hivm.rewrite_action = "multibuffer_true_rewrite_action_0002"} : memref<64x96xf16, #hivm.address_space<ub>>
    // HIVM V5.0 MultiBufferPlan true rewrite: pong slot for %s_ub (multibuffer_true_rewrite_action_0002)
    %s_ub_mb2_pong = memref.alloc() : memref<64x96xf16, #hivm.address_space<ub>>
    annotation.mark %s_ub_mb2_pong {hivm.multi_buffer_slot = "pong", hivm.rewrite_action = "multibuffer_true_rewrite_action_0002"} : memref<64x96xf16, #hivm.address_space<ub>>
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
    // HIVM V5.1 CVPipelinePlan sync edge: load_to_compute (cvpipeline_true_rewrite_action_0000)
    hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_V>, EVENT_ID_CVP_L2C_0]
    // HIVM V5.0 MultiBufferPlan use replacement: producer %q_ub -> %q_ub_mb0_ping (multibuffer_true_rewrite_action_0000)
    hivm.hir.load ins(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub_mb0_ping : memref<64x128xf16, #hivm.address_space<ub>>)
    // HIVM V5.0 MultiBufferPlan use replacement: consumer %q_ub -> %q_ub_mb0_ping (multibuffer_true_rewrite_action_0000)
    hivm.hir.nd2nz ins(%q_ub_mb0_ping : memref<64x128xf16, #hivm.address_space<ub>>) outs(%q_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>)
    scf.for %j = %c0 to %cE step %cB {   // @trip=10
      hivm.hir.load ins(%K_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%k_ub : memref<96x128xf16, #hivm.address_space<ub>>)
      hivm.hir.load ins(%V_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%v_ub : memref<96x128xf16, #hivm.address_space<ub>>)
      hivm.hir.nd2nz ins(%k_ub : memref<96x128xf16, #hivm.address_space<ub>>) outs(%k_l1_ping : memref<96x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.nd2nz ins(%v_ub : memref<96x128xf16, #hivm.address_space<ub>>) outs(%v_l1 : memref<96x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.copy ins(%K_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%k_l1_pong : memref<96x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.wait_flag {pipe="M",event="EVENT_ID0"}
    // HIVM V5.1 CVPipelinePlan wait edge: load_to_compute (cvpipeline_true_rewrite_action_0000)
    hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_V>, EVENT_ID_CVP_L2C_0]
      hivm.hir.mmad ins(%q_l1, %k_l1_ping : memref<64x128xf16, #hivm.address_space<cbuf>>, memref<96x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c : memref<64x96xf32, #hivm.address_space<cc>>)
    // HIVM V5.1 CVPipelinePlan sync edge: compute_to_store (cvpipeline_true_rewrite_action_0000)
    hivm.hir.set_flag[<PIPE_V>, <PIPE_MTE3>, EVENT_ID_CVP_C2S_0]
      // HIVM V5.0 MultiBufferPlan use replacement: producer %s_ub -> %s_ub_mb2_ping (multibuffer_true_rewrite_action_0002)
    // HIVM V5.1 CVPipelinePlan wait edge: compute_to_store (cvpipeline_true_rewrite_action_0000)
    hivm.hir.wait_flag[<PIPE_V>, <PIPE_MTE3>, EVENT_ID_CVP_C2S_0]
      hivm.hir.fixpipe ins(%s_l0c : memref<64x96xf32, #hivm.address_space<cc>>) outs(%s_ub_mb2_ping : memref<64x96xf16, #hivm.address_space<ub>>)
    // HIVM V5.1 CVPipelinePlan group end: cvpipeline_true_rewrite_action_0000
      // HIVM V5.0 MultiBufferPlan use replacement: consumer %s_ub -> %s_ub_mb2_ping (multibuffer_true_rewrite_action_0002)
      hivm.hir.vreduce ins(%s_ub_mb2_ping : memref<64x96xf16, #hivm.address_space<ub>>) outs(%m_ub : memref<64x1xf32, #hivm.address_space<ub>>) {reduce_op="max"}
      hivm.hir.vsub ins(%s_ub, %m_ub : memref<64x96xf16, #hivm.address_space<ub>>, memref<64x1xf32, #hivm.address_space<ub>>) outs(%p_ub : memref<64x96xf16, #hivm.address_space<ub>>)
      hivm.hir.vexp ins(%p_ub : memref<64x96xf16, #hivm.address_space<ub>>) outs(%p_ub : memref<64x96xf16, #hivm.address_space<ub>>)
      hivm.hir.vreduce ins(%p_ub : memref<64x96xf16, #hivm.address_space<ub>>) outs(%l_ub : memref<64x1xf32, #hivm.address_space<ub>>) {reduce_op="sum"}
      // HIVM V5.1 CVPipelinePlan group begin: cvpipeline_true_rewrite_action_0001 window=cv_window_0003
      //   restricted=true operation_movement=false loop_skewing=false
      hivm.hir.nd2nz ins(%p_ub : memref<64x96xf16, #hivm.address_space<ub>>) outs(%v_l1 : memref<96x128xf16, #hivm.address_space<cbuf>>)
      // HIVM V5.1 CVPipelinePlan sync edge: load_to_compute (cvpipeline_true_rewrite_action_0001)
      hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_V>, EVENT_ID_CVP_L2C_1]
      // HIVM V5.1 CVPipelinePlan wait edge: load_to_compute (cvpipeline_true_rewrite_action_0001)
      hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_V>, EVENT_ID_CVP_L2C_1]
      hivm.hir.mmad ins(%p_ub, %v_l1 : memref<64x96xf16, #hivm.address_space<ub>>, memref<96x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c : memref<64x96xf32, #hivm.address_space<cc>>)
      // HIVM V5.1 CVPipelinePlan sync edge: compute_to_store (cvpipeline_true_rewrite_action_0001)
      hivm.hir.set_flag[<PIPE_V>, <PIPE_MTE3>, EVENT_ID_CVP_C2S_1]
      // HIVM V5.0 MultiBufferPlan use replacement: producer %acc_ub -> %acc_ub_mb1_ping (multibuffer_true_rewrite_action_0001)
      // HIVM V5.1 CVPipelinePlan wait edge: compute_to_store (cvpipeline_true_rewrite_action_0001)
      hivm.hir.wait_flag[<PIPE_V>, <PIPE_MTE3>, EVENT_ID_CVP_C2S_1]
      hivm.hir.fixpipe ins(%s_l0c : memref<64x96xf32, #hivm.address_space<cc>>) outs(%acc_ub_mb1_ping : memref<64x128xf32, #hivm.address_space<ub>>)
      // HIVM V5.1 CVPipelinePlan group end: cvpipeline_true_rewrite_action_0001
      hivm.hir.set_flag {pipe="FIX",event="EVENT_ID0"}
    }
    // HIVM V5.0 MultiBufferPlan use replacement: consumer %acc_ub -> %acc_ub_mb1_ping (multibuffer_true_rewrite_action_0001)
    hivm.hir.vdiv ins(%acc_ub_mb1_ping, %l_ub : memref<64x128xf32, #hivm.address_space<ub>>, memref<64x1xf32, #hivm.address_space<ub>>) outs(%acc_ub_mb1_ping : memref<64x128xf32, #hivm.address_space<ub>>)
    hivm.hir.store ins(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%O_gm : memref<64x128xf16, #hivm.address_space<gm>>)
    return
  }
}