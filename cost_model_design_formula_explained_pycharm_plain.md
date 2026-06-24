# V3.3.1 Cost Model 设计说明：Structure-aware Cycle Correction

本文档说明当前版本的 cost model。核心原则是：**目标仍然是估计 total predicted cycles**。MLIR 与编译产物中的结构证据不是额外 score，也不是实机 profiling target，而是用于修正 load、compute、store、sync、scalar/control 等分项 cycles 的基础估计误差。

一句话概括：

```text
predicted_cycles = sum(corrected component cycle estimates) + necessary constraint/risk penalties
```

当前模型不声称输出真机 cycles。它是一个 structure-aware analytical cycle estimation model，适用于候选策略排序、缺陷识别、硬件边界审计和汇报解释。

---

## 1. 总公式

候选策略记为：

```text
x = (T, M, P, Y)
```

其中：

- `T` 是 TilingPlan；
- `M` 是 MultiBufferPlan；
- `P` 是 CVPipelinePlan；
- `Y` 是 SyncPlan。

总成本定义为：

```text
T_total(x) =
    T_tiles(x)
  + T_sync(x)
  + P_capacity(x)
  + P_shape(x)
  + P_legality(x)
```

其中：

```text
T_tiles(x) = N_tiles / E_parallel * T_tile(x)
```

`N_tiles` 是 tile 数，`E_parallel` 是考虑 block_dim、可用 core 数、wave tail efficiency 后的有效并行度。

---

## 2. 单 tile 成本

如果开启 double buffer 或 CV pipeline，单 tile 成本采用 pipeline exposed-time 形式：

```text
T_tile =
    max(T_load_exposed, T_compute_corrected, T_store_exposed)
  + T_workspace_exposed
  + T_scalar_corrected
  + T_schedule
  + T_warmup_drain
```

如果没有 double buffer / CV pipeline，则采用更保守的串行形式：

```text
T_tile =
    T_load_corrected
  + T_compute_corrected
  + T_store_corrected
  + T_workspace_exposed
  + T_scalar_corrected
  + T_schedule
```

这里的关键是：load、compute、store、sync、scalar/control 每一项仍然尽量保持 cycles 语义，而不是随意加权打分。

---

## 3. Base pipe cycles

首先基于策略参数和硬件参数计算基础估计：

```text
T_load_base
T_store_base
T_cube_base
T_vector_base
T_fix_base
T_sync_base
T_scalar_base
T_workspace_base
```

这些基础项来自 tile shape、dtype bytes、memory traffic、cube/vector op proxy、sync op count、硬件带宽/吞吐/latency 等 analytical 信息。它们不是实机测量值。

---

## 4. 结构证据

V3.3.1 从 MLIR 与编译产物中抽取结构证据：

| 证据类型 | 例子 | 用途 |
|---|---|---|
| flat op counts | `mmadL1`, `copy`, `fixpipe`, vector op, scalar op, barrier | 判断 compute/memory/vector/scalar/sync 结构比例 |
| loop-weighted counts | 内层循环中的 memory/scalar/sync 操作 | 修正 per-tile scalar/control 和 sync 估计 |
| memory path | GM/UB/L1/L0 space path bytes | 修正 load/store/workspace cycles |
| buffer lifetime | local buffer live span, byte-span pressure | 修正 workspace exposed cycles |
| sync criticality | inner-loop sync, cross-pipe set/wait, missing pair | 修正 sync cycles 和 legality risk |
| alignment/tail/mask | dim misalignment, offset misalignment, mask/tail ops | 修正 vector/fix/scalar fragmentation |
| sequence pattern | copy -> nd2nz -> cube, cube -> fixpipe -> vector | 判断 CV overlap 机会 |
| DES/trace product | pipe fraction, DMA path, event names | 作为 lowering 后结构证据，不作为 profiling target |

当 DES pipe fraction 可用时，当前版本采用保守融合：

```text
structure_ratios = 0.60 * MLIR_static_ratios + 0.40 * product_artifact_ratios
```

这样可以利用产物结构信息，但避免单个 DES pipe mix 过度主导 cost model。

---

