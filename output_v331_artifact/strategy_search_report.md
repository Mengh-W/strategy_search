# HIVM 四类 Plan 参数寻优报告

本报告由 `auto_strategy_search.py` 生成。当前版本聚焦于 strategy-level 参数寻优：在 `TilingPlan`、`MultiBufferPlan`、`CVPipelinePlan` 和 `SyncPlan` 四类 Plan 上进行组合搜索，并在解析式硬件约束与 cost model 下选择 predicted cycles 最低的合法候选。

> 说明：本版本不执行 IR rewrite，不包含瓶颈诊断，也不扩展 discrete memory access 分析。报告中的 predicted cycles 是解析模型下的相对排序信号，不等价于真机实测耗时。

## 1. 输入信息
- Kernel：`kernel_001.npuir.mlir`
- 硬件配置：`ascend_910b.json`
- 搜索空间：`AUTO_GENERATED`
- 搜索模式：`layered_beam_search`
- Cost risk mode：`conservative`
- Cost model config：`cost_model_conservative.json`

## 2. Kernel 静态特征
- 函数数量：2，AIC=True，AIV=True
- 同步操作：pipe_barrier=26, set_flag=33, wait_flag=32, sync_block_set=9, sync_block_wait=9
- 计算/搬运操作：nd2nz=5, mma=3, fixpipe=2, load=2, store=2, vector_ops=37
- 解析出的 local buffer 数量：92
- 静态 max-live 近似：{'l0c': 64.0, 'ub': 168.19, 'l0b': 0.0, 'l1': 328.0, 'l0a': 0.0} KB
- 推断的问题规模：`{"m_total": 16, "n_total": 512, "k_total": 512, "outer_iterations": 8, "kernel_family": "generic_hivm_structure", "extracted_tile_m": 16, "extracted_tile_n": 0, "extracted_tile_k": 512, "loop_trip_annotation": 0}`

## 3. 候选生成与搜索摘要
- 候选生成方式：`derived_default_not_searched`
- block_dim 使用的最大可用 core 数：40
- 全局 block_dim 候选：`[8, 16, 24, 32, 36, 38, 40]`
- 规则说明：block_dim is derived for each tile: argmax effective_parallelism under 1 <= B <= min(max_available_cores, n_tiles_total(tile))
- Layer-1 保留 cases：31
- Layer-1 因 alignment/single-buffer capacity 被拒绝：612
- Layer-2 overlap allocations：248
- Layer-3 生成候选数：2976
- Stage2b L1 保留策略：`cost_topw_plus_diversity_plus_pinned_standard_plus_fallback`
- Stage2b pinned standard L1 survivors：0
- Stage2b diversity 新增 L1 cases：3
- Stage2b fallback 新增 L1 cases：4
- Stage2b exact candidate 去重删除数：0
- 搜索质量审计：disabled（可用 `--enable-search-quality-audit` 开启小空间穷举/随机基线对照）
- Relax 后合法候选数：2976
- Relax 后仍拒绝候选数：0
- 通过 relax 变为可行的候选数：288

## 4. 寻优结果与优化前后对比
- 当前输入 IR 估计 predicted cycles：32341.59
- 最优候选 predicted cycles：12702.39
- 相对当前输入 IR 估计的预测加速比：N/A
- 最优候选风险等级：`HIGH`，风险模式：`conservative`
- 注意：当前输入 IR 在解析硬件 gate 下不可行，因此 speedup 不作为有效指标；下方仅保留 cost 对照用于诊断。

### 4.1 核心指标对比
| 指标 | 当前 IR 估计 | 最优候选 | 变化量 |
|---|---:|---:|---:|
| Predicted cycles | 32341.5866 | 12702.3949 | -19639.1918 |
| Tile 数量 | 32.0000 | 64.0000 | +32.0000 |
| Tile time | 1733.3977 | 1225.1601 | -508.2376 |
| 同步 cost | 30291.6163 | 4644.7291 | -25646.8872 |
| 资源压力惩罚 | 220.0000 | 220.0000 | +0.0000 |
| Shape 惩罚 | 0.0000 | 0.0000 | +0.0000 |
| 合法性风险惩罚 | 96.5727 | 5387.3457 | +5290.7730 |
| 有效并行度 | 32.0000 | 32.0000 | +0.0000 |
| Tail efficiency | 1.0000 | 1.0000 | +0.0000 |

