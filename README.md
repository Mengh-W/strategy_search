# HIVM / AscendNPU-IR 四类 Plan 参数寻优 Demo

本项目是一个面向 **HIVM / AscendNPU-IR / NPUIR 风格 MLIR kernel** 的 strategy-level analytical search demo。它的目标不是替代真实 HIVM 编译器，也不是直接输出真机 msprof 性能，而是在没有完整 compiler pass、dry-run、DES 仿真闭环或 msprof 的情况下，对 HIVM 中最核心的四类优化机制进行参数建模、硬件边界检查、解析式 cost 评估、候选寻优和可解释报告生成。

当前 demo 把一个策略候选统一表示为：

```text
x = (T, M, P, Y)
```

其中：

| 符号 | Plan | 主要职责 | 是否进入寻优 | 是否进入 cost model / hardware gate |
|---|---|---|---|---|
| `T` | `TilingPlan` | tile 形状、block 并行度、loop 顺序、tail 策略、reduce 维切分 | 是 | 是 |
| `M` | `MultiBufferPlan` | double buffer、per-buffer multiplier、stage buffer、load/store overlap | 是 | 是 |
| `P` | `CVPipelinePlan` | Cube/Vector 软流水、pipeline stage、CV 模板、producer-consumer 距离 | 是 | 是 |
| `Y` | `SyncPlan` | keep existing / graph sync solver、event reuse、sync 粒度、sync motion | 是 | 是 |

一句话概括：

```text
输入 MLIR → 恢复 current IR 策略 → 生成四类 Plan 候选 → 硬件 gate → cost model 排序 → 输出报告 / 可选 rewrite bundle
```

---



## V3.3.1：Structure-aware Cycle Correction Cost Model

V3.3.1 的核心定位是：**目标仍然是估计总 cycles**，但 MLIR 与编译产物不再作为额外打分项，而是用于修正各个分项 cycles 的基础估计误差。

更准确地说，本版本的 `predicted_cycles` 是：

```text
predicted_cycles =
    corrected_tile_cycles
  + corrected_sync_cycles
  + memory_capacity_penalty
  + shape_regularization_penalty
  + legality_risk_penalty
```

其中 `corrected_*_cycles` 仍然是 analytical estimate，不是真机 msprof cycles。在线寻优阶段不读取实机 profiling target，也不使用 DES makespan/global scale 做单样本校准。实机数据只应在离线阶段用于训练或校准 config 里的超参数。

### 0.1.1 为什么需要结构证据

基础 cost model 可以根据 tile shape、dtype bytes、带宽、吞吐和同步操作数量估计：

```text
T_load_base, T_store_base, T_cube_base, T_vector_base, T_sync_base, T_scalar_base
```

但这些基础项比较粗。例如同样的 `tile_m=64, tile_n=128, tile_k=64`，放在不同 kernel 里含义完全不同：

| kernel 结构 | 同样策略的真实含义 |
|---|---|
| cube-heavy | double buffer / CV pipeline 可能更有效 |
| memory-heavy | load/store exposed time 和 workspace traffic 更关键 |
| scalar/control-heavy | index/cast/control/schedule overhead 可能吃掉 pipeline 收益 |
| sync-heavy | event/barrier/wait 可能让 GraphSyncSolver 风险变高 |

所以 V3.3.1 使用 MLIR 与产物结构证据来修正分项 cycles，而不是直接给候选加一个抽象 score。

### 0.1.2 当前如何利用结构化信息

V3.3.1 会从 MLIR 和产物文件中抽取结构证据，包括：

- flat op counts：Cube、Vector、MTE/Layout、Sync、Scalar/Control/Address；
- loop-weighted op counts：内层循环中的 scalar/sync/memory/vector/compute 操作权重更高；
- memory space-path traffic：GM/UB/L1/L0 等空间路径上的静态 bytes 与 copy/layout 路径；
- buffer lifetime：局部 buffer 的 live span、byte-span pressure、per-buffer double-buffer benefit proxy；
- sync criticality proxy：内层同步、跨 pipe event pair、set/wait 配对缺失等；
- alignment/tail/mask proxy：shape 对齐、offset 对齐、mask/tail 操作密度；
- op sequence patterns：copy -> nd2nz -> cube、cube -> fixpipe -> vector、vector -> store 等流水机会；
- DES/trace JSON 中的 pipe mix、DMA path、sync/event name count 等结构信息。

结构证据先被归一化为：

```text
compute_ratio, memory_ratio, vector_ratio, scalar_ratio, sync_ratio
```

如果 DES 产物可用，当前采用保守融合：

```text
structure_ratios = 0.60 * MLIR_static_ratios + 0.40 * product_artifact_ratios
```

这样可以利用 lowering 后的产物结构信息，但避免 DES pipe fraction 单点过度主导模型。

### 0.1.3 结构证据如何进入分项 cycles

这些证据会被汇总到 `kernel_cost_profile.json`，生成一组 **cycle correction factors**：

| correction factor | 主要修正对象 | 证据来源 | 设计原则 |
|---|---|---|---|
| `memory_cycle_correction` | load/store cycles | memory ratio、DMA path、memory path bytes | memory 证据只修正搬运相关 cycles |
| `compute_cycle_correction` | cube compute cycles | cube op、compute ratio、CV opportunity | compute 证据不直接制造 reward，只修正 compute estimate |
| `vector_cycle_correction` | vector cycles | vector op、alignment/tail proxy | vector 与 alignment 影响 vector/fixpipe 估计 |
| `scalar_cycle_correction` | scalar/control cycles | scalar/control op、loop-weighted scalar | scalar 证据主要进入 scalar/control 项 |
| `sync_cycle_correction` | sync cycles | barrier、set/wait、sync criticality | sync 证据主要进入 sync 项 |
| `workspace_pressure_correction` | workspace exposed cycles | buffer lifetime、workspace pressure | 只修正额外 workspace traffic |
| `overlap_confidence` | load/store overlap ratio | scalar/sync/memory/CV opportunity | 只在窄范围内修正 overlap 可信度 |
| `cv_overlap_confidence` | cube-vector overlap ratio | compute/vector balance、sync/scalar density | 只在窄范围内修正 CV overlap 可信度 |

注意：旧字段名如 `scalar_control_multiplier`、`overlap_reward_scale` 仍作为兼容 alias 保留，但新语义是 cycle correction / overlap confidence，不再表示额外 ranking reward。

### 0.1.4 主公式

单 tile 的估计成本为：

```text
T_tile =
    max(T_load_exposed, T_compute_corrected, T_store_exposed)
  + T_scalar_corrected
  + T_workspace_exposed
  + T_schedule
  + T_warmup_drain
```

其中：

```text
T_load_corrected  = T_load_base  * memory_cycle_correction * memory_path_cycle_correction
T_store_corrected = T_store_base * memory_cycle_correction * memory_path_cycle_correction

T_cube_corrected   = T_cube_base   * compute_cycle_correction
T_vector_corrected = T_vector_base * vector_cycle_correction * alignment_cycle_correction
T_fix_corrected    = T_fix_base    * memory_cycle_correction * alignment_cycle_correction

T_compute_corrected =
    T_cube_corrected
  + T_vector_corrected
  - r_cv_strategy * cv_overlap_confidence * min(T_cube_corrected, T_vector_corrected)
  + T_fix_corrected

T_scalar_corrected = T_scalar_base * scalar_cycle_correction * small_tile_fragmentation_correction
T_sync_corrected   = T_sync_base   * sync_cycle_correction
```

overlap 只作用在 load/store 暴露部分和 cube-vector overlap：

```text
T_load_exposed  = T_load_corrected  * (1 - r_load_strategy  * overlap_confidence)
T_store_exposed = T_store_corrected * (1 - r_store_strategy * overlap_confidence)
```

总成本为：

```text
T_total =
    N_tiles / effective_parallelism * T_tile
  + T_sync_corrected
  + P_memory_capacity
  + P_shape
  + P_legality
```

这里 `P_legality` 专门表达 GraphSyncSolver / event reuse / CV pipeline legality 不确定性；它不再混入 sync cycles 的语义里。

### 0.1.5 和 V3.3 的区别

原 V3.3 的结构权重更像：

```text
结构证据 -> 多个 multiplier/reward/penalty -> total predicted cycles
```

同一个 scalar/sync-heavy 证据可能同时影响 scalar cost、sync cost、small tile penalty、overlap reward、CV reward、legality risk，容易出现 double counting。

V3.3.1 收敛为：

```text
结构证据 -> 对应分项 cycle correction -> 汇总 total predicted cycles
```

| 方面 | V3.3 | V3.3.1 |
|---|---|---|
| 总体语义 | structure-aware weighted cost | structure-aware corrected cycle estimate |
| 结构证据用途 | 可同时影响多个 cost/reward/penalty | 每类证据主要修正对应分项 cycles |
| scalar evidence | scalar、small tile、sync、overlap、CV reward 多路径影响 | 主要进入 scalar/control 和 fragmentation |
| sync evidence | sync multiplier、criticality multiplier、risk 可能叠加 | sync cycles 与 legality risk 分离 |
| overlap | 可能被 scalar/sync 较强打折 | 只做窄范围 confidence 修正 |
| DES artifact 权重 | 产物比例更强，容易主导 | MLIR 60% + artifact 40% 保守融合 |
| predicted_cycles 语义 | 更像 cycles-shaped ranking score | 更像 corrected component cycles sum |

更详细的公式、字段解释、样本解释和 V3.3 对比见 `cost_model_design_formula_explained.md` 或渲染后的 `cost_model_design_formula_explained_rendered.pdf`。

## 0.3 搜索质量审计说明（V3.2-stage2c）

在没有 profiling 数据时，当前版本新增 `--enable-search-quality-audit`，用于在紧凑候选空间上对 Beam Search 做两个基线对照：