## 5. Cycle correction factors

结构证据被映射为分项 cycle correction factors：

```text
m_mem       = memory_cycle_correction
m_mem_path  = memory_path_cycle_correction
m_cube      = compute_cycle_correction
m_vec       = vector_cycle_correction
m_align     = alignment_cycle_correction
m_scalar    = scalar_cycle_correction
m_frag      = small_tile_fragmentation_correction
m_sync      = sync_cycle_correction
m_ws        = workspace_pressure_correction
c_overlap   = overlap_confidence
c_cv         = cv_overlap_confidence
```

设计原则是：**每类结构证据只修正少数对应分项**。

| correction factor | 修正对象 | 不再做的事情 |
|---|---|---|
| `memory_cycle_correction` | load/store/fix memory side | 不修正 scalar/sync |
| `compute_cycle_correction` | cube compute | 不直接制造 cube reward |
| `vector_cycle_correction` | vector compute | 不直接影响 sync |
| `scalar_cycle_correction` | scalar/control cycles | 不强烈压低所有 overlap reward |
| `sync_cycle_correction` | sync cycles | 不混入 legality risk |
| `workspace_pressure_correction` | workspace exposed cycles | 不改变主 load/store overlap |
| `overlap_confidence` | load/store overlap 可信度 | 仅窄范围修正 |
| `cv_overlap_confidence` | cube-vector overlap 可信度 | 仅窄范围修正 |

---

## 6. Corrected component cycles

Memory 相关项：

```text
T_load_corrected  = T_load_base  * m_mem * m_mem_path
T_store_corrected = T_store_base * m_mem * m_mem_path
```

Compute 相关项：

```text
T_cube_corrected   = T_cube_base   * m_cube
T_vector_corrected = T_vector_base * m_vec * m_align
T_fix_corrected    = T_fix_base    * m_mem * m_align
```

Cube-vector pipeline 项：

```text
T_compute_corrected =
    T_cube_corrected
  + T_vector_corrected
  - r_cv * c_cv * min(T_cube_corrected, T_vector_corrected)
  + T_fix_corrected
```

其中 `r_cv` 主要来自候选策略的 CVPipelinePlan，`c_cv` 只是结构证据给出的窄范围 confidence。

Scalar/control 项：

```text
T_scalar_corrected = T_scalar_base * m_scalar * m_frag
```

Sync 项：

```text
T_sync = T_sync_base * m_sync
```

Workspace 项：

```text
T_workspace_exposed = T_workspace_base * m_ws
```

---

## 7. Overlap 处理

Double buffer / multi-buffer 的收益主要由候选策略决定：

```text
r_load_strategy
r_store_strategy
```

结构证据只修正这些 overlap 是否可信：

```text
r_load  = r_load_strategy  * c_overlap
r_store = r_store_strategy * c_overlap
```

暴露出来的 load/store 成本为：

```text
T_load_exposed  = T_load_corrected  * (1 - r_load)
T_store_exposed = T_store_corrected * (1 - r_store)
```

当前实现中 `c_overlap` 与 `c_cv` 被限制在较窄范围内，避免 scalar-heavy 或 sync-heavy 证据同时通过多个路径重复惩罚同一个候选。

---

## 8. Sync cost 与 legality risk 分离

同步操作本身的成本：

```text
T_sync = T_sync_base * sync_cycle_correction
```

GraphSyncSolver、event reuse、CV pipeline 等未完全验证的风险不再混入 sync cycles，而是单独进入：

```text
P_legality = P_sync_unknown + P_event_reuse + P_cv_estimated
```

这样可以保持两个语义清楚：

```text
T_sync      = 同步操作大约要花多少 cycles
P_legality  = 这个策略在真实 rewrite/编译中有多不确定
```

---

## 9. Penalty 项

当前保留三类主要 penalty。

### 9.1 Capacity penalty

```text
P_capacity = memory_pressure_penalty(scope_utilization, hardware_caps)
```

未 overflow 时，它是软惩罚；真正的 UB/L1/L0A/L0B/L0C/GM workspace overflow 由 feasibility gate 处理。

