# V4.0 SyncPlan 精确 Dry-run Contract 设计说明

## 1. 为什么继续推进 SyncPlan

基于 vTriton lite 源码分析，`HivmOpsEditor` 已经提供了较完整的同步相关 API，例如：

```text
addSetFlagBefore / addSetFlagAfter
addWaitFlagBefore / addWaitFlagAfter
addPipeBarrierBefore / addPipeBarrierAfter
addSyncBlockSetBefore / addSyncBlockWaitBefore
changePipeAttr / changeEventAttr / setEventId
```

因此四个 Plan 里，`SyncPlan` 是最适合最先接真实 HivmOpsEditor backend 的方向。

但同步 rewrite 不能只靠一句：

```text
barrier -> set_flag / wait_flag
```

真实后端必须知道：

```text
改哪个 barrier？
插在 before 还是 after？
set_pipe / wait_pipe 是什么？
event id 是新分配还是复用？
producer / consumer 是谁？
会不会 wait-before-set？
会不会 event live range 冲突？
会不会死锁？
```

所以 V4.0 新增了 `SyncPlan 精确 dry-run contract`，把粗粒度 sync readiness 变成 backend 可以检查的 action 列表。

---

## 2. 新增模块

```text
strategy_search/sync_contract_precision.py
tools/build_sync_precision_contract.py
tests/test_sync_contract_precision.py
docs/archive/rewrite_history/17_syncplan_precision_contract_CN.md
```

输出文件：

```text
sync_precision_contract.json
sync_precision_contract_summary.json
```

---

## 3. 它做什么

新模块会从 HIVM inventory 中识别三类 sync anchor：

### 3.1 已有 set_flag / wait_flag

用于生成：

```text
validate_existing_event_pair_liveness
```

这类 action 第一阶段只做检查，不做 mutation。

需要 backend 证明：

```text
event operands 能被真实 parser 解析；
set/wait pair 能匹配；
event live range 没有冲突；
不存在 wait-before-set 死锁风险。
```

### 3.2 pipe_barrier / legacy barrier

用于生成：

```text
barrier_to_directional_event_pair
```

这类 action 是未来最可能进入真实 SyncPlan rewrite 的候选，但当前仍然只是 dry-run。

需要 backend 证明：

```text
target barrier 能定位；
producer-consumer pair 能证明；
barrier 没有其他必须保留的依赖；
event id 能安全分配或复用；
backend 能用官方 printer 生成 set_flag / wait_flag；
roundtrip / verify 通过。
```

### 3.3 sync_block_wait / sync_block_set

用于生成：

```text
classify_sync_block_scope
```

这类 action 当前只分类，不 mutation。因为 sync_block 涉及参与者、作用域和死锁风险，比普通 set/wait 更复杂。

---

## 4. 为什么这不是新的 IR

`sync_precision_contract.json` 不是新的中间 IR，也不会替代 HivmOpsEditor。

它只是给后端的一份更精确施工单：

```text
selected_plan.json：高层策略
hivm_ir_inventory.official.json：当前 IR 里有什么
sync_precision_contract.json：SyncPlan 具体要检查/尝试哪些 action
HivmOpsEditor：真正做 Operation-level mutation
```

Python 层仍然禁止：

```text
直接打印新的 set_flag / wait_flag MLIR；
直接删除 barrier；
直接修改 event id；
绕过 verifier claim 真实 rewrite 成功。
```

---

## 5. 如何运行

```bash
python tools/build_sync_precision_contract.py \
  --ir sample_input/fa_best.hivm.mlir \
  --selected-plan artifacts/latest_smoke_run/selected_plan.json \
  --output-dir artifacts/latest_sync_precision_contract
```

Windows CMD：

```cmd
python tools\build_sync_precision_contract.py ^
  --ir sample_input\fa_best.hivm.mlir ^
  --selected-plan artifacts\latest_smoke_run\selected_plan.json ^
  --output-dir artifacts\latest_sync_precision_contract
```

输出：

```text
artifacts/latest_sync_precision_contract/
  hivm_ir_inventory.official.json
  four_plan_rewrite_plan.json
  sync_precision_contract.json
  sync_precision_contract_summary.json
```

---

## 6. 当前边界

当前版本仍然不做真实 mutation。

它的目标是把 SyncPlan 从：

```text
发现 sync op
```

推进到：

```text
生成精确的 backend dry-run/check action
```

下一步需要把 `sync_precision_contract.json` 接入真实 `hivm-operation-backend --dry-run`，让 C++ backend 基于 HivmOpsEditor 实际验证：

```text
是否能定位 action target；
是否能解析 event / pipe；
是否能构造官方 set_flag / wait_flag；
是否能 roundtrip / verify。
```
