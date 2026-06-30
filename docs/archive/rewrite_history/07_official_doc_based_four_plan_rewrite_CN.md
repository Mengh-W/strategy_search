# 基于官方 HIVM Dialect 文档的四个参数 Plan Rewrite 实现方案

## 1. 这一步到底要解决什么

当前策略搜索系统已经能输出 `selected_plan.json`，里面包含四类 Plan：

- `TilingPlan`
- `MultiBufferPlan`
- `CVPipelinePlan`
- `SyncPlan`

但 `selected_plan.json` 只是高层优化意图，例如：

```json
{
  "tile_m": 32,
  "tile_n": 64,
  "tile_k": 128,
  "double_buffer": true,
  "stage_num": 2,
  "sync_policy": "graph_sync_solver"
}
```

真实 HIVM rewrite 不能直接根据这些高层参数动 IR。原因是 HivmOpsEditor 需要知道：

- 当前 IR 里有哪些真实 `hivm.hir.*` op；
- 哪些 op 是 load/store/layout/compute/sync；
- selected Plan 应该作用到哪些 op 或 buffer；
- 哪些地方可以改，哪些地方只能生成 hint/report；
- 哪些 mutation 必须交给真实 vTriton/HivmOpsEditor 后端执行。

因此本阶段新增的是一个很薄的翻译层：

```text
selected_plan.json
    ↓
HIVM official op inventory
    ↓
four_plan_rewrite_plan.json
    ↓
HivmOpsEditor backend
    ↓
optimized.hivm.mlir
```

注意：这里没有再造一个新的 IR。`four_plan_rewrite_plan.json` 只是给后端看的“施工单”。

---

## 2. 官方文档如何用于实现

官方 AscendNPU-IR HIVM Dialect 文档给出了 HIVM op 的语法和语义。第一版只抽取四个 Plan rewrite 必须用到的 op 子集。

### 2.1 Load / Store

官方文档中 `hivm.hir.load` 和 `hivm.hir.store` 都是 destination-style op，语法形态是：

```mlir
hivm.hir.load  ins(%src : type) outs(%dst : type) attr-dict
hivm.hir.store ins(%src : type) outs(%dst : type) attr-dict
```

它们对应：

- `load`：GM 到 local buffer，例如 UB；
- `store`：local buffer 到 GM。

因此它们主要服务：

- `MultiBufferPlan`：判断哪些 load 目标 buffer 可以 clone；
- `CVPipelinePlan`：识别 load/store stage；
- GM round-trip deletion：识别冗余 GM load/store pattern。

### 2.2 set_flag / wait_flag

官方文档中 `hivm.hir.set_flag` / `hivm.hir.wait_flag` 的语法是：

```mlir
hivm.hir.set_flag  [set_pipe, wait_pipe, event] attr-dict
hivm.hir.wait_flag [set_pipe, wait_pipe, event] attr-dict
```

但是当前部分样例里可能出现：

```mlir
hivm.hir.set_flag {pipe="FIX", event="EVENT_ID0"}
hivm.hir.wait_flag {pipe="M", event="EVENT_ID0"}
```

这说明样例格式可能是旧格式、项目简化格式，或者某个中间态 printer 格式。因此 Python 层只把这类 op 当作已有同步 anchor 读取，不主动拼接这种格式。真实 event op 的生成应该交给 HivmOpsEditor backend，让 backend 使用当前 vTriton/HIVM 工具链认可的 printer 格式。

### 2.3 pipe_barrier

官方文档中 `hivm.hir.pipe_barrier` 是 pipe barrier 类型同步 op，语法形态是：

```mlir
hivm.hir.pipe_barrier [pipe] attr-dict
```

它主要服务 `SyncPlan`，用于识别可以被更细粒度 event sync 替代的 coarse sync candidate。

### 2.4 compute / layout op

第一版 schema 还记录：

- `hivm.hir.nd2nz`：layout transform stage；
- `hivm.hir.mmad` / `hivm.hir.mmadL1`：cube compute stage；
- `hivm.hir.fixpipe`：fixpipe / cube-to-vector 边界；
- `hivm.hir.vreduce` / `vsub` / `vexp` / `vdiv`：vector compute stage。

