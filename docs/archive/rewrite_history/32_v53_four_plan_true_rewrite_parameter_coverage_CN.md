# V5.3 四 Plan 统一 portable/restricted rewrite 与参数覆盖

## 目标

V5.3 解决两个问题：

1. 四个 Plan 不再分别跑，而是串成统一 portable/restricted rewrite pipeline；
2. 检查 `selected_plan.json` 里每一个 controllable knob 是否能回写到最终 optimized HIVM IR。

## 执行顺序

```text
TilingPlan metadata rewrite
  -> MultiBufferPlan ping/pong portable/restricted rewrite
  -> CVPipelinePlan restricted sync/stage portable/restricted rewrite
  -> SyncPlan audited portable rewrite cleanup
  -> selected parameter metadata coverage block
```

最终输出：

```text
optimized.four_plan_true_rewritten.hivm.mlir
four_plan_true_rewrite_summary.json
parameter_rewrite_coverage.json
parameter_rewrite_coverage_summary.json
```

## 参数覆盖的定义

V5.3 区分两类覆盖：

| 类型 | 含义 |
|---|---|
| `RESTRICTED_STRUCTURAL_REWRITE` | 参数驱动了 visible restricted IR mutation，例如 sync event、ping/pong slot、pipeline sync、tiling metadata constant |
| `TRACE_METADATA_REWRITE` | 参数被回写进最终 IR metadata block，具备可追踪性，但尚未完整 lowering 成 operation/loop mutation |

因此 V5.3 的结论是：

```text
每一个 controllable knob 都已经能回写到最终 optimized IR；
但不是每一个 knob 都已经具备完整 operation-level semantic lowering。
```

## 为什么需要 metadata coverage block

一些参数本质是策略参数，例如：

```text
layout_aware_tile
auto_cv_balance
remove_redundant_sync
event_reuse
buffer_multiplier_domain
```

它们不一定对应一条简单的 HIVM op 修改。为了避免这些参数“只影响 cost model、不落到 IR”，V5.3 会在最终 IR 中插入：

```mlir
// HIVM V5.3 Four-Plan selected-parameter rewrite metadata begin
// hivm.param plan=tiling_plan key=tile_m level=RESTRICTED_STRUCTURAL_REWRITE ...
// hivm.param plan=cv_pipeline_plan key=auto_cv_balance level=TRACE_METADATA_REWRITE ...
// HIVM V5.3 Four-Plan selected-parameter rewrite metadata end
```

这样每个参数都有明确回写痕迹。

## 边界

V5.3 可以说：

```text
四个 Plan 已形成 portable/restricted rewrite pipeline；
所有 controllable knobs 均能回写到 optimized HIVM IR；
部分参数具备语义级 restricted rewrite，部分参数是 metadata-level rewrite。
```

不能说：

```text
所有参数都已经完成 production operation-level lowering。
```

原因仍然是缺真实 HivmOpsEditor verifier、DES/trace 和 msprof 验证。