- small-space exhaustive：小空间穷举，检查 Beam best 与紧凑空间全局最优之间的 gap；
- random baseline：固定随机种子和采样预算，检查 Beam Search 相对随机搜索是否更稳定。

审计结果写入 `search_audit.json` 的 `search_quality_audit` 字段，并在 Markdown/HTML 报告中摘要展示。该功能不证明真实硬件最优，只用于验证 Beam Search 在 bounded subspace 上的搜索质量。

## 0.2 搜索稳定性说明（V3.2-stage2b）

V3.2-stage2b 在 stage2a 的搜索空间包含性基础上，进一步加入 diversity-preserving Layer-1 Beam Search。Layer-1 frontier 现在不再只由 coarse cost Top-W 决定，而是由以下几部分合并得到：

```text
cost_topw + diversity representatives + pinned standard survivors + deterministic fallback
```

这样可以降低 expanded/full 搜索空间中由于候选更多导致 standard 好候选被粗筛挤掉的风险。每次运行会在 `search_audit.json` 和 HTML/Markdown 报告中记录 diversity 新增候选数、pinned standard survivors 数量、fallback 新增候选数和最终 Layer-1 kept 数量。

详细说明见 `STAGE2B_BEAM_SEARCH_STABILITY.md`。

## 0. 工程结构说明（Stage 3）

为了让代码仓从单文件 demo 逐步演进成可长期维护的项目，当前版本已经引入 `strategy_search/` 包结构，并保留原有 `auto_strategy_search.py` 作为兼容入口。

推荐入口仍然兼容旧命令：

```bash
python auto_strategy_search.py --kernel sample_input/fa_bad_inefficient.hivm.mlir --hardware-config configs/ascend_910b.json
```

也可以使用包形式入口：

```bash
python -m strategy_search.cli --kernel sample_input/fa_bad_inefficient.hivm.mlir --hardware-config configs/ascend_910b.json
```

当前模块边界如下：

| 模块 | 职责 | 说明 |
|---|---|---|
| `strategy_search.core` | 当前兼容核心实现 | 保留完整算法逻辑，保证行为不变 |
| `strategy_search.plans` | Plan / Feature 数据结构 | 导出 `StrategyConfig`, `KernelFeatures`, `TilingPlan` 等 |
| `strategy_search.parser` | IR 解析与证据抽取 | 导出 `parse_kernel_features`, `extract_mlir_evidence` 等 |
| `strategy_search.hardware` | 硬件容量、footprint、feasibility | 导出 `memory_cap_bytes`, `estimate_max_live`, `feasibility` 等 |
| `strategy_search.cost_model` | risk-aware analytical cost model | 导出 `estimate_cost`, `build_four_plan_bundle`, risk/penalty 相关函数 |
| `strategy_search.search` | 参数空间生成与搜索 | 导出 `auto_generate_search_space`, `build_layered_candidates` 等 |
| `strategy_search.report` | JSON/Markdown/HTML 报告输出 | 导出 `write_html_report`, `write_markdown_report` 等 |
| `strategy_search.rewrite` | annotation / sidecar rewrite bundle | 导出 `emit_strategy_rewrite_outputs` 等 |
| `strategy_search.cli` | 包形式 CLI 入口 | 支持 `python -m strategy_search.cli` |

注意：本阶段是**兼容优先的工程结构化**。为了避免一次性大拆造成行为漂移，核心实现暂时集中在 `strategy_search.core`，其他模块作为稳定 facade 暴露清晰 API。后续阶段可以继续把 `core` 中的实现逐步物理拆分到各模块中。


---

## 0.1 搜索空间稳定性说明（V3.2-stage2a）

当前版本新增了 **Stage2a 搜索空间稳定性机制**，目标是在不引入 profiling 数据、不改变 cost model 主公式的前提下，先解决 layered beam search 的候选空间稳定性问题。

核心改动包括：

| 机制 | 作用 | 输出位置 |
|---|---|---|
| `strategy_signature` | 为候选策略生成稳定签名，忽略易变的 `strategy_id`，用于 exact dedup 和回归测试 | `strategy_search.plans` |
| standard tile containment | `expanded/full` 搜索空间显式包含 `standard` tile 候选，避免更大空间反而丢掉代表点 | `effective_search_space.json` |
| standard Layer-1 pinning | 在 `expanded/full` 模式下，先计算 standard 模式的 Layer-1 survivor，并强制保留到 expanded Layer-1 frontier | `search_audit.json` |
| exact candidate dedup | 对完整四 Plan 策略按 `strategy_signature` 去重，避免完全重复候选进入排序 | `search_audit.json` |
| post-relax dedup | relax 后再次按 signature 去重，避免不同候选 relax 成同一个策略后重复进入 Top-K | `search_audit.json` |
| search audit | 记录搜索空间、Layer-1 pinning、候选去重和 relax 后去重信息 | `search_audit.json` / 报告摘要 |

这一步不是 Stage2b 的 diversity-preserving beam。Stage2a 的目标更基础：

```text
expanded/full 搜索空间不能因为候选更多而无意丢掉 standard 搜索空间的关键候选；
搜索过程中的 exact duplicate 要被识别和记录；
搜索审计信息要可追踪、可回归。
```

示例运行：

```bash
python -m strategy_search.cli \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --candidate-space expanded \
  --search-mode layered \
  --guided-mode off \
  --cost-risk-mode conservative \
  --cost-model-config configs/cost_model_conservative.json \
  --output-dir output_stage2a
```

关键审计文件：

```text
search_audit.json
```

其中会包含：

```json
{
  "stage": "V3.2-stage2a-search-space-stability",
  "standard_candidates_included": true,
  "layer1_stability_audit": {
    "policy": "cost_topw_plus_pinned_standard_layer1_survivors",
    "pinned_standard_after_topw": 11
  },
  "candidate_dedup_audit": {
    "dedup_key": "strategy_signature_without_strategy_id"
  },
  "post_relax_legal_dedup_audit": {
    "dedup_removed_after_relax": 588
  }
}
```

## 1. 项目定位与边界

### 1.1 当前已经实现

当前代码仓已经实现了以下能力：

| 能力 | 当前状态 | 说明 |
|---|---|---|
| MLIR 静态解析 | 已实现 | 解析 memref、memory scope、mmad、vector op、copy/fixpipe、sync op 等信息 |
| Current IR baseline 修正 | 已实现 | 不再使用人为构造 baseline，而是从输入 IR 恢复 `current_ir_estimated_strategy` |
| 四类 Plan 参数空间生成 | 已实现 | 自动生成 `TilingPlan / MultiBufferPlan / CVPipelinePlan / SyncPlan` 候选 |
| 硬件容量边界 gate | 已实现 | 检查 UB/L1/L0A/L0B/L0C/GM workspace 容量、tile 对齐、block_dim 边界 |
| Analytical cost model | 已实现 | 输出 `predicted_cycles` 和详细 `cost_breakdown` |
| 分层寻优 | 已实现 | 支持 `layered` 与 `exhaustive` 两种搜索模式 |
| 中文 HTML / Markdown 报告 | 已实现 | 适合汇报展示和工程审计 |
| 可选 strategy-to-HIVM rewrite bundle | 支持 | 输出 annotated IR、safe structural IR、pass config、edit script 等候选制品 |

### 1.2 当前不能过度承诺

当前 demo 不应该被描述为：

```text
完整生产级 HIVM compiler optimizer；
能够直接输出真实 optimized.hivm.mlir 并保证可编译运行；
能够给出真实 NPU cycles；
能够证明 GraphSyncSolver 的依赖正确性、死锁安全性和 event id 分配合法性。
```

更准确的定位是：

```text
这是一个 strategy-level optimizer / analytical search demo。
它能比较同一输入 kernel 下不同策略的相对优劣，解释四类 Plan 参数如何影响 cost 和硬件边界，
但 predicted_cycles 仍然是解析式估计，不是真机实测时间。
```

---

## 2. 整体运行流程

### 2.1 流程总览

```text
Step 1  输入 HIVM / NPUIR / MLIR kernel
        ↓
Step 2  解析 kernel 静态结构 KernelFeatures
        ↓
Step 3  恢复 current IR estimated strategy
        ↓
Step 4  根据 shape / memory / hardware 自动生成四类 Plan 参数空间
        ↓
Step 5  Layer-1：Tiling 粗筛，做容量、对齐、block_dim gate
        ↓
Step 6  Layer-2：组合 MultiBuffer / CVPipeline，重新估计 max-live 和 overlap
        ↓
Step 7  Layer-3：组合 SyncPlan，计算完整 predicted_cycles
        ↓
Step 8  选择 predicted_cycles 最低的合法候选
        ↓
Step 9  输出 JSON / Markdown / HTML 报告，以及可选 rewrite bundle
```

### 2.2 输入解析内容

输入文件可以是：

```text
.hivm.mlir
.npuir.mlir
.mlir
```

系统按文件内容解析，而不是只按后缀判断。主要抽取以下证据：

| 抽取信息 | 用途 |
|---|---|
| `memref<...>` shape / dtype / address space | 推断 problem shape、buffer 大小、存储层级、tile 证据 |
| `gm / ub / cbuf / cc / l0a / l0b / l0c` | 估计不同 memory scope 的 footprint 和 max-live |
| `hivm.hir.mmad / hivm.hir.mmadL1` | 识别 Cube 计算，推断 tile_m/tile_n/tile_k |
| `nd2nz / copy / load / store / fixpipe` | 识别搬运、layout transform 和 Cube 输出路径 |
| `vadd / vmul / vexp / vdiv / vreduce / softmax-like op` | 识别 Vector 计算和 CV pipeline 潜力 |
| `set_flag / wait_flag / pipe_barrier / sync_block_*` | 识别显式同步负担 |
| `multi_buffer = 2`、`ping/pong` | 判断输入 IR 是否已有 double buffer / staged buffer |
| `cube_loop / vector_loop` | 判断输入 IR 是否已有 CV pipeline 结构 |
| `hivm.sync = "graph_sync_solver"` | 判断输入 IR 是否已有 graph sync 方向的同步状态 |

