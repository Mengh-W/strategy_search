# V4.10 CVPipelinePlan staged rewrite planner

## 目标

V4.10 开始推进 CVPipelinePlan rewrite 主线。由于 CVPipeline 涉及 operation reorder、stage overlap、loop prologue/steady/epilogue 和 SyncPlan/MultiBufferPlan 联动，本版本不直接移动 operation，而是先生成 staged rewrite planner。

核心目标是把 HIVM/NPU-IR 文本切分为：

- view / buffer-view stage；
- load / transfer stage；
- compute stage；
- store / fixpipe stage；
- sync stage；
- loop context。

然后寻找 `load -> compute -> store` 的候选 pipeline window，并输出 `cvpipeline_rewrite_plan.json`。

## 输出文件

默认输出目录：

```text
artifacts/v410_cvpipeline_stage_planner/
```

主要文件：

```text
cvpipeline_stage_report.json
cvpipeline_rewrite_plan.json
cvpipeline_stage_annotated_not_mutated.hivm.mlir
cvpipeline_annotation_report.json
cvpipeline_stage_planner_summary.json
```

## 当前边界

V4.10 只做 planner，不做 semantic mutation。

不做：

- 不移动 operation；
- 不 clone loop body；
- 不改 loop index；
- 不改 buffer use；
- 不删除或新增真实 sync op；
- 不宣称 production rewrite。

仍然输出：

```json
{
  "semantic_mutation_performed": false,
  "production_rewrite_claim_allowed": false
}
```

## 和 V4.9 的关系

V4.9 已经给出 MultiBufferPlan 的 producer-consumer stage-boundary scaffold。V4.10 在此基础上把更大范围的 HIVM operation 切成 pipeline stage，判断是否存在 CVPipelinePlan 可以利用的 `load / compute / store` 窗口。

后续如果具备真实 HivmOpsEditor / MLIR verifier 环境，V4.10 的 action 可以迁移为 Operation-level pass：

1. 定位 load/view/compute/store stage；
2. 结合 MultiBufferPlan 建立 ping-pong buffer；
3. 结合 SyncPlan 插入或复用 set_flag/wait_flag；
4. 生成 loop prologue / steady-state / epilogue；
5. exportToFile 并 verifier；
6. 用 DES/trace/msprof 验证。

## Windows CMD

```cmd
scripts\run_v410_cvpipeline_stage_planner.cmd
```

自定义参数：

```cmd
scripts\run_v410_cvpipeline_stage_planner.cmd ^
  sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir ^
  artifacts\latest_smoke_run\selected_plan.json ^
  artifacts\v410_cvpipeline_stage_planner ^
  50 ^
  20
```
