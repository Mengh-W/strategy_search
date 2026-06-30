# V3.3.1 Step-1 Strategy-to-HIVM Annotation Rewrite Audit
- Strategy: `candidate_01681`
- Rewrite mode: `both`
- Safety: `conservative`
- Annotated IR: `optimized.annotated.hivm.mlir`
- Safe structural IR: `optimized.safe_structural.hivm.mlir`
- Formal structural IR: `optimized.structural.hivm.mlir`
- Structural rewrite report: `structural_rewrite_report.json`
- Structural validation summary: `structural_validation_summary.json`
- HIVM bridge manifest: `hivm_bridge_manifest.json`（兼容保留 `vtriton_adapter_manifest.json`）
- Phase-2 closure report: `phase2_closure_report.json`
- Phase-3A op inventory: `hivm_ir_inventory.json`
- Phase-3A dependency graph: `dependency_graph_report.json`
- Phase-3A event liveness: `event_liveness_report.json`
- Phase-3A summary: `phase3a_analysis_summary.json`
- Phase-3B buffer liveness: `buffer_liveness_report.json`
- Phase-3B capacity recheck: `capacity_recheck_report.json`
- Phase-3B GM alias report: `gm_alias_report.json`
- Phase-3B summary: `phase3b_analysis_summary.json`
- Phase-3C GM MemorySSA report: `gm_memory_ssa_report.json`
- Phase-3C GM deletion decision: `gm_roundtrip_deletion_decision.json`
- Phase-3C rewrite legality gate: `rewrite_legality_gate_report.json`
- Phase-3C summary: `phase3c_analysis_summary.json`
- Phase-3D load-hoist proof: `loop_invariant_load_hoist_report.json`
- Phase-3D Q-load hoist decision: `q_load_hoist_decision.json`
- Phase-3D summary: `phase3d_analysis_summary.json`
- Phase-3E DES/trace validation wrapper: `vtriton_des_trace_validation_report.json`
- Phase-3E trace comparison HTML: `trace_comparison_report.html`
- Phase-3E summary: `phase3e_analysis_summary.json`
- Phase-3F closure report: `phase3_closure_report.json`
- Phase-3F summary: `phase3f_analysis_summary.json`
- Phase-4A target parser / bridge hardening report: `target_parser_validation_report.json`
- Phase-4A summary: `phase4a_analysis_summary.json`
- Phase-4D Operation-level dry-run contract: `phase4d_operation_rewrite_dry_run_report.json`
- Phase-4D official MLIR compliance report: `phase4d_official_mlir_compliance_report.json`
- Phase-4D summary: `phase4d_analysis_summary.json`
- Phase-4E closure report: `phase4_closure_report.json`
- Phase-4E summary: `phase4e_analysis_summary.json`
- Capability report: `rewrite_capability_report.json`
- CVPipeline rewrite report: `cv_pipeline_rewrite_report.json`