### 2.3 Current IR baseline 的修正

旧版 demo 曾使用人为构造的 baseline，容易出现一个问题：即使把 optimized / target IR 作为输入，仍然可能显示虚高 speedup。

当前版本改为：

```text
current IR estimated strategy → best searched strategy
```

也就是说，系统会先根据输入 IR 当前已有结构恢复一个：

```text
current_ir_estimated_strategy
```

再计算：

```text
predicted_speedup_vs_current_ir_estimated
= current_ir_estimated_predicted_cycles / best_predicted_cycles
```

恢复规则包括：

| IR 可见特征 | current IR 策略恢复 |
|---|---|
| 输入 IR 中解析出的 tile shape | 作为 current tile |
| `multi_buffer = 2` 或 ping/pong buffer | `double_buffer=True` |
| `cube_loop / vector_loop` | `cv_pipeline_stage=2` |
| `hivm.sync="graph_sync_solver"` | 当前 IR 已有 graph sync 证据 |
| 显式 `set_flag/wait_flag/pipe_barrier` | 当前 IR 同步负担较重，cost 中保留同步开销 |
| 无显式 sync op | 当前 IR sync cost 较低 |

注意：`current_ir_estimated_predicted_cycles` 仍然是 analytical estimate，不是真机实测时间。

---

## 3. 四个参数 Plan 的设计

当前项目将策略空间显式拆成四类 Plan。这样做的好处是：每类参数的工程语义清楚，并且可以分别解释它们如何影响硬件容量、pipeline overlap、sync cost 和最终 predicted cycles。

---

### 3.1 TilingPlan

```text
TilingPlan = {
  tile_m,
  tile_n,
  tile_k,
  block_dim,
  loop_order,
  tail_strategy,
  reduce_tile_policy,
  layout_aware_tile
}
```

| 参数 | 取值来源/范围 | 工程含义 | 对 cost / gate 的影响 |
|---|---|---|---|
| `tile_m` | shape divisor、Cube alignment、常见 tile 值 | M 维 tile 大小 | 影响 L0A/L0C/UB 工作集、tile 数、Cube FLOPs |
| `tile_n` | shape divisor、Cube alignment、preferred tile_n | N 维 tile 大小 | 影响 L0B/L0C/UB 工作集、store bytes、tail penalty |
| `tile_k` | reduce 维、Cube K alignment、常见 tile 值 | K/reduce 维 tile 大小 | 影响 L0A/L0B/L1 输入工作集和 reduce loop |
| `block_dim` | 根据 tile 数和 core 数派生 | 并行 block 数 | 影响 effective parallelism；受 core 数和 tile 数限制 |
| `loop_order` | `outer_mnk / outer_mkn / outer_nmk` | 外层 tile loop 顺序 | 影响 locality 和 load 修正系数 |
| `tail_strategy` | `mask_or_pad / peel / pad` | shape 不整除 tile 时的尾块处理 | pad 增加搬运，peel 降低搬运但增加控制成本 |
| `reduce_tile_policy` | `full_k / half_k` | reduce 维是否拆小 | `half_k` 可降低单 tile 容量压力，但增加调度/循环成本 |
| `layout_aware_tile` | `true / false` | 是否偏好 layout/Cube-friendly tile | 影响 load/store 修正和 shape regularization |

TilingPlan 是四类 Plan 的基础，因为 tile 先决定单 tile 工作集、tile 数、L0/L1/UB 占用和并行粒度。后续 MultiBuffer 和 CVPipeline 是否可行，都依赖当前 tile 是否还有足够片上存储余量。

---

### 3.2 MultiBufferPlan

```text
MultiBufferPlan = {
  double_buffer,
  multibuffer_template,
  stage_buffer_policy,
  buffer_multipliers_json,
  ub_multiplier,
  l1_multiplier
}
```

| 参数 | 当前含义 | 对 cost / gate 的影响 |
|---|---|---|
| `double_buffer` | 是否启用高层 double buffer / ping-pong 策略 | 提高 load/store overlap，但增加 live buffer 压力 |
| `multibuffer_template` | `M0_no_multibuffer / M1_input_double_buffer / M4_cv_stage_aware_multibuffer` 等 | 影响 `load_overlap_ratio`、`store_overlap_ratio` 和轻量 template overhead |
| `stage_buffer_policy` | `none / ub_stage / l1_stage / l1_reuse / gm_workspace` 等 | 决定 stage buffer 主要压 UB、L1 还是 fallback 到 GM workspace |
| `buffer_multipliers_json` | 对代表性 local buffer 使用 `nbuf_b ∈ {1,2}` | 具体 buffer 级 ping-pong 额外副本进入 max-live 和 overlap bonus |
| `ub_multiplier / l1_multiplier` | 兼容字段 | 当前主要保留字段语义，实际搜索更依赖 per-buffer multiplier |

说明：per-buffer multiplier 没有完整枚举所有 buffer 的 `2^N` 组合，而是筛选代表性 local buffer 做受控候选生成，避免组合爆炸。

MultiBufferPlan 的核心 trade-off 是：

```text
更高 overlap  ↔  更高 UB/L1/L0 live buffer 压力
```

---

### 3.3 CVPipelinePlan

```text
CVPipelinePlan = {
  cv_pipeline_stage,
  cv_pipeline_template,
  enable_mixed_cv,
  tile_mix_cube_loop,
  tile_mix_vector_loop,
  auto_cv_balance,
  producer_consumer_distance
}
```

| 参数 | 当前含义 | 对 cost / gate 的影响 |
|---|---|---|
| `cv_pipeline_stage` | `1 / 2 / 4`，分别表示无 pipeline、stage-2 pipeline、更激进 pipeline | 提高 Cube/Vector overlap，但增加 stage buffer 压力和 warmup/drain |
| `cv_pipeline_template` | `P0_no_cv_pipeline / P1_stage2_basic / P2_stage2_balanced / P_PREFILL_LARGE_SBS_REUSE` 等 | 影响 `cv_overlap_ratio`、warmup/drain、template overhead |
| `enable_mixed_cv` | 是否允许 Cube-heavy / Vector-heavy 混合调度 | 影响 Cube/Vector overlap 建模 |
| `tile_mix_cube_loop` | Cube loop 在混合调度中的相对粒度 | 影响 CV mix balance penalty |
| `tile_mix_vector_loop` | Vector loop 在混合调度中的相对粒度 | 影响 CV mix balance penalty |
| `auto_cv_balance` | 是否根据 Cube/Vector 压力自动平衡 overlap | 影响 `cv_overlap_ratio` 的修正 |
| `producer_consumer_distance` | Cube 产出与 Vector 消费之间的 pipeline 距离 | 影响 overlap 折减和 producer-consumer 调度开销 |

CVPipelinePlan 的核心目标是让 Cube 和 Vector 不再完全串行，而是形成软流水：

```text
Cube compute 和 Vector compute 可重叠的部分，最多不超过 min(tau_cube, tau_vector)。
```

---

### 3.4 SyncPlan

```text
SyncPlan = {
  sync_policy,
  sync_template,
  barrier_level,
  event_reuse,
  sync_granularity,
  event_id_policy,
  sync_motion
}
```

| 参数 | 当前含义 | 对 cost / gate 的影响 |
|---|---|---|
| `sync_policy` | `keep_existing / graph_sync_solver` | 决定同步成本是否保留现有模式或进入 graph sync 抽象估计 |
| `sync_template` | `Y0_keep_existing / Y1_conservative_barrier / Y2_graph_sync_solver / Y3_event_reuse` | 影响 barrier/event 估计数量、stall factor、fixed overhead |
| `barrier_level` | 同步保守程度 | 影响 barrier penalty |
| `event_reuse` | 是否复用 event id | 降低 set/wait event 负担 |
| `sync_granularity` | `op / tile / stage` | 同步粒度越粗，理论次数越少，但真实正确性需要 compiler proof |
| `event_id_policy` | `keep / reuse / compact` 等抽象字段 | 影响 event stall 和同步开销 |
| `sync_motion` | `none / local_move` 等抽象字段 | 估计局部 sync motion 的收益 |

注意：当前 demo 只能估计 sync cost，不能证明 graph sync 的依赖正确性、死锁安全性或 event id 分配合法性。

---

## 4. 参数空间自动生成

参数空间不是手写一个固定模板，也不是完整枚举 HIVM 全部 pass，而是结合输入 MLIR、硬件配置和搜索密度自动生成。

支持三种候选密度：

| 参数 | 含义 |
|---|---|
| `--candidate-space standard` | 快速代表性搜索，适合 smoke test |
| `--candidate-space expanded` | 更密集的工程候选，推荐用于 demo 展示 |
| `--candidate-space full` | 更大的离散网格，可能较慢 |

支持两种搜索方式：

| 参数 | 含义 |
|---|---|
| `--search-mode layered` | 分层 / beam search，默认推荐 |
| `--search-mode exhaustive` | 对 demo 搜索空间做更展开的枚举，但不等价于真实 compiler oracle |

### 4.1 block_dim 的派生逻辑

`block_dim` 不是完全自由变量，而是由 tile 数量和硬件 core 数共同派生：

```text
block_dim <= available_cores
block_dim <= num_tiles
```

这样避免两类不合理候选：

| 不合理情况 | 原因 |
|---|---|
| `block_dim` 大于硬件可用 core 数 | 超出真实并行资源 |
| `block_dim` 远大于 tile 数 | 大量 block 没有实际工作，parallelism 估计虚高 |

程序会优先保留 full-core、half-core、quarter-core、tile-count boundary 等代表性点，而不是盲目枚举所有整数。

### 4.2 四类 Plan 不是独立打分

