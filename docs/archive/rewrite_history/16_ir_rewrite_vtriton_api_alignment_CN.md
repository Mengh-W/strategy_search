# V4.0：基于 vTriton 源码的 IR Rewrite 推进方案

## 1. 当前结论

你提供的 `vTriton lite.zip` 证明：vTriton 中确实存在可用于真实 HIVM IR 编辑的 `HivmOpsEditor`，并且已有 `hivm-crud` 作为 CLI 示例。因此，后续 IR rewrite 不应该继续依赖 Python 文本替换，而应该把 V4.0 的 `four_plan_backend_contract.json` 交给一个 HivmOpsEditor-backed 工具执行。

不过，源码也说明：当前 HivmOpsEditor 并不是完整生产级 optimizer。它已经支持 parse/list/export、插入/删除/替换部分 op，以及有限的 GM round-trip prototype；但还没有看到成熟的 buffer clone、scoped use replacement、operation region motion、loop split 等 API。因此四个 Plan 要分层推进。

## 2. vTriton 中可直接复用的接口

### 2.1 文件读写与 inventory

`HivmOpsEditor.h/.cpp` 提供：

```cpp
static OwningOpRef<ModuleOp> loadFromFile(MLIRContext &ctx, llvm::StringRef path);
LogicalResult exportToFile(llvm::StringRef path);
std::string exportToString();
SmallVector<HivmOpInfo> listOps();
std::map<std::string, unsigned> opCounts();
void printSummary(raw_ostream &os);
```

这些接口足以支撑 V4.0 后端的：

```text
--inventory
--roundtrip
--verify-only
```

### 2.2 Sync 相关接口

HivmOpsEditor 已有：

```cpp
addSetFlagWaitFlagBefore / addSetFlagWaitFlagAfter
addSetFlagBefore / addSetFlagAfter
addWaitFlagBefore / addWaitFlagAfter
addPipeBarrierBefore / addPipeBarrierAfter
addSyncBlockBefore / addSyncBlockAfter
addSyncBlockSetBefore / addSyncBlockSetAfter
addSyncBlockWaitBefore / addSyncBlockWaitAfter
changePipeAttr
changeEventAttr
setEventId
```

这说明 SyncPlan 是四个 Plan 中最接近真实 backend mutation 的一个。但 V4.0 仍然不应直接批量插入事件，因为还缺：

```text
producer-consumer pipe pair proof
fresh/reusable event proof
event liveness proof
deadlock freedom check
exact target op index
```

因此当前策略是：先做 `sync_event_insertion` dry-run / rejection contract，等 contract 精确后再开放单 action guarded mutation。

### 2.3 GM round-trip prototype

HivmOpsEditor 提供：

```cpp
removeRedundantLoadStorePair(unsigned n);
deleteRedundantGMTrips(unsigned count);
```

`hivm-crud` 已经通过 `--remove-gm-trips` 调用了这一路径。因此 V4.0 的 `hivm-operation-backend` 可以保守开放：

```text
--mutate --mutation-kind gm_roundtrip_deletion --max-gm-pairs N
```

但它仍然只是 prototype，必须配合 alias / memory SSA / boundary buffer 检查，不能直接用于复杂 kernel 的大范围生产改写。

## 3. 四个 Plan 的真实落地状态

| Plan | vTriton API 支持度 | 当前能做 | 暂时不能做 |
|---|---|---|---|
| SyncPlan | 高 | inventory、event op 识别、set/wait 插入 API 已存在 | 批量 event rewrite，需要 event liveness/deadlock proof |
| MultiBufferPlan | 中低 | candidate / contract / dry-run | buffer clone、scoped use replacement 需要新增 API |
| CVPipelinePlan | 中低 | stage classifier / contract / dry-run | region motion、prologue/steady/epilogue 需要新增 API |
| TilingPlan | 低 | loop anchor report / hint | loop split、index remap、slice/tail mask 需要新增 API |

## 4. 后续推进顺序

### Milestone A：hivm-operation-backend 对齐 hivm-crud

目标是让后端真正按照 vTriton 现有风格工作：

```text
loadFromFile -> HivmOpsEditor -> listOps / verify / exportToFile
```

验收项：

```text
--print-capabilities
--inventory
--roundtrip
--verify-only
--dry-run
```

### Milestone B：SyncPlan dry-run contract 精确化

让 contract 不再只说“sync_event_insertion”，而是必须给出：

```json
{
  "target_op_index": 123,
  "insert_position": "before|after",
  "set_pipe": "PIPE_MTE2",
  "wait_pipe": "PIPE_V",
  "event": "EVENT_ID2",
  "proofs": {
    "producer_consumer_pair_proven": true,
    "event_liveness_ok": true,
    "deadlock_check_passed": true
  }
}
```

### Milestone C：开放单 action SyncPlan guarded mutation

只有当 Milestone B 的 proof 全部齐备，才允许：

```text
--mutate --mutation-kind sync_event_insertion
```

### Milestone D：MultiBufferPlan 先新增 API，不急着 mutation

需要在 HivmOpsEditor 中新增或包装：

```text
cloneLocalBuffer
replaceUsesInRegion
verifyAllUsesAccountedFor
checkBufferLiveness
checkCapacityAfterClone
```

没有这些 API 前，MultiBufferPlan 只能停留在 readiness / contract。

### Milestone E：CVPipeline/Tiling 继续保持 report/hint

CVPipeline 和 Tiling 暂时不作为第一批真实 mutation，因为它们需要 operation motion、loop split、index remap 和 tail mask 支持。

## 5. 当前 V4.0 代码更新

本版已经将 `vtriton_hivm_operation_backend/hivm_operation_backend.cpp` 的 capability 输出改为更贴合真实 vTriton API：

```text
hivmopseditor_load_export_list_ops = true
hivmopseditor_insert_sync_ops_api_available = true
hivmopseditor_gm_roundtrip_delete_api_available = true
hivmopseditor_buffer_clone_api_available = false
hivmopseditor_replace_uses_api_available = false
hivmopseditor_region_motion_api_available = false
hivmopseditor_loop_split_api_available = false
```

并且明确拒绝以下 mutation，直到 API/proof 齐备：

```text
sync_event_insertion
multibuffer_clone
cv_pipeline_stage_reorder
tiling_loop_split
q_load_hoist
```

当前唯一保守开放的真实 mutation 仍然是：

```text
gm_roundtrip_deletion
```

但它必须 limited by `--max-gm-pairs`，且不能用于宣称复杂 kernel production rewrite 已完成。

## 6. 总结

基于 vTriton 源码，IR rewrite 的下一步不是继续写 Python 文本改写，而是把 V4.0 backend adapter 做成 `hivm-crud` 的增强版。第一阶段先完成 parse/list/export/verify/dry-run；第二阶段只开放非常保守的单 action guarded mutation；第三阶段再为 MultiBuffer、CVPipeline、Tiling 补缺失的 Operation-level API。
