# V5.3.1 E2E 样本下的 cost model 初步校准报告

本报告基于两个真实 E2E 样本做 cost model 的初步校准：

- `e2e_split_qkv`：小型 `split_qkv_rmsnorm_mrope_kernel`，用于 memory-heavy 方向的 sanity calibration。
- `e2e_chunk`：大型 `chunk_kda_bwd_kernel_wy_dqkg_fused_opt_v2`，用于 scalar-control / sync-heavy 方向的 sanity calibration。

这里的“校准”不是训练一个新的高精度模型，而是把真实 `op_summary.csv` 中的 msprof 信号作为 profile-aware prior，修正 cost model 的分项权重和绝对量级。

## 1. 校准方式

当前项目已经支持两种 msprof 校准模式：

```bash
--msprof-calibration-mode component_prior
```

该模式只修正 component correction，例如：

- `memory_cycle_correction`
- `scalar_cycle_correction`
- `sync_cycle_correction`
- `overlap_confidence`
- `cv_overlap_confidence`

它不会把预测值强行缩放到真实耗时，因此更适合作为默认初步校准模式。

```bash
--msprof-calibration-mode component_plus_scale
```

该模式在 `component_prior` 基础上，再用当前 IR 的实测 cycles 做全局尺度校准：

```text
measured_total_cycles = task_duration_us × cycles_per_us

global_cycle_scale = measured_total_cycles / current_ir_predicted_cycles_before_scale
```

该模式可以让 `current_ir_estimated_predicted_cycles` 与真实 msprof cycles 对齐，但它不会改变候选排序，因为所有候选都乘以同一个 scale。因此它适合做报告里的量级对齐，不适合声称 ranking 已被训练好。

## 2. split_qkv 校准结果

输入 kernel：

```text
split_qkv_rmsnorm_mrope_kernel
```

真实 msprof 信号：

```text
task_duration_us = 2433.789
measured_total_cycles = 4502509.65
dominant_runtime_signal = memory
```

component ratio：

```text
compute = 0.0000
memory = 0.2688
vector = 0.1045
scalar_control = 0.1375
```

`component_prior` 前后的关键权重：

| 权重 | 校准前 | 校准后 | 解释 |
|---|---:|---:|---|
| `memory_cycle_correction` | 1.0384 | 1.1614 | msprof 显示 memory 信号较强，因此上调 memory 成本 |
| `scalar_cycle_correction` | 1.6615 | 1.6615 | 原始结构 profile 已经给出更高 scalar 权重，因此不再下降 |
| `sync_cycle_correction` | 1.3505 | 1.3505 | 原始结构 profile 已更保守 |
| `overlap_confidence` | 0.8947 | 0.8947 | msprof prior 不覆盖更保守的原值 |
| `cv_overlap_confidence` | 0.9137 | 0.9137 | 同上 |

搜索结果：

```text
best_strategy_id = candidate_00005
best_predicted_cycles, component_prior = 171931.79
```

绝对尺度校准结果：

```text
current_ir_predicted_cycles_before_scale = 136667.95
measured_total_cycles = 4502509.65
global_cycle_scale = 32.9449
best_predicted_cycles, component_plus_scale = 5664272.93
```

解释：

- `component_prior` 主要让模型承认该 kernel 的 memory 项被低估。
- `component_plus_scale` 把当前 IR 的预测量级拉到 msprof 实测量级，但不改变候选排序。

## 3. chunk_kda 校准结果

输入 kernel：

```text
chunk_kda_bwd_kernel_wy_dqkg_fused_opt_v2
```

真实 msprof 信号：

```text
task_duration_us = 111891.595
measured_total_cycles = 206999450.75
dominant_runtime_signal = scalar_control
```

component ratio：

```text
compute = 0.0057
memory = 0.0827
vector = 0.0448
scalar_control = 0.8400
```

`component_prior` 前后的关键权重：