虽然参数空间被拆成四类 Plan，但最终 cost model 是统一的：

```text
x = (T, M, P, Y)
predicted_cycles = CostModel(x)
```

也就是说，四个 Plan 不是各自独立打分后加权投票，而是共同改变同一组中间变量：

```text
num_tiles
max_live
load/store bytes
Cube/Vector pipeline
sync cost
overlap ratio
effective parallelism
memory pressure penalty
shape regularization penalty
```

---

## 5. 硬件边界约束

硬件边界不是 cost model 的普通扣分项，而是候选进入排序之前必须通过的 legality gate。核心原则是：

```text
先保证候选 strategy 在真实片上存储层级中“放得下、对得齐、并行度不虚高”，
再允许 cost model 比较性能优劣。
```

### 5.1 硬件配置来源

硬件配置来自 JSON，例如：

```bash
configs/ascend_910b.json
```

程序从 `hardware_config.json` 的 `memory_spaces` 字段读取片上存储容量：

| Scope | 配置字段 | 当前含义 |
|---|---|---|
| `ub` | `memory_spaces.ub.size_kb` | Vector 计算、临时张量、mask、stage buffer 的主要容量边界 |
| `l1` / `cbuf` | `memory_spaces.l1.size_kb` | Cube 输入 staging、L1 reuse、部分 K/V staging 的容量边界 |
| `l0a` | `memory_spaces.l0a.size_kb` | Cube 左输入 tile 的容量边界 |
| `l0b` | `memory_spaces.l0b.size_kb` | Cube 右输入 tile 的容量边界，通常对 `tile_n × tile_k` 敏感 |
| `l0c` / `cc` | `memory_spaces.l0c.size_kb` | Cube accumulator / output tile 的容量边界 |
| `gm_ws` | `workspace_model` 或默认 workspace budget | GM workspace fallback / spill 的容量边界 |

主要代码入口：

```text
memory_cap_bytes(hw, space)
estimate_max_live(candidate, kernel_features, hw)
feasibility(candidate, max_live, hw)
```

### 5.2 max-live 估计公式

对一个候选策略：

```text
x = (T, M, P, Y)
```

每个 memory scope 的利用率为：

```text
util_S(x) = estimated_max_live_S(x) / capacity_S
```

其中：

```text
S ∈ {UB, L1, L0A, L0B, L0C, GM_WS}
```

max-live 估计采用：

```text
estimated_max_live_S(x)
= align_S( tile_working_set_S(T,M,P) + 0.08 × static_max_live_S(IR) )
```

含义如下：

| 项 | 说明 |
|---|---|
| `tile_working_set_S(T,M,P)` | 由 tile 大小、double buffer、CV stage、per-buffer multiplier、stage buffer policy 推导出的当前 tile 工作集 |
| `static_max_live_S(IR)` | 从输入 MLIR local buffer 中解析出的静态 max-live 近似 |
| `0.08 × static_max_live_S(IR)` | kernel 复杂度修正项，避免把静态 buffer 和合成 tile buffer 完全重复计算 |
| `align_S` | 按 scope 对齐：UB/L1 通常 32B，L0A/L0B/L0C 使用更粗的 512B 对齐近似 |

核心 working set 估计如下：

| Scope | 估计逻辑 | 主要受哪些 Plan 影响 |
|---|---|---|
| `l1` | `(tile_m×tile_k + tile_k×tile_n) × elem_bytes × double_buffer_multiplier × l1_multiplier` | `TilingPlan`、`MultiBufferPlan`、`reduce_tile_policy`、`stage_buffer_policy` |
| `l0a` | `tile_m × tile_k × elem_bytes` | `tile_m`、`tile_k` |
| `l0b` | `tile_k × tile_n × elem_bytes` | `tile_k`、`tile_n` |
| `l0c` | `tile_m × tile_n × accumulator_bytes` | `tile_m`、`tile_n` |
| `ub` | `tile_m × tile_n × vector/input/output staging`，再乘以 double buffer / stage / reuse 修正 | `tile_m`、`tile_n`、`double_buffer`、`cv_pipeline_stage`、`stage_buffer_policy` |
| `gm_ws` | CV handoff / spill fallback 对应的 off-chip workspace | `stage_buffer_policy=gm_workspace`、`cv_pipeline_stage`、`active_blocks` |

当前主路径近似：

```text
elem_bytes = 2          # bf16/fp16
accumulator_bytes = 4   # fp32 accumulator
```

### 5.3 硬约束 hard gate

候选必须满足：

```text
for S in {UB, L1, L0A, L0B, L0C, GM_WS}:
    estimated_max_live_S(x) <= capacity_S
```

或者等价地：

```text
max_S util_S(x) <= 1
```

若任意 scope 出现：

```text
util_S(x) > 1
```

该候选直接非法，不进入最终 ranking。

### 5.4 对齐与并行资源边界

当前 Ascend 910B 配置中常用 Cube/fractal 对齐为：

```text
tile_m % 16 == 0
tile_n % 16 == 0
tile_k % 16 == 0
```

同时检查基础搬运对齐：

```text
tile_n × elem_bytes 需要 32B 对齐
tile_k × elem_bytes 需要 32B 对齐
```

并行资源约束为：

```text
block_dim <= min(available_cores, num_tiles)
```

因此，当前硬件边界约束可以总结为：

| 约束类型 | 数学表达 | 作用 |
|---|---|---|
| 片上容量约束 | `estimated_max_live_S(x) <= capacity_S` | 防止 UB/L1/L0A/L0B/L0C/GM workspace overflow |
| Cube 对齐约束 | `tile_m,tile_n,tile_k` 满足 16 对齐 | 保证 tile 适合 Cube/fractal 计算 |
| 搬运对齐约束 | `tile_n×elem_bytes`、`tile_k×elem_bytes` 满足 32B 对齐近似 | 防止明显不合理的 DMA/ND2NZ 搬运 shape |
| 并行资源约束 | `block_dim <= min(available_cores, num_tiles)` | 防止 block 数超过 core 数或超过实际 tile 数 |
| GM workspace 约束 | `workspace_bytes(x) <= capacity_GM_WS` | 防止把 CV stage handoff / spill fallback 无限制放到 HBM |

### 5.5 软惩罚 soft penalty

如果候选没有超过容量，但某个 scope 利用率过高，则进入 memory pressure soft penalty，而不是直接拒绝：

```text
if util_S > threshold_S:
    penalty_S = alpha_S × ((util_S - threshold_S) / (1 - threshold_S))^2
else:
    penalty_S = 0
```

实际实现中还会做 per-scope cap：

```text
penalty_S = min(cap_S, penalty_S)
```

最终：

```text
memory_pressure_penalty = Σ_S penalty_S
```

区别如下：

| 情况 | 当前处理 |
|---|---|
| `util_S > 1` | hard reject，候选非法 |
| `threshold_S < util_S <= 1` | 候选合法，但加入 memory pressure soft penalty |
| `util_S <= threshold_S` | 候选合法，通常不加资源压力惩罚 |

### 5.6 relax 逻辑

如果候选超过硬件容量，demo 会尝试有限 relax，而不是马上全部丢弃。大致顺序是：

```text
level2 reuse → level1 → level0 → inplace
关闭 double buffer / 清空 per-buffer multiplier
降低 cv_pipeline_stage
缩小 tile_n
缩小 tile_k
缩小 tile_m
```

对应工程直觉是：

```text
先降低额外 buffer 和 pipeline 压力，再缩小 tile。
```

成功 relax 后的候选会记录到：

```text
relaxed_candidates.json
```

完全无法修复的候选会进入：

```text
rejected_candidates.json
```

---

## 6. Cost model 设计与公式展开

当前 cost model 的作用是对合法候选排序和解释优化方向。它不是精确性能模型，但会把输入 IR 的静态结构、四类 Plan 参数和硬件配置合成一个：

```text
predicted_cycles(x)
```

### 6.1 cost model 输入

| 输入 | 来源 | 作用 |
|---|---|---|
| `KernelFeatures` | 从 MLIR 解析 | 提供 shape、mmad 数、vector op 数、sync op 数、fixpipe/copy 证据 |
| `StrategyConfig` | 搜索空间生成 | 表示当前候选的四类 Plan 参数 |
| `hardware_config` | JSON 配置 | 提供 memory capacity、bandwidth、cube/vector throughput、core 数、校准参数 |
| `max_live` | `estimate_max_live` | 提供 UB/L1/L0A/L0B/L0C/GM workspace 利用率，用于 hard gate 和 soft penalty |
| optional DES / trace | `optional_profiles/*.json` | 作为 soft evidence 修正 pipeline fraction / sync scale，不作为真实 baseline |

### 6.2 总公式

当前主模型是：

```text
predicted_cycles(x)
= num_tiles(x) × steady_tile_time(x) / effective_parallelism(x)
  + sync_cost(x)
  + memory_pressure_penalty(x)
  + shape_regularization_penalty(x)
```

其中：

```text
x = (T, M, P, Y)
```

四类 Plan 共同影响同一个总公式，而不是分别独立评分。

---

### 6.3 Tile 数量

设整体问题规模为：

```text
M_total, N_total, K_total
```

当前候选 tile 为：

```text
tile_m, tile_n, tile_k
```

则 tile 数量为：

```text
num_tiles
= ceil(M_total / tile_m)
× ceil(N_total / tile_n)
× ceil(K_total / tile_k)
× outer_iterations
```

`M_total/N_total/K_total` 优先来自 MLIR 解析和 `search_space_demo.json` 中的 `problem_shape_hint`。

---

### 6.4 Load / Store 字节数与时间

基础搬运字节数：

```text
load_bytes
≈ (tile_m×tile_k + tile_k×tile_n + tile_m×tile_n) × elem_bytes

store_bytes
≈ tile_m×tile_n × elem_bytes
```

对应 cycles：

