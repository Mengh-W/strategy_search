# 10. 四个 Plan Backend Contract 执行层说明

这一版新增的是 **backend contract execution harness**。

它不是新的 rewrite 算法，也不直接修改 HIVM IR。它的作用是把前面生成的 `four_plan_backend_contract.json` / `sync_multibuffer_backend_contract.json` 交给一个 backend 可执行程序，按统一流程跑：

```text
capabilities
  ↓
inventory
  ↓
roundtrip
  ↓
verify-only
  ↓
dry-run with edit-script
  ↓
optional mutate
```

> **重要口径：本文件描述 contract execution harness。使用 fake backend 通过时，只能说明 Python 调用、CLI 参数、JSON report 和 dry-run/mutate 流程正确；不能作为真实 production rewrite 证据。真实证据必须来自 Linux 环境中的真实 vTriton/BiShengIR/HivmOpsEditor backend。**

## 1. 为什么需要这一层

前面已经有：

```text
selected_plan.json
  ↓
hivm_ir_inventory.official.json
  ↓
four_plan_rewrite_plan.json
  ↓
four_plan_rewrite_readiness.json
  ↓
four_plan_backend_contract.json
```

这些文件回答的是：

```text
四个 Plan 想改什么？
候选 op / buffer / loop 在哪里？
哪些 rewrite 可以进入 backend dry-run？
backend 需要证明什么？
```

但是还缺一步：

```text
这些 contract 能不能真的被 backend 消费？
backend 能不能读 IR、roundtrip、verify、dry-run？
```

所以新增执行层：

```text
four_plan_backend_contract.json
  ↓
execute_backend_contract.py
  ↓
backend_capabilities.json
backend_inventory.json
backend_roundtrip.json
backend_verify.json
backend_dry_run_contract.json
backend_contract_execution_summary.json
```

## 2. 新增代码

```text
strategy_search/backend_contract_runner.py
  负责执行 backend contract smoke sequence。

tools/execute_backend_contract.py
  命令行入口。

tests/test_backend_contract_runner.py
  使用 fake backend 验证流程。
```

## 3. 当前使用 fake backend 的本地命令

这条命令我已经跑通过。它只验证 CLI/report plumbing，不是真实 compiler rewrite。

```bash
python tools/build_four_plan_backend_contract.py \
  --ir sample_input/fa_best.hivm.mlir \
  --selected-plan artifacts/latest_smoke_run/selected_plan.json \
  --output-dir artifacts/latest_backend_contract

python tools/execute_backend_contract.py \
  --backend tools/fake_hivm_operation_backend.py \
  --ir sample_input/fa_best.hivm.mlir \
  --contract artifacts/latest_backend_contract/sync_multibuffer_backend_contract.json \
  --output-dir artifacts/latest_backend_contract_execution
```

输出：

```text
artifacts/latest_backend_contract_execution/
  backend_capabilities.json
  backend_inventory.json
  roundtrip.hivm.mlir
  backend_roundtrip.json
  backend_verify.json
  backend_dry_run_contract.json
  backend_contract_execution_summary.json
```

其中 `backend_contract_execution_summary.json` 会明确写出：

```json
{
  "is_real_mlir_backend": false,
  "all_required_commands_ok": true,
  "production_rewrite_claim_allowed": false
}
```

这表示 fake backend 只能证明流程通了，不能证明真实 rewrite 成功。

## 4. 之后换成真实 HivmOpsEditor backend 时怎么跑

等真实 `hivm-operation-backend` 编译出来后，用同一条执行命令，只替换 `--backend`：

```bash
python tools/execute_backend_contract.py \
  --backend /path/to/vTriton/build/bin/hivm-operation-backend \
  --ir sample_input/fa_best.hivm.mlir \
  --contract artifacts/latest_backend_contract/sync_multibuffer_backend_contract.json \
  --output-dir artifacts/real_backend_contract_execution
```

第一轮不要加 `--run-mutate`。

只有当下面几步都通过后，才考虑 mutation：

```text
--print-capabilities 通过
--inventory 通过
--roundtrip 通过
--verify-only 通过
--dry-run + edit-script 通过
```

之后再谨慎跑：

```bash
python tools/execute_backend_contract.py \
  --backend /path/to/vTriton/build/bin/hivm-operation-backend \
  --ir sample_input/fa_best.hivm.mlir \
  --contract artifacts/latest_backend_contract/sync_multibuffer_backend_contract.json \
  --output-dir artifacts/real_backend_contract_mutation \
  --run-mutate \
  --mutation-kind sync_multibuffer_contract
```

## 5. 当前四个 Plan 的推进状态

| Plan | 当前状态 | 是否进入真实 mutation |
|---|---|---|
| SyncPlan | 已生成 backend contract，可 dry-run | 等真实 backend |
| MultiBufferPlan | 已生成 buffer clone contract，可 dry-run | 等真实 backend |
| CVPipelinePlan | 已生成 stage reorder contract，但依赖 Sync/MultiBuffer | 暂不 mutation |
| TilingPlan | hint/report only | 暂不 mutation |

## 6. 当前不能 claim 什么

当前不能说：

```text
已经完成真实 SyncPlan rewrite。
已经完成真实 MultiBufferPlan buffer clone。
已经完成 CVPipeline overlap。
已经完成真实 TilingPlan lowering。
```

当前可以说：

```text
已经完成四个 Plan 从 selected strategy 到 backend-facing contract 的链路；
已经完成 SyncPlan + MultiBufferPlan 的第一阶段 backend dry-run contract；
已经完成 fake backend 下的 contract execution harness 验证；
下一步需要真实 HivmOpsEditor backend 跑同一套 contract。
```
