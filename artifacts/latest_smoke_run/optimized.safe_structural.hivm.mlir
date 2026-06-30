// >>> auto_strategy_search V3.3.1 Step-2 safe structural HIVM/NPUIR
// Safe local hint rewrite only: existing tile attrs + alloc-level multi_buffer/hivm.nbuf hints + CV op-level hints.
// No loop generation, no buffer duplication, no op motion/reordering, no barrier/event rewrite.
// vTriton/real compiler verification is required before claiming realized speedup.
// >>> auto_strategy_search V3.3.1 Step-1 annotated HIVM/NPUIR
// This file carries strategy hints. It is not proof that backend compiler passes were executed.
// fa_bad_inefficient.hivm.mlir
// Purpose: deliberately inefficient HIVM/MLIR-style FlashAttention candidate for optimizer testing.
// Main defects:
//   1) Small BN=32 -> too many K/V loop blocks and poor tensor-core utilization.
//   2) score buffer uses f32 -> high UB pressure and extra bandwidth.
//   3) no P/S reuse -> allocates both s_ub and p_ub.
//   4) single L1 buffer -> no ping-pong prefetch overlap.
//   5) barrier synchronization -> coarse pipeline stall.
//   6) reloads Q inside the K/V loop -> redundant GM/UB/L1 traffic.