```text
tau_load
= load_bytes / bandwidth_mte2 + dma_startup

tau_store
= store_bytes / bandwidth_mte3 + dma_startup
```

其中：

```text
elem_bytes = 2
```

主要对应 bf16/fp16 主路径。

TilingPlan 和 DMA/layout 相关字段会对 load/store 做轻量修正：

| 参数 | 修正含义 |
|---|---|
| `reduce_tile_policy=half_k` | 单 tile 输入搬运略降，但 reduce loop 增多 |
| `layout_aware_tile=True` | 偏好 ND/NZ/Cube-friendly tile，load/store 略降 |
| `loop_order=outer_mkn` | 偏好 K locality，load 略降 |
| `tail_strategy=pad` | pad 会增加搬运 |
| `tail_strategy=peel` | peel 略减搬运但增加控制成本 |

---

### 6.5 Cube compute cost

Cube 计算按矩阵乘法 FLOPs 估计：

```text
flops_cube
= 2 × tile_m × tile_n × tile_k × max(1, num_mmad)
```

Cube 时间为：

```text
tau_cube
= flops_cube / cube_flops_per_cycle + cube_startup
```

其中：

```text
cube_flops_per_cycle
= cube_tflops_fp16 × 10^12 / frequency_hz
```

`cube_tflops_fp16` 和 `frequency_hz` 来自硬件配置。

---

### 6.6 Vector cost

Vector cost 按 vector op 数量和 tile 面积估计：

```text
vector_elements
= tile_m × tile_n × max(1, num_vector_ops)
```

基础时间为：

```text
tau_vector
= vector_elements / vector_width_elements + vector_startup
```

重型 vector op 会额外放大：

```text
heavy = 3×num_vexp + 2×num_vdiv + num_vreduce

tau_vector := tau_vector × (1 + 0.04 × heavy)
```

当前权重直觉：

| op 类型 | 当前处理 |
|---|---|
| `vexp` | 权重最高，约视为 simple op 的 4 倍影响 |
| `vdiv` | 中等偏重 |
| `vreduce` | 轻度额外开销 |
| `vadd/vmul/vsub` | simple op 基准 |

---

### 6.7 Fixpipe cost

Fixpipe 按 accumulator 输出搬运近似：

```text
tau_fix
= num_fixpipe × (tile_m × tile_n × accumulator_bytes)
  / bandwidth_mte3 × 0.20
```

其中：

```text
accumulator_bytes = 4
```

`0.20` 是当前解析式模型中的保守折算系数，用于表示 fixpipe 不完全等价于一次完整 store。

---

### 6.8 Cube/Vector pipeline 合成时间

如果没有 CV overlap，则：

```text
tau_cube_vector
= tau_cube + tau_vector + tau_fix
```

若启用 CV pipeline，则：

```text
tau_cube_vector
= tau_cube + tau_vector
  - cv_overlap × min(tau_cube, tau_vector)
  + tau_fix
```

含义是：Cube 和 Vector 可重叠部分最多不能超过两者中较短的一段。

`cv_overlap` 由 CVPipelinePlan 决定，并会受到以下因素影响：

| 参数 | 影响 |
|---|---|
| `cv_pipeline_stage` | stage 越深，理论 overlap 越高，但 warmup/drain 和容量压力也更高 |
| `cv_pipeline_template` | 不同模板给不同基础 overlap、调度开销和 warmup/drain |
| `enable_mixed_cv` | 允许 Cube-heavy / Vector-heavy 混合调度 |
| `auto_cv_balance` | 根据 Cube/Vector 压力轻度调节 overlap |
| `tile_mix_cube_loop / tile_mix_vector_loop` | 若 Cube/Vector 粒度不平衡，会进入 mix balance penalty |
| `producer_consumer_distance` | 距离过远会折减 overlap 并增加调度开销 |

---

### 6.9 Double buffer 后的暴露搬运时间

load/store overlap 后的暴露时间：

```text
load_exposed
= tau_load × (1 - load_overlap_ratio)

store_exposed
= tau_store × (1 - store_overlap_ratio)
```

`load_overlap_ratio` 和 `store_overlap_ratio` 主要由 MultiBufferPlan 决定：

| 参数 | 影响 |
|---|---|
| `double_buffer=True` | 提高 load/store overlap |
| `multibuffer_template=M1_input_double_buffer` | 增强输入双缓冲 overlap |
| `multibuffer_template=M4_cv_stage_aware_multibuffer` | 进一步考虑 CV stage aware overlap |
| `buffer_multipliers_json` | 对具体 local buffer 的 ping-pong 额外增加 overlap bonus |
| `stage_buffer_policy` | UB/L1/GM stage 不同，会影响 overlap 和 workspace cost |

如果启用了 double buffer 或 CV pipeline：

```text
steady_tile_time
= max(load_exposed, tau_cube_vector, store_exposed)
  + workspace_exposed
  + warmup_drain
  + template_schedule_overhead
```

如果没有启用 overlap：

```text
steady_tile_time
= tau_load + tau_cube_vector + tau_store
  + workspace_exposed
  + template_schedule_overhead
```

其中：

```text
warmup_drain
= (tau_load + tau_store + tau_cube_vector + workspace_exposed)
  × warmup_drain_factor
```

### 6.10 资源压力对 overlap 的折减

为了避免高资源利用率下 overlap 过度乐观，当前模型会根据 UB/L1/L0B/L0C 等 scope 的利用率降低 overlap：

```text
overlap_ratio := overlap_ratio × overlap_pressure_factor
```

也就是说，如果某个候选虽然没有 overflow，但 UB 或 L0B 已经非常紧张，那么它的 double buffer / CV pipeline overlap 不会被完全乐观兑现。

---

### 6.11 GM workspace fallback / spill cost

V2.8.7 之后，`gm_workspace` 被建模为更接近真实编译语义的 fallback / spill resource。它不是普通优化策略，也不是免费扩大 UB 的方式。

搜索优先级是：

```text
优先：UB stage buffer / L1 reuse
其次：调整 tile、降低 stage、降低 multibuffer 压力
最后：只有片上 stage-buffer 方案不可行时，才允许 GM workspace fallback
```

当候选满足：

```text
cv_pipeline_stage > 1
stage_buffer_policy = gm_workspace
```

会估算：

```text
handoff_bytes_per_stage
≈ tile_m × tile_n × elem_bytes × handoff_tensor_count
  + tile_m × tile_n × acc_bytes × partial_output_tensor_count × 0.25

workspace_bytes
= align32(handoff_bytes_per_stage × (stage - 1) × active_blocks)

workspace_traffic_per_tile
= handoff_bytes_per_stage × (stage - 1) × read_write_multiplier
```

并加入 hard gate：

```text
workspace_bytes <= capacity_GM_WS
workspace_bytes <= capacity_GM_WS × max_workspace_utilization
```

同时，如果片上方案可行，则拒绝 GM workspace fallback：

```text
if stage_buffer_policy == gm_workspace
   and require_onchip_infeasible == true
   and any(policy in {ub_stage, l1_reuse, none} is feasible):
       reject gm_workspace candidate
```

GM workspace read/write 会复用 MTE2/MTE3 通道，因此不是独立 lane，而是暴露 spill/fallback 代价：

```text
workspace_raw
= workspace_read_bytes / bandwidth_mte2
  + workspace_write_bytes / bandwidth_mte3
  + workspace_startup_cycles

workspace_exposed
= workspace_raw
  × (1 - workspace_overlap_ratio)
  × workspace_penalty_factor
```

所以 steady tile time 中是加法：

```text
steady_tile_time
= max(load_exposed, tau_cube_vector, store_exposed)
  + workspace_exposed
  + warmup_drain
  + template_schedule_overhead
```

---

### 6.12 模板类参数的 cost 映射：V3.0.1 重点

V3.0.1 修正了一个关键问题：template/hint 类参数如果只改变字段名、不改变 cost，就会导致 Top candidates 大量重复，看起来“在寻优”，但实际上参数没有真正影响模型。

当前原则是：

```text
只有当参数能改变 predicted cost、hardware gate 或最终 rewrite 行为时，才应作为有效寻优参数。
```

V3.0.1 将以下参数显式映射进 cost model：

| 参数 | 进入 cost model 的方式 |
|---|---|
| `multibuffer_template` | 影响 `load_overlap_ratio`、`store_overlap_ratio`，并增加轻量 per-tile schedule overhead |
| `cv_pipeline_template` | 影响 `cv_overlap_ratio`、`warmup_drain_factor` 和 CV 调度开销 |
| `tile_mix_cube_loop` / `tile_mix_vector_loop` | 影响 `tile_mix_balance_penalty` |
| `producer_consumer_distance` | 影响 CV overlap 折减和 `producer_consumer_distance_penalty` |
| `sync_template` | 影响 estimated barrier/event 数量、stall factor 和 fixed sync overhead |
| `event_id_policy` | 影响 event stall 和 event reuse 收益 |
| `sync_motion` | 影响同步移动收益估计 |

模板调度开销在总 tile time 中体现为：

```text
template_schedule_overhead
= mb_template_overhead
  + cv_template_overhead
  + tile_mix_penalty_cycles
  + producer_consumer_penalty_cycles
```

其中：

```text
mb_template_overhead
= (tau_load + tau_store) × mb_template_schedule_overhead_ratio

cv_template_overhead
= tau_cube_vector × cv_template_schedule_overhead_ratio

tile_mix_penalty_cycles
= tau_cube_vector × tile_mix_balance_penalty

producer_consumer_penalty_cycles
= tau_cube_vector × producer_consumer_distance_penalty
```

这样可以避免“模板字段不同但 predicted_cycles 完全相同”的大量重复候选。

---

### 6.13 Sync cost

同步成本来自输入 IR 中解析出的同步信号：

```text
raw_sync_ops
= num_pipe_barrier + num_set_flag + num_wait_flag + sync_block_ops
```

