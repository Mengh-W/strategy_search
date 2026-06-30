# E2E + Prefill-A5 合并校准配置说明

## 1. 目的

本次新增一个合并配置：

```text
configs/cost_model_e2e_prefill_merged.json
```

它把两类校准证据放进同一个 cost model config：

1. **E2E component-prior 校准**：来自 `split_qkv` 和 `chunk_kda` 两个真实 E2E 样本，用于修正 memory-heavy 与 scalar-control/sync-heavy kernel 的分项权重方向。
2. **Prefill-A5 plan-level 校准**：来自 `prefill_a5` 的 S0-S6 多阶段真实耗时轨迹，用于修正当前四个 Plan 参数变化的收益方向。

这个合并配置不是完整训练得到的真机 ranking model，而是一个更实用的弱校准配置：既保留通用 component-prior，又保留 prefill/attention 场景下有证据支持的 plan-level prior。

## 2. 合并原则

合并不是简单平均，而是分层保留：

| 来源 | 合并到哪里 | 作用 |
|---|---|---|
| `cost_model_e2e_initial_calibrated.json` | 作为主体配置 | 保留保守 risk control、E2E component calibration metadata、memory/scalar/sync profile-aware prior 使用方式 |
| `cost_model_prefill_a5_plan_calibrated.json` | 合入 `cost_model_strategy_effects.cv_pipeline` 和 `cost_model_calibration.plan_level_latency_priors` | 修正 mixed_cv、auto_cv_balance、tile_mix=4:1 这类 CVPipelinePlan 参数收益方向 |

因此，运行时仍推荐配合：

```bash
--msprof-calibration-mode component_prior
```

如果只是为了把报告中的 predicted cycles 拉到当前原始 kernel 的真机量级，可以用：

```bash
--msprof-calibration-mode component_plus_scale
```

## 3. 已完成的复核结果

### 3.1 Prefill-A5 plan-only validation

使用合并配置后，Prefill-A5 的四个可表达 Plan transition 全部方向正确：

```text
direction_hit_rate = 1.00
hits = 4 / 4
mean_absolute_gain_error = 0.0126
```

这说明合并配置保留了之前 Prefill-A5 校准的核心收益：

- `S1 -> S2`: `BLOCK_SBS=256 + multibuffer=False` 方向正确；
- `S2 -> S3`: `enable_mixed_cv=False` 方向修正为正确；
- `S4 -> S5`: `enable_hivm_auto_cv_balance=True` 方向正确；
- `S5 -> S6`: `tile_mix_cube_loop=4, tile_mix_vector_loop=1` 方向修正为正确。

### 3.2 split_qkv E2E 样本

使用合并配置 + `component_prior` 后，`split_qkv` 仍能完整 search：

```text
best_strategy_id = candidate_00005
best_predicted_cycles = 171931.79
Layer1 kept = 37
Layer3 candidates = 3384
legal candidates = 3384
dominant_runtime_signal = memory
```

这说明合并配置没有破坏 `split_qkv` 的 memory-heavy E2E component-prior 判断。

### 3.3 chunk_kda 轻量 E2E 样本

使用合并配置 + `component_prior` 后，`chunk_kda` 在 MLIR + msprof 轻量模式下仍能完整 search：

```text
best_strategy_id = candidate_00241
best_predicted_cycles = 19678.94
Layer1 kept = 34
Layer3 candidates = 3264
legal candidates = 3264
relaxed candidates = 144
dominant_runtime_signal = scalar_control
```

这说明合并配置没有破坏 `chunk_kda` 的 scalar-control/sync-heavy 判断。

## 4. 推荐使用方式

### 4.1 默认推荐

```bash
python auto_strategy_search.py \
  --kernel <kernel.npuir.mlir> \
  --hardware-config configs/ascend_910b.json \
  --cost-model-config configs/cost_model_e2e_prefill_merged.json \
  --cost-risk-mode conservative \
  --candidate-space standard \
  --artifact-kernel-profile on \
  --msprof-op-summary <op_summary.csv> \
  --msprof-calibration-mode component_prior \
  --output-dir artifacts/<case>_merged_component_prior
```

### 4.2 如果有 DES/trace

```bash
python auto_strategy_search.py \
  --kernel <kernel.npuir.mlir> \
  --hardware-config configs/ascend_910b.json \
  --cost-model-config configs/cost_model_e2e_prefill_merged.json \
  --cost-risk-mode conservative \
  --candidate-space standard \
  --artifact-kernel-profile on \
  --artifact-des-graph <des.json> \
  --artifact-trace <trace.json> \
  --msprof-op-summary <op_summary.csv> \
  --msprof-calibration-mode component_prior \
  --output-dir artifacts/<case>_merged_component_prior
```

### 4.3 只想做量级对齐

```bash
--msprof-calibration-mode component_plus_scale
```

注意：`component_plus_scale` 会把 predicted cycles 拉到当前原始 kernel 的 measured cycles 量级，但它主要用于报告展示，不等价于真实候选排序训练。

## 5. 仍然需要保留的边界

这个合并 config 可以作为当前阶段更合理的默认实验配置，但不能过度宣传为“真机训练完成”：

1. E2E component-prior 只有两个原始 kernel 样本；
2. Prefill-A5 只有一个 staged trajectory；
3. 仍然缺少多个 rewritten candidate 的真实 msprof 排序数据；
4. Prefill-A5 的 plan prior 对 attention/prefill-like kernel 最可靠，不能直接视为所有 kernel 的通用规律；
5. production rewrite 仍需要真实 BiShengIR parser、MLIR verifier、HivmOpsEditor roundtrip、vTriton DES/trace 与 msprof 真机 profile 验证。

## 6. 一句话结论

`cost_model_e2e_prefill_merged.json` 是目前最适合使用的单一弱校准配置：它同时保留了 `split_qkv/chunk_kda` 的 component-prior 校准，以及 `prefill_a5` 的 plan-level 参数收益校准；适合作为当前项目后续 search/rewrite 实验的默认 calibrated config。
