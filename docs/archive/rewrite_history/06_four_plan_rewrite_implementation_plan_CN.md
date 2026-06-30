# 四个参数 Plan 的 HIVM Rewrite 实现推进文档

> 目标：把当前 cost model 搜索出来的四类 Plan，从 `selected_plan.json` 里的参数，逐步落到真实 HIVM IR 结构改写上。  
> 核心原则：cost model 只负责推荐，legality gate 负责否决，backend rewriter 负责真正改 IR。不能证明安全，就不改。

---

## 0. 当前项目定位

当前项目已经具备：

1. 四类 Plan 的策略搜索：`TilingPlan`、`MultiBufferPlan`、`CVPipelinePlan`、`SyncPlan`。
2. annotation / hint 级别 IR 写回。
3. 小范围 sync/barrier 类真实结构改写。
4. 受限正例上的 Q-load hoist 与 GM round-trip deletion 文本/受限真改写。
5. vTriton / HivmOpsEditor 后端骨架。
6. 编译和验收脚本：`phase6e_build_hivm_operation_backend.sh`、`phase6f_accept_compiled_backend.sh`。

但是还没有完成：

1. 真实复杂 kernel 上的 production rewrite。
2. real double-buffer ping-pong rewrite。
3. full CVPipeline overlap rewrite。
4. real tiling loop lowering。
5. msprof 真机性能验证闭环。

所以后续不要继续堆阶段报告，而是要按 rewrite 难度和依赖关系推进。

推荐顺序：

```text
SyncPlan
  ↓
MultiBufferPlan
  ↓
CVPipelinePlan
  ↓
TilingPlan
```

---

## 1. 总体执行链路

四类 Plan 的统一 rewrite 链路应该固定为：

```text
selected_plan.json
        ↓
candidate scan：找当前 IR 里能不能改
        ↓
legality gate：判断这个改写是否安全
        ↓
dry-run mutation plan：只生成改写计划，不动 IR
        ↓
real rewrite：真正修改 HIVM IR
        ↓
roundtrip：读写一遍检查 IR 是否稳定
        ↓
verify：用 backend/verifier 检查 IR 合法性
        ↓
DES/trace：用 tritonsim-hivm 看结构变化是否符合预期
        ↓
msprof：最后才做真机性能验证
```

这里要特别注意：

```text
cost model 推荐 ≠ 一定可以 rewrite
selected_plan.json 推荐 ≠ 一定可以落地
rewrite 能不能执行，必须由 legality gate 决定
```

---

## 2. SyncPlan Rewrite

### 2.1 目标

把粗粒度同步：

```mlir
hivm.barrier_all
```

改成更细粒度的方向性同步：

```mlir
hivm.set_flag
hivm.wait_flag
```

通俗说，原来是“所有人等所有人”，现在改成“真正有依赖的 producer / consumer 之间互相等”。

### 2.2 第一阶段只支持的安全 pattern

先只支持最简单的结构：

```text
A 写 buffer
barrier_all
B 读 buffer
```

如果能证明 B 只依赖 A，不依赖其他未知 op，就改成：

```text
A 写 buffer
set_flag
wait_flag
B 读 buffer
```

### 2.3 需要新增/强化的模块

建议新增：

```text
analysis/dependency_graph.py
analysis/event_liveness.py
legality/sync_gate.py
rewriter/sync_rewriter.py
```

如果暂时不拆目录，也至少在现有 `strategy_search/phase*_analysis.py` 与 `strategy_search/structural_rewrite.py` 中形成独立函数：

```text
scan_sync_rewrite_candidates()
check_sync_rewrite_legality()
build_sync_mutation_plan()
apply_sync_rewrite()
```

### 2.4 输出文件

建议输出：

```text
sync_rewrite_candidates.json
sync_rewrite_decision.json
sync_rewrite_report.json
optimized.sync_rewritten.hivm.mlir
```

### 2.5 验收标准

成功标准不是 cost model 里 sync 成本下降，而是：

```text
1. 输出 IR 中 barrier_all 数量减少
2. set_flag / wait_flag 数量增加
3. dependency graph 没断
4. event liveness 通过
5. roundtrip 通过
6. verifier 通过
7. DES/trace 结构合理
```