若候选使用 `sync_policy=keep_existing`，则基本保留原有同步负担。若使用 `graph_sync_solver`，则通过抽象 multiplier 估计 barrier/set/wait 减少效果。

当前公式为：

```text
sync_cost
= (num_barrier_estimated × barrier_unit_cost
   + (num_set_flag_estimated + num_wait_flag_estimated) × event_unit_cost)
  × stall_factor
  × sync_scale
  + template_fixed_overhead_cycles
```

其中：

```text
barrier_unit_cost = min(150, cycles_per_inner_iteration / 50)
event_unit_cost = 8
```

各参数影响如下：

| 参数 | 影响 |
|---|---|
| `sync_policy` | 决定保留原 sync 还是使用 graph sync 抽象估计 |
| `sync_template` | 改变 estimated barrier/event 数量、stall factor、fixed overhead |
| `barrier_level` | 控制 barrier 保守程度 |
| `event_reuse=True` | 降低 set/wait 负担 |
| `sync_granularity=op/tile/stage` | 粒度越粗，理论同步次数越少，但真实正确性需要 compiler proof |
| `event_id_policy=reuse/compact/keep` | 抽象估计 event id 复用收益 |
| `sync_motion=local_move` | 抽象估计局部同步移动收益 |
| optional DES sync evidence | 可作为 `sync_scale` 修正，不替代真实 GraphSyncSolver |

---

### 6.14 有效并行度

`block_dim` 不能直接当成有效并行度。当前模型会考虑 tile 数、core 数、waves 和 tail efficiency：

```text
active_blocks
= min(block_dim, available_cores, ceil(num_tiles))

waves
= ceil(num_tiles / active_blocks)

tail_efficiency
= num_tiles / (waves × active_blocks)

effective_parallelism
= active_blocks × tail_efficiency
```

这样可以避免：

```text
tile 数只有 8，但 block_dim 设置为 40，于是虚假获得 40 倍并行度。
```

---

### 6.15 Shape regularization penalty

为了避免 cost model 盲目偏好“刚好能塞进硬件的大 tile”，当前版本保留轻量 shape regularization，但已经取消原来的固定大额跳变惩罚。

当前 shape penalty 是连续、低权重、可封顶的 soft regularization：

```text
shape_regularization_penalty
= tail_penalty
  + irregular_tile_n_penalty
  + large_tile_n_penalty
```

尾块惩罚：

```text
tail_fraction
= min(tail, tile_n - tail) / tile_n

tail_penalty
= min(cap, alpha × tail_fraction^power)
```

不规则 tile_n 惩罚：

```text
distance_fraction
= abs(tile_n - nearest_preferred_tile_n)
  / max(64, tile_n, nearest_preferred_tile_n)

irregular_tile_n_penalty
= min(cap, alpha × distance_fraction^power)
```

过大 tile_n 惩罚：

```text
large_tile_n_penalty
= min(cap, alpha × ((tile_n - large_tile_n_soft_cap) / 64)^power)
```

这三项只应理解为轻量形状正则项，而不是 benchmark 含义的真实耗时。如果报告中 shape penalty 贡献过大，应优先审查 cost model calibration。

---

### 6.16 Cost breakdown 字段解释

`cost_breakdown.json` 中会保存以下关键字段：

| 字段 | 含义 |
|---|---|
| `per_tile_load_exposed` | overlap 后仍暴露的 load 时间 |
| `per_tile_store_exposed` | overlap 后仍暴露的 store 时间 |
| `per_tile_workspace_exposed` | GM workspace 读写后仍暴露的时间；未使用 workspace 时为 0 |
| `gm_workspace_bytes` | 该候选估计的 GM workspace live bytes |
| `gm_workspace_bytes_per_tile_total` | 每 tile workspace 读写总流量 |
| `per_tile_cube_vector_pipeline` | Cube/Vector/fixpipe 合成时间 |
| `template_schedule_overhead` | V3.0.1 中模板类参数引入的轻量调度开销 |
| `mb_template_overhead` | MultiBuffer 模板开销 |
| `cv_template_overhead` | CVPipeline 模板开销 |
| `tile_mix_penalty_cycles` | Cube/Vector tile mix 不平衡惩罚 |
| `producer_consumer_penalty_cycles` | producer-consumer 距离惩罚 |
| `parallelized_tile_cycles` | tile 时间除以有效并行度后的主体成本 |
| `sync_cost` | 同步成本 |
| `memory_pressure_penalty` | 资源压力惩罚 |
| `shape_regularization_penalty` | tile 形状正则惩罚 |
| `overlap_pressure_factor` | 高资源压力下 overlap 被压低的比例 |
| `tail_efficiency` | waves 尾部利用率 |

---

## 7. 寻优模式策略

### 7.1 优化目标

最终选择规则非常简单：

```text
best = argmin_x predicted_cycles(x)
subject to HardwareGate(x) = PASS
```

也就是说，guided mode 或诊断信息不会直接指定最优解；最终仍然由同一个 cost model 的 `predicted_cycles` 最小化决定。

---

### 7.2 Layered search

默认推荐：

```bash
--search-mode layered
```

它不是一次性对所有参数做笛卡尔积暴力枚举，而是拆成三层：

```text
Layer 1: Tiling 粗筛
Layer 2: MultiBuffer / CVPipeline allocation
Layer 3: SyncPlan refinement + 完整 cost 排序
```

对应代码入口：

```text
search_tiling_fusion(...)  # Layer 1
alloc_overlap(...)         # Layer 2
refine_inner(...)          # Layer 3
```

### 7.3 Layer 1：先找合法且有潜力的 tile

Layer 1 主要枚举：

```text
tile_m, tile_n, tile_k, block_dim,
loop_order, tail_strategy, reduce_tile_policy, layout_aware_tile
```

这一层只使用 single-buffer 近似做快速筛选：

```text
estimated_max_live_S(single_buffer) <= capacity_S
```

同时检查：

```text
Cube tile alignment
DMA basic alignment
block_dim <= min(available_cores, num_tiles)
```

粗 cost 近似为：

```text
coarse_cost
= num_tiles × (tau_load + max(tau_cube, tau_vector, tau_fix) + tau_store)
  + memory_pressure_penalty
  + shape_regularization_penalty
```

这一层的目标不是最终精确排序，而是排除明显不合法或明显低潜力的 tile。

### 7.4 Layer 2：在好 tile 上分配 overlap 机制

Layer 2 在 Layer 1 保留下来的 tile 上继续枚举：

```text
double_buffer
multibuffer_template
per-buffer multiplier
cv_pipeline_stage
cv_pipeline_template
stage_buffer_policy
load/store/CV overlap ratio
```

核心问题是：

```text
这个 tile 上，是否值得引入 double buffer？
是否有足够 UB/L1 余量支持 CV pipeline？
per-buffer multiplier 取 2 后是否会导致某个 scope overflow？
```

Layer 2 会重新估算：

```text
estimated_max_live_S(T, M, P)
= tile_working_set_S(T, M, P) + static_lifetime_correction_S(IR)
```

如果 double buffer、stage buffer 或 per-buffer multiplier 导致 overflow，该 allocation 会被拒绝或尝试 relax。

### 7.5 Layer 3：同步策略细化并完整排序

Layer 3 在已经通过容量检查的 `(T,M,P)` 上枚举 SyncPlan：

```text
sync_policy
sync_template
barrier_level
event_reuse
sync_granularity
event_id_policy
sync_motion
```

然后对完整候选：

```text
x = (T, M, P, Y)
```

计算完整：

```text
predicted_cycles(x)
```

最终选择 predicted_cycles 最低的合法候选。

### 7.6 为什么可以分层寻优

分层寻优成立的工程原因是四类 Plan 有明显依赖关系：

| 依赖关系 | 含义 |
|---|---|
| `TilingPlan` 决定基础工作集 | tile_m/tile_n/tile_k 先决定 L0A/L0B/L0C/UB/L1 基本占用 |
| `MultiBufferPlan` 依赖 tile | double buffer 和 per-buffer multiplier 的额外容量必须建立在某个 tile 的 working set 上 |
| `CVPipelinePlan` 依赖 tile 和 buffer 余量 | stage 越深，UB/L1 压力越大，所以必须知道 tile 和 buffer 后才能判断是否合法 |
| `SyncPlan` 对容量影响相对较小 | sync 主要影响 stall/cost，不主要改变 tile working set，因此适合放在最后细化 |

优点：

| 优点 | 说明 |
|---|---|
| 避免组合爆炸 | per-buffer multiplier 和 CV 模板如果全量笛卡尔积会快速膨胀 |
| 保留主要耦合关系 | Layer 2 会基于 Layer 1 的 tile 重新计算容量，不是简单独立打分 |
| 结果更可解释 | 报告能分别说明 tile、buffer/pipeline、sync 三层的作用 |

### 7.7 Exhaustive 与 guided mode

`--search-mode exhaustive` 用于小 kernel 或对照测试。它只是对 demo 搜索空间做更展开的枚举，不等价于完整 HIVM compiler oracle。

`--guided-mode` 可以作为诊断引导搜索空间的 soft bias。它可以帮助优先探索符合诊断方向的候选，但不能让非法候选通过，也不能压过 cost model。最终选择仍然是：

```text
min predicted_cycles among legal candidates
```

---

## 8. 输出文件与可视化展示

运行后会在 `--output-dir` 下生成：

