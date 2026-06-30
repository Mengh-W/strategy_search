# 缺陷 HIVM 样例 cost model 识别与寻优测试报告

版本：`V5.3.1-backend-contract-ready-prelinux-lf-hygiene`  
报告位置：`docs/test_report/01_defect_hivm_cost_model_test_report_CN.md`  
测试对象：`tests/defect_inputs/` 下 14 个 synthetic defect HIVM/NPUIR MLIR 样例。

---

## 1. 测试目的

本测试不是为了证明真实 msprof 性能收益，而是验证当前 analytical cost model 与 hardware gate 对“明显缺陷 HIVM”的方向识别能力。具体看三件事：

1. parser 是否能从缺陷 MLIR 中读出当前 tile、barrier、set/wait flag 等结构特征；
2. hardware gate 是否能识别 UB overflow 等非法 baseline；
3. cost model 是否会把明显低质量策略推向更合理的四 Plan 组合，例如更稳的 tile、double buffer、CV stage 2、graph sync/event reuse。

---

## 2. 测试样例覆盖范围

| 编号 | 样例 | 缺陷类型 | 预期优化方向 |
|---:|---|---|---|
| 1 | `defect_A_small_tile_f32_barrier` | 小 tile + f32 + barrier：tile_n 偏小、未启用 double buffer、存在 pipe_barrier，容易造成访存/同步开销偏高。 | 应提高有效 tile 利用率、启用双缓冲、用 graph/event sync 降低 barrier stall。 |
| 2 | `defect_B_large_tile_ub_overflow` | 大 tile UB overflow：128x256x128 tile 触发 UB 容量风险，当前 IR 被判为不可行。 | hardware gate 应拒绝当前配置，并搜索更小、更安全的 tile。 |
| 3 | `defect_C_barrier_heavy_sync_stall` | barrier-heavy 同步停顿：tile 本身不极端，但 pipe_barrier 数量高，显著增加同步 stall。 | 应优先降低同步开销，选择 graph_sync_solver/event reuse，并保留安全 tile。 |
| 4 | `defect_D_no_overlap_good_tile` | tile 尚可但没有 overlap：当前 64x64 tile 不算极差，但未开启 double buffer/CV pipeline，load/compute/store 重叠不足。 | 应通过 double buffer + CV pipeline 提高 overlap。 |
| 5 | `defect_E_small_tile_many_sync_f32_redundantQ` | 小 tile + 多同步 + f32/redundant Q：tile 偏小、barrier 多、f32 score/冗余 Q 造成计算和访存压力。 | 应同时修正 tile、buffer、pipeline、sync，而不是只改单一维度。 |
| 6 | `defect_F_large_tile_overflow_sync_pressure` | 大 tile overflow + 同步压力：大 tile 触发 UB overflow，同时 barrier 多。 | hardware gate 应先识别非法 baseline，再搜索安全 tile 与低同步策略。 |
| 7 | `defect_G_existing_pingpong_but_bad_sync_dtype` | 已有 ping-pong 但同步/dtype 较差：已经有 ping-pong 痕迹，但 barrier 仍高，f32/vector-heavy 造成开销。 | 模型不能被“已有 ping-pong”误导，应继续优化 tile、CV pipeline 和 sync。 |
| 8 | `defect_H_event_sync_but_small_tile_no_overlap` | 已有 event sync 但小 tile/无 overlap：已有 set/wait flag，但 tile 偏小且未开启 double buffer/CV overlap。 | 应保留 event reuse 方向，并补齐 double buffer 与 CV pipeline。 |
| 9 | `defect_I_medium_tile_memory_pressure_vector_heavy` | 中等 tile + memory/vector pressure：tile 不明显非法，但存在 memory/layout/vector-heavy 压力与同步开销。 | 应降低 memory dominant cost，使用更稳的 tile 与 pipeline。 |
| 10 | `defect_J_tiny_tile_nested_barrier_f32` | 极小 tile + 嵌套 barrier + f32：16x16 tile 过小，循环/同步开销被放大，barrier 很多。 | 应显著放大有效 tile，启用 double buffer、CV stage 2 与 graph sync。 |
| 11 | `defect_K_oversized_m128n192_f32_overflow` | 超大 tile + f32 overflow：128x192x128 tile 与 f32 buffer 压力导致 UB overflow。 | 应判定 current IR 不可行，并退回安全 tile。 |
| 12 | `defect_L_good_tile_event_mismatch_vector_heavy` | 已有 ping-pong + event mismatch + vector-heavy：已有 double buffer，但 set/wait 不匹配、vector-heavy、tile_n 偏大。 | 应继续修复 sync 与 pipeline，而不是因已有 ping-pong 停止优化。 |
| 13 | `defect_M_tail_unfriendly_n176_no_overlap` | tail-unfriendly N=176 + 无 overlap：N=176 对 tail/对齐不友好，未开启 overlap，barrier 较多。 | 应回到更稳定 tile，并补齐 double buffer/CV pipeline/sync。 |
| 14 | `defect_O_pingpong_but_many_barriers_extra_buffers` | 已有 ping-pong 但 barrier/extra buffer 多：已有 ping-pong，但 barrier 多、额外 buffer 多，仍存在同步和内存压力。 | 应识别 ping-pong 不是充分条件，继续优化 sync/pipeline/tile。 |