---

## 3. MultiBufferPlan Rewrite

### 3.1 目标

把 `nbuf=2`、`double buffer` 从 hint 变成真实 buffer 结构。

原来：

```text
for tile:
    load GM -> Q_ub
    compute Q_ub
```

改成：

```text
alloc Q_ub_0
alloc Q_ub_1

for tile:
    load GM -> Q_ub[tile % 2]
    compute Q_ub[tile % 2]
```

### 3.2 推进阶段

#### MB1：real buffer clone

只做 buffer clone，不做跨 iteration overlap。

目标：证明后端能把一个 buffer 安全复制成两个 buffer，并正确替换 operand。

#### MB2：ping-pong buffer rewrite

在 loop 内按照 iteration 切换 buffer slot：

```text
buffer_id = tile_id % 2
```

#### MB3：和 SyncPlan 联动

当 ping-pong buffer 与跨阶段 producer/consumer 结合时，插入必要的 `set_flag / wait_flag`。

### 3.3 需要新增/强化的模块

建议新增：

```text
analysis/buffer_liveness.py
analysis/capacity_checker.py
analysis/alias_checker.py
legality/multibuffer_gate.py
rewriter/multibuffer_rewriter.py
```

关键函数：

```text
scan_multibuffer_candidates()
check_buffer_clone_legality()
build_buffer_clone_plan()
apply_buffer_clone()
check_pingpong_legality()
apply_pingpong_rewrite()
```

### 3.4 legality gate 必须检查

```text
1. buffer 是否只在局部 loop 内使用
2. buffer 是否没有 escape 到未知 op
3. buffer 是否不是 output/boundary buffer
4. clone 后 UB/L1/L0 容量是否仍然满足硬件边界
5. 所有 consumer 是否都能被正确替换
6. 是否存在 alias
7. 是否存在跨 loop hidden dependency
8. 是否存在 unknown side effect op
```

### 3.5 输出文件

```text
multibuffer_candidates.json
buffer_clone_decision.json
pingpong_rewrite_report.json
buffer_liveness_report.json
capacity_recheck_report.json
optimized.multibuffer.hivm.mlir
optimized.pingpong.hivm.mlir
```

### 3.6 验收标准

```text
1. IR 里真的出现 buffer_0 / buffer_1
2. load/store/compute operand 被正确替换
3. capacity_recheck_report.json 通过
4. buffer_liveness_report.json 通过
5. verifier 通过
6. DES/trace 通过
```

---

## 4. CVPipelinePlan Rewrite

### 4.1 目标

把 load / nd2nz / compute / store 这类阶段做重排，形成流水 overlap。

原始：

```text
for tile i:
    load i
    nd2nz i
    compute i
    store i
```

pipeline 后：

```text
prologue:
    load 0
    nd2nz 0

steady state:
for tile i:
    load i+1
    nd2nz i+1
    compute i
    store i-1

epilogue:
    compute last
    store last
```

### 4.2 重要前提

CVPipelinePlan 不建议独立做。它依赖：

```text
1. MultiBufferPlan：防止 load i+1 覆盖 compute i 正在使用的 buffer
2. SyncPlan：保证跨 stage producer/consumer 顺序
```

所以真实推进顺序应该是：

```text
SyncPlan 真改写
  ↓
MultiBufferPlan ping-pong
  ↓
CVPipelinePlan two-stage pipeline
```

### 4.3 推进阶段

#### CV1：candidate scan，不改 IR

先只识别 pipeline 机会，输出：

```text
cv_pipeline_candidates.json
cv_pipeline_legality_report.json
```

要回答：

```text
哪些 op 是 load stage？
哪些 op 是 transform stage？
哪些 op 是 compute stage？
哪些 op 是 store stage？
为什么能 pipeline？
为什么不能 pipeline？
```

#### CV2：restricted two-stage pipeline

只支持：

```text
load stage + compute stage
```

不要一上来做 load + nd2nz + compute + store 四阶段。

#### CV3：扩展到 nd2nz / store stage

当 CV2 稳定后，再扩展完整流水。

