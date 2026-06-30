# V4.12 Controller Acceptance Report

版本：`V4.12-controller-acceptance-report`

## 1. 目标

V4.11 已经把 SyncPlan、MultiBufferPlan、CVPipelinePlan 和 TilingPlan 串成统一 controller。V4.12 在这个基础上新增验收报告层，把大量 JSON 输出整理成适合汇报、审计和交付的 Markdown/HTML 报告。

这版不新增新的语义 rewrite。它解决的是另一个问题：现在项目已经有很多中间 artifact，但人看起来费劲。V4.12 会明确回答：

- 哪些阶段真的执行了 rewrite；
- 哪些阶段只是 planner/scaffold；
- 哪些验收项通过；
- 哪些结论不能过度 claim；
- 后续 HivmOpsEditor migration 队列是什么。

## 2. 新增输出

默认输出目录：

```text
artifacts/v412_controller_acceptance_report/
```

核心输出：

```text
controller_run/four_plan_rewrite_controller_report.json
controller_run/four_plan_rewrite_controller_summary.json
acceptance_report/controller_acceptance_model.json
acceptance_report/controller_acceptance_report.md
acceptance_report/controller_acceptance_report.html
acceptance_report/controller_acceptance_summary.json
```

## 3. 验收口径

V4.12 的验收口径是：

```text
可以验收为 portable/controller demo；不能宣称 production-level HivmOpsEditor rewrite 已完成。
```

原因是当前没有真实 BiShengIR/vTriton/HivmOpsEditor 编译环境，也没有 MLIR verifier、DES/trace 和 msprof 真机结果。

## 4. Windows CMD

```cmd
scripts\run_v412_controller_acceptance_report.cmd
```

指定参数：

```cmd
scripts\run_v412_controller_acceptance_report.cmd ^
  sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir ^
  artifacts\latest_smoke_run\selected_plan.json ^
  artifacts\v412_controller_acceptance_report ^
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

## 5. 当前能力边界

- SyncPlan：已经执行 audited portable rewrite。
- MultiBufferPlan：readiness + stage-boundary scaffold。
- CVPipelinePlan：staged rewrite planner。
- TilingPlan：feasibility scan。
- Production rewrite：仍需真实 HivmOpsEditor/MLIR verifier/DES/msprof。