> 说明：这里的“优化前”是 current-IR estimated strategy，“优化后”是 selected best strategy；当前版本不执行 IR rewrite。

### 4.2 最优候选策略
- `strategy_id`：`candidate_00017`
- `fusion`：`keep_existing`
- `tile_m`：`16`
- `tile_n`：`64`
- `tile_k`：`512`
- `block_dim`：`32`
- `double_buffer`：`True`
- `cv_pipeline_stage`：`2`
- `cv_split_ratio`：`1:1`
- `memory_reuse_level`：`level1`
- `sync_policy`：`graph_sync_solver`
- `dma_policy`：`keep_existing`
- `loop_order`：`outer_mkn`
- `tail_strategy`：`mask_or_pad`
- `multibuffer_template`：`M1_input_double_buffer`
- `cv_pipeline_template`：`P2_stage2_balanced`
- `sync_template`：`Y2_graph_sync_solver`
- `enable_mixed_cv`：`False`
- `tile_mix_cube_loop`：`1`
- `tile_mix_vector_loop`：`1`
- `auto_cv_balance`：`True`
- `barrier_level`：`low`
- `event_reuse`：`True`
- `sync_granularity`：`stage`
- `reduce_tile_policy`：`half_k`
- `layout_aware_tile`：`True`
- `ub_multiplier`：`1`
- `l1_multiplier`：`1`
- `stage_buffer_policy`：`none`
- `buffer_multipliers_json`：`{"30":1,"80":1,"82":1,"collapse_shape":1}`
- `producer_consumer_distance`：`1`
- `event_id_policy`：`reuse`
- `sync_motion`：`local_move`
- `model_version`：`V3.3-artifact-kernel-profile`

### 4.2 模型选择该策略的原因
- Layered search selected this StrategyConfig after L1 tiling/fusion pruning, L2 overlap allocation, and L3 refinement.
- m=double_buffer enables the document-3 overlap model: serial load+compute+store moves toward max(load, compute, store).
- s=2 models CV soft-pipeline overlap; r=1:1 balances Cube/Vector chunks.
- y=graph_sync_solver uses a lower analytical sync-cost proxy than keep_existing/inject-style sync.
- PlanMemory-style estimated maxLive_UB=41.97 KB within 256.00 KB capacity.
- Predicted tile_time=1225.16 cycles, n_tiles=64.

### 4.3 风险评估与收益来源归因
- Risk level：`HIGH`，Risk score：`119.0`，Risk mode：`conservative`
  - uses graph_sync_solver; demo cannot prove deadlock-free sync rewrite
  - sync legality is UNKNOWN without real sync_plan sidecar
  - uses event reuse; requires real event-id dependency validation
  - CVPipeline separability is PASS_ESTIMATED, not pass-verified
  - uses double/multi-buffer overlap assumptions
  - near hardware capacity boundary: l0b=1.00

| Cost / Risk 组成项 | cycles |
|---|---:|
| parallelized_tile_cycles | 2450.32 |
| sync_cost | 4644.73 |
| memory_pressure_penalty | 220.00 |
| shape_regularization_penalty | 0.00 |
| legality_risk_penalty | 5387.35 |

| 风险调整项 | cycles |
|---|---:|
| sync_unknown_penalty | 4677.66 |
| event_reuse_penalty | 654.00 |
| cv_estimated_penalty | 55.69 |

## 5. 分层算法覆盖范围
- L1 搜索 `TilingPlan`：在 alignment 与 single-buffer capacity 检查下搜索 tile shape。
- L2 搜索 `MultiBufferPlan` 与 template-bundled `CVPipelinePlan`：在估计容量压力下评估 double buffer / pipeline stage 等组合。
- L3 搜索 `SyncPlan`：在 keep-existing 与 GraphSyncSolver-style policy 之间做策略级选择。
- `selected_plan.json` 和 `top_plans.json` 保存四类 Plan 的可控参数、派生成本特征与合法性状态。
- `estimate_max_live()` 是当前 memory-capacity 模型：基于解析出的 local-buffer lifetimes 和 strategy-dependent tile/stage buffers 估计 PlanMemory-style max-live pressure。

