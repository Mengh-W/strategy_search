# 技术报告二：HIVM 四参数 Plan Rewrite 与 Backend Contract 系统报告

版本：`V5.3.1-backend-contract-ready-prelinux-lf-hygiene`  
适用代码仓：`vTRiton_search / HIVM_strategy_search_demo`  
报告主题：四参数 Plan 如何回写到 HIVM artifact，backend contract 如何承接真实后端，以及 Linux 真实验证前后的边界。

---

## 1. Rewrite 系统目标

Rewrite 系统的目标是将寻优阶段输出的 `selected_plan.json` 落回到 HIVM / NPU-IR MLIR 文件中，生成 optimized artifact，并进一步生成真实 backend 可消费的 contract。

当前链路：

```text
input HIVM MLIR
  -> selected_plan.json
  -> TilingPlan trace metadata rewrite
  -> MultiBufferPlan restricted structural rewrite
  -> CVPipelinePlan restricted structural rewrite
  -> SyncPlan restricted structural rewrite / safety audit
  -> selected parameter metadata coverage block
  -> optimized.four_plan_true_rewritten.hivm.mlir
  -> four_plan_backend_contract.json
  -> fake backend contract execution
  -> Linux real backend handoff
```

当前输出包括：

```text
optimized.four_plan_true_rewritten.hivm.mlir
four_plan_true_rewrite_summary.json
parameter_rewrite_coverage.json
parameter_rewrite_coverage_summary.json
four_plan_backend_contract.json
backend_contract_execution_summary.json
```

---

## 2. Rewrite 分层定义

为了避免把 planner/report 误称为 production rewrite，当前项目统一使用三层口径：

```text
TRACE_METADATA_REWRITE
  参数写入 metadata / annotation，用于 provenance、trace、回放和后续 lowering。

RESTRICTED_STRUCTURAL_REWRITE
  在 portable/text-level 层面对 IR 做可见结构变化，例如 event pair、ping/pong slot、pipeline marker。
  这仍不是 production operation mutation。

PRODUCTION_OPERATION_REWRITE
  通过真实 HivmOpsEditor / MLIR operation-level mutation，且通过 parser/verifier/DES/trace/compile/msprof。
  当前尚未完成。
```

当前 V5.3.1 的真实状态：

```text
四个 Plan 都能把 selected_plan 参数追踪并写回最终 artifact；
部分参数能驱动 restricted structural mutation；
backend contract 和 fake backend 验收链路已经跑通；
真实 production operation rewrite 仍等待 Linux/vTriton/BiShengIR 环境验证。
```

---

## 3. 官方 HIVM 同步语法对齐

当前项目不再生成未定义 SSA 风格 event 占位符，例如：

```mlir
%hivm_sync_auto0
```

而使用更接近 HIVM bracket-style 的 event 写法：

```mlir
hivm.hir.pipe_barrier[<PIPE_V>]
hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_V>, EVENT_ID_AUTO0]
hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_V>, EVENT_ID_AUTO0]
```

这降低了文本语法风险，但不能替代真实 BiShengIR parser / MLIR verifier。

---

## 4. SyncPlan Rewrite

### 4.1 目标

SyncPlan 希望将粗粒度 barrier 转化为更细粒度的 event pair，同步 producer/consumer 顺序，并降低不必要的全局等待。

### 4.2 当前支持

当前支持：

```text
识别 pipe_barrier / set_flag / wait_flag；
为安全 candidate 生成 set_flag/wait_flag event pair；
生成 before/after liveness report；
生成 safety audit；
blocked action 不会被执行；
strict e2e 中 blocked action 会诚实导致失败。
```

### 4.3 当前不做

```text
不删除已有 set_flag/wait_flag；
不做高风险 PIPE_ALL 细化；
不执行 event reuse；
不执行 sync motion；
不删除 redundant sync；
不声称 event liveness 已由真实 verifier 证明。
```

---

## 5. MultiBufferPlan Rewrite

### 5.1 目标

MultiBufferPlan 的目标是从单 buffer 使用模式推进到 ping/pong buffer 结构，为后续 pipeline overlap 提供存储基础。

### 5.2 当前支持

当前支持：

```text
识别 READY_FOR_PINGPONG_PLAN 的 buffer candidate；
插入 ping/pong slot；
对局部 producer/consumer use 做有限替换；
保留原 buffer 作为 fallback；
生成 backend contract action。
```

### 5.3 当前不做

```text
不证明完整 alias analysis；
不证明跨 iteration i % 2 parity；
不证明完整 producer/consumer lifetime；
不证明真实 UB/L1 capacity allocation；
不做 HivmOpsEditor operation-level use replacement。
```

---

## 6. CVPipelinePlan Rewrite

### 6.1 目标

CVPipelinePlan 希望把 load、compute、store stage 组织成可 overlap 的 pipeline。

### 6.2 当前支持

当前支持：

```text
识别 load/view -> compute -> store window；
插入 load->compute event pair；
插入 compute->store event pair；
插入 pipeline group marker；
生成 pipeline intent 和 coverage report。
```