这些用于 `CVPipelinePlan` 的 stage 分类，也用于 `TilingPlan` 判断 cube tile shape evidence。

---

## 3. 新增实现文件

本阶段新增两个核心文件：

```text
strategy_search/hivm_official_rewrite_plan.py
tools/build_four_plan_rewrite_plan.py
```

### 3.1 `strategy_search/hivm_official_rewrite_plan.py`

这个模块负责三件事：

1. 定义 `OFFICIAL_HIVM_OP_SCHEMA`，记录官方文档中与四个 Plan 相关的 op 子集；
2. 从 `.hivm.mlir` 文本中生成 `hivm_ir_inventory.official.json`；
3. 根据 `selected_plan.json + inventory` 生成 `four_plan_rewrite_plan.json`。

它不会真实修改 IR。

### 3.2 `tools/build_four_plan_rewrite_plan.py`

这个脚本用于命令行生成报告：

```bash
python tools/build_four_plan_rewrite_plan.py \
  --ir sample_input/fa_best.hivm.mlir \
  --selected-plan artifacts/latest_smoke_run/selected_plan.json \
  --output-dir artifacts/latest_smoke_run_official_rewrite_plan
```

输出：

```text
artifacts/latest_smoke_run_official_rewrite_plan/
  hivm_ir_inventory.official.json
  hivm_official_op_schema_subset.json
  four_plan_rewrite_plan.json
```

---

## 4. 四个 Plan 如何转成 rewrite plan

### 4.1 SyncPlan

输入来自 `selected_plan.json`：

```json
{
  "policy": "graph_sync_solver",
  "template": "Y3_event_reuse",
  "event_reuse": true,
  "event_id_policy": "reuse",
  "sync_motion": "local_move"
}
```

inventory 会寻找：

- `hivm.hir.pipe_barrier`
- `hivm.hir.set_flag`
- `hivm.hir.wait_flag`
- legacy/project sample barrier

生成的 rewrite request 包括：

```text
1. detect_pipe_barrier_or_legacy_barrier_candidates
2. derive_producer_consumer_pipe_pairs
3. allocate_fresh_or_proven_reusable_event_ids
4. ask_backend_to_create_set_flag_wait_flag_using_official_syntax
5. defer_event_printing_to_HivmOpsEditor
```

最低安全门禁：

```text
producer_consumer_pair_proven
event_live_range_non_overlapping_or_fresh_event
no_cross_iteration_dependency_removed
deadlock_freedom_check_required
backend_roundtrip_and_verify_pass
```

**结论：SyncPlan 可以先进入 backend-required 真改写路径，但 Python 不再手拼 set/wait 格式。**

---

### 4.2 MultiBufferPlan

输入来自：

```json
{
  "double_buffer": true,
  "input_buffer_multiplier": 2,
  "stage_buffer_multiplier": 2,
  "buffer_multipliers": {
    "q_l1": 1,
    "q_ub": 1,
    "v_l1": 1,
    "k_l1": 1
  }
}
```

inventory 会寻找：

- local buffers：`#hivm.address_space<ub>`、`cbuf/l1`、`cc/l0c`；
- load op；
- layout op；
- compute op 的 operands。

生成的 rewrite request 包括：

```text
1. select_cloneable_local_buffers
2. create_backend_buffer_clone_requests
3. replace_load_layout_compute_operands_by_iteration_or_stage_policy
4. defer_actual_buffer_creation_and_use_replacement_to_HivmOpsEditor
```

最低安全门禁：

```text
target_buffer_has_known_address_space
all_uses_are_known_or_backend_resolvable
no_unknown_side_effect_op_between_producer_consumer
capacity_recheck_passes_after_extra_buffer_slots
buffer_liveness_no_overwrite
backend_roundtrip_and_verify_pass
```

**结论：MultiBufferPlan 的真实 rewrite 是 buffer clone + operand replacement，必须交给 HivmOpsEditor。Python 只生成 clone 请求。**

---

### 4.3 CVPipelinePlan

输入来自：

```json
{
  "stage_num": 2,
  "template": "P2_stage2_balanced",
  "producer_consumer_distance": 1
}
```

