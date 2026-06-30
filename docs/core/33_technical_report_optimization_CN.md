# 技术报告一：HIVM 四参数 Plan 寻优系统设计报告

版本：`V5.3.1-backend-contract-ready-prelinux-lf-hygiene`  
适用代码仓：`vTRiton_search / HIVM_strategy_search_demo`  
报告主题：四参数 Plan 的参数空间、cost model、搜索流程、硬件边界、selected_plan 输出，以及 Linux 真实后端前的验收边界。

---

## 1. 项目目标

本项目不是通用 MLIR 编译器，也不是已经接入真实 BiShengIR / CANN / msprof 的生产级 pass。它的当前目标是：

```text
在给定 HIVM / NPU-IR 输入时，自动生成四类编译策略候选，
用 cost model 和硬件边界约束完成策略排序，
选出 selected_plan.json，
并交给 rewrite/backend-contract 层继续验证。
```

当前四类 Plan 是：

```text
TilingPlan
MultiBufferPlan
CVPipelinePlan
SyncPlan
```

整体寻优链路：

```text
输入 HIVM / NPU-IR MLIR
  -> 解析 IR 结构特征和可选 profile/artifact
  -> 构造四参数 Plan 搜索空间
  -> 生成 candidate strategy
  -> hardware gate 过滤明显不可行候选
  -> cost model 估计候选成本
  -> beam/ranking 选择 selected_plan
  -> 输出 selected_plan.json 与 cost/search 报告
  -> 交给 rewrite 和 backend contract 阶段
```

---

## 2. 输入与输出

### 2.1 输入

| 输入 | 说明 |
|---|---|
| HIVM / NPU-IR MLIR | 例如 `sample_input/fa_bad_inefficient.hivm.mlir` |
| 硬件配置 | 例如 `configs/ascend_910b.json` |
| cost model 配置 | 例如 `configs/cost_model_conservative.json` |
| 可选 profile / artifact | 例如 DES/trace、chunk profile、prefill_a5 profile、artifact inventory |
| 搜索空间配置 | tile、buffer、pipeline、sync 的候选参数域 |

### 2.2 输出

| 输出 | 作用 |
|---|---|
| `selected_plan.json` | 被选中的四参数 Plan，是 rewrite/backend contract 的核心输入 |
| `selected_strategy.json` | 策略级摘要 |
| `cost_breakdown.json` | load/compute/store/sync/penalty/overlap 等分项成本 |
| `search_report.json` | 搜索过程和 top candidates |
| `parameter_space_audit.json` | 参数空间审计 |
| `hardware_boundary_audit.json` | 硬件边界检查结果 |
| `strategy_search_report.md/html` | 可读报告 |

---

## 3. 四参数 Plan 参数空间

### 3.1 TilingPlan

主要 knobs：

```text
tile_m
tile_n
tile_k
logical_axes
loop_order
tail_strategy
reduce_tile_policy
layout_aware_tile
generic_logical_axes_evidence
```

当前含义：

```text
tile_m/tile_n/tile_k
  决定 tile 形状，影响 working set、GM/UB/L1 搬运量和计算粒度。

loop_order
  表示逻辑 loop traversal 顺序，影响访存局部性和 pipeline window。

tail_strategy
  表示尾块策略，例如 mask、pad 或 guarded tail。

reduce_tile_policy
  表示 reduce 维度如何切分和累加。

logical_axes / layout_aware_tile / evidence
  表示从 IR/profile 中提取到的轴语义和 layout 证据。
```

当前 rewrite 状态：TilingPlan 主要以 `TRACE_METADATA_REWRITE` 方式写回，不声称已经完成真实 loop/index/tail lowering。

### 3.2 MultiBufferPlan

主要 knobs：

```text
double_buffer
input_buffer_multiplier
stage_buffer_multiplier
ub_multiplier
l1_multiplier
buffer_multipliers
stage_buffer_policy
buffer_multiplier_domain
detected_ping_pong_multibuffer
template
```

当前含义：

```text
double_buffer
  是否启用 ping/pong buffer。

input_buffer_multiplier / stage_buffer_multiplier
  逻辑输入和 stage buffer 的倍数。

ub_multiplier / l1_multiplier
  UB/L1 scope 的 buffer 倍数。

buffer_multipliers
  逻辑 buffer 名到倍数的配置，例如 q/k/v 或 stage buffer。

stage_buffer_policy
  stage 如何绑定 buffer。
```

当前 rewrite 状态：部分 buffer candidate 可以生成 ping/pong slot 和局部 use replacement，属于 `RESTRICTED_STRUCTURAL_REWRITE`；完整 alias/liveness/capacity proof 仍需真实 backend/verifier。

### 3.3 CVPipelinePlan

主要 knobs：

```text
stage_num
producer_consumer_distance
stage_buffer_policy
enable_mixed_cv
tile_mix_cube_loop
tile_mix_vector_loop
auto_cv_balance
template
```

当前含义：

```text
stage_num
  pipeline stage 数。

producer_consumer_distance
  producer 与 consumer 之间的同步/调度距离。

stage_buffer_policy
  stage 如何使用 buffer。

enable_mixed_cv
  是否启用 cube/vector 混合 pipeline。

auto_cv_balance
  是否自动平衡 load/compute/store stage。
```

当前 rewrite 状态：可以插入 pipeline marker 和 load->compute、compute->store event pair；尚未完成真实 operation movement、loop skew、prologue/steady/epilogue lowering。

### 3.4 SyncPlan

主要 knobs：

