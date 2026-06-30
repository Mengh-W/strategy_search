# V4.4 SyncPlan HivmOpsEditor Mutation Prototype

## 1. 本版目标

V4.4 的目标是把 V4.3 中已经跑通的受限文本级 SyncPlan rewrite：

```text
hivm.hir.pipe_barrier[<PIPE_X>]
  -> hivm.hir.set_flag[<PIPE_X>, <PIPE_X>, <EVENT_ID0>]
  -> hivm.hir.wait_flag[<PIPE_X>, <PIPE_X>, <EVENT_ID0>]
```

迁移到真实 vTriton/HivmOpsEditor 后端路径中。

换句话说，V4.3 是 Python 文本级闭环；V4.4 是 C++ HivmOpsEditor mutation prototype。

## 2. 这版真正新增了什么

`vtriton_hivm_operation_backend/hivm_operation_backend.cpp` 新增了 SyncPlan mutation prototype：

1. 读取 `sync_precision_contract.json`；
2. 只选择一个 `barrier_to_directional_event_pair` action；
3. 根据 contract 中的 line anchor 在 `HivmOpsEditor::listOps()` 中定位目标 `pipe_barrier`；
4. 解析 `set_pipe / wait_pipe / event_id`；
5. 调用：

```cpp
editor.addSetFlagWaitFlagBefore(target, setPipe, waitPipe, eventAttr);
editor.deleteOp(target);
editor.exportToFile(outputFilename);
mlir::verify(*module);
```

6. 输出 `sync_hivmopseditor_mutation_report.json`。

## 3. 当前支持范围

当前只支持一个非常保守的 mutation：

```text
mutation_kind = sync_event_insertion
contract action = barrier_to_directional_event_pair
目标 op = 单个 hivm.hir.pipe_barrier
```

当前不支持：

```text
已有 set_flag/wait_flag 的 cleanup；
sync_block_set / sync_block_wait 改写；
PIPE_ALL 拆分；
批量 barrier mutation；
跨 loop / 跨 block 同步重排；
CVPipeline / MultiBuffer 联动 mutation。
```

## 4. 为什么仍然叫 prototype

V4.4 已经把 SyncPlan rewrite 接进 HivmOpsEditor mutation 路径，但还不能直接宣称 production rewrite。原因是：

1. 需要在真实 vTriton/BiShengIR 环境中编译验证；
2. 需要真实 MLIR verifier 通过；
3. 需要 tritonsim-hivm 生成 DES / trace 对比；
4. 需要确认 same-pipe set/wait 是否符合目标同步语义；
5. 需要 event liveness / deadlock proof；
6. 需要 msprof 真机验证。

因此 report 中仍然保留：

```json
"production_rewrite_claim_allowed": false
```

## 5. Windows CMD 使用方式

真实 mutation 默认被环境变量保护。必须显式打开：

```cmd
set HIVM_ALLOW_SYNC_MUTATION=1
scripts\run_v44_real_sync_mutation.cmd ^
  D:\path\to\vTriton\build\bin\Release\hivm-operation-backend.exe ^
  sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir ^
  artifacts\latest_smoke_run\selected_plan.json ^
  artifacts\v44_real_sync_mutation
```

输出：

```text
artifacts\v44_real_sync_mutation\sync_precision_contract\sync_precision_contract.json
artifacts\v44_real_sync_mutation\optimized.sync_hivmopseditor.hivm.mlir
artifacts\v44_real_sync_mutation\sync_hivmopseditor_mutation_report.json
```

## 6. 后续验收路线

如果真实 backend 编译通过并且 mutation report 显示：

```json
"mutation_performed": true,
"export_succeeded": true,
"verify_after_mutation": true
```

下一步才进入：

1. 对比 original / optimized inventory；
2. 使用 `tritonsim-hivm` 生成 DES graph；
3. 比较 barrier / set_flag / wait_flag 数量和依赖；
4. 如果 DES/trace 合理，再考虑 msprof 真机验证。
