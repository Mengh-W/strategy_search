# V6.0 四 Plan Real Operation Materialization 说明

V6.0 的目标不是继续增加 readiness 或注释，而是把 V5.8/V5.9 中仍依赖 comment 表达的策略语义，进一步实体化到 HIVM operation 属性或 `annotation.mark` operation 上。

## 1. 相比 V5.9 推进点

V5.9 已经完成四 Plan semantic rewrite、M/N/K 常量修正、memref syntax hardening 和 event op normalization。V6.0 在此基础上新增：

```text
semantic binding comments
→ HIVM op attributes / annotation.mark operations
→ marker-as-logic audit
```

核心输出：

```text
optimized.four_plan_real_operation_materialized.hivm.mlir
v60_real_operation_materialization_report.json
v60_multibuffer_use_def_coverage.json
v60_semantic_marker_materialization_audit.json
```

## 2. 四个 Plan 的 V6.0 materialization

| Plan | V6.0 实体化内容 |
|---|---|
| TilingPlan | `tile_role`、`tile_offsets`、`tile_shape`、`tile_axes`、reduction accumulator semantics、tail/reduce/layout guard annotation |
| MultiBufferPlan | ping/pong slot use-def coverage report，检查每个 materialized buffer 是否有 ping/pong slot |
| CVPipelinePlan | `pipeline_stage_role`、`pipeline_schedule`、`pipeline_region`、`producer_consumer_distance`、`tile_index_expr`、`pipeline_template`、`pipeline_stage_num`、`stage_buffer_policy` |
| SyncPlan | `wait_flag/set_flag` 上标注 `v60_sync_dependency_regenerated` 与 schedule graph dependency scope |

## 3. 新增审计标准

V6.0 新增：

```json
{
  "semantic_marker_as_logic_count": 0,
  "passed_v60_marker_materialization_audit": true
}
```

这表示 `HIVM V5.8 tile-slice binding`、`HIVM V5.8 reduction binding`、`HIVM V5.8 CVPipeline stage binding`、`HIVM V5.6 TilingPlan tail/reduction/layout guard` 等旧 comment 不再承担核心语义。

## 4. 运行方式

```bash
bash scripts/run_v60_four_plan_real_operation_materialization.sh \
  sample_input/fa_best.hivm.mlir \
  artifacts/latest_smoke_run/selected_plan.json \
  artifacts/v60_four_plan_real_operation_materialization
```

## 5. 诚实边界

V6.0 仍然不能声称已经 Linux 可编译、可运行或能证明 msprof 性能提升。它只是比 V5.9 更接近真实 backend handoff：核心策略语义已经不再只存在于注释里，而是落到 op 属性/annotation 上。最终仍必须在 Ascend Linux backend 中完成 parse、roundtrip、verifier、compile、correctness 和 msprof 验证。
