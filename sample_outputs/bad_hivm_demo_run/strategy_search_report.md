# HIVM 四类 Plan 参数寻优报告

本报告由 `auto_strategy_search.py` 生成。当前版本聚焦于 strategy-level 参数寻优：在 `TilingPlan`、`MultiBufferPlan`、`CVPipelinePlan` 和 `SyncPlan` 四类 Plan 上进行组合搜索，并在解析式硬件约束与 cost model 下选择 predicted cycles 最低的合法候选。

> 说明：本版本不执行 IR rewrite，不包含瓶颈诊断，也不扩展 discrete memory access 分析。报告中的 predicted cycles 是解析模型下的相对排序信号，不等价于真机实测耗时。

## 1. 输入信息
- Kernel：`fa_bad_inefficient.hivm.mlir`
- 硬件配置：`ascend_910b.json`
- 搜索空间：`AUTO_GENERATED`
- 搜索模式：`layered_beam_search`

## 2. Kernel 静态特征
- 函数数量：1，AIC=True，AIV=True
- 同步操作：pipe_barrier=2, set_flag=0, wait_flag=0, sync_block_set=0, sync_block_wait=0
- 计算/搬运操作：nd2nz=3, mma=2, fixpipe=2, load=3, store=1, vector_ops=5
- 解析出的 local buffer 数量：13
- 静态 max-live 近似：{'l0a': 0.0, 'ub': 96.5, 'l0c': 8.0, 'l0b': 0.0, 'l1': 32.0} KB
- 推断的问题规模：`{"m_total": 64, "n_total": 1024, "k_total": 128, "outer_iterations": 1, "kernel_family": "generic_hivm_structure", "extracted_tile_m": 64, "extracted_tile_n": 32, "extracted_tile_k": 128, "loop_trip_annotation": 32}`

## 3. 候选生成与搜索摘要
- 候选生成方式：`derived_default_not_searched`
- block_dim 使用的最大可用 core 数：40
- 全局 block_dim 候选：`[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 21, 22, 24, 26, 28, 30, 32, 33, 36, 38, 39, 40]`
- 规则说明：block_dim is derived for each tile: argmax effective_parallelism under 1 <= B <= min(max_available_cores, n_tiles_total(tile))
- Layer-1 保留 cases：24
- Layer-1 因 alignment/single-buffer capacity 被拒绝：28044
- Layer-2 overlap allocations：143
- Layer-3 生成候选数：1716
- Relax 后合法候选数：1716
- Relax 后仍拒绝候选数：0
- 通过 relax 变为可行的候选数：288

## 4. 寻优结果与优化前后对比
- 当前输入 IR 估计 predicted cycles：623.57
- 最优候选 predicted cycles：386.73
- 相对当前输入 IR 估计的预测加速比：1.612x
- 解析模型下 predicted cycles 减少：236.84，下降约 38.0%

### 4.1 核心指标对比
| 指标 | 当前 IR 估计 | 最优候选 | 变化量 |
|---|---:|---:|---:|
| Predicted cycles | 623.5725 | 386.7296 | -236.8429 |
| Tile 数量 | 32.0000 | 22.0000 | -10.0000 |
| Tile time | 303.5725 | 308.1446 | +4.5721 |
| 同步 cost | 300.0000 | 66.9183 | -233.0817 |
| 资源压力惩罚 | 0.0000 | 0.0000 | +0.0000 |
| Shape 惩罚 | 20.0000 | 11.6667 | -8.3333 |
| 有效并行度 | 32.0000 | 22.0000 | -10.0000 |
| Tail efficiency | 1.0000 | 1.0000 | +0.0000 |

> 说明：这里的“优化前”是 current-IR estimated strategy，“优化后”是 selected best strategy；当前版本不执行 IR rewrite。

### 4.2 最优候选策略
- `strategy_id`：`candidate_01441`
- `fusion`：`keep_existing`
- `tile_m`：`64`
- `tile_n`：`48`
- `tile_k`：`128`
- `block_dim`：`22`
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
- `sync_template`：`Y3_event_reuse`
- `enable_mixed_cv`：`True`
- `tile_mix_cube_loop`：`1`
- `tile_mix_vector_loop`：`2`
- `auto_cv_balance`：`True`
- `barrier_level`：`low`
- `event_reuse`：`True`
- `sync_granularity`：`stage`
- `reduce_tile_policy`：`half_k`
- `layout_aware_tile`：`True`
- `ub_multiplier`：`1`
- `l1_multiplier`：`1`
- `stage_buffer_policy`：`none`
- `buffer_multipliers_json`：`{"k_l1":1,"q_l1":1,"q_ub":1,"v_l1":1}`
- `producer_consumer_distance`：`1`
- `event_id_policy`：`reuse`
- `sync_motion`：`local_move`
- `model_version`：`V2.8.5-continuous-capped-penalty-model`

