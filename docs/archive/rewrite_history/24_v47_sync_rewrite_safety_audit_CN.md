# V4.7 SyncPlan rewrite safety & audit

版本：`V4.7-syncplan-rewrite-safety-audit`

## 1. 本版目标

V4.6 已经实现了 portable/text-level 的完整 SyncPlan rewrite 闭环，可以批量将非 `PIPE_ALL` 的
`hivm.hir.pipe_barrier` 改写为 `hivm.hir.set_flag + hivm.hir.wait_flag`，并输出 optimized MLIR、diff、liveness 和 validation。

V4.7 继续增强的是“可审计性”：让每个 rewrite action 都能回答以下问题：

1. 为什么这个 barrier 被选中？
2. 它属于哪个 pipe？
3. 风险等级是什么？
4. 附近是否存在其他 sync op？
5. rewrite 前后 sync op 数量是否符合预期？
6. 生成 event 是否唯一？
7. 后续迁移到 HivmOpsEditor 时应调用哪些 API？

因此，V4.7 的核心不是扩大 rewrite 范围，而是把 SyncPlan 从“能改”推进到“改得可解释、可审计、可迁移”。

## 2. 新增文件

```text
strategy_search/sync_rewrite_audit.py
tests/test_v47_sync_rewrite_audit.py
scripts/run_v47_sync_rewrite_safety_audit.cmd
scripts/run_v47_sync_rewrite_safety_audit.sh
docs/archive/rewrite_history/24_v47_sync_rewrite_safety_audit_CN.md
```

## 3. 新增输出

V4.7 在 V4.6 输出基础上新增：

```text
sync_rewrite_safety_audit.json
```

该文件包含：

```text
before_sync_counts
after_sync_counts
before_sync_by_pipe
after_sync_by_pipe
structural_delta
event_naming
risk_counts
batch_warnings
action_audit
hivmopseditor_migration_action_list
```

## 4. 风险分级规则

当前规则是 conservative portable audit，不是 production proof。

### LOW

通常包括：

```text
PIPE_MTE1 / PIPE_MTE2 / PIPE_MTE3
非 PIPE_ALL
存在明确 line anchor
附近没有密集 sync op
当前 run 已被 rewrite
```

### MEDIUM

通常包括：

```text
PIPE_V barrier
附近两行内存在其他 sync op
连续或密集 pipe_barrier 区域
memory transfer pipe 但邻域复杂
```

### HIGH

通常包括：

```text
非标准 pipe
未知 pipe
不常见 sync pattern
```

### BLOCKED

一定不允许 portable mutation：

```text
PIPE_ALL
缺少 line anchor
未知 pipe
非 barrier_to_directional_event_pair action
```

注意：BLOCKED action 会出现在 audit 中，但不会被 portable rewrite 执行。

## 5. before/after 结构审计

V4.7 会检查：

```text
pipe_barrier_delta == -rewritten_action_count
set_flag_delta == +rewritten_action_count
wait_flag_delta == +rewritten_action_count
```

如果三者不匹配，说明 portable rewrite 的结构变化不符合预期，audit 会失败。

## 6. event 命名审计

V4.7 会检查生成的 event：

```text
EVENT_ID_AUTO0
EVENT_ID_AUTO1
...
```

是否全部唯一。这个检查很重要，因为 event id 冲突会导致同步语义混乱。

## 7. HivmOpsEditor migration action list

V4.7 新增 `hivmopseditor_migration_action_list`，用于把 portable rewrite 迁移到真实 Operation-level mutation。

每个 rewritten action 会被整理成：

```json
{
  "action_id": "...",
  "line": 301,
  "pipe": "PIPE_MTE2",
  "event_id": "EVENT_ID_AUTO0",
  "operation_level_target": "hivm.hir.pipe_barrier",
  "hivmopseditor_api_sequence": [
    "addSetFlagWaitFlagBefore",
    "deleteOp",
    "exportToFile",
    "verify"
  ]
}
```

也就是说，V4.7 不只是产出文本 rewrite，也产出后续真实 HivmOpsEditor backend 应执行的 action 清单。

## 8. Windows CMD 使用

```cmd
cd /d D:\hivm\HIVM_strategy_search_demo_V4.7
scripts\run_v47_sync_rewrite_safety_audit.cmd
```

只改前 3 个候选：

```cmd
scripts\run_v47_sync_rewrite_safety_audit.cmd ^
  sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir ^
  artifacts\latest_smoke_run\selected_plan.json ^
  artifacts\v47_sync_rewrite_safety_audit ^
  3
```

## 9. 当前 smoke 结果

在 `chunk_kda_kernel_clean.npuir.mlir` 上，默认 full run 输出摘要：

```json
{
  "candidate_action_count": 74,
  "mutation_performed": true,
  "rewritten_action_count": 74,
  "skipped_action_count": 0,
  "passed_portable_validation": true,
  "passed_portable_liveness_after": true,
  "audit_decision": "PORTABLE_REWRITE_AUDITED_NOT_PRODUCTION",
  "audit_risk_counts": {
    "MEDIUM": 73,
    "BLOCKED": 6,
    "LOW": 1
  },
  "hivmopseditor_migration_action_count": 74,
  "portable_full_rewrite_closure_passed": true,
  "production_rewrite_claim_allowed": false
}
```

这里的 `BLOCKED=6` 通常来自 contract 中的 `PIPE_ALL` 等不可安全 portable mutation 的 barrier action。它们不会被 rewrite，但会被审计报告记录。

## 10. 当前边界

V4.7 仍然不能 claim production rewrite：

```text
1. 仍是 portable/text-level rewrite；
2. 没有真实 HivmOpsEditor parser/verifier；
3. 没有 DES/trace；
4. 没有 msprof；
5. audit 是结构与风险审计，不是语义正确性证明。
```

但是现在可以更稳地说：

```text
SyncPlan portable rewrite 已经完成从候选识别、批量改写、结构校验、liveness、diff 到 safety audit 的完整闭环；
并且每个 rewritten action 都有可迁移到 HivmOpsEditor 的 API 执行清单。
```