```text
policy
barrier_level
event_id_policy
event_reuse
sync_granularity
sync_motion
remove_redundant_sync
sync_style_from_ir
template
```

当前含义：

```text
policy / barrier_level
  决定是否尝试将粗粒度 barrier 细化为 event pair。

event_id_policy / event_reuse
  决定 event id 生成和复用策略。

sync_granularity
  决定 op/block/stage 级同步粒度。

sync_motion / remove_redundant_sync
  表示是否允许移动或删除 sync；当前只做 guarded 分析，不做破坏性 mutation。
```

当前 rewrite 状态：安全 candidate 可以生成 `set_flag / wait_flag` event pair；blocked action 会导致 strict e2e 失败，不会包装成成功。

---

## 4. Cost Model 设计

当前 cost model 的定位是 analytical ranking model，即用于同一输入 IR 下的候选策略相对排序，而不是直接预测真实 msprof cycle。

总成本可概括为：

```text
TotalCost = LoadCost + ComputeCost + StoreCost + SyncCost + PenaltyCost - OverlapBenefit
```

### 4.1 分项解释

```text
LoadCost
  由 tile shape、GM/UB/L1 搬运量、load op 数量和 buffer overlap 影响。

ComputeCost
  由 tile shape、计算 proxy、reduce policy、cube/vector balance 影响。

StoreCost
  由 store bytes、store/fixpipe op、compute->store overlap 影响。

SyncCost
  由 barrier 数量、event pair 数量、sync granularity、event reuse 风险影响。

PenaltyCost
  包括 capacity overflow、stage imbalance、sync pressure、shape mismatch、unsupported rewrite risk。

OverlapBenefit
  来自 double buffer、pipeline window、load/compute/store overlap。
```

### 4.2 当前能做什么

可以用于：

```text
候选策略排序；
解释 selected_plan 为什么优于其他候选；
为 rewrite/backend contract 阶段提供统一策略输入；
结合少量 profile 做初步常数校准。
```

不能用于：

```text
直接声称 predicted_cycles 等于真实 cycles；
直接声称 predicted speedup 等于 msprof speedup；
替代 DES/trace 或真机 profile。
```

---

## 5. 硬件边界约束

硬件 gate 的作用是尽早过滤明显不可行候选，避免搜索空间被无效策略污染。

当前关注：

```text
UB/L1/GM working set 是否超界；
buffer multiplier 是否导致容量压力过大；
stage buffer 是否与 pipeline policy 冲突；
sync/event 数量是否异常；
tile shape 是否导致 shape 或 tail 风险；
profile/artifact 证据是否支持该候选。
```

硬件 gate 的边界：

```text
它是静态筛选，不等于真实编译器 verifier；
它不能证明所有 memory alias、dominance、event liveness 都合法；
它不能证明真机性能提升。
```

---

## 6. selected_plan 与 honest e2e

寻优阶段输出的 `selected_plan.json` 必须和当前输入 IR 强绑定，不能拿历史 plan 去 rewrite 新 IR。

推荐入口：

```bash
python tools/run_search_and_four_plan_rewrite.py \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --cost-model-config configs/cost_model_conservative.json \
  --cost-risk-mode conservative \
  --candidate-space standard \
  --output-dir artifacts/v531_bound_search_rewrite
```

该入口的 summary 中：

```text
selected_plan_bound_to_same_input = true
```

只说明 plan 绑定正确，不等于完整 e2e 通过。完整通过必须看：

```text
end_to_end_passed = true
```

当前 wrapper 已采用 strict/honest 返回语义：rewrite 或 validation 失败时返回非 0，不再包装成成功。

---

## 7. backend contract 与寻优系统的关系

寻优系统输出的是策略；backend contract 是把策略翻译成后端可消费施工单的桥梁。

```text
selected_plan.json
  -> rewrite readiness / inventory
  -> four_plan_backend_contract.json
  -> fake backend dry-run / acceptance
  -> future real HivmOpsEditor/vTriton backend
```

backend contract 不证明真实 rewrite 成功。它只证明：Python 侧已经把“要做什么、在哪里做、验收什么”表达成结构化工作单。

---

## 8. Linux 环境前已完成的寻优侧任务

当前版本已经完成：

```text
P0 工程自洽：脚本入口、honest e2e、缓存清理脚本、README/docs 更新；
P1 fake backend 链路：contract、runner、dry-run、roundtrip、guarded mutation、acceptance harness；
pre-Linux 本地门禁：run_v531_fast_ci、run_phase5b_roundtrip_ci、run_backend_fake_ci、run_phase6_positive_ci 四条命令。
```

本地验收命令：

```bash
bash scripts/run_v531_fast_ci.sh
bash scripts/run_backend_fake_ci.sh
```

或：

```bash
bash scripts/run_v531_fast_ci.sh
bash scripts/run_phase5b_roundtrip_ci.sh
bash scripts/run_backend_fake_ci.sh
bash scripts/run_phase6_positive_ci.sh
```

通过这些测试后，可以说项目已经准备好交给 Linux/vTriton/BiShengIR 环境继续验证。

---

## 9. Linux 环境后的下一步

下一步不是继续堆 Python Phase，而是接真实后端：

```text
真实 BiShengIR parser
真实 MLIR verifier
真实 HivmOpsEditor operation-level roundtrip
真实 vTriton DES/trace
CANN compile/runtime
msprof 真机 profile
cost model profile-aware calibration
```

只有完成这些后，才能逐步从 analytical ranking model 走向 calibrated ranking model，并从 restricted rewrite artifact 走向 production operation rewrite。
