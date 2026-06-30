# V4.5 SyncPlan Portable Rewrite Closure

版本：`V4.5-syncplan-portable-rewrite-closure`

## 1. 目标

V4.5 的目标是：在没有真实 vTriton/BiShengIR/HivmOpsEditor 编译环境时，先把 SyncPlan 的受限 rewrite 闭环打通到一个可本地执行、可产物检查、可结构验证的 portable 路径。

这不是 production compiler rewrite。它的定位是：

```text
selected_plan.json
  -> sync_precision_contract.json
  -> restricted portable SyncPlan rewrite
  -> optimized.sync_portable_rewritten.hivm.mlir
  -> portable structural validation
```

## 2. 当前真实实现

当前支持的受限 rewrite 是单个 `hivm.hir.pipe_barrier[<PIPE_X>]`：

```mlir
hivm.hir.pipe_barrier[<PIPE_MTE2>]
```

改写为：

```mlir
// HIVM V4.3 restricted SyncPlan rewrite: original hivm.hir.pipe_barrier[<PIPE_MTE2>]
hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_MTE2>, EVENT_ID_AUTO0]
hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_MTE2>, EVENT_ID_AUTO0]
```

默认只改 1 个 action，默认跳过 `PIPE_ALL`。

## 3. 新增文件

```text
strategy_search/sync_rewrite_validator.py
tools/run_sync_rewrite_closure.py
scripts/run_v45_sync_portable_rewrite.cmd
scripts/run_v45_sync_portable_rewrite.sh
tests/test_sync_rewrite_validator.py
docs/archive/rewrite_history/22_v45_syncplan_portable_rewrite_closure_CN.md
```

## 4. Windows CMD 运行

```cmd
scripts\run_v45_sync_portable_rewrite.cmd
```

默认输入：

```text
sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir
artifacts\latest_smoke_run\selected_plan.json
artifacts\v45_sync_portable_rewrite
```

也可以指定：

```cmd
scripts\run_v45_sync_portable_rewrite.cmd ^
  sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir ^
  artifacts\latest_smoke_run\selected_plan.json ^
  artifacts\my_sync_rewrite_out
```

## 5. 输出

```text
sync_precision_contract/sync_precision_contract.json
optimized.sync_portable_rewritten.hivm.mlir
sync_portable_rewrite_report.json
sync_portable_rewrite_validation.json
sync_portable_rewrite_closure_summary.json
```

重点看 `sync_portable_rewrite_closure_summary.json`：

```json
{
  "mutation_performed": true,
  "rewritten_action_count": 1,
  "passed_portable_validation": true,
  "production_rewrite_claim_allowed": false
}
```

## 6. Portable validation 检查什么

V4.5 会检查：

```text
1. 非注释 pipe_barrier 是否减少 1；
2. set_flag 是否增加 1；
3. wait_flag 是否增加 1；
4. 新生成 event 是否一 set 一 wait；
5. set 是否出现在 wait 之前；
6. 大括号数量是否保持平衡；
7. 输出文件是否生成。
```

## 7. 安全边界

V4.5 仍然不能声称 production rewrite 完成，原因是：

```text
1. 当前 portable rewrite 是文本级 rewrite，不是 MLIR Operation mutation；
2. 没有真实 HivmOpsEditor verifier；
3. 没有 DES/trace 对比；
4. 没有 msprof 真机验证；
5. same-pipe set/wait 是受限 barrier-emulation prototype，不等于已证明最优同步优化。
```

## 8. 下一步

如果暂时没有真实 vTriton 环境，下一步建议继续沿 portable 路线增强：

```text
1. 支持多 action rewrite，但默认仍限制为 1；
2. 增加 before/after diff report；
3. 针对 e2e_chunk 的 pipe_barrier 做分类型 rewrite candidate ranking；
4. 为真实 HivmOpsEditor mutation 保留同构 contract。
```

如果未来有真实环境，V4.5 的 contract 和输出可以直接用于对照 HivmOpsEditor mutation 的结果。
