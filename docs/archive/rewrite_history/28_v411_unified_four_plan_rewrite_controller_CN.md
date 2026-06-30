# V4.11 Unified Four-Plan Rewrite Controller

版本：`V4.11-unified-four-plan-rewrite-controller`

## 1. 目标

V4.11 的目标是把之前分散推进的几个 rewrite 模块串成一个统一入口：

1. `SyncPlan`：已具备 audited portable/text-level rewrite；
2. `MultiBufferPlan`：已具备 buffer-like anchor readiness 和 stage-boundary plan；
3. `CVPipelinePlan`：已具备 staged rewrite planner；
4. `TilingPlan`：新增 conservative feasibility scan。

这版不是宣称四个 plan 都能 production mutation，而是建立统一控制器，明确每个 plan 当前处在哪个 rewrite 层级、输出哪些 artifact、哪些 action 可以迁移到真实 `HivmOpsEditor`。

## 2. 为什么需要 controller

之前每个 plan 各自有工具：

- `run_sync_full_rewrite.py`
- `run_multibuffer_rewrite_readiness.py`
- `run_multibuffer_stage_boundary.py`
- `run_cvpipeline_stage_planner.py`

这些工具能单独跑，但项目汇报和后续工程落地需要一个统一视角：

```text
input HIVM
  -> SyncPlan audited rewrite
  -> MultiBufferPlan readiness
  -> MultiBufferPlan stage-boundary
  -> CVPipelinePlan staged planner
  -> TilingPlan feasibility
  -> unified controller report
```

V4.11 新增的统一报告可以回答：

- 当前哪些 plan 已经能 rewrite？
- 哪些 plan 只是 planner/readiness？
- 每个 plan 的 blocker 是什么？
- 后续接真实 HivmOpsEditor 时应该按什么顺序迁移？

## 3. 新增文件

```text
strategy_search/four_plan_rewrite_controller.py
tools/run_four_plan_rewrite_controller.py
scripts/run_v411_four_plan_rewrite_controller.cmd
scripts/run_v411_four_plan_rewrite_controller.sh
tests/test_v411_four_plan_rewrite_controller.py
docs/archive/rewrite_history/28_v411_unified_four_plan_rewrite_controller_CN.md
```

## 4. Controller 执行顺序

### 4.1 SyncPlan

执行 audited portable rewrite：

```text
pipe_barrier -> set_flag + wait_flag
```

并输出：

```text
optimized.sync_controller_rewritten.hivm.mlir
sync_controller_rewrite_report.json
sync_controller_rewrite_validation.json
sync_controller_rewrite_diff.json
sync_rewrite_safety_audit.json
```

这是当前唯一执行了语义级 portable rewrite 的 plan。

### 4.2 MultiBufferPlan readiness

识别：

```text
pointer_cast
memref.subview
memref.reinterpret_cast
memref.cast
memref.alloc
```

并输出 buffer-like anchor readiness 和 mutation plan scaffold。

### 4.3 MultiBufferPlan stage-boundary

进一步识别：

```text
producer
consumer
sync context
loop context
```

输出 ping-pong double-buffer plan scaffold。

### 4.4 CVPipelinePlan stage planner

识别：

```text
load/view segment
compute segment
store/fixpipe segment
sync segment
loop context
```

输出 CVPipeline staged rewrite plan。

### 4.5 TilingPlan feasibility

新增 conservative scan，检查：

```text
selected_plan 中是否有 tile_m / tile_n / tile_k 等 tiling knobs；
IR 中是否有 scf.for / affine.for loop anchor；
IR 中是否有 compute / memory anchor；
```

注意：TilingPlan 不执行 mutation。它只输出：

```text
tiling_rewrite_feasibility.json
```

## 5. 输出文件

默认目录：

```text
artifacts/v411_four_plan_rewrite_controller/
```

核心文件：

```text
four_plan_rewrite_controller_report.json
four_plan_rewrite_controller_summary.json
```

分阶段文件在：

```text
stages/01_syncplan/
stages/02_multibuffer_readiness/
stages/03_multibuffer_stage_boundary/
stages/04_cvpipeline_stage_planner/
stages/05_tiling_feasibility/
```

## 6. smoke 结果

在 `chunk_kda_kernel_clean.npuir.mlir` 上运行：

```json
{
  "overall_decision": "PORTABLE_SYNC_REWRITE_PLUS_MULTI_PLAN_SCAFFOLD_READY",
  "sync_rewritten_action_count": 74,
  "sync_portable_rewrite_passed": true,
  "multibuffer_ready_count": 20,
  "cvpipeline_window_count": 50,
  "cvpipeline_ready_count": 36,
  "tiling_readiness": "READY_FOR_TILING_PLAN_SCAFFOLD",
  "hivmopseditor_migration_queue_count": 4,
  "semantic_mutation_count": 1,
  "planned_only_count": 4,
  "production_rewrite_claim_allowed": false
}
```

解释：

- `semantic_mutation_count = 1`：只有 SyncPlan 执行了 portable semantic rewrite；
- `planned_only_count = 4`：MultiBuffer readiness、MultiBuffer stage-boundary、CVPipeline、Tiling 都是 planner/scaffold；
- `production_rewrite_claim_allowed = false`：没有真实 HivmOpsEditor verifier/DES/msprof，不能 claim production rewrite。

## 7. Windows CMD 运行方式

```cmd
cd /d D:\hivm\HIVM_strategy_search_demo_V4.11
scripts\run_v411_four_plan_rewrite_controller.cmd
```

指定参数：

```cmd
scripts\run_v411_four_plan_rewrite_controller.cmd ^
  sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir ^
  artifacts\latest_smoke_run\selected_plan.json ^
  artifacts\v411_four_plan_rewrite_controller ^
  999999 ^
  80 ^
  50 ^
  20
```

参数含义：

```text
999999 = max sync rewrite actions
80     = max multibuffer candidates
50     = max cvpipeline windows
20     = max annotations
```

## 8. 当前边界

V4.11 可以说：

```text
已经建立四个 plan 的统一 rewrite controller；
SyncPlan 已经具备 audited portable rewrite；
MultiBufferPlan、CVPipelinePlan、TilingPlan 已经进入统一 planner/scaffold 管线；
所有输出都汇总到统一 controller report。
```

不能说：

```text
四个 plan 都已完成真实 production rewrite。
```

真实 production rewrite 仍然需要：

```text
HivmOpsEditor 编译运行；
MLIR verifier；
DES/trace；
msprof 真机 profile；
```

## 9. 下一步

建议下一步进入：

```text
V4.12：Four-Plan rewrite controller dashboard / acceptance report
```

目标是把 controller 输出整理成更适合汇报和验收的 HTML/Markdown 报告：

- 每个 plan 的状态；
- 每个 plan 的关键 artifact；
- 当前已 rewrite 的内容；
- planner-only 的原因；
- 后续接 HivmOpsEditor 的迁移顺序。
