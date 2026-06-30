# V4.9 MultiBufferPlan stage-boundary analysis

## 1. 本版目标

V4.8 已经能识别 HIVM 中的 buffer-like anchor，并生成 double-buffer mutation plan。V4.9 继续向真实 MultiBufferPlan rewrite 推进，但仍不直接 clone buffer 或替换 use，而是补上真实 rewrite 最关键的中间层：**producer / consumer / sync / loop stage-boundary analysis**。

换句话说，V4.8 回答：

> 哪些 buffer 看起来像 double-buffer 候选？

V4.9 进一步回答：

> 这个 buffer 是否能找到生产者、消费者、同步上下文和循环上下文？它是否具备 ping-pong rewrite 的 stage 边界？

## 2. 为什么不能直接 mutation

MultiBufferPlan 不像 SyncPlan 的 `pipe_barrier -> set_flag/wait_flag` 那样局部。真实 double buffer 需要：

1. 创建或 clone 第二个本地 buffer slot；
2. 生产阶段写入 `slot[iteration % 2]`；
3. 消费阶段读取 `slot[(iteration + lag) % 2]`；
4. 正确插入或复用 SyncPlan event；
5. 保证 UB/L1/L0 容量不溢出；
6. 保证 dominance、alias、use replacement 合法；
7. 通过真实 MLIR verifier 和 DES/trace 验证。

所以 V4.9 做的是 stage-boundary plan，不冒充 production mutation。

## 3. 新增文件

```text
strategy_search/multibuffer_stage_boundary.py
tools/run_multibuffer_stage_boundary.py
scripts/run_v49_multibuffer_stage_boundary.cmd
scripts/run_v49_multibuffer_stage_boundary.sh
tests/test_v49_multibuffer_stage_boundary.py
docs/archive/rewrite_history/26_v49_multibuffer_stage_boundary_CN.md
```

## 4. 输出文件

默认输出目录：

```text
artifacts/v49_multibuffer_stage_boundary/
```

主要文件：

```text
multibuffer_stage_boundary_report.json
multibuffer_stage_mutation_plan.json
multibuffer_stage_annotated_not_mutated.hivm.mlir
multibuffer_stage_annotation_report.json
multibuffer_stage_boundary_summary.json
```

## 5. stage-boundary report 包含什么

每个候选会输出：

```json
{
  "symbol": "%69",
  "target": {"line": 184, "scope": "L1_CBUF"},
  "stage_boundary_status": "READY_FOR_PINGPONG_PLAN",
  "producer_candidates": [...],
  "consumer_candidates": [...],
  "nearest_stage_pair": {...},
  "sync_context": [...],
  "loop_context_lines": [...],
  "required_for_real_mutation": [...]
}
```

其中：

- `producer_candidates`：疑似写入该 buffer 的 op，例如 `load outs(...)`、`nd2nz outs(...)`、`memref.store`；
- `consumer_candidates`：疑似读取该 buffer 的 op，例如 vector/cube compute 的 `ins(...)`、store/fixpipe 的 input；
- `sync_context`：producer-consumer 附近的 `set_flag / wait_flag / pipe_barrier / sync_block`；
- `loop_context_lines`：候选是否处于 `scf.for / affine.for` 循环区域；
- `stage_boundary_status`：是否足以进入 ping-pong plan。

## 6. mutation plan 的含义

V4.9 会生成 `multibuffer_stage_mutation_plan.json`，但它仍然是：

```text
STAGE_PLANNED_NOT_MUTATED
```

里面会明确给出未来 HivmOpsEditor 后端需要执行的步骤：

```text
locate target defining op by line/symbol
locate producer and consumer operations
clone target buffer op or create second slot
rewrite producer stage uses
rewrite consumer stage uses
insert/reuse SyncPlan set_flag/wait_flag
exportToFile and mlir::verify
```

## 7. Windows CMD

```cmd
cd /d D:\hivm\HIVM_strategy_search_demo_V4.9
scripts\run_v49_multibuffer_stage_boundary.cmd
```

指定输入：

```cmd
scripts\run_v49_multibuffer_stage_boundary.cmd ^
  sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir ^
  artifacts\latest_smoke_run\selected_plan.json ^
  artifacts\v49_multibuffer_stage_boundary ^
  80 ^
  30
```

## 8. 当前边界

V4.9 没有进行语义级 mutation：

```json
{
  "semantic_mutation_performed": false,
  "production_rewrite_claim_allowed": false
}
```

这是有意设计。没有真实 HivmOpsEditor / verifier / DES 的情况下，MultiBufferPlan 直接替换 use 风险很高。V4.9 的价值是把真正 mutation 需要的 producer-consumer-stage 信息准备好。

## 9. 下一步

下一步可以进入：

```text
V4.10 CVPipelinePlan staged rewrite planner
```

因为 MultiBufferPlan 已经从 buffer candidate 推进到 stage-boundary plan，接下来可以把 load / compute / store / sync 划分为 pipeline stage，为 CVPipelinePlan 做准备。
