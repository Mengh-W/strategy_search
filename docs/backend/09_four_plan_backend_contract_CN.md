# 09 四个参数 Plan 的 Backend Contract 推进说明

> **重要口径：以下文档中的 backend contract 只表示“真实后端施工单已经生成”，不表示真实 backend 已经执行成功。fake backend 通过只能证明接口和报告链路通，不等同于 BiShengIR parser、MLIR verifier、HivmOpsEditor roundtrip、DES/trace 或 msprof 通过。**

## 1. 这一版解决什么问题

前一版已经能做：

```text
selected_plan.json
  ↓
官方文档驱动的 HIVM op inventory
  ↓
four_plan_rewrite_plan.json
  ↓
four_plan_rewrite_readiness.json
```

这一版继续往前推进一步：把 readiness 报告整理成 **HivmOpsEditor backend 可消费/可验收的 contract**。

注意：这里的 contract 不是新的 IR，也不会直接改 `.hivm.mlir`。它是 Python 策略搜索系统给 C++ HivmOpsEditor backend 的“施工单”。

最终链路变成：

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
  ↓
真实 HivmOpsEditor backend dry-run / mutate / verify
```

## 2. 新增文件

```text
strategy_search/backend_contract.py
```

负责生成 backend-facing contract。

```text
tools/build_four_plan_backend_contract.py
```

命令行入口，输入 HIVM IR 和 selected_plan，输出 backend contract 相关报告。

```text
tests/test_backend_contract.py
```

测试 contract 是否包含四个 Plan 的 action、backend requirements 和 acceptance 条件。

```text
artifacts/latest_backend_contract/
```

当前样例上的生成结果。

## 3. 现在生成哪些输出

运行：

```bash
python tools/build_four_plan_backend_contract.py \
  --ir sample_input/fa_best.hivm.mlir \
  --selected-plan artifacts/latest_smoke_run/selected_plan.json \
  --output-dir artifacts/latest_backend_contract
```

会生成：

```text
artifacts/latest_backend_contract/
  hivm_ir_inventory.official.json
  four_plan_rewrite_plan.json
  four_plan_rewrite_readiness.json
  four_plan_backend_contract.json
  sync_multibuffer_backend_contract.json
```

其中最重要的是：

```text
four_plan_backend_contract.json
```

它完整描述四个 Plan 的 backend work order。

```text
sync_multibuffer_backend_contract.json
```

它只保留第一阶段真正建议接 backend dry-run 的内容：SyncPlan + MultiBufferPlan。

## 4. 为什么先做 SyncPlan + MultiBufferPlan

四个 Plan 的真实 rewrite 难度不同：

```text
SyncPlan
  最容易先做，因为主要是同步事件检查、barrier/event cleanup、set/wait liveness。

MultiBufferPlan
  是 CVPipelinePlan 的前置条件，因为没有真实 buffer slot / ping-pong，pipeline overlap 很容易覆盖数据。

CVPipelinePlan
  依赖 SyncPlan 和 MultiBufferPlan，不能孤立真改。

TilingPlan
  最接近 compiler lowering，要改 loop/index/slice/tail mask，所以当前只做 report/hint。
```

所以当前第一阶段 backend contract 只建议推进：

```text
SyncPlan + MultiBufferPlan backend dry-run
```

## 5. 当前样例上的 contract 结果

基于 `sample_input/fa_best.hivm.mlir`，当前生成的第一阶段 backend milestone 是：

```text
SyncPlan + MultiBufferPlan dry-run contract
```

包含的 action 大致是：

```text
sync_002_existing_event_liveness_check
mb_001_clone_k_l1_ping
mb_002_clone_k_l1_pong
mb_003_clone_q_ub
mb_004_clone_p_ub
mb_005_clone_k_ub
mb_006_clone_v_ub
mb_007_clone_q_l1
mb_008_clone_v_l1
```

这说明当前样例里没有明显 `pipe_barrier/barrier_all` 可以直接替换，但存在已有 `set_flag/wait_flag`，所以 SyncPlan 第一阶段更适合做 event liveness/格式检查；MultiBufferPlan 则能找到多个可能的 local buffer clone candidate。

## 6. 四个 Plan 的 contract 语义

### 6.1 SyncPlan

生成的 backend action 类型包括：

```text
validate_existing_set_wait_events
sync_barrier_to_directional_event
```

当前样例里主要是：

```text
validate_existing_set_wait_events
```

原因是样例已经有：

```text
hivm.hir.wait_flag
hivm.hir.set_flag
```

但样例格式可能是 legacy/sample 形式，所以 Python 不主动生成新的 event op，而是要求 backend：

```text
parse_event_operands_or_legacy_attrs
normalize_to_official_event_model_without_text_rewrite
prove_event_live_ranges_do_not_conflict
```

### 6.2 MultiBufferPlan

生成的 backend action 类型是：

```text
clone_local_buffer_slots_and_replace_uses
```

每个 action 会指定：

```text
target_buffer
address_space
alloc_line
producer_ops
consumer_ops
requested_slots
replacement_policy
```

但 contract 明确要求：

```text
mutation_allowed_without_backend_proof = false
```

也就是说，Python 只负责指出“可能 clone 哪个 buffer”；真实 clone、use replacement、capacity/liveness 检查必须由 HivmOpsEditor/MLIR backend 完成。

### 6.3 CVPipelinePlan

生成的 backend action 类型是：

```text
cv_pipeline_stage_reorder
```

但当前模式是：

```text
contract_only_until_sync_and_multibuffer_pass
```

意思是：只有等 SyncPlan 和 MultiBufferPlan backend dry-run/verify 通过后，CVPipelinePlan 才能进入真实 stage reorder。

### 6.4 TilingPlan

生成的 backend action 类型是：

```text
tiling_hint_or_restricted_loop_tiling
```

当前模式是：

```text
hint_and_report_only_v1
```

因为真实 tiling 需要：

```text
loop split
index remap
load/store slice
Tail mask
capacity after tiling
```

这些不能由 Python 文本层硬改。

## 7. 什么时候需要用户运行 bash

当前还不需要。

现在本仓库内部已经能生成：

```text
four_plan_backend_contract.json
sync_multibuffer_backend_contract.json
```

等下一步需要验证真实 HivmOpsEditor API 时，才需要用户在真实 vTriton 环境里运行：

```bash
bash scripts/phase6e_build_hivm_operation_backend.sh \
  /path/to/vTriton \
  /path/to/vTriton/build
```

编译成功后再运行：

```bash
bash scripts/phase6f_accept_compiled_backend.sh \
  /path/to/vTriton/build/bin/hivm-operation-backend \
  sample_input/phase6_positive_fixtures/restricted_gm_roundtrip_positive.hivm.mlir \
  phase6f_backend_acceptance_out \
  /path/to/vTriton/build/bin/tritonsim-hivm
```

如果没有 `tritonsim-hivm`，最后一个参数可以先不传。

## 8. 当前明确禁止 claim什么

当前仍然明确禁止 claim：

```text
SyncPlan 已经真实 rewrite 成功
MultiBufferPlan 已经真实 clone buffer 成功
CVPipelinePlan 已经真实 overlap
TilingPlan 已经真实 loop tiling
性能已经真实提升
```

当前可以稳妥声称：

```text
已经把四个 Plan 的 selected strategy 翻译成了 backend-facing rewrite contract；
其中 SyncPlan 和 MultiBufferPlan 已经具备进入真实 HivmOpsEditor backend dry-run 的施工单；
CVPipelinePlan 和 TilingPlan 仍保持保守，分别处于依赖前置条件和 hint/report 阶段。
```