| 权重 | 校准前 | 校准后 | 解释 |
|---|---:|---:|---|
| `memory_cycle_correction` | 1.2335 | 1.2335 | 结构 profile 已经比 msprof memory prior 更保守 |
| `scalar_cycle_correction` | 1.4763 | 1.8018 | msprof 显示 scalar/control 极重，明显上调 scalar 成本 |
| `sync_cycle_correction` | 1.4530 | 1.4530 | 结构 profile 已经给出较高 sync 权重 |
| `overlap_confidence` | 0.9206 | 0.7385 | scalar-control-heavy 场景下，降低 overlap 乐观程度 |
| `cv_overlap_confidence` | 0.9182 | 0.7824 | 同上，降低 C/V pipeline overlap 的乐观估计 |

搜索结果：

```text
best_strategy_id = candidate_00241
best_predicted_cycles, component_prior = 20040.49
```

绝对尺度校准结果：

```text
current_ir_predicted_cycles_before_scale = 25247.39
measured_total_cycles = 206999450.75
global_cycle_scale = 8198.8445
best_predicted_cycles, component_plus_scale = 164308889.27
```

解释：

- `chunk_kda` 的最大价值是证明 scalar/control/sync 不能只作为小 penalty。
- 对这类 kernel，模型应显著提高 scalar-cycle 权重，并降低 overlap confidence。
- 绝对尺度 scale 极大，说明当前 analytical cycles 与真实 wall-clock cycles 还不是同一量纲；因此 scale 只能用于量级对齐，不能用于训练候选排序。

## 4. 初步校准后的推荐用法

### 推荐：分项校准模式

用于正常寻优：

```bash
python auto_strategy_search.py \
  --kernel <kernel.npuir.mlir> \
  --hardware-config configs/ascend_910b.json \
  --cost-model-config configs/cost_model_e2e_initial_calibrated.json \
  --cost-risk-mode conservative \
  --candidate-space standard \
  --artifact-kernel-profile on \
  --msprof-op-summary <op_summary.csv> \
  --msprof-calibration-mode component_prior \
  --output-dir artifacts/e2e_initial_calibration/<case>_component_prior
```

这个模式更适合作为当前项目的“初步校准后寻优”。

### 可选：绝对量级对齐模式

用于报告中展示与真机 cycles 对齐后的 predicted cycles：

```bash
python auto_strategy_search.py \
  --kernel <kernel.npuir.mlir> \
  --hardware-config configs/ascend_910b.json \
  --cost-model-config configs/cost_model_e2e_initial_calibrated.json \
  --cost-risk-mode conservative \
  --candidate-space standard \
  --artifact-kernel-profile on \
  --msprof-op-summary <op_summary.csv> \
  --msprof-calibration-mode component_plus_scale \
  --output-dir artifacts/e2e_initial_calibration/<case>_component_plus_scale
```

注意：`component_plus_scale` 会把所有候选乘以同一个 scale，因此排序不变。

## 5. 当前能宣称什么

可以宣称：

```text
基于两个真实 E2E 样本，当前 cost model 已经完成初步 profile-aware 校准。
split_qkv 样本用于提高 memory 分项识别；chunk_kda 样本用于提高 scalar-control/sync 分项识别，并降低 overlap 过度乐观。
校准后模型能更合理地区分 memory-heavy 与 scalar-control-heavy kernel，并把 msprof 信号反映到 component correction 中。
```

不能宣称：

```text
不能说 cost model 已经完成训练。
不能说候选排序已经被真机 profile 证明。
不能说 rewrite 后真机一定加速。
不能说 component_plus_scale 后的 best_predicted_cycles 就是真实优化后 cycles。
```

## 6. 后续真正训练需要什么

要把当前初步校准升级成严格训练，需要至少补充：

1. 同一 kernel 下多个 rewritten candidate 的真实 msprof。
2. rewrite 前后同条件 profile 对比。
3. DES/trace 重新生成后的 before/after 对比。
4. 至少覆盖 memory-heavy、compute-heavy、scalar-control-heavy、sync-heavy、mixed 五类 kernel。
5. 每类 kernel 至少 5 到 10 组候选策略 profile。

当前两个样本足够做 sanity calibration，但还不足以训练 ranking model。