### 4.4 legality gate 必须检查

```text
1. stage 之间的数据依赖是线性的
2. 没有跨 tile reduction 语义
3. 没有 unknown side effect op
4. load i+1 不会覆盖 compute i 正在用的 buffer
5. store i-1 不会覆盖后续还要读的数据
6. set/wait flag 能保证 producer-consumer 顺序
7. prologue / steady-state / epilogue 都正确
8. tail tile / mask 语义正确
```

### 4.5 输出文件

```text
cv_pipeline_candidates.json
cv_pipeline_legality_report.json
cv_pipeline_rewrite_report.json
optimized.cv_two_stage.hivm.mlir
optimized.cv_pipeline.hivm.mlir
```

### 4.6 验收标准

```text
1. IR 中 op 顺序真的发生 stage 重排
2. buffer 使用变成 ping-pong
3. set_flag / wait_flag 插入正确
4. trace 中能看到 load/compute overlap
5. verifier 通过
6. DES/trace 通过
```

---

## 5. TilingPlan Rewrite

### 5.1 目标

把 tile_m / tile_n / tile_k 从参数变成真实 loop nest、index、slice、mask 的改变。

真实 tiling 不是写 attribute，而是改变：

```text
1. loop nest
2. index mapping
3. load/store memory slice
4. compute tile shape
5. tail mask
6. buffer capacity
```

### 5.2 推进阶段

#### T1：tiling legality report，不改 IR

先回答：

```text
当前 IR 能不能 tile？
哪些维度能 tile？
tile_m/n/k 是否合法？
是否需要 tail mask？
tile 后 buffer 容量是否满足？
```

#### T2：tiling metadata / hint

继续保留 hint 写回能力：

```mlir
hivm.strategy.tile_m = 64
hivm.strategy.tile_n = 128
hivm.strategy.tile_k = 64
```

这一步是给后端 compiler pass 读取策略，不等于真实 tiling。

#### T3：restricted loop tiling

只支持简单 loop：

```text
1. 单层或双层 affine-like loop
2. 规则 load/compute/store
3. 无复杂 branch
4. 无 dynamic shape
5. 无复杂 reduction
```

#### T4：tail mask

真实 kernel 很少刚好整除，所以最后必须支持：

```text
M % tile_m != 0
N % tile_n != 0
K % tile_k != 0
```

### 5.3 需要新增/强化的模块

```text
analysis/loop_analyzer.py
analysis/index_analyzer.py
analysis/tail_mask_checker.py
legality/tiling_gate.py
rewriter/tiling_rewriter.py
```

### 5.4 输出文件

```text
tiling_candidates.json
tiling_legality_report.json
capacity_after_tiling_report.json
tiling_rewrite_report.json
optimized.tiled.hivm.mlir
```

### 5.5 验收标准

```text
1. IR 里 loop nest 发生变化
2. load/store slice 发生变化
3. compute tile shape 发生变化
4. tail mask 正确
5. capacity recheck 通过
6. verifier 通过
7. DES/trace 通过
```

---

## 6. 推荐里程碑

### Milestone 1：SyncPlan 真改写

目标：

```text
barrier_all → set_flag / wait_flag
```

验收：

```text
barrier_all 减少
set_flag/wait_flag 增加
dependency/event liveness 通过
roundtrip/verify 通过
```

### Milestone 2：MultiBufferPlan real buffer clone

目标：

```text
nbuf=2 → 真实 clone buffer_0 / buffer_1
```

验收：

```text
buffer clone 出现
operand 替换正确
capacity/liveness 通过
```

### Milestone 3：MultiBufferPlan ping-pong

目标：

```text
loop 内 buffer 按 tile_id % 2 切换
```

验收：

```text
没有 overwrite
没有 alias
buffer lifetime 正确
```

### Milestone 4：CVPipelinePlan candidate scan

目标：

```text
先识别 pipeline 机会，不改 IR
```

验收：

```text
能解释哪些 stage 能 pipeline，哪些不能，原因是什么
```

### Milestone 5：CVPipelinePlan restricted two-stage overlap

目标：

