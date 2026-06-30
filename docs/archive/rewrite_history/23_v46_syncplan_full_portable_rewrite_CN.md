# V4.6 SyncPlan portable full rewrite 说明

版本：`V4.6-syncplan-portable-full-rewrite`

## 目标

V4.6 回答的问题是：在没有真实 vTriton / BiShengIR / HivmOpsEditor 编译环境的情况下，SyncPlan 能不能先形成一个“尽可能完整”的本地 rewrite 闭环。

本版实现的是：

```text
input MLIR
  -> sync_precision_contract.json
  -> candidate ranking / selection
  -> multi-action portable rewrite
  -> optimized.sync_full_portable_rewritten.hivm.mlir
  -> structural validation
  -> before/after sync liveness report
  -> unified diff report
  -> closure summary
```

## 支持范围

当前支持将多个非 `PIPE_ALL` 的：

```mlir
hivm.hir.pipe_barrier[<PIPE_X>]
```

改写为：

```mlir
// HIVM V4.3 restricted SyncPlan rewrite: original hivm.hir.pipe_barrier[<PIPE_X>]
hivm.hir.set_flag[<PIPE_X>, <PIPE_X>, EVENT_ID_AUTON]
hivm.hir.wait_flag[<PIPE_X>, <PIPE_X>, EVENT_ID_AUTON]
```

默认最多改写所有候选；可以通过 `--max-actions` 或 CMD 第四个参数限制数量。

## Windows CMD 使用

```cmd
scripts\run_v46_sync_full_portable_rewrite.cmd
```

也可以指定：

```cmd
scripts\run_v46_sync_full_portable_rewrite.cmd ^
  sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir ^
  artifacts\latest_smoke_run\selected_plan.json ^
  artifacts\v46_sync_full_portable_rewrite ^
  3
```

第四个参数 `3` 表示只改写前三个候选。

## 输出

```text
sync_precision_contract/sync_precision_contract.json
sync_full_rewrite_candidates.json
optimized.sync_full_portable_rewritten.hivm.mlir
sync_full_portable_rewrite_report.json
sync_full_portable_rewrite_validation.json
sync_liveness_before.json
sync_liveness_after.json
sync_full_portable_rewrite_diff.json
sync_full_portable_rewrite_closure_summary.json
```

## 边界

V4.6 是 portable/text-level full closure，不是 production HivmOpsEditor rewrite。不能 claim production 的原因：

1. 没有真实 MLIR Operation-level mutation；
2. 没有真实 HivmOpsEditor verifier；
3. 没有 DES/trace；
4. 没有 msprof；
5. same-pipe set/wait 仍是 barrier-emulation prototype，不是已经证明性能提升的同步优化。

但 V4.6 可以 claim：

> SyncPlan 已经形成完整 portable rewrite 闭环：候选识别、批量受限改写、输出 optimized MLIR、结构校验、liveness 报告、diff 报告、closure summary。
