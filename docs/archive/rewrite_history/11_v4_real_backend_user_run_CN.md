# V4.0：真实 Backend Dry-run 用户运行说明

## 1. V4.0 当前定位

V4.0 把前面几版的 rewrite 链路收敛成一个更清楚的工程闭环：

```text
selected_plan.json
  -> 官方 HIVM op inventory
  -> four_plan_rewrite_plan.json
  -> four_plan_rewrite_readiness.json
  -> four_plan_backend_contract.json
  -> backend contract execution
```

其中真正会动 HIVM IR 的仍然是 vTriton/HivmOpsEditor backend。Python 侧只负责：

1. 根据官方 HIVM Dialect 文档识别 load/store/compute/sync/loop/buffer；
2. 把四个 Plan 的寻优结果翻译成后端施工单；
3. 统一调用 backend 的 `inventory / roundtrip / verify-only / dry-run`；
4. 明确禁止在未验证前声称 production rewrite 成功。

## 2. 现在为什么还不用直接 mutate

V4.0 的第一目标不是直接改完整四个 Plan，而是先让真实 backend 证明：

```text
我能读这个 HIVM IR；
我能原样 roundtrip；
我能 verify；
我能读懂 SyncPlan + MultiBufferPlan 的 contract；
我能 dry-run 并说明哪些 action 能定位、哪些不能定位、为什么。
```

只有 dry-run 通过后，才进入单 action guarded mutation。不要一上来批量 mutate。

## 3. 本地 fake smoke，不需要 vTriton

这一步只验证仓库脚本和 JSON 链路没坏：

```bash
bash scripts/run_v4_fake_backend_smoke.sh
```

输出目录：

```text
artifacts/v4_fake_backend_smoke/
  backend_contract/
  backend_execution/
```

重点看：

```text
artifacts/v4_fake_backend_smoke/backend_execution/backend_contract_execution_summary.json
```

fake backend 的预期结果是：

```json
{
  "is_real_mlir_backend": false,
  "all_required_commands_ok": true,
  "production_rewrite_claim_allowed": false
}
```

这说明执行链路通了，但不能作为真实 rewrite 证据。

## 4. 真实 vTriton backend dry-run

等真实 `hivm-operation-backend` 编译出来后，运行：

```bash
bash scripts/run_v4_real_backend_dryrun.sh \
  /path/to/vTriton/build/bin/hivm-operation-backend \
  sample_input/fa_best.hivm.mlir \
  artifacts/latest_smoke_run/selected_plan.json \
  artifacts/v4_real_backend_dryrun
```

这个脚本不会请求 mutation，只会跑：

```text
--print-capabilities
--inventory
--roundtrip
--verify-only
--dry-run --edit-script sync_multibuffer_backend_contract.json
```

输出目录：

```text
artifacts/v4_real_backend_dryrun/
  backend_contract/
    hivm_ir_inventory.official.json
    four_plan_rewrite_plan.json
    four_plan_rewrite_readiness.json
    four_plan_backend_contract.json
    sync_multibuffer_backend_contract.json
  backend_execution/
    backend_capabilities.json
    backend_inventory.json
    roundtrip.hivm.mlir
    backend_roundtrip.json
    backend_verify.json
    backend_dry_run_contract.json
    backend_contract_execution_summary.json
```

## 5. 你需要把哪些结果贴回来

如果真实 dry-run 失败，把这些贴回来：

```text
artifacts/v4_real_backend_dryrun/backend_execution/backend_contract_execution_summary.json
artifacts/v4_real_backend_dryrun/backend_execution/backend_capabilities.json
artifacts/v4_real_backend_dryrun/backend_execution/backend_inventory.json
artifacts/v4_real_backend_dryrun/backend_execution/backend_roundtrip.json
artifacts/v4_real_backend_dryrun/backend_execution/backend_verify.json
artifacts/v4_real_backend_dryrun/backend_execution/backend_dry_run_contract.json
```

如果某条命令直接崩溃，也把终端完整报错贴回来。

## 6. 如何判断进入下一步

只有同时满足以下条件，才进入 guarded mutation：

```text
is_real_mlir_backend = true
all_required_commands_ok = true
roundtrip 成功
verify-only 成功
dry-run 能定位至少一个 SyncPlan/MultiBufferPlan action
backend 对拒绝的 action 给出明确 reason
```

下一步只允许单 action mutate，不允许一次性改所有 action。

## 7. 四个 Plan 的 V4.0 顺序

V4.0 仍然坚持这个落地顺序：

```text
SyncPlan dry-run / event liveness
  -> MultiBufferPlan dry-run / buffer clone contract
  -> guarded single-action mutation
  -> CVPipelinePlan candidate/stage contract
  -> TilingPlan hint/report only
```

CVPipelinePlan 必须等 SyncPlan 和 MultiBufferPlan 至少 dry-run 通过后再推进。TilingPlan 在 V4.0 中仍不做真实 loop rewrite。