| 文件 | 内容 | 怎么看 |
|---|---|---|
| `strategy_search_report.html` | 中文可视化报告 | 最适合汇报展示，直接浏览器打开 |
| `strategy_search_report.md` | 中文 Markdown 报告 | 适合粘贴到文档或代码评审 |
| `search_report.json` | 总报告 JSON | 包含 current IR、best strategy、top-k、search stats |
| `selected_strategy.json` | 最优候选策略 | 看 best candidate 和 current-IR reference |
| `selected_plan.json` | 最优候选四类 Plan sidecar | 看四个 Plan 的字段和 derived features |
| `top_candidates.json` | Top-K 候选列表 | 看排名靠前策略差异 |
| `top_plans.json` | Top-K 候选对应 plan sidecar | 比较不同 Plan 组合 |
| `hardware_boundary_audit.json` | 硬件边界检查结果 | 看容量、对齐、block_dim gate 是否通过 |
| `cost_breakdown.json` | cost breakdown | 看 predicted cycles 是由哪些项组成 |
| `buffer_life_report.json` | buffer lifetime / max-live 估计 | 看各 memory scope 的 max-live 和利用率 |
| `effective_search_space.json` | 实际生成的搜索空间 | 看参数空间是否真的展开 |
| `parameter_space_audit.json` | 参数空间审计 | 看四类 Plan 参数覆盖情况 |
| `rejected_candidates.json` | 被硬件 gate 拒绝的候选预览 | 看哪些候选因为 overflow / alignment 被拒绝 |
| `relaxed_candidates.json` | relax 后可行的候选预览 | 看系统如何修复原本不可行的候选 |

### 8.1 HTML 报告建议阅读顺序

汇报时建议按下面顺序看：

```text
1. 输入 kernel 与硬件配置
2. Search statistics：候选数量、合法数量、relax 数量
3. Current IR vs Best strategy：看 predicted speedup
4. Best strategy 四个 Plan 参数：看 T/M/P/Y 分别选了什么
5. Top-K candidates：看候选是否重复、排序是否合理
6. Cost breakdown：看收益来自 load/store overlap、CV overlap、sync 下降还是 penalty 变化
7. Hardware boundary：看 UB/L1/L0/GM workspace 是否都在容量内
8. Rejected / Relaxed candidates：看硬件 gate 是否真的生效
```

### 8.2 汇报口径

可以这样说：

```text
报告中的 predicted_cycles 是 analytical estimate。
它适合同一个 kernel 下比较不同 strategy 的相对优劣，
也适合解释四类 Plan 参数为什么影响 cost，
但不能直接当成真机 msprof cycles。
```

---

## 9. 运行示例

推荐使用 bad HIVM 输入演示，因为它更适合展示 demo 是否能识别缺陷并给出优化方向。

```bash
python auto_strategy_search.py \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --candidate-space expanded \
  --search-mode layered \
  --guided-mode off \
  --output-dir sample_outputs/bad_hivm_demo_run
```

本仓库已保存一次实际运行结果：

```text
sample_outputs/bad_hivm_demo_run/
```

可以重点查看：

```text
sample_outputs/bad_hivm_demo_run/strategy_search_report.html
sample_outputs/bad_hivm_demo_run/selected_strategy.json
sample_outputs/bad_hivm_demo_run/cost_breakdown.json
sample_outputs/bad_hivm_demo_run/hardware_boundary_audit.json
```

---

## 10. MLIR-derived Artifact Inputs (V3.3)

V3.3 支持读取 vTriton/HIVM analysis 从 `.npuir.mlir` 生成的结构化产物文件。推荐命名为：

```text
--artifact-des-graph <prefill_des.json>
--artifact-trace <prefill_trace.json>
```

这些文件是 **MLIR-derived artifacts**，不是实机 profiling 数据。V3.3 默认只使用其中的结构字段，不使用 DES makespan、真实 latency 或 global scale 校准。

| Artifact | 来源 | V3.3 使用方式 | 不使用的内容 |
|---|---|---|---|
| `prefill_des.json` | vTriton/HIVM analysis 对 MLIR 的 DES graph 导出 | pipe/op composition、dependency、sync/barrier/event、buffer read/write、memory path、loop multiplier、bytes/flops proxy | `max(end_cycle)` 作为 target、DES makespan/global scale |
| `prefill_trace.json` | DES schedule 的 Perfetto/Chrome trace 导出 | event-name counts、scalar/sync/memory/vector hints、sequence pattern evidence | 实机耗时、真实 kernel latency |

推荐命令：

```bash
python -m strategy_search.cli \
  --kernel sample_product/kernel_001.npuir.mlir \
  --hardware-config configs/ascend_910b.json \
  --artifact-des-graph sample_product/prefill_des.json \
  --artifact-trace sample_product/prefill_trace.json \
  --artifact-kernel-profile on \
  --des-calibration-mode off \
  --output-dir out_artifact_kernel_profile
```

兼容旧参数名，但不推荐在新文档中使用：

```text
--des-profile    -> --artifact-des-graph
--trace-profile  -> --artifact-trace
```

### 10.1 Artifact on/off 的含义

`--artifact-kernel-profile off`：使用原 analytical cost model，主要依赖 MLIR 静态解析、四类 Plan 参数和硬件约束。

`--artifact-kernel-profile on`：在 analytical cost model 上额外构建 `KernelCostProfile`，根据 MLIR + artifact 结构证据动态调整 compute、memory、vector、scalar、sync、overlap 和 risk 分项权重。

这不是：

```text
T_new = global_scale * T_old
```

而是：

```text
T_total =
    w_compute(kernel) * T_compute(plan)
  + w_memory(kernel)  * T_memory(plan)
  + w_vector(kernel)  * T_vector(plan)
  + w_scalar(kernel)  * T_scalar_control(plan)
  + w_sync(kernel)    * T_sync(plan)
  - S_overlap(plan, kernel)
  + P_hardware(plan, kernel)
  + P_risk(plan, kernel)
```

其中 `w_*` 来自 MLIR 和 artifact 的结构证据。

## 11. V3.0 Strategy-to-HIVM Rewrite Bridge

V3.0 增加了可选的 strategy-to-HIVM rewrite bridge。使用：

```bash
--enable-ir-rewrite
```

可以额外输出：

```text
optimized.annotated.hivm.mlir
optimized.safe_structural.hivm.mlir
pass_pipeline_config.json
strategy_edit_script.json
rewrite_diff_report.json
vtriton_candidate_bundle.json
```

含义如下：

| 文件 | 含义 |
|---|---|
| `optimized.annotated.hivm.mlir` | 在原 IR 上添加 strategy hints / attributes，供后续 pass 消费 |
| `optimized.safe_structural.hivm.mlir` | 只做保守结构化改写，例如 module sync hints 和安全 local attributes |
| `pass_pipeline_config.json` | 给 vTriton / compiler pass 的候选配置 |
| `strategy_edit_script.json` | 描述从 best strategy 到 IR edit 的结构化脚本 |
| `rewrite_diff_report.json` | 对比原 IR 与 rewrite artifact 的差异 |
| `vtriton_candidate_bundle.json` | 给 vTriton 集成使用的候选 bundle |

需要强调：

```text
annotated IR 和 safe structural IR 不是完整可执行优化 IR。
真正可编译、可运行、可 msprof 对比的 optimized HIVM，仍需要 vTriton / 真实 AscendNPU compiler passes 消费这些 hints 后生成并验证。
```

---

## 12. 测试

当前测试体系已经拆成三层：

| 层级 | 默认是否运行 | 目标 | 典型内容 |
|---|---:|---|---|
| `unit` | 是 | 秒级定位局部逻辑错误 | parser、Plan 参数敏感性、hardware gate、package facade |
| `smoke` | 是 | 验证主流程能跑通 | 小 sample kernel 的 CLI/direct run、报告文件生成、current-IR reference |
| `slow` | 否 | 验证搜索质量与扩展空间稳定性 | Beam vs compact exhaustive、random baseline、search quality audit schema |

推荐日常运行：

```bash
python -m pytest
```

由于 `pytest.ini` 默认配置了 `-m "not slow"`，日常测试会跳过耗时的搜索质量审计。

运行完整慢测试：

```bash
python -m pytest -m slow
```

运行全部测试，包括默认测试和 slow 测试：

```bash
python -m pytest -m "unit or smoke or regression or slow"
```

仍然兼容 unittest discover，但不建议作为日常入口，因为 unittest 不理解 pytest marker，可能会把 slow 测试一起跑掉：

```bash
python -m unittest discover -s tests -v
```

测试覆盖：

| 测试内容 | 说明 |
|---|---|
| sync parser | 同时识别 `hivm.set_flag`、`hivm.wait_flag`、`hivm.pipe_barrier` 和 `hivm.hir.*` 写法 |
| CLI end-to-end | 能从 sample bad HIVM 跑完整流程并生成 JSON/HTML/Markdown |
| current-IR reference | 输出 `current_ir_estimated_strategy` 与 `predicted_speedup_vs_current_ir_estimated` |
| Top-K 排序 | Top candidates 按 predicted cycles 排序 |
| TilingPlan 敏感性 | 改变 tile shape 后，`n_tiles` 和局部 memory footprint 必须变化 |
| MultiBufferPlan 敏感性 | 开启 double buffer 后，load/store exposed time 应下降，同时 live memory 应上升 |
| CVPipelinePlan 敏感性 | 开启 stage-2 pipeline 后，Cube/Vector overlap 项应变化，并显式产生估计合法性风险 |
| SyncPlan 敏感性 | `graph_sync_solver` / event reuse 应改变 sync cost，并显式产生未知合法性风险 |
| 硬件 gate 边界 | 刚好等于容量上限应通过，超过容量上限应被拒绝并给出 overflow 原因 |
| 搜索稳定性 | expanded 搜索空间包含 standard tiles，Layer-1 frontier 有 pinned standard survivors、diversity 和 fallback 审计 |
| 搜索质量审计 | slow 测试中比较 Beam、compact exhaustive 和 random baseline，防止 Beam 严重偏离小空间最优 |

---

## 13. 当前不足与下一步

### 13.1 当前不足

