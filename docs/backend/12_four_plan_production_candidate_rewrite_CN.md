# V5.5 四 Plan production-candidate rewrite 说明

本版本新增 `tools/run_four_plan_production_candidate_rewrite.py`，目标是把寻优后的四个参数 Plan 都串到同一个真实输出文件：

```text
input.hivm.mlir + selected_plan.json
→ optimized.four_plan_production_candidate.hivm.mlir
```

## 重要边界

本版本已经要求四个 Plan 都产生可见的 IR mutation：

1. **TilingPlan**：执行 local memref shape / operation type rewrite candidate。
2. **MultiBufferPlan**：执行 additive ping-pong buffer rewrite。
3. **CVPipelinePlan**：插入 pipeline sync edge，并做可见 slot binding。
4. **SyncPlan**：将已有 `set_flag/wait_flag {pipe=..., event=...}` 归一化成 bracket-style event operation。

但是这仍然不是最终生产声明。原因是 Linux 真机性能验证必须先通过：

```text
MLIR/HIVM parse
HivmOpsEditor roundtrip
MLIR verifier
backend compile
functional correctness check
msprof baseline/optimized 对比
```

因此本版本的 final summary 中仍然保留：

```json
"production_rewrite_claim_allowed": false,
"linux_msprof_ready": false
```

意思不是没有 rewrite，而是还没有经过真实 Linux backend 验证，不能把 msprof 性能提升说成已经成立。

## 运行方式

```bash
bash scripts/run_v55_four_plan_production_candidate_rewrite.sh \
  sample_input/fa_best.hivm.mlir \
  artifacts/latest_smoke_run/selected_plan.json \
  artifacts/v55_four_plan_production_candidate_rewrite
```

或直接运行：

```bash
python tools/run_four_plan_production_candidate_rewrite.py \
  --ir sample_input/fa_best.hivm.mlir \
  --selected-plan artifacts/latest_smoke_run/selected_plan.json \
  --output-dir artifacts/v55_four_plan_production_candidate_rewrite
```

## 样例结果

当前样例运行结果：

```json
{
  "stage_mutation": {
    "tiling": true,
    "multibuffer": true,
    "cvpipeline": true,
    "sync": true
  },
  "four_plan_operation_mutation_performed": true,
  "all_portable_validations_passed": true,
  "all_controllable_parameters_rewritten_back_to_ir": true,
  "linux_msprof_ready": false
}
```

输出主文件：

```text
artifacts/v55_four_plan_production_candidate_rewrite/optimized.four_plan_production_candidate.hivm.mlir
```

## 各 Plan 的 rewrite 内容

### TilingPlan

新增模块：

```text
strategy_search/tiling_operation_true_rewrite_v55.py
```

它不再只插入 metadata，而是会根据 `tile_m/tile_n/tile_k` 对常见 local buffer 的 memref shape 和 operation type signature 做可见 mutation。示例：

```text
q_ub/q_l1/acc_ub: tile_m x tile_k
s_ub/p_ub/s_l0c: tile_m x tile_n
k_ub/v_ub/k_l1/v_l1: tile_n x tile_k
m_ub/l_ub: tile_m x 1
```

该阶段本质上是 operation/type-shape candidate rewrite。loop split、index remap、tail mask 和 reduction legality 仍必须由 Linux backend 验证。

### MultiBufferPlan

沿用已有：

```text
strategy_search/multibuffer_true_rewrite.py
```

执行 additive ping/pong slot clone，并对选中的 producer/consumer pair 做 use replacement。

### CVPipelinePlan

沿用已有：

```text
strategy_search/cvpipeline_true_rewrite.py
```

插入 pipeline group marker、load-to-compute / compute-to-store event edge，并在已有 MultiBuffer slot 上做可见 slot binding。

### SyncPlan

新增模块：

```text
strategy_search/sync_event_true_rewrite_v55.py
```

当没有 barrier candidate 时，它也会对已有 `set_flag/wait_flag` 执行 visible operation normalization，使 SyncPlan 在四 Plan pipeline 中确实产生 mutation。

## Linux 真机验证建议

在 Ascend Linux 环境中，建议按顺序验证：

```text
1. 原始 HIVM parse / compile / msprof
2. optimized.four_plan_production_candidate.hivm.mlir parse
3. HivmOpsEditor roundtrip
4. MLIR verifier
5. backend compile
6. functional correctness check
7. msprof repeated runs
8. median latency/cycles 对比
```

只有这些通过之后，才能把本版本的 production candidate 称为真机可验证优化。