inventory 会寻找：

```text
load → nd2nz/copy → cube/mmad → fixpipe → vector → store
```

生成的 rewrite request 包括：

```text
1. classify_ops_into_load_transform_cube_vector_store_stages
2. check_stage_dependency_is_linear
3. require_MultiBufferPlan_pingpong_for_overlap
4. insert_or_reuse_SyncPlan_directional_events_at_stage_boundaries
5. defer_true_stage_reorder_to_HivmOpsEditor
```

最低安全门禁：

```text
stage_sequence_detected
no_cross_tile_reduction_or_unknown_side_effect
pingpong_or_stage_buffer_available
event_liveness_passes
prologue_steady_state_epilogue_defined
backend_roundtrip_verify_DES_trace_pass
```

**结论：CVPipelinePlan 不能独立硬改。它依赖 MultiBufferPlan 和 SyncPlan。第一阶段只做 stage candidate 与 backend mutation plan。**

---

### 4.4 TilingPlan

输入来自：

```json
{
  "tile_m": 32,
  "tile_n": 64,
  "tile_k": 128,
  "loop_order": "outer_mkn",
  "tail_strategy": "mask_or_pad",
  "reduce_tile_policy": "half_k"
}
```

inventory 会寻找：

- `scf.for` loop；
- cube compute op；
- load/store slice anchor；
- buffer capacity evidence。

生成的 rewrite request 包括：

```text
1. emit_tiling_hint_to_backend
2. analyze_loop_split_legality
3. defer_true_loop_index_slice_tailmask_rewrite_to_HivmOpsEditor_or_MLIR_pass
```

最低安全门禁：

```text
loop_bounds_identified
load_store_slice_mapping_identified
tail_mask_policy_defined
capacity_after_tiling_passes
backend_roundtrip_and_verify_pass
```

**结论：TilingPlan 第一阶段只做 report/hint，不建议马上真实 loop rewrite。真实 tiling 最后做。**

---

## 5. 目前基于 `fa_best.hivm.mlir` 的实际结果

已运行：

```bash
python tools/build_four_plan_rewrite_plan.py \
  --ir sample_input/fa_best.hivm.mlir \
  --selected-plan artifacts/latest_smoke_run/selected_plan.json \
  --output-dir artifacts/latest_smoke_run_official_rewrite_plan
```

得到四个 Plan 的状态：

```json
{
  "SyncPlan": "backend_required",
  "MultiBufferPlan": "backend_required",
  "CVPipelinePlan": "backend_required",
  "TilingPlan": "report_and_hint_only_v1"
}
```

这个结果很合理：

- SyncPlan、MultiBufferPlan、CVPipelinePlan 都需要真实 HivmOpsEditor backend；
- TilingPlan 目前只进入 report/hint 阶段，因为真实 loop/index/slice/tail-mask rewrite 风险最高。

---

## 6. 下一步怎么接 HivmOpsEditor

后端应该消费：

```text
selected_plan.json
hivm_ir_inventory.official.json
four_plan_rewrite_plan.json
```

然后按下面流程执行：

```text
1. inventory
2. roundtrip
3. verify-only
4. dry-run mutation
5. mutate
6. post-mutate verify
7. DES/trace
8. msprof 或 simulator evidence
```

后端第一批建议只实现：

```text
1. SyncPlan: barrier/pipe_barrier → official set_flag/wait_flag
2. MultiBufferPlan: selected local buffer clone + use replacement dry-run
```

CVPipelinePlan 和 TilingPlan 暂时不要直接真改。

---

## 7. 最终一句话

基于官方文档实现 rewrite 的核心不是“Python 直接改 HIVM op 格式”，而是：

```text
官方 HIVM Dialect 文档定义可识别 op
fa_best.hivm.mlir 提供真实样例 pattern
inventory 识别当前 IR 的 op/buffer/loop/sync
selected_plan 表达四个 Plan 的优化意图
four_plan_rewrite_plan 把优化意图翻译成 backend mutation 请求
HivmOpsEditor 负责真实 IR 改写
vTriton verifier/DES/trace/msprof 负责验收
```
