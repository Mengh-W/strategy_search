# V4.2 SyncPlan Real-backend Locator Dry-run 说明

## 1. 本版本解决什么问题

V4.1 已经能生成 `sync_precision_contract.json`，并把它交给 backend dry-run。但 V4.1 的真实 backend skeleton 仍主要停留在：

```text
我读到了 action_id / mutation_kind
```

V4.2 继续推进到：

```text
我尝试在真实 MLIR Operation 层定位这个 action 指向的 sync op。
```

这一步仍然不做 mutation。它只是让 `hivm-operation-backend --dry-run` 逐条回答：

```text
1. contract 中的 action 是否被读取？
2. 对应的 set_flag / wait_flag / pipe_barrier / sync_block 是否能被 HivmOpsEditor listOps 定位？
3. 对 existing event pair，backend 是否能通过 operation printed text 或 source location 找到 set/wait pair？
4. 对 barrier candidate，backend 是否能定位目标 barrier？
5. 还缺哪些 proof 才能进入 guarded mutation？
```

## 2. 新增的 backend 能力

`vtriton_hivm_operation_backend/hivm_operation_backend.cpp` 新增：

```text
readTextFileBestEffort
parseEditScriptActionsBestEffort
locateSyncActionJson
```

其中：

- `parseEditScriptActionsBestEffort` 从 `sync_precision_contract.json` 里抽取 `action_id`、`mutation_kind`、`event_id` 和候选 source line。
- `locateSyncActionJson` 使用 HivmOpsEditor `listOps()` 返回的 operation 指针，结合 `FileLineColLoc` 和 operation printed text，做 per-action locator。
- locator 结果会写入 backend dry-run JSON。

输出示意：

```json
{
  "action_id": "sync_check_event_EVENT_ID0",
  "mutation_kind": "validate_existing_event_pair_liveness",
  "event_id": "EVENT_ID0",
  "operation_found": true,
  "located": true,
  "locator": {
    "strategy": "event_id_or_contract_line_against_HivmOpsEditor_listOps",
    "matched_operation_count": 2,
    "matched_ops": [
      {"index": 7, "name": "hivm.hir.wait_flag", "line": 24},
      {"index": 17, "name": "hivm.hir.set_flag", "line": 34}
    ]
  },
  "checks": {
    "backend_parsed_event_operands": true,
    "event_pairs_reported": true,
    "event_liveness_passed": false,
    "no_deadlock_or_conflict_reported": false
  },
  "blockers": [
    "event_liveness_proof_not_implemented_yet",
    "deadlock_check_not_implemented_yet"
  ]
}
```

## 3. 为什么仍然不能 mutation

V4.2 只解决了“能不能定位目标 operation”。它还没有解决：

```text
event live range 是否冲突
wait 是否真的在调度上发生在 set 之后
是否会产生 deadlock
barrier 替换后是否遗漏其他依赖
producer-consumer dependency 是否被真实证明
```

因此，即使 locator 成功，SyncPlan 仍然是 dry-run/check-only。

## 4. Windows CMD 运行方式

### fake backend

```cmd
scripts\run_v42_sync_fake_backend_dryrun.cmd
```

fake backend 只用于验证 Python/JSON/脚本链路，不代表真实 rewrite 能力。

### real backend

等真实 `hivm-operation-backend.exe` 编译出来后：

```cmd
scripts\run_v42_sync_real_backend_dryrun.cmd ^
  D:\path\to\vTriton\build\bin\Release\hivm-operation-backend.exe ^
  sample_input\fa_best.hivm.mlir ^
  artifacts\latest_smoke_run\selected_plan.json ^
  artifacts\v42_sync_real_backend_dryrun
```

重点回传：

```text
artifacts\v42_sync_real_backend_dryrun\backend_execution\backend_dry_run_contract.json
artifacts\v42_sync_real_backend_dryrun\sync_backend_dryrun_analysis\sync_backend_dryrun_analysis.json
```

## 5. 下一步

V4.3 建议继续做 SyncPlan，但不要急着 mutation。下一步应实现：

```text
1. event liveness proof skeleton；
2. set/wait pair schedule warning；
3. pipe-level conflict report；
4. barrier candidate 的 producer-consumer dependency dry-run report。
```

只有这些 proof 有结果后，才能讨论单 action guarded SyncPlan mutation。