### 9.2 Shape regularization penalty

```text
P_shape = shape_regularization_penalty(tile_m, tile_n, tile_k, tail_strategy, alignment)
```

它用于惩罚过碎、过不规则、对齐差或 tail 处理代价高的 tile。

### 9.3 Legality risk penalty

```text
P_legality = sync_unknown_penalty + event_reuse_penalty + cv_estimated_penalty
```

它用于表达 demo 阶段无法证明 GraphSyncSolver deadlock-free、event reuse 合法性或 CV pipeline legality 的不确定性。

---

## 10. 与原 V3.3 的关键区别

原 V3.3 的 artifact kernel profile 已经能使用 MLIR 与产物结构证据，但权重传播偏宽，存在 double counting 风险。例如 scalar/sync-heavy 证据可能同时：

```text
提高 scalar cost
提高 sync cost
提高 small tile penalty
压低 overlap reward
压低 CV reward
提高 legality/sync criticality multiplier
```

V3.3.1 收敛为：

```text
结构证据 -> 对应分项 cycle correction -> 汇总 total predicted cycles
```

主要变化：

| 位置 | 原 V3.3 | V3.3.1 |
|---|---|---|
| DES/MLIR 融合 | MLIR 35% + product 65% | MLIR 60% + product 40% |
| scalar evidence | 影响 scalar/sync/overlap/CV/small tile | 主要影响 scalar/control 和 fragmentation |
| sync evidence | 影响 sync、overlap、CV、criticality multiplier | 主要影响 sync cycles，risk 单独进入 penalty |
| overlap | 可能被结构证据大幅压低 | 只做窄范围 confidence 修正 |
| cost 语义 | 更像 weighted analytical score | 更像 corrected total cycle estimate |

---

## 11. 当前输出字段说明

`cost_breakdown` 中关键字段包括：

| 字段 | 含义 |
|---|---|
| `tau_load`, `tau_store` | 修正后的 load/store per-tile cycles |
| `tau_cube`, `tau_vector`, `tau_fix` | 修正后的 cube/vector/fix per-tile cycles |
| `load_exposed`, `store_exposed` | overlap 后暴露出来的 load/store cycles |
| `cube_vector_time` | cube/vector/fix pipeline 后的 compute 侧 cycles |
| `scalar_control_time` | scalar/control/address/schedule 的 per-tile cycles |
| `workspace_exposed` | GM workspace fallback/spill 的暴露成本 |
| `sync_cost` | 修正后的同步成本 |
| `memory_pressure_penalty` | 容量压力软惩罚 |
| `shape_regularization_penalty` | shape/tail/alignment 软惩罚 |
| `legality_risk_penalty` | 未验证策略的风险惩罚 |
| `parallelized_tile_cycles` | 乘以 tile 数并除以有效并行度后的 tile 主体成本 |
| `predicted_cycles` | 总 estimated cycles |

---

## 12. 当前边界

当前 cost model 仍然有以下边界：

1. `predicted_cycles` 是 analytical estimate，不是真机实测 cycles。
2. `kernel_cost_profile` 使用 MLIR 与产物结构证据，但不使用 msprof target。
3. DES pipe fraction 只作为 product artifact ratio，不作为 makespan/global scale。
4. 所有 correction factor 仍需要未来通过多 kernel 实机 profiling 数据离线训练。
5. GraphSyncSolver 的 UNKNOWN legality 只能通过 penalty 表达，不能证明真实 rewrite 安全。

---

## 13. 最推荐的汇报表述

可以这样介绍当前版本：

```text
当前 cost model 的目标仍然是估计总 cycles。我们先基于 tile、buffer、pipeline、sync plan 和硬件参数计算 load、compute、store、sync、scalar/control 的基础 cycles，再用 MLIR 与编译产物中的结构证据对对应分项做 cycle correction，最后汇总得到 total predicted cycles。结构证据不是额外打分项，也不是实机 profiling 校准，而是用于修正 analytical model 的系统性偏差。
```

也可以更短地说：

```text
V3.3.1 是 structure-aware cycle estimation model，不是 profiling-calibrated hardware performance model。
```
