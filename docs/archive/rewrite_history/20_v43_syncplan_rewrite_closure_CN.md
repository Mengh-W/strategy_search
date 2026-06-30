# V4.3 SyncPlan 受限 Rewrite 闭环报告

版本：`V4.3-syncplan-restricted-rewrite-closure`

## 1. 这版解决什么

V4.2 已经能生成 `sync_precision_contract.json`，并让 backend dry-run 去定位 sync action。V4.3 继续推进一步：在没有真实 HivmOpsEditor 编译环境的情况下，先把 SyncPlan 的**受限 rewrite 闭环**打通。

闭环为：

```text
input MLIR
  -> sync_precision_contract.json
  -> restricted SyncPlan rewrite executor
  -> optimized.sync_rewritten.hivm.mlir
  -> sync_rewrite_report.json
```

这说明 SyncPlan 不再只是 report/dry-run，而是能产生一个实际改写后的 IR 文件。

## 2. 当前支持的 rewrite

当前只支持一种非常受限的改写：

```text
hivm.hir.pipe_barrier[<PIPE_X>]
```

改写为：

```text
// HIVM V4.3 restricted SyncPlan rewrite: original hivm.hir.pipe_barrier[<PIPE_X>]
hivm.hir.set_flag[<PIPE_X>, <PIPE_X>, EVENT_ID_AUTO0]
hivm.hir.wait_flag[<PIPE_X>, <PIPE_X>, EVENT_ID_AUTO0]
```

默认只改一个 action，并且默认跳过 `PIPE_ALL`。

## 3. 这是不是 production rewrite？

不是。

这是一版 `restricted_text_rewrite`，用途是打通 SyncPlan 的工程闭环。它不能替代真实 HivmOpsEditor mutation，也不能直接 claim 性能优化。

当前报告会明确输出：

```json
"production_rewrite_claim_allowed": false
```

原因是：

1. 这是文本级 rewrite，不是 MLIR Operation-level mutation；
2. same-pipe set/wait pair 是保守的 barrier emulation anchor，不是已证明的 directional synchronization 优化；
3. 还没有真实 event liveness proof；
4. 还没有 deadlock proof；
5. 还没有 DES/trace/msprof 验收。

## 4. Windows CMD 运行方式

```cmd
scripts\run_v43_sync_rewrite_smoke.cmd
```

默认输入：

```text
sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir
artifacts\latest_smoke_run\selected_plan.json
artifacts\v43_sync_rewrite_smoke
```

也可以指定：

```cmd
scripts\run_v43_sync_rewrite_smoke.cmd ^
  sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir ^
  artifacts\latest_smoke_run\selected_plan.json ^
  artifacts\v43_sync_rewrite_smoke
```

## 5. 输出文件

```text
artifacts/v43_sync_rewrite_smoke/
  sync_precision_contract/sync_precision_contract.json
  optimized.sync_rewritten.hivm.mlir
  sync_rewrite_report.json
  sync_rewrite_summary.json
```

## 6. 后续计划

下一步不应该扩大文本 rewrite，而应该把同样的 mutation kind 接到真实 HivmOpsEditor backend：

1. backend 读取 `sync_precision_contract.json`；
2. 定位目标 `pipe_barrier` Operation；
3. 调用 HivmOpsEditor 插入官方 `set_flag / wait_flag`；
4. 删除或替换原 barrier；
5. roundtrip / verify；
6. tritonsim-hivm 生成 DES/trace；
7. 最后再考虑单 action guarded mutation。

当前 V4.3 的价值是证明 SyncPlan rewrite 的端到端工程链路已经通了，但生产级 rewrite 仍然等待真实 backend 编译验证。