module attributes {hivm.sync = "graph_sync_solver", hivm.strategy.source = "auto_strategy_search_v3", hivm.strategy.version = "V3.3.1-step2-safe-structural"} {
  func.func @fa_bad(
      %Q_gm : memref<64x128xf16, #hivm.address_space<gm>>,
      %K_gm : memref<1024x128xf16, #hivm.address_space<gm>>,
      %V_gm : memref<1024x128xf16, #hivm.address_space<gm>>,
      %O_gm : memref<64x128xf16, #hivm.address_space<gm>>) attributes {hivm.strategy.strategy_id = "candidate_01681", hivm.strategy.model_version = "V3.3-artifact-kernel-profile", hivm.strategy.tile_m = 32 : i64, hivm.strategy.tile_n = 64 : i64, hivm.strategy.tile_k = 128 : i64, hivm.strategy.block_dim = 32 : i64, hivm.strategy.loop_order = "outer_mkn", hivm.strategy.tail_strategy = "mask_or_pad", hivm.strategy.reduce_tile_policy = "half_k", hivm.strategy.layout_aware_tile = true, hivm.strategy.double_buffer = true, hivm.strategy.ub_multiplier = 1 : i64, hivm.strategy.l1_multiplier = 1 : i64, hivm.strategy.buffer_multipliers_json = "{\"k_l1\":1,\"q_l1\":1,\"q_ub\":1,\"v_l1\":1}", hivm.strategy.multibuffer_template = "M1_input_double_buffer", hivm.strategy.stage_buffer_policy = "none", hivm.strategy.memory_reuse_level = "level1", hivm.strategy.dma_policy = "keep_existing", hivm.strategy.cv_pipeline_stage = 2 : i64, hivm.strategy.cv_pipeline_template = "P2_stage2_balanced", hivm.strategy.cv_split_ratio = "1:1", hivm.strategy.enable_mixed_cv = false, hivm.strategy.tile_mix_cube_loop = 1 : i64, hivm.strategy.tile_mix_vector_loop = 1 : i64, hivm.strategy.auto_cv_balance = true, hivm.strategy.producer_consumer_distance = 1 : i64, hivm.strategy.fusion = "keep_existing", hivm.strategy.sync_policy = "graph_sync_solver", hivm.strategy.sync_template = "Y3_event_reuse", hivm.strategy.barrier_level = "low", hivm.strategy.event_reuse = true, hivm.strategy.sync_granularity = "stage", hivm.strategy.event_id_policy = "reuse", hivm.strategy.sync_motion = "local_move"} {

    // Inefficient parameter vector:
    // BM=64, BN=32, D=128, seq=1024, dt_score=f32, dt_acc=f32,
    // reuse_p=0, nbuf_l1=1, sync=barrier.
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

    // Bad: Q load could be hoisted outside the loop, but here it is repeated.
    scf.for %j = %c0 to %c1024 step %c32 {   // @trip=32
      hivm.hir.load ins(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>)
      hivm.hir.nd2nz ins(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%q_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>)

      hivm.hir.load ins(%K_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%k_ub : memref<32x128xf16, #hivm.address_space<ub>>)
      hivm.hir.load ins(%V_gm : memref<1024x128xf16, #hivm.address_space<gm>>) outs(%v_ub : memref<32x128xf16, #hivm.address_space<ub>>)
      hivm.hir.nd2nz ins(%k_ub : memref<32x128xf16, #hivm.address_space<ub>>) outs(%k_l1 : memref<32x128xf16, #hivm.address_space<cbuf>>)
      hivm.hir.nd2nz ins(%v_ub : memref<32x128xf16, #hivm.address_space<ub>>) outs(%v_l1 : memref<32x128xf16, #hivm.address_space<cbuf>>)

      // Bad: global barrier serializes stages and prevents fine-grained overlap.
      // [auto_strategy sync_hint] GraphSyncSolver candidate; Step-2 does not remove/move barriers without dependency legality proof
      hivm.hir.barrier {mode = "ALL"}

      hivm.hir.mmad {hivm.cv.pipeline_hint = true, hivm.cv.role = "cube", hivm.cv.stage = 2 : i64, hivm.cv.template = "P2_stage2_balanced", hivm.cv.producer_consumer_distance = 1 : i64, hivm.cv.cube_loop = 1 : i64, hivm.cv.vector_loop = 1 : i64, hivm.cv.enable_mixed_cv = false, hivm.cv.auto_balance = true, hivm.cv.anchor_index = 0 : i64} ins(%q_l1, %k_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>, memref<32x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c : memref<64x32xf32, #hivm.address_space<cc>>)
      hivm.hir.fixpipe {hivm.cv.pipeline_hint = true, hivm.cv.role = "fixpipe", hivm.cv.stage = 2 : i64, hivm.cv.template = "P2_stage2_balanced", hivm.cv.producer_consumer_distance = 1 : i64, hivm.cv.cube_loop = 1 : i64, hivm.cv.vector_loop = 1 : i64, hivm.cv.enable_mixed_cv = false, hivm.cv.auto_balance = true, hivm.cv.anchor_index = 0 : i64} ins(%s_l0c : memref<64x32xf32, #hivm.address_space<cc>>) outs(%s_ub : memref<64x32xf32, #hivm.address_space<ub>>)
      hivm.hir.vreduce {hivm.cv.pipeline_hint = true, hivm.cv.role = "vector", hivm.cv.stage = 2 : i64, hivm.cv.template = "P2_stage2_balanced", hivm.cv.producer_consumer_distance = 1 : i64, hivm.cv.cube_loop = 1 : i64, hivm.cv.vector_loop = 1 : i64, hivm.cv.enable_mixed_cv = false, hivm.cv.auto_balance = true, hivm.cv.anchor_index = 0 : i64} ins(%s_ub : memref<64x32xf32, #hivm.address_space<ub>>) outs(%m_ub : memref<64x1xf32, #hivm.address_space<ub>>) {reduce_op="max"}
      hivm.hir.vsub {hivm.cv.pipeline_hint = true, hivm.cv.role = "vector", hivm.cv.stage = 2 : i64, hivm.cv.template = "P2_stage2_balanced", hivm.cv.producer_consumer_distance = 1 : i64, hivm.cv.cube_loop = 1 : i64, hivm.cv.vector_loop = 1 : i64, hivm.cv.enable_mixed_cv = false, hivm.cv.auto_balance = true, hivm.cv.anchor_index = 1 : i64} ins(%s_ub, %m_ub : memref<64x32xf32, #hivm.address_space<ub>>, memref<64x1xf32, #hivm.address_space<ub>>) outs(%p_ub : memref<64x32xf32, #hivm.address_space<ub>>)
      hivm.hir.vexp {hivm.cv.pipeline_hint = true, hivm.cv.role = "vector", hivm.cv.stage = 2 : i64, hivm.cv.template = "P2_stage2_balanced", hivm.cv.producer_consumer_distance = 1 : i64, hivm.cv.cube_loop = 1 : i64, hivm.cv.vector_loop = 1 : i64, hivm.cv.enable_mixed_cv = false, hivm.cv.auto_balance = true, hivm.cv.anchor_index = 2 : i64} ins(%p_ub : memref<64x32xf32, #hivm.address_space<ub>>) outs(%p_ub : memref<64x32xf32, #hivm.address_space<ub>>)
      hivm.hir.vreduce {hivm.cv.pipeline_hint = true, hivm.cv.role = "vector", hivm.cv.stage = 2 : i64, hivm.cv.template = "P2_stage2_balanced", hivm.cv.producer_consumer_distance = 1 : i64, hivm.cv.cube_loop = 1 : i64, hivm.cv.vector_loop = 1 : i64, hivm.cv.enable_mixed_cv = false, hivm.cv.auto_balance = true, hivm.cv.anchor_index = 3 : i64} ins(%p_ub : memref<64x32xf32, #hivm.address_space<ub>>) outs(%l_ub : memref<64x1xf32, #hivm.address_space<ub>>) {reduce_op="sum"}

      // P x V accumulation, intentionally kept with small BN and f32 P path.
      hivm.hir.mmad {hivm.cv.pipeline_hint = true, hivm.cv.role = "cube", hivm.cv.stage = 2 : i64, hivm.cv.template = "P2_stage2_balanced", hivm.cv.producer_consumer_distance = 1 : i64, hivm.cv.cube_loop = 1 : i64, hivm.cv.vector_loop = 1 : i64, hivm.cv.enable_mixed_cv = false, hivm.cv.auto_balance = true, hivm.cv.anchor_index = 1 : i64} ins(%p_ub, %v_l1 : memref<64x32xf32, #hivm.address_space<ub>>, memref<32x128xf16, #hivm.address_space<cbuf>>) outs(%s_l0c : memref<64x32xf32, #hivm.address_space<cc>>)
      hivm.hir.fixpipe {hivm.cv.pipeline_hint = true, hivm.cv.role = "fixpipe", hivm.cv.stage = 2 : i64, hivm.cv.template = "P2_stage2_balanced", hivm.cv.producer_consumer_distance = 1 : i64, hivm.cv.cube_loop = 1 : i64, hivm.cv.vector_loop = 1 : i64, hivm.cv.enable_mixed_cv = false, hivm.cv.auto_balance = true, hivm.cv.anchor_index = 1 : i64} ins(%s_l0c : memref<64x32xf32, #hivm.address_space<cc>>) outs(%acc_ub : memref<64x128xf32, #hivm.address_space<ub>>)

      // Bad: another coarse barrier after compute.
      // [auto_strategy sync_hint] GraphSyncSolver candidate; Step-2 does not remove/move barriers without dependency legality proof
      hivm.hir.barrier {mode = "ALL"}
    }

    hivm.hir.vdiv {hivm.cv.pipeline_hint = true, hivm.cv.role = "vector", hivm.cv.stage = 2 : i64, hivm.cv.template = "P2_stage2_balanced", hivm.cv.producer_consumer_distance = 1 : i64, hivm.cv.cube_loop = 1 : i64, hivm.cv.vector_loop = 1 : i64, hivm.cv.enable_mixed_cv = false, hivm.cv.auto_balance = true, hivm.cv.anchor_index = 4 : i64} ins(%acc_ub, %l_ub : memref<64x128xf32, #hivm.address_space<ub>>, memref<64x1xf32, #hivm.address_space<ub>>) outs(%acc_ub : memref<64x128xf32, #hivm.address_space<ub>>)
    hivm.hir.cast {hivm.cv.pipeline_hint = true, hivm.cv.role = "vector", hivm.cv.stage = 2 : i64, hivm.cv.template = "P2_stage2_balanced", hivm.cv.producer_consumer_distance = 1 : i64, hivm.cv.cube_loop = 1 : i64, hivm.cv.vector_loop = 1 : i64, hivm.cv.enable_mixed_cv = false, hivm.cv.auto_balance = true, hivm.cv.anchor_index = 5 : i64} ins(%acc_ub : memref<64x128xf32, #hivm.address_space<ub>>) outs(%o_ub : memref<64x128xf16, #hivm.address_space<ub>>)
    hivm.hir.store ins(%o_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%O_gm : memref<64x128xf16, #hivm.address_space<gm>>)
    return
  }
}
