# V5.8 TilingPlan / CVPipelinePlan Semantic Rewrite Hardening

## 目标

V5.8 在 V5.7 的四 Plan operation-level MVP rewrite + precompile audit 基础上，继续推进两个最弱环节：

1. **TilingPlan**：从 loop scaffold / shape mutation 推进到 axis binding、per-operation tile-slice binding、tail/reduction semantic binding。
2. **CVPipelinePlan**：从 sync-edge / slot marker 推进到 stage graph、prologue/steady/epilogue schedule binding。

本版本仍不宣称 Linux backend 已编译通过；它的定位是生成更接近完整策略落地的 optimized HIVM candidate，并输出更严格的语义绑定报告，供 Ascend Linux backend 做 parse、roundtrip、verifier、compile、correctness、msprof 验证。

## 新增模块

```text
strategy_search/operation_rewrite/tiling_semantic_full_rewrite_v58.py
strategy_search/operation_rewrite/cvpipeline_semantic_schedule_v58.py
```

## 新增输出

运行：

```bash
bash scripts/run_v58_tiling_cvpipeline_semantic_rewrite.sh
```

默认输出目录：

```text
artifacts/v58_tiling_cvpipeline_semantic_rewrite/
```

关键文件：

```text
optimized.four_plan_operation_rewrite.hivm.mlir
optimized.four_plan_operation_rewrite.precompile_hardened.hivm.mlir
stages/01_tiling_semantic_operation_rewrite/tiling_axis_binding.json
stages/01_tiling_semantic_operation_rewrite/tiling_semantic_full_rewrite_report.json
stages/03_cvpipeline_operation_rewrite/cvpipeline_stage_graph.json
stages/03_cvpipeline_operation_rewrite/cvpipeline_semantic_schedule_report.json
four_plan_operation_rewrite_summary.json
operation_parameter_coverage.json
v57_linux_precompile_audit.json
```

## TilingPlan 推进内容

V5.8 新增：

- 从函数签名和 memref shape 推断 Q/K/V/O tensor roles；
- 绑定 M/N/K/D axes；
- 将 `tile_m/tile_n/tile_k` 绑定到 `%m_outer/%n_outer/%k_outer`；
- 在 load/copy/nd2nz/mmad/fixpipe/vector/store 等 HIVM operation 前插入 tile-slice semantic binding；
- 对 score/output reduction 插入 reduction binding；
- 将 `tail_strategy` 表达为 tile_end / mask-or-pad 语义；
- 将 `reduce_tile_policy` 表达为 partial accumulator 语义；
- 将 `layout_aware_tile` 表达为 layout transform / legality guard 语义。

仍需 Linux backend 验证和下沉的内容：

- 将 semantic binding 降成官方 dialect 合法的 loop/index/slice operation；
- 验证 tail mask / pad 是否符合 backend 语义；
- 验证 reduction accumulator 初始化、更新、final store 是否正确；
- 验证 load/store slice offset 是否完全匹配真实 tensor layout。

## CVPipelinePlan 推进内容

V5.8 新增：

- 从 HIVM ops 构建 stage graph：load/layout/compute/vector/store/sync；
- 将 `stage_num`、`template`、`producer_consumer_distance`、`stage_buffer_policy` 映射到显式 prologue/steady/epilogue schedule；
- 在各 stage operation 前插入 stage binding；
- 明确 producer-consumer distance：`load tile[i+d]` 与 `compute/vector/store tile[i]` 的关系；
- 明确 stage buffer slot policy 与 MultiBufferPlan 的联动边界。

仍需 Linux backend 验证和下沉的内容：

- 将 schedule binding 降成真实 reordered loop body；
- 检查 pipeline 后 producer-consumer dependency；
- 检查 slot = i mod buffer_count 的 use-def；
- 重新验证 SyncPlan set/wait 是否和新 schedule 一致。

## 当前状态

V5.8 默认样例满足：

```json
{
  "tiling_semantic_full_rewrite_performed": true,
  "cvpipeline_semantic_schedule_performed": true,
  "linux_precompile_audit_passed": true,
  "linux_compile_ready_claim": false,
  "linux_backend_validation_required": true
}
```

因此本版本可以说：

> TilingPlan 和 CVPipelinePlan 已从 MVP marker / scaffold 进一步推进到 axis/slice/reduction 与 stage schedule semantic binding；四 Plan 的寻优策略在 optimized HIVM candidate 中体现得更完整。下一步必须交给 Ascend Linux backend 完成官方 legality、compile、correctness 与 msprof 验证。

不能说：

> V5.8 已经证明 optimized HIVM 能 Linux 编译、能运行、能加速。