### 4.2 模型选择该策略的原因
- Layered search selected this StrategyConfig after L1 tiling/fusion pruning, L2 overlap allocation, and L3 refinement.
- m=double_buffer enables the document-3 overlap model: serial load+compute+store moves toward max(load, compute, store).
- s=2 models CV soft-pipeline overlap; r=1:1 balances Cube/Vector chunks.
- y=graph_sync_solver uses a lower analytical sync-cost proxy than keep_existing/inject-style sync.
- PlanMemory-style estimated maxLive_UB=93.28 KB within 256.00 KB capacity.
- Predicted tile_time=308.14 cycles, n_tiles=22.

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
| UB | 49.97 | 93.28 | 256.00 |
| L1 | 44.81 | 45.94 | 1024.00 |
| L0A | 16.00 | 16.00 | 64.00 |
| L0B | 8.00 | 12.00 | 64.00 |
| L0C | 9.00 | 13.00 | 256.00 |

### 6.2 Cost Breakdown 对比
| 组成项 | 当前 IR 估计 | 最优候选 | 变化量 |
|---|---:|---:|---:|
| 并行化 tile cycles | 303.57 | 308.14 | +4.57 |
| 每 tile 暴露 load | 151.77 | 114.85 | -36.92 |
| Cube/Vector pipeline | 303.57 | 292.40 | -11.17 |
| 每 tile 暴露 store | 76.13 | 88.20 | +12.07 |
| warmup / drain | 0.00 | 15.74 | +15.74 |
| 同步 cost | 300.00 | 66.92 | -233.08 |
| 资源压力惩罚 | 0.00 | 0.00 | +0.00 |
| shape 惩罚 | 20.00 | 11.67 | -8.33 |

## 7. Top 候选排行
| Rank | Strategy ID | Predicted cycles | Tile | DB | CV stage | Sync | DMA | Reuse | maxLive UB KB |
|---:|---|---:|---|---|---:|---|---|---|---:|
| 1 | candidate_01441 | 386.73 | (64,48,128) | True | 2 | graph_sync_solver | keep_existing | level1 | 93.28 |
| 2 | candidate_01445 | 386.73 | (64,48,128) | True | 2 | graph_sync_solver | keep_existing | level1 | 93.28 |
| 3 | candidate_01446 | 386.73 | (64,48,128) | True | 2 | graph_sync_solver | keep_existing | level1 | 93.28 |
| 4 | candidate_01477 | 386.73 | (64,48,128) | True | 2 | graph_sync_solver | keep_existing | level1 | 93.28 |
| 5 | candidate_01481 | 386.73 | (64,48,128) | True | 2 | graph_sync_solver | keep_existing | level1 | 93.28 |
| 6 | candidate_01482 | 386.73 | (64,48,128) | True | 2 | graph_sync_solver | keep_existing | level1 | 93.28 |
| 7 | candidate_01429 | 388.57 | (64,48,128) | True | 2 | graph_sync_solver | keep_existing | level1 | 93.28 |
| 8 | candidate_01433 | 388.57 | (64,48,128) | True | 2 | graph_sync_solver | keep_existing | level1 | 93.28 |
| 9 | candidate_01434 | 388.57 | (64,48,128) | True | 2 | graph_sync_solver | keep_existing | level1 | 93.28 |
| 10 | candidate_01465 | 388.57 | (64,48,128) | True | 2 | graph_sync_solver | keep_existing | level1 | 93.28 |

## 8. Scope 与解释边界
- 当前版本是参数搜索实现：它把 HIVM 行为抽象为四类可搜索 Plan，并在合法候选上最小化解析 cost model。
- 当前独立仓库通过 IR parsing 与硬件规则解析得到 Plan 字段；真实 compiler pass dumps 不是运行必需项，但如果可获得，将是更强的数据来源。
- 当前 estimated capacity / alignment / tiling / pipeline gate 覆盖了主要硬件边界；SyncPlan 只提供策略级同步建模，不提供形式化 deadlock proof。
- 本版本不做 IR rewrite；如需证明策略可以真实落地，还需要后续接入 IR rewrite、compiler dry-run 与真机 profiling。