### 6.3 当前不做

```text
不移动真实 compute/load/store op；
不做 loop skew；
不生成 prologue/steady-state/epilogue；
不证明 pipeline overlap 在 DES/trace 或 msprof 中真实出现。
```

---

## 7. TilingPlan Rewrite

### 7.1 目标

TilingPlan 希望将 tile shape、tail policy、loop order 等参数落到 IR。

### 7.2 当前支持

当前支持：

```text
插入 tile_m/tile_n/tile_k metadata constant；
插入 annotation / provenance block；
记录 loop order、tail strategy、reduce tile policy 等参数。
```

### 7.3 当前不做

```text
不修改 loop bound；
不修改 index expression；
不修改 memref shape；
不生成 tail mask；
不拆分 reduce loop；
不声称完成真实 tiling lowering。
```

因此 TilingPlan 当前主要是 `TRACE_METADATA_REWRITE`。

---

## 8. Backend Contract

### 8.1 定义

backend contract 是 Python 侧交给真实 HivmOpsEditor/vTriton backend 的“施工单”。它不是新的 IR，也不是性能证据。

它描述：

```text
要定位哪些 op；
要检查哪些 insertion point；
哪些 action 只能 dry-run；
哪些 action 可以 guarded mutate；
需要输出哪些 report；
哪些条件满足后才允许 production claim。
```

### 8.2 当前 contract 链路

```text
selected_plan.json
  -> hivm_ir_inventory
  -> four_plan_rewrite_plan
  -> four_plan_rewrite_readiness
  -> four_plan_backend_contract.json
  -> execute_backend_contract.py
  -> fake_hivm_operation_backend.py
  -> backend_contract_execution_summary.json
```

### 8.3 fake backend 的作用

fake backend 可以验证：

```text
CLI 参数是否正确；
capability probe 是否通；
inventory / roundtrip / verify-only / dry-run / mutate report 是否能生成；
contract runner 是否能收集 summary；
测试 harness 是否能区分 fake 和 real backend。
```

fake backend 不能证明：

```text
HIVM 真实语法合法；
MLIR verifier 真实通过；
HivmOpsEditor operation mutation 正确；
DES/trace 无死锁；
msprof 真机提速。
```

---

## 9. Honest e2e 语义

当前 `tools/run_search_and_four_plan_rewrite.py` 采用严格通过条件：

```text
search_returncode == 0
rewrite_returncode == 0
rewrite_summary_loaded == true
all_portable_validations_passed == true
```

只有全部满足，才会：

```text
end_to_end_passed = true
```

特别注意：

```text
selected_plan_bound_to_same_input = true
```

只说明没有用旧 plan，不等于 rewrite 成功。

如果 SyncPlan 出现 blocked action，或者 rewrite 子进程返回非 0，wrapper 会诚实返回失败。这个设计是刻意的，目的是避免把 partial success 包装成 complete success。

---

## 10. Linux 环境前已完成事项

当前版本已经完成：

```text
1. Python 寻优主链路。
2. selected_plan 与当前输入 IR 强绑定。
3. portable/restricted rewrite artifact 生成。
4. honest e2e 返回语义。
5. backend contract 生成。
6. fake backend capability / inventory / roundtrip / verify-only / dry-run / guarded mutation。
7. phase5/phase6 fake acceptance harness。
8. pre-Linux CI 脚本。
9. 发布包清理脚本。
10. README 与核心 docs 口径重写。
```

本地验收命令：

```bash
bash scripts/run_v531_fast_ci.sh
bash scripts/run_phase5b_roundtrip_ci.sh
bash scripts/run_backend_fake_ci.sh
bash scripts/run_phase6_positive_ci.sh
```

---

## 11. Linux 环境后需要完成的真实验证

下一阶段必须在 Linux + vTriton / BiShengIR / CANN 环境中完成：

```text
BiShengIR parser
  官方工具能否读入 optimized HIVM。

MLIR verifier
  IR 内部 SSA、type、operand、region、dialect legality 是否通过。

HivmOpsEditor roundtrip
  是否能用真实 operation-level API 读入、修改、导出、再读入。

vTriton DES / trace
  是否存在 producer-consumer 顺序错误、死锁、异常 stall；pipeline overlap 是否真实出现。

CANN compile/runtime
  是否能进入真实编译运行链路。

msprof 真机 profile
  baseline 与 optimized 是否结果正确、性能稳定、确实加速。

cost model 校准
  用 DES/msprof 反校准 load/compute/store/sync/overlap/penalty 参数。
```

---

## 12. 当前对外汇报口径

可以说：

```text
当前项目已经从 portable rewrite prototype 推进到 backend-contract-ready prototype；
本地 fake backend 验收链路已经跑通；
现在已经具备交给 Linux/vTriton/BiShengIR 环境做真实验证的条件。
```

不能说：

```text
当前已经完成真实 production operation rewrite；
当前已经通过真实 BiShengIR / MLIR verifier；
当前已经通过 vTriton DES/trace；
当前已经通过 msprof 证明性能提升。
```