## 6. 资源占用与 Cost Breakdown 对比
### 6.1 硬件资源占用对比
| Scope | 当前 IR 估计 KB | 最优候选 KB | 容量上限 KB |
|---|---:|---:|---:|
| UB | 70.50 | 41.97 | 256.00 |
| L1 | 279.69 | 150.16 | 1024.00 |
| L0A | 16.00 | 16.00 | 64.00 |
| L0B | 128.00 | 64.00 | 64.00 |
| L0C | 13.50 | 9.50 | 256.00 |
| GM_WS | 0.00 | 0.00 | 2097152.00 |

### 6.2 Cost Breakdown 对比
| 组成项 | 当前 IR 估计 | 最优候选 | 变化量 |
|---|---:|---:|---:|
| 并行化 tile cycles | 1733.40 | 2450.32 | +716.92 |
| 每 tile 暴露 load | 892.67 | 487.91 | -404.76 |
| Cube/Vector pipeline | 1210.53 | 686.02 | -524.51 |
| 每 tile 暴露 store | 102.41 | 88.27 | -14.14 |
| 每 tile 暴露 GM workspace | 0.00 | 0.00 | +0.00 |
| GM workspace live bytes | 0.00 | 0.00 | +0.00 |
| warmup / drain | 59.80 | 33.18 | -26.62 |
| 同步 cost | 30291.62 | 4644.73 | -25646.89 |
| 资源压力惩罚 | 220.00 | 220.00 | +0.00 |
| shape 惩罚 | 0.00 | 0.00 | +0.00 |
| 合法性风险惩罚 | 96.57 | 5387.35 | +5290.77 |

## 7. Top 候选排行
| Rank | Strategy ID | Predicted cycles | Risk | Tile | DB | CV stage | Sync | DMA | Reuse | maxLive UB KB |
|---:|---|---:|---|---|---|---:|---|---|---|---:|
| 1 | candidate_00017 | 12702.39 | HIGH | (16,64,512) | True | 2 | graph_sync_solver | keep_existing | level1 | 41.97 |
| 2 | candidate_00005 | 12702.91 | HIGH | (16,64,512) | True | 2 | graph_sync_solver | keep_existing | level1 | 41.97 |
| 3 | candidate_00053 | 12712.12 | HIGH | (16,64,512) | True | 2 | graph_sync_solver | keep_existing | level1 | 41.97 |
| 4 | candidate_00041 | 12712.64 | HIGH | (16,64,512) | True | 2 | graph_sync_solver | keep_existing | level1 | 41.97 |
| 5 | candidate_00089 | 12731.58 | HIGH | (16,64,512) | True | 2 | graph_sync_solver | keep_existing | level1 | 41.97 |
| 6 | candidate_00077 | 12732.10 | HIGH | (16,64,512) | True | 2 | graph_sync_solver | keep_existing | level1 | 41.97 |
| 7 | candidate_00029 | 12755.93 | HIGH | (16,64,512) | True | 2 | graph_sync_solver | keep_existing | level1 | 41.97 |
| 8 | candidate_00065 | 12765.66 | HIGH | (16,64,512) | True | 2 | graph_sync_solver | keep_existing | level1 | 41.97 |
| 9 | candidate_00013 | 12936.20 | HIGH | (16,64,512) | True | 2 | graph_sync_solver | keep_existing | level1 | 41.97 |
| 10 | candidate_00001 | 12936.72 | HIGH | (16,64,512) | True | 2 | graph_sync_solver | keep_existing | level1 | 41.97 |

## 8. Scope 与解释边界
- 当前版本是参数搜索实现：它把 HIVM 行为抽象为四类可搜索 Plan，并在合法候选上最小化解析 cost model。
- 当前独立仓库通过 IR parsing 与硬件规则解析得到 Plan 字段；真实 compiler pass dumps 不是运行必需项，但如果可获得，将是更强的数据来源。
- 当前 estimated capacity / alignment / tiling / pipeline gate 覆盖了主要硬件边界；SyncPlan 只提供策略级同步建模，不提供形式化 deadlock proof。
- 第一阶段 risk-aware 改造后，UNKNOWN GraphSyncSolver 和 PASS_ESTIMATED CVPipeline 不再默认拿满收益；报告同时输出 risk_level 和 legality_risk_penalty。
- 本版本不做 IR rewrite；如需证明策略可以真实落地，还需要后续接入 IR rewrite、compiler dry-run 与真机 profiling。