```text
load i+1 与 compute i 形成简单 overlap
```

验收：

```text
prologue/steady-state/epilogue 正确
trace 中看到 overlap
```

### Milestone 6：TilingPlan legality report

目标：

```text
判断当前 IR 是否具备真实 tiling 条件
```

验收：

```text
tile_m/n/k 合法性、tail mask、capacity 全部有报告
```

### Milestone 7：TilingPlan restricted loop rewrite

目标：

```text
简单 loop 的真实 tiling rewrite
```

验收：

```text
loop/index/slice/mask 全部真实改变，verify 通过
```

---

## 7. 需要跑哪些 bash

下面分成两类：

1. 本仓库本地就能跑的 Python / smoke / fake backend。
2. 必须在真实 vTriton 构建环境里跑的 backend 编译和验收。

---

### 7.1 本仓库本地 smoke run

进入仓库根目录：

```bash
cd /path/to/HIVM_strategy_search_demo_V4.0_clean
```

跑一次完整策略搜索 + annotation/hint/structural dry-run：

```bash
python -m strategy_search.cli \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --candidate-space standard \
  --artifact-kernel-profile on \
  --enable-ir-rewrite \
  --rewrite-mode both \
  --enable-structural-rewrite \
  --structural-rewrite-backend dry_run \
  --output-dir demo_out
```

看输出：

```bash
ls demo_out
```

重点看：

```text
selected_strategy.json
selected_plan.json
cost_breakdown.json
strategy_search_report.html
optimized.annotated.hivm.mlir
optimized.safe_structural.hivm.mlir
optimized.structural.hivm.mlir
```

---

### 7.2 跑测试

基础测试：

```bash
python -m pytest tests/test_strategy_search_smoke.py -q
python -m pytest tests/test_cost_model_unit.py -q
```

rewrite 相关测试：

```bash
python -m pytest tests/test_rewrite_step1_annotation.py -q
python -m pytest tests/test_rewrite_step2_safe_structural.py -q
python -m pytest tests/test_rewrite_cvpipeline_hint.py -q
python -m pytest tests/test_structural_rewrite_step3.py -q
```

Phase 6 fake/受限后端测试：

```bash
python -m pytest tests/test_phase6a_real_backend_integration.py -q
python -m pytest tests/test_phase6b_positive_case_harness.py -q
python -m pytest tests/test_phase6c_restricted_true_rewrite.py -q
python -m pytest tests/test_phase6d_vtriton_adapter_skeleton.py -q
python -m pytest tests/test_phase6e_vtriton_integration_pack.py -q
python -m pytest tests/test_phase6f_backend_acceptance.py -q
```

如果想一次性跑全部测试：

```bash
python -m pytest -q
```

---

### 7.3 本仓库 fake backend smoke

这个不需要真实 vTriton，只是确认验收脚本链路能跑。

```bash
chmod +x tools/fake_hivm_operation_backend.py
chmod +x scripts/phase6e_smoke_test_backend.sh

bash scripts/phase6e_smoke_test_backend.sh \
  ./tools/fake_hivm_operation_backend.py \
  sample_input/phase6_positive_fixtures/restricted_gm_roundtrip_positive.hivm.mlir \
  phase6e_fake_smoke_out
```

如果样例路径不存在，可以先找一下：

```bash
find sample_input -name '*gm*' -o -name '*roundtrip*' -o -name '*positive*'
```

---

### 7.4 真实 vTriton 环境：编译 hivm-operation-backend

这一步必须在有 vTriton 源码、CMake build 目录、MLIR/LLVM/BishengIR 依赖配置好的机器上跑。

假设：

```text
vTriton 源码路径：/path/to/vTriton
vTriton build 路径：/path/to/vTriton/build
本项目路径：/path/to/HIVM_strategy_search_demo_V4.0_clean
```

先进入本项目：

```bash
cd /path/to/HIVM_strategy_search_demo_V4.0_clean
```

执行：

```bash
bash scripts/phase6e_build_hivm_operation_backend.sh \
  /path/to/vTriton \
  /path/to/vTriton/build
```

这个脚本会做三件事：