覆盖的缺陷类型包括：

- 小 tile / 极小 tile 导致循环与同步开销被放大；
- 大 tile / 超大 tile 导致 UB 容量溢出；
- barrier-heavy 同步停顿；
- 已有 event 或 ping-pong 但仍存在其他瓶颈；
- tail-unfriendly N 维度；
- memory/layout/vector-heavy 压力；
- 多缺陷叠加场景。

---

## 3. 实跑命令与通过情况

### 3.1 默认轻量 regression

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_defect_injection_cases.py -m regression
```

结果：

```text
28 passed, 14 skipped
```

说明：默认测试会检查 14 个 defect 文件存在、parser 读取结果与记录一致，以及 recorded search summary 是否朝预期方向移动；live optimizer 搜索默认跳过，避免普通 CI 过慢。

### 3.2 live optimizer 分批实跑

由于 14 个 live search 连续跑耗时较长，本次按批次执行，避免单次命令超时。

```bash
RUN_DEFECT_LIVE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -m slow tests/test_defect_injection_cases.py -k 'defect_A_small_tile_f32_barrier or defect_B_large_tile_ub_overflow or defect_C_barrier_heavy_sync_stall or defect_D_no_overlap_good_tile'
```

结果：

```text
4 passed
```

```bash
RUN_DEFECT_LIVE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -m slow tests/test_defect_injection_cases.py -k 'defect_E_small_tile_many_sync_f32_redundantQ or defect_F_large_tile_overflow_sync_pressure or defect_G_existing_pingpong_but_bad_sync_dtype'
```

结果：

```text
3 passed
```

```bash
RUN_DEFECT_LIVE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -m slow tests/test_defect_injection_cases.py -k 'defect_H_event_sync_but_small_tile_no_overlap or defect_I_medium_tile_memory_pressure_vector_heavy or defect_J_tiny_tile_nested_barrier_f32 or defect_K_oversized_m128n192_f32_overflow'
```

结果：

```text
4 passed
```

```bash
RUN_DEFECT_LIVE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -m slow tests/test_defect_injection_cases.py -k 'defect_L_good_tile_event_mismatch_vector_heavy or defect_M_tail_unfriendly_n176_no_overlap or defect_O_pingpong_but_many_barriers_extra_buffers'
```

结果：

```text
3 passed
```

因此，本轮 14 个 defect 样例 live optimizer 均已跑通。

---

## 4. 总体结果

- 总样例数：14
- current IR 可行样例：11
- current IR 被判为不可行样例：3
- 不可行原因：均为 `UB overflow`
- 所有可行 baseline 的 best predicted cycles 均低于 current estimated cycles。
- 所有可行 baseline 的 predicted speedup 均大于 1。
- 所有样例的 best strategy 均启用 double buffer、CV stage 2、graph_sync_solver、event reuse。
- UB overflow 样例被 hardware gate 明确识别为 current IR infeasible，并被搜索拉回更小、更安全的 tile。

---

## 5. 汇总表

| 样例 | current tile | feasible | reason | current cycles | best tile | best cycles | speedup | legal | relaxed |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| `defect_A_small_tile_f32_barrier` | 64x32x128 | True | ok | 1084.034 | 32x64x128 | 458.503 | 2.364 | 2748 | 1152 |
| `defect_B_large_tile_ub_overflow` | 128x256x128 | False | UB overflow | 5437.001 | 64x64x128 | 613.071 | N/A | 2388 | 600 |
| `defect_C_barrier_heavy_sync_stall` | 64x64x128 | True | ok | 2252.966 | 32x64x128 | 825.115 | 2.73 | 2748 | 1152 |
| `defect_D_no_overlap_good_tile` | 64x64x128 | True | ok | 1352.966 | 32x64x128 | 458.503 | 2.951 | 2748 | 1152 |
| `defect_E_small_tile_many_sync_f32_redundantQ` | 64x32x128 | True | ok | 1704.923 | 32x64x128 | 698.747 | 2.44 | 2748 | 0 |
| `defect_F_large_tile_overflow_sync_pressure` | 128x256x128 | False | UB overflow | 6671.235 | 64x64x128 | 1025.558 | N/A | 2388 | 0 |
| `defect_G_existing_pingpong_but_bad_sync_dtype` | 96x96x128 | True | ok | 2509.547 | 16x176x128 | 1103.274 | 2.275 | 2412 | 0 |
| `defect_H_event_sync_but_small_tile_no_overlap` | 64x32x128 | True | ok | 841.813 | 32x64x128 | 431.746 | 1.95 | 2748 | 0 |
| `defect_I_medium_tile_memory_pressure_vector_heavy` | 64x64x128 | True | ok | 1820.083 | 32x64x128 | 699.560 | 2.602 | 2832 | 0 |
| `defect_J_tiny_tile_nested_barrier_f32` | 16x16x128 | True | ok | 5918.171 | 32x64x128 | 1087.578 | 5.442 | 3084 | 768 |
| `defect_K_oversized_m128n192_f32_overflow` | 128x192x128 | False | UB overflow | 6495.883 | 32x64x128 | 711.419 | N/A | 2412 | 1092 |
| `defect_L_good_tile_event_mismatch_vector_heavy` | 64x96x128 | True | ok | 1467.427 | 32x64x128 | 778.808 | 1.884 | 2832 | 1104 |
| `defect_M_tail_unfriendly_n176_no_overlap` | 32x176x128 | True | ok | 2756.537 | 32x64x128 | 711.949 | 3.872 | 2748 | 960 |
| `defect_O_pingpong_but_many_barriers_extra_buffers` | 96x64x128 | True | ok | 2461.289 | 32x64x128 | 1123.573 | 2.191 | 2580 | 1020 |

---

## 6. 分样例分析

### 6.1 `defect_A_small_tile_f32_barrier`

- 缺陷定位：tile_n 偏小、未启用 double buffer、存在 pipe_barrier，容易造成访存/同步开销偏高。
- 预期方向：应提高有效 tile 利用率、启用双缓冲、用 graph/event sync 降低 barrier stall。
- 当前解析结果：tile=`64x32x128`，double_buffer=`False`，CV stage=`1`，barrier=2，set/wait=0/0。
- current IR legality：可行，estimated cycles=1084.034。
- best strategy：tile=`32x64x128`，block=32，double_buffer=`True`，CV stage=2，sync=`graph_sync_solver`，event_reuse=`True`，risk=`HIGH`。
- best predicted cycles=458.503，predicted speedup=2.364x。
- 判定：cost model 能识别该缺陷，并把策略推向更低预测成本的方向。

### 6.2 `defect_B_large_tile_ub_overflow`

- 缺陷定位：128x256x128 tile 触发 UB 容量风险，当前 IR 被判为不可行。
- 预期方向：hardware gate 应拒绝当前配置，并搜索更小、更安全的 tile。
- 当前解析结果：tile=`128x256x128`，double_buffer=`False`，CV stage=`1`，barrier=2，set/wait=0/0。
- current IR legality：不可行，原因=`UB overflow`，current cycles 仅作为不可行 baseline 的估计参考，不用于计算 speedup。
- best strategy：tile=`64x64x128`，block=32，double_buffer=`True`，CV stage=2，sync=`graph_sync_solver`，event_reuse=`True`，risk=`HIGH`。
- best predicted cycles=613.071。
- 判定：hardware gate 能识别 UB overflow，并将搜索结果拉回安全 tile。

### 6.3 `defect_C_barrier_heavy_sync_stall`

- 缺陷定位：tile 本身不极端，但 pipe_barrier 数量高，显著增加同步 stall。
- 预期方向：应优先降低同步开销，选择 graph_sync_solver/event reuse，并保留安全 tile。
- 当前解析结果：tile=`64x64x128`，double_buffer=`False`，CV stage=`1`，barrier=8，set/wait=0/0。
- current IR legality：可行，estimated cycles=2252.966。
- best strategy：tile=`32x64x128`，block=32，double_buffer=`True`，CV stage=2，sync=`graph_sync_solver`，event_reuse=`True`，risk=`HIGH`。
- best predicted cycles=825.115，predicted speedup=2.73x。
- 判定：cost model 能识别该缺陷，并把策略推向更低预测成本的方向。

### 6.4 `defect_D_no_overlap_good_tile`

- 缺陷定位：当前 64x64 tile 不算极差，但未开启 double buffer/CV pipeline，load/compute/store 重叠不足。
- 预期方向：应通过 double buffer + CV pipeline 提高 overlap。
- 当前解析结果：tile=`64x64x128`，double_buffer=`False`，CV stage=`1`，barrier=2，set/wait=0/0。
- current IR legality：可行，estimated cycles=1352.966。
- best strategy：tile=`32x64x128`，block=32，double_buffer=`True`，CV stage=2，sync=`graph_sync_solver`，event_reuse=`True`，risk=`HIGH`。
- best predicted cycles=458.503，predicted speedup=2.951x。
- 判定：cost model 能识别该缺陷，并把策略推向更低预测成本的方向。

### 6.5 `defect_E_small_tile_many_sync_f32_redundantQ`

- 缺陷定位：tile 偏小、barrier 多、f32 score/冗余 Q 造成计算和访存压力。
- 预期方向：应同时修正 tile、buffer、pipeline、sync，而不是只改单一维度。
- 当前解析结果：tile=`64x32x128`，double_buffer=`False`，CV stage=`1`，barrier=6，set/wait=0/0。
- current IR legality：可行，estimated cycles=1704.923。
- best strategy：tile=`32x64x128`，block=32，double_buffer=`True`，CV stage=2，sync=`graph_sync_solver`，event_reuse=`True`，risk=`HIGH`。
- best predicted cycles=698.747，predicted speedup=2.44x。
- 判定：cost model 能识别该缺陷，并把策略推向更低预测成本的方向。

### 6.6 `defect_F_large_tile_overflow_sync_pressure`

- 缺陷定位：大 tile 触发 UB overflow，同时 barrier 多。
- 预期方向：hardware gate 应先识别非法 baseline，再搜索安全 tile 与低同步策略。
- 当前解析结果：tile=`128x256x128`，double_buffer=`False`，CV stage=`1`，barrier=8，set/wait=0/0。
- current IR legality：不可行，原因=`UB overflow`，current cycles 仅作为不可行 baseline 的估计参考，不用于计算 speedup。
- best strategy：tile=`64x64x128`，block=32，double_buffer=`True`，CV stage=2，sync=`graph_sync_solver`，event_reuse=`True`，risk=`HIGH`。
- best predicted cycles=1025.558。
- 判定：hardware gate 能识别 UB overflow，并将搜索结果拉回安全 tile。

### 6.7 `defect_G_existing_pingpong_but_bad_sync_dtype`

- 缺陷定位：已经有 ping-pong 痕迹，但 barrier 仍高，f32/vector-heavy 造成开销。
- 预期方向：模型不能被“已有 ping-pong”误导，应继续优化 tile、CV pipeline 和 sync。
- 当前解析结果：tile=`96x96x128`，double_buffer=`True`，CV stage=`1`，barrier=10，set/wait=0/0。
- current IR legality：可行，estimated cycles=2509.547。
- best strategy：tile=`16x176x128`，block=36，double_buffer=`True`，CV stage=2，sync=`graph_sync_solver`，event_reuse=`True`，risk=`HIGH`。
- best predicted cycles=1103.274，predicted speedup=2.275x。
- 判定：cost model 能识别该缺陷，并把策略推向更低预测成本的方向。

### 6.8 `defect_H_event_sync_but_small_tile_no_overlap`

- 缺陷定位：已有 set/wait flag，但 tile 偏小且未开启 double buffer/CV overlap。
- 预期方向：应保留 event reuse 方向，并补齐 double buffer 与 CV pipeline。
- 当前解析结果：tile=`64x32x128`，double_buffer=`False`，CV stage=`1`，barrier=0，set/wait=1/1。
- current IR legality：可行，estimated cycles=841.813。
- best strategy：tile=`32x64x128`，block=32，double_buffer=`True`，CV stage=2，sync=`graph_sync_solver`，event_reuse=`True`，risk=`HIGH`。
- best predicted cycles=431.746，predicted speedup=1.95x。
- 判定：cost model 能识别该缺陷，并把策略推向更低预测成本的方向。

### 6.9 `defect_I_medium_tile_memory_pressure_vector_heavy`

- 缺陷定位：tile 不明显非法，但存在 memory/layout/vector-heavy 压力与同步开销。
- 预期方向：应降低 memory dominant cost，使用更稳的 tile 与 pipeline。
- 当前解析结果：tile=`64x64x128`，double_buffer=`False`，CV stage=`1`，barrier=4，set/wait=0/0。
- current IR legality：可行，estimated cycles=1820.083。
- best strategy：tile=`32x64x128`，block=32，double_buffer=`True`，CV stage=2，sync=`graph_sync_solver`，event_reuse=`True`，risk=`HIGH`。
- best predicted cycles=699.560，predicted speedup=2.602x。
- 判定：cost model 能识别该缺陷，并把策略推向更低预测成本的方向。

### 6.10 `defect_J_tiny_tile_nested_barrier_f32`

- 缺陷定位：16x16 tile 过小，循环/同步开销被放大，barrier 很多。
- 预期方向：应显著放大有效 tile，启用 double buffer、CV stage 2 与 graph sync。
- 当前解析结果：tile=`16x16x128`，double_buffer=`False`，CV stage=`1`，barrier=10，set/wait=0/0。
- current IR legality：可行，estimated cycles=5918.171。
- best strategy：tile=`32x64x128`，block=32，double_buffer=`True`，CV stage=2，sync=`graph_sync_solver`，event_reuse=`True`，risk=`HIGH`。
- best predicted cycles=1087.578，predicted speedup=5.442x。
- 判定：cost model 能识别该缺陷，并把策略推向更低预测成本的方向。
- 附加诊断：dominant_component=`memory`，kernel_type=`memory_or_layout_heavy`。

### 6.11 `defect_K_oversized_m128n192_f32_overflow`

- 缺陷定位：128x192x128 tile 与 f32 buffer 压力导致 UB overflow。
- 预期方向：应判定 current IR 不可行，并退回安全 tile。
- 当前解析结果：tile=`128x192x128`，double_buffer=`False`，CV stage=`1`，barrier=4，set/wait=0/0。
- current IR legality：不可行，原因=`UB overflow`，current cycles 仅作为不可行 baseline 的估计参考，不用于计算 speedup。
- best strategy：tile=`32x64x128`，block=32，double_buffer=`True`，CV stage=2，sync=`graph_sync_solver`，event_reuse=`True`，risk=`HIGH`。
- best predicted cycles=711.419。
- 判定：hardware gate 能识别 UB overflow，并将搜索结果拉回安全 tile。
- 附加诊断：dominant_component=`memory`，kernel_type=`memory_or_layout_heavy`。

### 6.12 `defect_L_good_tile_event_mismatch_vector_heavy`

- 缺陷定位：已有 double buffer，但 set/wait 不匹配、vector-heavy、tile_n 偏大。
- 预期方向：应继续修复 sync 与 pipeline，而不是因已有 ping-pong 停止优化。
- 当前解析结果：tile=`64x96x128`，double_buffer=`True`，CV stage=`1`，barrier=1，set/wait=3/2。
- current IR legality：可行，estimated cycles=1467.427。
- best strategy：tile=`32x64x128`，block=32，double_buffer=`True`，CV stage=2，sync=`graph_sync_solver`，event_reuse=`True`，risk=`HIGH`。
- best predicted cycles=778.808，predicted speedup=1.884x。
- 判定：cost model 能识别该缺陷，并把策略推向更低预测成本的方向。
- 附加诊断：dominant_component=`memory`，kernel_type=`memory_or_layout_heavy`。

### 6.13 `defect_M_tail_unfriendly_n176_no_overlap`

- 缺陷定位：N=176 对 tail/对齐不友好，未开启 overlap，barrier 较多。
- 预期方向：应回到更稳定 tile，并补齐 double buffer/CV pipeline/sync。
- 当前解析结果：tile=`32x176x128`，double_buffer=`False`，CV stage=`1`，barrier=4，set/wait=0/0。
- current IR legality：可行，estimated cycles=2756.537。
- best strategy：tile=`32x64x128`，block=32，double_buffer=`True`，CV stage=2，sync=`graph_sync_solver`，event_reuse=`True`，risk=`HIGH`。
- best predicted cycles=711.949，predicted speedup=3.872x。
- 判定：cost model 能识别该缺陷，并把策略推向更低预测成本的方向。
- 附加诊断：dominant_component=`memory`，kernel_type=`memory_or_layout_heavy`。

### 6.14 `defect_O_pingpong_but_many_barriers_extra_buffers`

- 缺陷定位：已有 ping-pong，但 barrier 多、额外 buffer 多，仍存在同步和内存压力。
- 预期方向：应识别 ping-pong 不是充分条件，继续优化 sync/pipeline/tile。
- 当前解析结果：tile=`96x64x128`，double_buffer=`True`，CV stage=`1`，barrier=8，set/wait=1/1。
- current IR legality：可行，estimated cycles=2461.289。
- best strategy：tile=`32x64x128`，block=32，double_buffer=`True`，CV stage=2，sync=`graph_sync_solver`，event_reuse=`True`，risk=`HIGH`。
- best predicted cycles=1123.573，predicted speedup=2.191x。
- 判定：cost model 能识别该缺陷，并把策略推向更低预测成本的方向。
- 附加诊断：dominant_component=`memory`，kernel_type=`memory_or_layout_heavy`。

---

## 7. 对 cost model 的解释

从 14 个样例看，当前 cost model 对人工构造缺陷的方向识别主要来自四类信号：

1. tile shape 信号：极小 tile 会放大循环、同步和 launch-like 固定开销；超大 tile 会触发 UB 容量压力。
2. memory / overlap 信号：未启用 double buffer 或 CV pipeline 时，load、compute、store 缺乏重叠，预测成本升高。
3. sync 信号：barrier 数量多时，sync/stall 项升高；graph_sync_solver 与 event reuse 会降低同步相关预测成本。
4. hardware gate 信号：UB overflow 不再只是成本变高，而是直接标记 current IR infeasible。

因此，这批样例验证的是“方向感”：模型能不能看出哪些配置明显不合理，并把策略推向合理区域。它不是 profile-level 精度验证。

---

## 8. 当前测试结论

本轮测试结论如下：

- 对小 tile、极小 tile、多 barrier、无 overlap、已有 ping-pong 但同步仍差等可行 baseline，cost model 均给出更低 predicted cycles 的 best strategy。
- 对大 tile / 超大 tile 的 UB overflow 样例，hardware gate 能将 current IR 判为不可行。
- 搜索结果普遍倾向 `32x64x128` 或 `64x64x128` 一类更稳的 tile，并启用 double buffer、CV stage 2、graph_sync_solver、event reuse。
- 对已经存在 ping-pong 或 event sync 的样例，模型不会简单认为“已经优化完成”，而是继续根据 barrier、tile、pipeline、memory pressure 寻找更优方向。

一句话总结：

```text
当前 analytical cost model 对 synthetic defect HIVM 具备明确的缺陷方向识别能力；hardware gate 能识别 UB overflow；但这仍然是 Python/fake-backend 层面的方向验证，不等价于真实 NPU 性能验证。
```

---

## 9. 边界与后续验证

本报告不能 claim：

- predicted speedup 等于 msprof 真机 speedup；
- rewritten HIVM 已通过真实 BiShengIR parser / MLIR verifier；
- graph_sync_solver 一定能被真实后端安全 lowering；
- synthetic defect 覆盖了所有真实 HIVM 坏例。

后续在 Linux 真实后端环境中，建议继续做：

1. 对这 14 个 defect 样例生成 backend contract；
2. 用真实 HivmOpsEditor 执行 contract；
3. 跑 BiShengIR parser / MLIR verifier；
4. 跑 vTriton DES/trace；
5. 若有可编译 kernel，再用 CANN + msprof 比较真实运行时间。