## What was changed
- `module_attr`: {'type': 'module_attr', 'key': 'hivm.sync', 'after': 'graph_sync_solver', 'insertion': 'created_attributes_block'}
- `module_attr`: {'type': 'module_attr', 'key': 'hivm.strategy.source', 'after': 'auto_strategy_search_v3', 'insertion': 'created_attributes_block'}
- `module_attr`: {'type': 'module_attr', 'key': 'hivm.strategy.version', 'after': 'V3.3.1-step2-safe-structural', 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.strategy_id', 'after': 'candidate_01681', 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.model_version', 'after': 'V3.3-artifact-kernel-profile', 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.tile_m', 'after': 32, 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.tile_n', 'after': 64, 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.tile_k', 'after': 128, 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.block_dim', 'after': 32, 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.loop_order', 'after': 'outer_mkn', 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.tail_strategy', 'after': 'mask_or_pad', 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.reduce_tile_policy', 'after': 'half_k', 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.layout_aware_tile', 'after': True, 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.double_buffer', 'after': True, 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.ub_multiplier', 'after': 1, 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.l1_multiplier', 'after': 1, 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.buffer_multipliers_json', 'after': '{"k_l1":1,"q_l1":1,"q_ub":1,"v_l1":1}', 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.multibuffer_template', 'after': 'M1_input_double_buffer', 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.stage_buffer_policy', 'after': 'none', 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.memory_reuse_level', 'after': 'level1', 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.dma_policy', 'after': 'keep_existing', 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.cv_pipeline_stage', 'after': 2, 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.cv_pipeline_template', 'after': 'P2_stage2_balanced', 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.cv_split_ratio', 'after': '1:1', 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.enable_mixed_cv', 'after': False, 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.tile_mix_cube_loop', 'after': 1, 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.tile_mix_vector_loop', 'after': 1, 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.auto_cv_balance', 'after': True, 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.producer_consumer_distance', 'after': 1, 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.fusion', 'after': 'keep_existing', 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.sync_policy', 'after': 'graph_sync_solver', 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.sync_template', 'after': 'Y3_event_reuse', 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.barrier_level', 'after': 'low', 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.event_reuse', 'after': True, 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.sync_granularity', 'after': 'stage', 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.event_id_policy', 'after': 'reuse', 'insertion': 'created_attributes_block'}
- `func_attr`: {'type': 'func_attr', 'key': 'hivm.strategy.sync_motion', 'after': 'local_move', 'insertion': 'created_attributes_block'}
- `cv_op_attr`: {'type': 'cv_op_attr', 'op': 'hivm.hir.mmad', 'role': 'cube', 'line_hint_index': 0, 'change': 'add hivm.cv.* pipeline hint attrs', 'stage': 2, 'template': 'P2_stage2_balanced', 'safety': 'conservative', 'structural_reorder': False}
- `cv_op_attr`: {'type': 'cv_op_attr', 'op': 'hivm.hir.fixpipe', 'role': 'fixpipe', 'line_hint_index': 0, 'change': 'add hivm.cv.* pipeline hint attrs', 'stage': 2, 'template': 'P2_stage2_balanced', 'safety': 'conservative', 'structural_reorder': False}
- `cv_op_attr`: {'type': 'cv_op_attr', 'op': 'hivm.hir.vreduce', 'role': 'vector', 'line_hint_index': 0, 'change': 'add hivm.cv.* pipeline hint attrs', 'stage': 2, 'template': 'P2_stage2_balanced', 'safety': 'conservative', 'structural_reorder': False}
- `cv_op_attr`: {'type': 'cv_op_attr', 'op': 'hivm.hir.vsub', 'role': 'vector', 'line_hint_index': 1, 'change': 'add hivm.cv.* pipeline hint attrs', 'stage': 2, 'template': 'P2_stage2_balanced', 'safety': 'conservative', 'structural_reorder': False}
- `cv_op_attr`: {'type': 'cv_op_attr', 'op': 'hivm.hir.vexp', 'role': 'vector', 'line_hint_index': 2, 'change': 'add hivm.cv.* pipeline hint attrs', 'stage': 2, 'template': 'P2_stage2_balanced', 'safety': 'conservative', 'structural_reorder': False}
- `cv_op_attr`: {'type': 'cv_op_attr', 'op': 'hivm.hir.vreduce', 'role': 'vector', 'line_hint_index': 3, 'change': 'add hivm.cv.* pipeline hint attrs', 'stage': 2, 'template': 'P2_stage2_balanced', 'safety': 'conservative', 'structural_reorder': False}
- `cv_op_attr`: {'type': 'cv_op_attr', 'op': 'hivm.hir.mmad', 'role': 'cube', 'line_hint_index': 1, 'change': 'add hivm.cv.* pipeline hint attrs', 'stage': 2, 'template': 'P2_stage2_balanced', 'safety': 'conservative', 'structural_reorder': False}
- `cv_op_attr`: {'type': 'cv_op_attr', 'op': 'hivm.hir.fixpipe', 'role': 'fixpipe', 'line_hint_index': 1, 'change': 'add hivm.cv.* pipeline hint attrs', 'stage': 2, 'template': 'P2_stage2_balanced', 'safety': 'conservative', 'structural_reorder': False}
- `cv_op_attr`: {'type': 'cv_op_attr', 'op': 'hivm.hir.vdiv', 'role': 'vector', 'line_hint_index': 4, 'change': 'add hivm.cv.* pipeline hint attrs', 'stage': 2, 'template': 'P2_stage2_balanced', 'safety': 'conservative', 'structural_reorder': False}
- `cv_op_attr`: {'type': 'cv_op_attr', 'op': 'hivm.hir.cast', 'role': 'vector', 'line_hint_index': 5, 'change': 'add hivm.cv.* pipeline hint attrs', 'stage': 2, 'template': 'P2_stage2_balanced', 'safety': 'conservative', 'structural_reorder': False}
- `sync_hint`: {'type': 'sync_hint', 'change': 'annotate barrier only', 'safety': 'conservative', 'structural_rewrite': False}
- `sync_hint`: {'type': 'sync_hint', 'change': 'annotate barrier only', 'safety': 'conservative', 'structural_rewrite': False}
- `replace_barrier_all_with_directional_sync`: {'type': 'replace_barrier_all_with_directional_sync', 'line': 53, 'before': 'hivm.hir.barrier {mode = "ALL"}', 'after': ['hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_M>, <EVENT_ID0>]', 'hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_M>, <EVENT_ID0>]'], 'structural_change': True}
- `replace_barrier_all_with_directional_sync`: {'type': 'replace_barrier_all_with_directional_sync', 'line': 68, 'before': 'hivm.hir.barrier {mode = "ALL"}', 'after': ['hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_M>, <EVENT_ID0>]', 'hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_M>, <EVENT_ID0>]'], 'structural_change': True}
- `insert_sync_before_first_vector_op`: {'type': 'insert_sync_before_first_vector_op', 'line': 59, 'target': 'hivm.hir.vreduce {hivm.cv.pipeline_hint = true, hivm.cv.role = "vector", hivm.cv.stage = 2 : i64, hivm.cv.template = "P2_stage2_balanced", hivm.cv.producer_consumer_distance = 1 : i64, hivm.cv.cube_loop = 1 : i64, hivm.cv.vector_loop = 1 : i64, hivm.cv.enable_mixed_cv = false, hivm.cv.auto_balance = true, hivm.cv.anchor_index = 0 : i64} ins(%s_ub : memref<64x32xf32, #hivm.address_space<ub>>) outs(%m_ub : memref<64x1xf32, #hivm.address_space<ub>>) {reduce_op="max"}', 'inserted': ['hivm.hir.set_flag[<PIPE_FIX>, <PIPE_V>, <EVENT_ID1>]', 'hivm.hir.wait_flag[<PIPE_FIX>, <PIPE_V>, <EVENT_ID1>]'], 'structural_change': True}
- `hoist_invariant_q_load_from_simple_loop`: {'type': 'hoist_invariant_q_load_from_simple_loop', 'loop_line': 42, 'removed_lines_in_loop': [43, 44], 'hoisted_lines': ['hivm.hir.load ins(%Q_gm : memref<64x128xf16, #hivm.address_space<gm>>) outs(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>)', 'hivm.hir.nd2nz ins(%q_ub : memref<64x128xf16, #hivm.address_space<ub>>) outs(%q_l1 : memref<64x128xf16, #hivm.address_space<cbuf>>)'], 'structural_change': True}

## Step-2C CVPipeline hint summary
- cv_op_hints_added: `10`
- role_counts: `{'load': 6, 'sync': 2, 'cube': 2, 'fixpipe': 2, 'vector': 6, 'store': 1}`
- structural_reorder: `False`

## Step-3 formal structural rewrite summary
- structural_rewrite_performed: `True`
- change_counts: `{'replace_barrier_all_with_directional_sync': 2, 'insert_sync_before_first_vector_op': 1, 'hoist_invariant_q_load_from_simple_loop': 1}`
- backend: `{'mode': 'dry_run', 'mutated_ir_written': False, 'reason': 'edit script/schema/backend plan emitted only'}`

## Phase-3A dependency-analysis foundation
- op_count: `19`; unknown_op_count: `0`
- dependency_edges: `29`; edge_counts: `{'memory_raw': 14, 'coarse_barrier_order': 11, 'memory_waw': 3, 'memory_war': 1}`
- event_count: `0`; local_event_liveness: `True`
- Note: Phase-3A emits evidence only. It does not unlock GM deletion, event reuse, real double-buffer, full CV overlap, or tiling lowering.

## Phase-3B buffer-liveness and GM-alias foundation
- buffer_count: `17`; local_buffer_count: `13`; gm_buffer_count: `4`
- capacity_passed: `True`; peak_by_space: `{'l0c': {'conservative_peak_bytes': 8192, 'default_limit_bytes': 262144, 'within_default_limit': True, 'utilization': 0.03125}, 'l1': {'conservative_peak_bytes': 32768, 'default_limit_bytes': 1048576, 'within_default_limit': True, 'utilization': 0.03125}, 'ub': {'conservative_peak_bytes': 98816, 'default_limit_bytes': 262144, 'within_default_limit': True, 'utilization': 0.376953}}`
- gm_access_count: `4`; gm_roundtrip_candidates: `0`; deletion_unlocked: `False`
- Note: Phase-3B emits memory evidence only. GM deletion, Q-load hoist, real double-buffer and full CV overlap remain locked.

## Phase-4A bridge hardening / target-parser readiness
- target_parser_status: `not_connected`
- blocker_count: `2`; blockers: `['hivm_bridge_capability_handshake_missing_or_unavailable', 'target_parser_or_tritonsim_not_connected']`
- Note: Phase-4A is a readiness audit only. It does not enable GM deletion, Q-load production hoist, double-buffer, CV overlap, or tiling lowering.

## Phase-4B DES/trace execution gate
- status: `pending_or_failed_des_trace_execution`; passed_external_des_trace_gate: `False`
- reasons: `['tritonsim-hivm did not run for both original and optimized IR', 'no tritonsim-hivm path configured; use --run-vtriton-validation --tritonsim-hivm /path/to/tritonsim-hivm']`
- Note: Phase-4B is an external validation gate. Passing it is necessary but not sufficient for risky production mutations.

## Phase-4C guarded Q-load hoist prototype gate
- candidates: `1`; backend_dry_run_ready: `0`; production_allowed: `0`
- blockers: `['target parser / bridge validation is not strong enough for region motion', 'DES/trace execution gate did not pass']`
- Note: Phase-4C emits a backend dry-run worklist only; it does not perform unsafe text-level region motion.

## Phase-5D guarded Operation-level mutation execution gate
- status: `pending_or_failed_guarded_mutation_gate`; mutation_performed: `False`; production_allowed: `False`
- blockers: `['backend_did_not_perform_mutation', 'des_trace_after_mutation_not_passed', 'dominance_proof_not_passed', 'mlir_verifier_after_mutation_not_passed', 'mutation_backend_is_not_real_mlir_or_hivmopseditor_backend', 'no_mutation_actions_available', 'operation_backend_mutation_command_failed_or_not_run', 'operation_backend_mutation_output_missing', 'operation_backend_mutation_report_missing', 'operation_backend_not_connected', 'phase5b_noop_roundtrip_verify_gate_not_passed', 'phase5c_operation_dry_run_gate_not_passed', 'region_motion_proof_not_passed']`
- Note: Phase-5D may call a backend mutation contract, but fake/non-MLIR backends are explicitly rejected as non-production. No Python text-level region motion is performed.

## Phase-5E limited GM round-trip deletion gate
- status: `pending_or_failed_limited_gm_roundtrip_deletion_gate`; candidates: `0`; executable: `0`; deleted_pairs: `0`; production_allowed: `False`
- blockers: `['no_gm_roundtrip_candidates_from_phase3c', 'no_gm_roundtrip_deletion_actions_available', 'operation_backend_not_connected', 'phase5b_noop_roundtrip_verify_gate_not_passed']`
- Note: Phase-5E prepares a GM deletion backend contract only. It does not text-delete GM traffic; fake/non-MLIR backends and deferred Phase-3C candidates are rejected.

## Phase-4D official-docs-aligned Operation-level dry-run contract
- dry_run_actions: `0`; production_allowed: `0`
- blockers: `['phase4a_target_parser_gate_not_clean', 'phase4b_des_trace_gate_not_passed', 'no_phase4c_backend_dry_run_candidates', 'operation_level_dominance_and_region_motion_backend_not_connected']`
- Note: Phase-4D follows official MLIR rewrite discipline: no text-level region motion, no production mutation, and future movement must go through an Operation-level backend with legality/dominance/verifier gates.

## Phase-4E closure and Phase-5 handoff
- phase4_status: `closed_bridge_validation_and_dry_run_contract`; remaining_blockers: `7`
- production_mutations_unlocked: `{'q_load_hoist': False, 'gm_roundtrip_deletion': False, 'real_double_buffer': False, 'full_cv_overlap': False, 'real_tiling_loop_lowering': False}`
- Note: Phase-4E closes the bridge/dry-run phase. It does not unlock risky mutations; Phase 5 must connect a real Operation-level backend and verifier first.

## Phase-3C GM MemorySSA and rewrite legality gate
- gm_access_count: `4`; memory_events: `4`; candidates: `0`
- gm_delete_allowed: `0`; deferred: `0`; deletion_unlocked: `False`
- rewrite_gates: `{'barrier_or_sync_local_rewrite_audit': True, 'gm_roundtrip_deletion': False, 'q_load_hoist_with_proof': False, 'real_double_buffer': False, 'real_cv_overlap': False, 'real_tiling_loop_lowering': False}`
- Note: Phase-3C adds GM MemorySSA-like decision gates. It only allows deletion when all gates pass; otherwise deletion remains deferred.

## Phase-3D loop-invariant load-hoist proof gate
- hoist_candidates: `1`; local_proof_passed: `1`; hoist_allowed: `0`; hoist_unlocked: `False`
- Note: Phase-3D nominates candidates only. Production mutation remains locked without target parser region-motion proof.

## Phase-3E external DES/trace validation wrapper
- validation_status: `pending_or_failed_external_des_trace_validation`; tritonsim_ran_both: `False`; artifacts_available: `False`
- Note: Phase-3E is a validation wrapper. It does not prove numerical correctness or real msprof speedup.

## Phase-3F closure and Phase-4 handoff
- phase3_status: `closed_analysis_foundation`; remaining_blockers: `3`
- phase4_candidate_status: `{'sync_rewrite_audit_and_refinement': 'eligible_for_prototype', 'gm_roundtrip_deletion': 'locked', 'q_load_hoist': 'eligible_for_guarded_prototype', 'real_double_buffer_pingpong': 'locked', 'full_cv_pipeline_overlap': 'locked', 'real_tiling_loop_lowering': 'locked'}`
- Note: Phase-3F closes the analysis foundation. It does not default-enable GM deletion, real double-buffer, full CV overlap, or tiling lowering.

## Step-2 capability summary
- alloc_level_multibuffer_hint: `False`
- cv_pipeline_op_level_hint_attrs: `True`
- cv_pipeline_structural_reorder: `False`
- existing_tile_attr_replacement: `False`
- func_and_module_annotation: `True`
- load_store_op_motion: `False`
- real_pingpong_buffer_duplication: `False`
- sync_barrier_or_event_rewrite: `False`
- tiling_loop_nest_generation: `False`

## Step-2 fallback reasons
- tile_loop_rewrite: not_in_step2; requires index remapping, tail masks, reduction accumulation, and legality checks
- real_multibuffer_pingpong: not_in_step2; requires buffer duplication, producer-consumer live-range analysis, and event/wait insertion
- cv_pipeline_structural_reorder: not_in_step2; requires cube/vector/fixpipe/store dependency graph, live-range analysis, and event/wait legality
- sync_rewrite: not_in_step2; requires proven dependency graph and deadlock/data-race validation
- tile_attr_replacement: no_existing_tile_attribute_anchor_found; kept function-level strategy annotation only
- conservative_multibuffer: no concrete safe alloc-level multi-buffer rewrite was emitted under current safety mode

## What was intentionally not changed
- Step-2 may replace existing tile attributes, but it does not generate a new tiling loop nest.
- Step-2 may add alloc-level multi_buffer/hivm.nbuf hints, but it does not duplicate buffers or implement ping-pong scheduling.
- CVPipeline op-level hivm.cv.* hints may be emitted in Step-2, but cube/vector/fixpipe/store operations are not reordered.
- Sync barrier/event deletion, motion, and reuse are not structurally rewritten in Step-2.
- Compiler-pass-level optimized IR must be produced/validated by vTriton or a real AscendNPU compiler pass pipeline.

## vTriton validation expectation
Run `tritonsim-hivm` on the emitted IR to generate DES/trace-after, then use vTriton counterfactual/compile/verify/delta harness for authoritative validation.
