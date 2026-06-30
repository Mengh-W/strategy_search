# 四个参数 Plan 的 Rewrite Readiness 实现说明

这一步的目标不是继续增加 Phase，也不是直接声称已经完成真实 rewrite，而是把四个 Plan 的寻优结果整理成 HivmOpsEditor 后端能够执行的“施工单”。

一句话：

```text
selected_plan.json 是优化意图；
four_plan_rewrite_plan.json 是后端施工单；
four_plan_rewrite_readiness.json 是动手前的安全检查表；
真正改 HIVM IR 的动作仍然由 vTriton/HivmOpsEditor backend 执行。
```

## 1. 为什么需要 readiness，而不是直接 rewrite？

四个 Plan 的参数是高层策略，例如：

```json
{
  "tile_m": 32,
  "tile_n": 64,
  "tile_k": 128,
  "double_buffer": true,
  "stage_num": 2,
  "policy": "graph_sync_solver"
}
```

但 HivmOpsEditor 需要的是更具体的信息：

```text
要 clone 哪个 buffer？
要替换哪些 producer/consumer 的 operand？
哪个 barrier 能变成 set_flag/wait_flag？
哪些 load/nd2nz/mmad/store 能组成 pipeline stage？
哪个 loop 能被 tile？tail mask 怎么处理？
```

所以本阶段做的是“把策略翻译成可执行 rewrite 计划”，而不是用 Python 直接修改真实 HIVM IR。

## 2. 新增模块

新增源码：

```text
strategy_search/rewrite_readiness.py
```

新增命令：

```text
tools/build_four_plan_rewrite_readiness.py
```

新增测试：

```text
tests/test_rewrite_readiness.py
```

输出目录示例：

```text
artifacts/latest_rewrite_readiness/
  hivm_ir_inventory.official.json
  four_plan_rewrite_plan.json
  four_plan_rewrite_readiness.json
  sync_plan_readiness.json
  multibuffer_plan_readiness.json
  cv_pipeline_plan_readiness.json
  tiling_plan_readiness.json
```

## 3. 实现流程

```text
输入 HIVM IR
  ↓
官方文档驱动的 HIVM op inventory
  ↓
读取 selected_plan.json
  ↓
生成 four_plan_rewrite_plan.json
  ↓
生成四个 Plan 的 readiness report
  ↓
后续交给 HivmOpsEditor backend 做 dry-run / mutate / verify
```

其中 `hivm_ir_inventory.official.json` 负责识别当前 IR 里实际有哪些 op、buffer、loop 和 sync anchor。

`four_plan_rewrite_plan.json` 负责把四个 Plan 的参数翻译成 mutation request。

`four_plan_rewrite_readiness.json` 负责告诉你：

```text
当前能不能进入 backend dry-run？
如果不能，缺什么证据？
如果能，后端应该执行哪类 mutation？
真实 mutate 前必须证明什么？
```

## 4. 四个 Plan 如何落地

### 4.1 SyncPlan

目标：

```text
barrier / pipe_barrier / 粗粒度同步
  → directional set_flag / wait_flag 或 sync cleanup
```

readiness 会输出：

```text
sync_ops
barrier_like_ops
existing_event_ops
possible_producer_ops
possible_consumer_ops
```

真实 mutate 前必须证明：

```text
producer-consumer pair 可证明；
event id fresh 或 live range 不冲突；
不会 wait-before-set 死锁；
不会删掉跨 iteration 依赖；
roundtrip / verify 通过。
```

当前样例 `fa_best.hivm.mlir` 上，SyncPlan 可以进入 backend dry-run。

### 4.2 MultiBufferPlan

目标：

```text
nbuf = 2 / double_buffer
  → 真实 buffer slot clone + operand replacement
```

readiness 会输出：

```text
candidate_buffers
producer_ops
consumer_ops
backend_clone_request
```

真实 mutate 前必须证明：

```text
所有 use 都能被 MLIR use-def 解析；
target buffer 没有逃逸到 unknown side-effect op；
额外 buffer slot 后 capacity recheck 通过；
buffer liveness 不覆盖；
roundtrip / verify 通过。
```

当前样例上，MultiBufferPlan 可以进入 backend dry-run。

### 4.3 CVPipelinePlan

目标：

```text
load / transform / cube / vector / store
  → pipeline stage reorder / overlap
```

readiness 会输出：

```text
stage_sequence_by_line
load_ops
layout_ops
copy_ops
cube_ops
vector_ops
fixpipe_ops
store_ops
sync_ops
```

真实 mutate 前必须证明：

```text
stage dependency 是线性的；
没有跨 tile reduction 或 side-effect 阻止重排；
已有 ping-pong buffer 或可以由 MultiBufferPlan 提供；
prologue / steady-state / epilogue 构造正确；
DES/trace 真的能看到 overlap，才能声称 pipeline 成功。
```

当前样例上，CVPipelinePlan 可以进入 backend dry-run，但真实 overlap 必须依赖 MultiBufferPlan 和 SyncPlan。

### 4.4 TilingPlan

目标：

```text
tile_m / tile_n / tile_k
  → loop split + index remap + load/store slice + tail mask
```

但真实 tiling 最接近 compiler lowering，风险最高。因此当前版本只做：

```text
REPORT_AND_HINT_ONLY_V1
```

也就是只输出 loop anchor、tile 参数和 backend hint，不直接声称已经完成真实 loop rewrite。

真实 mutate 前必须证明：

```text
loop bounds 和 induction vars 可识别；
load/store slice mapping 可识别；
tail mask 语义明确；
capacity after tiling 通过；
roundtrip / verify 通过。
```

## 5. 如何运行

在项目根目录运行：

```bash
python tools/build_four_plan_rewrite_readiness.py \
  --ir sample_input/fa_best.hivm.mlir \
  --selected-plan artifacts/latest_smoke_run/selected_plan.json \
  --output-dir artifacts/latest_rewrite_readiness
```

测试：

```bash
pytest -q tests/test_official_hivm_rewrite_plan.py tests/test_rewrite_readiness.py
```

当前测试结果：

```text
6 passed
```

## 6. 当前阶段的真实结论

当前代码已经能基于官方文档约束和真实样例，输出四个 Plan 的 rewrite readiness：

```text
SyncPlan: 可以进入 backend dry-run
MultiBufferPlan: 可以进入 backend dry-run
CVPipelinePlan: 可以进入 backend dry-run，但依赖 Sync + MultiBuffer
TilingPlan: 当前只做 report/hint，不直接真实改 loop
```

这说明项目已经从：

```text
只知道 selected_plan 选了什么
```

推进到：

```text
知道 selected_plan 应该作用到 IR 的哪些 op/buffer/loop/sync 上，
并能生成 HivmOpsEditor 后端需要的 mutation request/checklist。
```

下一步真正需要用户本地运行的，是在真实 vTriton 环境里编译并运行 HivmOpsEditor backend。没有到这一步之前，当前工作都可以继续在仓库内推进。