| 不足 | 说明 |
|---|---|
| Cost model 仍需实测校准 | 带宽、启动开销、overlap ratio、sync stall 等参数需要通过离线实机数据训练/校准 |
| 精确 buffer lifetime 未完整实现 | 当前是解析式 max-live 估计，不是真实 PlanMemory lifetime dump |
| GraphSyncSolver 不证明正确性 | 只估计 sync cost，不证明依赖图无死锁、event id 合法 |
| Bank conflict / stride legality 未完整覆盖 | 当前主要覆盖容量和基础对齐，没有完整地址级冲突分析 |
| IR rewrite 仍是 bridge 级别 | 当前输出 annotated / safe structural artifacts，不等于完整可编译 optimized HIVM |
| 跨 kernel predicted_cycles 不可直接比较 | 适合比较同一 kernel 下策略相对优劣，不适合作为跨 kernel 绝对性能指标 |

### 13.2 下一步最关键工作

优先级最高的是两个闭环：

```text
1. 离线接入真实 msprof / 实机数据，训练或校准 cost model 参数，并固化到 config；在线阶段仍只读取 MLIR + artifact。
2. 打通 best strategy → 合法 HIVM rewrite → 编译通过 → msprof 对比 的完整工程闭环。
```

更具体地说，需要补充：

| 方向 | 需要的数据/能力 |
|---|---|
| cost model 更真实 | 不同 tile/stage/buffer 策略的 msprof cycles、MTE/Cube/Vector pipe utilization、带宽和启动开销校准 |
| max-live 更真实 | compiler PlanMemory allocation / lifetime dump |
| sync 更真实 | GraphSyncSolver 输出的真实 dependency graph、event id 分配、barrier/set/wait 结果 |
| rewrite 更真实 | vTriton pass 消费 `pass_pipeline_config.json` / `strategy_edit_script.json` 后生成可编译 HIVM |
| 对比更真实 | 原始 IR 与 optimized IR 在同一硬件、同一输入 shape 下的 msprof 对比 |

---

## 14. 推荐汇报口径

可以这样向同事或领导介绍：

> 当前系统是一个面向 HIVM / AscendNPU-IR 的四类 Plan 参数寻优 demo。它从输入 MLIR 中抽取 kernel 静态结构，恢复 current IR 的策略状态，并在硬件容量约束下生成 TilingPlan、MultiBufferPlan、CVPipelinePlan 和 SyncPlan 的候选组合。系统使用 analytical cost model 对候选进行排序，输出相对于 current IR estimated cost 的 predicted speedup，并生成中文可解释报告。当前版本定位为 strategy-level optimizer，不执行完整 IR rewrite，也不声称输出真机实测性能。它的价值在于把 HIVM 优化策略拆成可审计、可解释、可迭代校准的参数空间和 cost model，为后续接入 vTriton pass、DES-after 和 msprof 闭环打基础。


## V3.2 第一阶段更新：Risk-aware Cost Model（无 profiling 数据阶段）

当前仓库尚未接入真实 `msprof` / profiling 数据，因此本阶段不再把 predicted speedup 作为真实硬件收益承诺，而是把系统定位为 **保守、稳定、可解释、未来可校准的策略候选生成器**。

### 1. Cost model 主入口

主搜索流程统一使用：

```python
estimate_cost(...)
```

当前主搜索统一使用 `estimate_cost(...)` 作为正式 cost model 入口；旧版 legacy cost model 已删除，避免两套公式并存造成维护混淆。

### 2. 新增 cost risk mode

CLI 新增参数：

```bash
--cost-risk-mode conservative   # 默认；无 profiling 数据时推荐
--cost-risk-mode balanced       # demo 展示折中模式
--cost-risk-mode aggressive     # 探索模式，保留较激进 overlap/sync 收益
```

三种模式的含义：

| 模式 | 含义 | 适用场景 |
|---|---|---|
| `conservative` | 对 `GraphSyncSolver` 的 `UNKNOWN` 合法性和 `CVPipeline` 的 `PASS_ESTIMATED` 合法性显式降权 | 没有 profiling / sidecar 数据时默认使用 |
| `balanced` | 保留大部分策略收益，但加入较轻风险惩罚 | 汇报 demo 或策略对比 |
| `aggressive` | 基本保留原本乐观收益估计 | 只用于探索潜在候选，不能作为真实性能承诺 |

也可以通过配置文件覆盖风险参数：

```bash
--cost-model-config configs/cost_model_conservative.json
--cost-model-config configs/cost_model_balanced.json
--cost-model-config configs/cost_model_aggressive.json
```

### 3. 新增 legality risk penalty

当候选策略依赖尚未验证的优化时，cost model 会额外输出并计入：

```json
"legality_risk_penalty": ...,
"sync_unknown_penalty": ...,
"event_reuse_penalty": ...,
"cv_estimated_penalty": ...
```

具体处理包括：

- `sync_legality = UNKNOWN` 且使用 `graph_sync_solver`：增加同步未知风险惩罚；
- `event_reuse = true` 且同步合法性未知：增加 event reuse 风险惩罚；
- `cv_pipeline_stage > 1` 且 CV 合法性只是 `PASS_ESTIMATED`：降低 CV overlap，并增加 CV 估计风险惩罚。

### 4. 新增 risk level 与收益归因

每个 candidate 的 cost 中新增：

```json
"risk_level": "LOW | MEDIUM | HIGH",
"risk_assessment": {
  "risk_score": ...,
  "risk_mode": ...,
  "risk_reasons": [...]
},
"improvement_attribution": {
  "positive_cost_components_cycles": {...},
  "optimistic_savings_proxies_per_tile": {...},
  "risk_adjustments_cycles": {...}
}
```

报告中会显示：

- 最优候选风险等级；
- 风险原因；
- 合法性风险惩罚；
- load/store/CV overlap 的收益代理项；
- Top candidates 的 risk level。


### 5. Cost model 超参数配置化

第一阶段已经把主 cost model 中最容易造成“魔数感”的参数移动到 `configs/cost_model_*.json`：

- `cost_model_risk_modes`：控制 conservative / balanced / aggressive 下的合法性风险惩罚；
- `cost_model_safety`：控制 memory pressure、shape regularization、overlap pressure 等安全系数；
- `cost_model_strategy_effects`：控制 MultiBuffer、CVPipeline、SyncPlan 对 overlap、stall、barrier/event 数量和 template overhead 的经验影响。

代码中仍保留同名默认值作为兜底，避免未传 `--cost-model-config` 时程序无法运行；正式实验和汇报建议始终显式传入：

```bash
--cost-model-config configs/cost_model_conservative.json
```

这一步并不等于已经完成 profiling 标定，只是把经验参数从源码魔数改为可审计、可替换、未来可校准的配置项。

### 6. 推荐运行命令

无 profiling 数据时推荐：

```bash
python auto_strategy_search.py \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --candidate-space expanded \
  --search-mode layered \
  --guided-mode off \
  --cost-risk-mode conservative \
  --cost-model-config configs/cost_model_conservative.json \
  --output-dir output_risk_aware_conservative
```

对比 balanced / aggressive：

```bash
python auto_strategy_search.py \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --candidate-space expanded \
  --search-mode layered \
  --guided-mode off \
  --cost-risk-mode balanced \
  --cost-model-config configs/cost_model_balanced.json \
  --output-dir output_risk_aware_balanced

python auto_strategy_search.py \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --candidate-space expanded \
  --search-mode layered \
  --guided-mode off \
  --cost-risk-mode aggressive \
  --cost-model-config configs/cost_model_aggressive.json \
  --output-dir output_risk_aware_aggressive
```

### 6. 解释边界

本阶段更新不会解决真实性能验证问题。它解决的是：

1. 没有 profiling 数据时，避免 cost model 过度乐观；
2. 明确区分 aggressive candidate 和 conservative candidate；
3. 把 GraphSyncSolver / CVPipeline 的未知合法性风险显式写入 cost 和报告；
4. 为未来 profiling 校准预留可配置参数接口。

因此，报告中的 predicted cycles 仍然是 analytical cost model 的排序信号，不是实测 cycles。


### 缺陷注入测试

当前仓库新增了 9 个 synthetic bad MLIR 样例，位于 `tests/defect_inputs/`。这些样例用于验证搜索器是否能识别小 tile、UB overflow、barrier-heavy、缺少 overlap、已有局部优化但整体仍差、以及多种瓶颈叠加等情况。详细结果见 `DEFECT_INJECTION_TEST_REPORT.md`。

常用命令：

```bash
python -m pytest -q tests/test_defect_injection_cases.py -m regression
```

需要重新实跑缺陷搜索时：

```bash
RUN_DEFECT_LIVE=1 python -m pytest -q -m slow tests/test_defect_injection_cases.py
```

## Appendix. Legacy/offline DES makespan calibration

V3.3 主路线不使用 DES makespan/global scale。历史版本中保留的 `--des-calibration-mode single_trace_prior` 只作为 legacy/offline experiment，不能作为默认在线 cost model 介绍口径。

如果确实需要离线实验，可先生成 artifact DES summary：

```bash
python scripts/build_artifact_des_summary.py \
  --artifact-des-graph profiles/raw/chunk_des.json \
  --mlir sample_input/chunk_kernel.npuir.mlir \
  --sample-id chunk_kernel_001 \
  --output profiles/summaries/chunk_kernel_001_summary.json
```

然后显式开启 legacy calibration：

```bash
python -m strategy_search.cli \
  --kernel sample_input/chunk_kernel.npuir.mlir \
  --hardware-config configs/ascend_910b.json \
  --artifact-des-summary profiles/summaries/chunk_kernel_001_summary.json \
  --des-calibration-mode single_trace_prior \
  --output-dir outputs/legacy_des_calibration
```

该模式会使用 DES makespan/global scale 对 analytical cycles 做单样本尺度对齐。它不是实机 profiling 校准，也不是 V3.3 默认推荐路径。V3.3 默认推荐始终使用：

```text
--artifact-kernel-profile on
--des-calibration-mode off
```
