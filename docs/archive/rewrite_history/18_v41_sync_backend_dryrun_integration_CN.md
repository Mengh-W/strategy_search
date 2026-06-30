# V4.1 SyncPlan Backend Dry-run Integration

## 1. 本版本目标

V4.1 将 V4.0 的 `sync_precision_contract.json` 接入 backend dry-run execution。它仍然不做真实 mutation，而是让 fake/real backend 按统一流程回答：

1. backend 能否读取 HIVM IR；
2. backend 能否 roundtrip 输出；
3. backend verify 是否通过；
4. backend 能否读取 SyncPlan precision contract；
5. backend 是否能对每个 sync action 给出定位和 proof 状态。

这一步的核心价值是把 SyncPlan 从“生成施工单”推进到“施工单可以交给后端 dry-run 验收”。

## 2. 新增链路

```text
sample_input/fa_best.hivm.mlir
  + selected_plan.json
  -> sync_precision_contract.json
  -> backend_execution/backend_dry_run_contract.json
  -> sync_backend_dryrun_analysis.json
```

## 3. 新增文件

```text
strategy_search/sync_backend_dryrun_analyzer.py
tools/execute_sync_precision_contract.py
tests/test_sync_backend_dryrun_analyzer.py
scripts/run_v41_sync_fake_backend_dryrun.cmd/.sh
scripts/run_v41_sync_real_backend_dryrun.cmd/.sh
docs/archive/rewrite_history/18_v41_sync_backend_dryrun_integration_CN.md
```

## 4. Windows CMD 用法

### fake backend smoke

```cmd
scripts\run_v41_sync_fake_backend_dryrun.cmd
```

该命令不需要 vTriton，只验证 JSON/CLI/报告链路。正常结论应为：

```text
WAIT_FOR_REAL_BACKEND
```

### real backend dry-run

等真实 `hivm-operation-backend.exe` 编译出来后运行：

```cmd
scripts\run_v41_sync_real_backend_dryrun.cmd ^
  D:\path\to\vTriton\build\bin\Release\hivm-operation-backend.exe ^
  sample_input\fa_best.hivm.mlir ^
  artifacts\latest_smoke_run\selected_plan.json ^
  artifacts\v41_sync_real_backend_dryrun
```

## 5. 输出文件

```text
artifacts/v41_sync_fake_backend_dryrun/
  sync_precision_contract/
    sync_precision_contract.json
    sync_precision_contract_summary.json
  backend_execution/
    backend_capabilities.json
    backend_inventory.json
    backend_roundtrip.json
    backend_verify.json
    backend_dry_run_contract.json
    backend_contract_execution_summary.json
  sync_backend_dryrun_analysis/
    sync_backend_dryrun_analysis.json
    sync_backend_dryrun_analysis_summary.json
```

## 6. 安全边界

V4.1 仍然禁止 SyncPlan mutation。即使真实 backend dry-run 的 proofs 都完整，结论也只是：

```text
REAL_BACKEND_SYNC_PROOFS_AVAILABLE_REVIEW_REQUIRED
```

也就是说，下一步需要人工审查单个 action，再单独设计 guarded mutation。V4.1 不会批量删除 barrier，也不会由 Python 拼接新的 `set_flag/wait_flag` MLIR。

## 7. 接下来怎么推进

真实 backend dry-run 通过后，下一步应优先做：

1. 让 HivmOpsEditor backend 对 `validate_existing_event_pair_liveness` 返回真实 event liveness proof；
2. 对 barrier-heavy 样例生成 `barrier_to_directional_event_pair` action；
3. 只选择一个 barrier action 设计 guarded mutation；
4. mutation 后必须 roundtrip / verify / DES / trace。
