# V4.0：真实 backend dry-run 解析与 guarded mutation 选择

本阶段不是直接扩大 rewrite 范围，而是补上真实 backend dry-run 之后最关键的一步：**判断哪些 action 真的可以进入单步 mutation**。

## 1. 为什么需要这一层

V4.0 前面已经能生成：

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
backend dry-run
```

但 dry-run 只是后端输出的一份结果。它还需要被解析：

```text
这个 action 后端找到了吗？
use-def 证明了吗？
capacity recheck 过了吗？
buffer liveness 过了吗？
有没有 blockers？
是不是 fake backend？
是不是只能 verify，不能 mutate？
```

所以本阶段新增了：

```text
backend_dryrun_analysis.json
guarded_mutation_selection.json
single_guarded_action_contract.json
```

它们的作用是把 dry-run 结果转换成非常保守的 mutation 决策。

## 2. 新增模块

```text
strategy_search/backend_dryrun_analyzer.py
tools/analyze_backend_dryrun.py
scripts/run_v4_real_backend_mutate_selected_guarded.sh
scripts/run_v4_fake_backend_smoke.sh              # 已更新：自动生成 dry-run analysis
scripts/run_v4_real_backend_dryrun.sh             # 已更新：自动生成 dry-run analysis
```

## 3. 决策规则

### fake backend 永远不能 mutation

如果：

```json
"is_real_mlir_backend": false
```

则所有 action 都会被判定为：

```text
BLOCKED_FAKE_BACKEND
```

这保证 fake backend 只能用于流程测试，不能被误认为生产 rewrite 证据。

### SyncPlan 第一阶段只做 verify/check

对于已有 `set_flag / wait_flag` 的样例，第一阶段 SyncPlan action 通常是：

```text
validate_existing_set_wait_events
```

它不是 mutation，而是检查已有 event 是否能被后端解析和证明 live range 不冲突。因此会被标记为：

```text
VERIFY_ONLY_NOT_MUTATION
```

### MultiBufferPlan 是第一批 guarded mutation 候选

第一批可尝试的真实 mutation 只允许：

```text
MultiBufferPlan 单个 buffer clone action
```

并且必须由真实 backend dry-run 明确证明：

```text
operation_found
located
use_def_resolution_ok
all_uses_accounted_for
capacity_recheck_passed
buffer_liveness_passed
post_mutate_verify_expected
```

缺任何一个证明，都会被拦住。

## 4. 输出文件怎么看

### backend_dryrun_analysis.json

这是逐 action 分析。重点字段：

```text
decision
missing_proofs
failed_proofs
blockers
static_complexity
```

典型 decision：

```text
BLOCKED_FAKE_BACKEND
BLOCKED_DRY_RUN_PROOF_INCOMPLETE
VERIFY_ONLY_NOT_MUTATION
ELIGIBLE_FOR_SINGLE_ACTION_GUARDED_MUTATION
DRY_RUN_PASSED_BUT_DEFER_COMPLEX_ACTION
```

### guarded_mutation_selection.json

这是最终是否选择一个 guarded mutation action 的报告。

如果：

```json
"selected": false
```

说明当前还不能进入 mutation。

如果：

```json
"selected": true
```

则会同时生成：

```text
single_guarded_action_contract.json
```

这个文件只包含一个 action，后续 mutation 只能基于它执行。

## 5. 当前你以后需要跑的顺序

真实 backend 编译出来后，先跑：

```bash
bash scripts/run_v4_real_backend_dryrun.sh \
  /path/to/vTriton/build/bin/hivm-operation-backend \
  sample_input/fa_best.hivm.mlir \
  artifacts/latest_smoke_run/selected_plan.json \
  artifacts/v4_real_backend_dryrun
```

它会自动生成：

```text
artifacts/v4_real_backend_dryrun/backend_dryrun_analysis/
  backend_dryrun_analysis.json
  guarded_mutation_selection.json
  single_guarded_action_contract.json   # 只有 selected=true 时才有
```

如果 `guarded_mutation_selection.json` 里 `selected=true`，再考虑跑：

```bash
HIVM_ALLOW_GUARDED_MUTATION=1 \
bash scripts/run_v4_real_backend_mutate_selected_guarded.sh \
  /path/to/vTriton/build/bin/hivm-operation-backend \
  sample_input/fa_best.hivm.mlir \
  artifacts/v4_real_backend_dryrun/backend_dryrun_analysis \
  artifacts/v4_real_backend_guarded_mutation
```

这个脚本一次只会 mutate 一个 action。

## 6. 当前仍然不能 claim 什么

即使 single guarded mutation 通过，也还不能直接说四个 Plan 全部真实 rewrite 完成。

必须继续做：

```text
post-mutate verify
DES / trace 对比
必要时 msprof 真机性能验证
```

V4.0 当前最稳的表述是：

```text
系统已经能把四个 Plan 的 selected strategy 转换成官方 HIVM op 驱动的 rewrite plan、readiness report、backend contract，并能解析真实 backend dry-run 结果，保守选择单 action guarded mutation 候选。
```