```text
1. 把 vtriton_hivm_operation_backend/ 接入 vTriton
2. 调用 cmake --build 编译 hivm-operation-backend
3. 执行 hivm-operation-backend --print-capabilities
```

如果成功，应该能找到：

```text
/path/to/vTriton/build/bin/hivm-operation-backend
```

---

### 7.5 真实 vTriton 环境：compiled backend 验收

编译成功后，跑：

```bash
bash scripts/phase6f_accept_compiled_backend.sh \
  /path/to/vTriton/build/bin/hivm-operation-backend \
  sample_input/phase6_positive_fixtures/restricted_gm_roundtrip_positive.hivm.mlir \
  phase6f_backend_acceptance_out \
  /path/to/vTriton/build/bin/tritonsim-hivm
```

如果暂时没有 `tritonsim-hivm`，可以先不传第四个参数：

```bash
bash scripts/phase6f_accept_compiled_backend.sh \
  /path/to/vTriton/build/bin/hivm-operation-backend \
  sample_input/phase6_positive_fixtures/restricted_gm_roundtrip_positive.hivm.mlir \
  phase6f_backend_acceptance_out
```

输出目录应包含：

```text
capabilities.json
inventory.json
roundtrip.hivm.mlir
roundtrip.json
verify.json
gm_mutation.json
optimized.gm_removed.hivm.mlir
optimized_des_graph.json              # 如果传了 tritonsim-hivm
optimized_perfetto_trace.json         # 如果传了 tritonsim-hivm
```

---

## 8. 当前最应该跑的最小 bash 顺序

如果你只是想推进下一步，推荐最小顺序是：

### Step 1：本仓库 smoke

```bash
cd /path/to/HIVM_strategy_search_demo_V4.0_clean

python -m strategy_search.cli \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --candidate-space standard \
  --artifact-kernel-profile on \
  --enable-ir-rewrite \
  --rewrite-mode both \
  --enable-structural-rewrite \
  --structural-rewrite-backend dry_run \
  --output-dir demo_out
```

### Step 2：本仓库测试

```bash
python -m pytest tests/test_phase6f_backend_acceptance.py -q
```

### Step 3：真实 vTriton 编译 backend

```bash
bash scripts/phase6e_build_hivm_operation_backend.sh \
  /path/to/vTriton \
  /path/to/vTriton/build
```

### Step 4：真实 backend 验收

```bash
bash scripts/phase6f_accept_compiled_backend.sh \
  /path/to/vTriton/build/bin/hivm-operation-backend \
  sample_input/phase6_positive_fixtures/restricted_gm_roundtrip_positive.hivm.mlir \
  phase6f_backend_acceptance_out \
  /path/to/vTriton/build/bin/tritonsim-hivm
```

如果 Step 3 编译失败，优先收集：

```text
1. CMake 报错
2. include path 报错
3. namespace 报错
4. HivmOpsEditor API 不匹配报错
5. link library 报错
```

这些报错就是下一轮真正要修的东西。

---

## 9. 下一轮开发任务建议

不要继续新增大而空的 phase。建议下一轮只做两个目标：

```text
目标 A：SyncPlan 真改写闭环
目标 B：MultiBufferPlan buffer clone 闭环
```

也就是：

```text
SyncPlan:
  barrier_all → set_flag / wait_flag

MultiBufferPlan:
  nbuf=2 → buffer_0 / buffer_1
```

这两个完成之后，再推进 CVPipelinePlan。TilingPlan 最后做。

---

## 10. 对外汇报口径

可以这样说：

```text
当前项目已经完成四类 Plan 的策略搜索和 IR 写回原型，
并且已经具备受限真实 rewrite 与 vTriton/HivmOpsEditor backend skeleton。
下一阶段的重点不是继续扩展 cost model，而是把四类 Plan 中最容易落地的 SyncPlan 和 MultiBufferPlan 先做成真实 rewrite 闭环。
具体路线是：先完成 barrier_all 到 set_flag/wait_flag 的真实同步改写，再完成 nbuf=2 对应的真实 buffer clone；之后再基于这两个基础能力推进 CVPipeline overlap，最后才推进真实 tiling loop lowering。
```
