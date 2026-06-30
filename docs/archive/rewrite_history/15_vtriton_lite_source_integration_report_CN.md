# vTriton Lite 源码接入分析报告（V4.0）

## 1. 本次检查结论

用户上传的 `vTriton lite.zip` 可以正常解压读取，体积约 1.1MB，包含 368 个文件。关键文件齐全，包括：

```text
include/AscendModel/Transforms/HivmOpsEditor.h
lib/AscendModel/Transforms/HivmOpsEditor.cpp
tools/hivm-crud/hivm-crud.cpp
tools/tritonsim-hivm/tritonsim-hivm.cpp
include/AscendModel/Analysis/HIVMAnalysis.h
lib/AscendModel/Analysis/HIVMAnalysis.cpp
CMakeLists.txt
tools/CMakeLists.txt
lib/AscendModel/Transforms/CMakeLists.txt
test/hivm_add_kernel.npuir.mlir
test/hivm_mixed_cv_kernel.npuir.mlir
perfbound/validate/hivm_edits.py
```

这说明后续不需要重新上传完整 vTriton 仓库；当前 lite 包已经足够做源码级接入分析。

---

## 2. HivmOpsEditor 的真实定位

`HivmOpsEditor.h` 说明它是一个 C++ API，用于在 MLIR `ModuleOp` 上对 HIVM operations 做 programmatic create/read/update/delete。典型 workflow 是：

```text
1. HivmOpsEditor::loadFromFile(ctx, path)
2. 调用 editor methods 应用优化建议
3. editor.exportToFile(outputPath)
```

这验证了 V4.0 的路线是正确的：真实 rewrite 应该通过 HivmOpsEditor，而不是长期依赖 Python 文本替换。

HivmOpsEditor 的 namespace 是：

```cpp
namespace mlir {
namespace ascend {
class HivmOpsEditor { ... };
}
}
```

核心构造方式：

```cpp
explicit HivmOpsEditor(ModuleOp module) : module(module) {}
static OwningOpRef<ModuleOp> loadFromFile(MLIRContext &ctx, llvm::StringRef path);
LogicalResult exportToFile(llvm::StringRef path);
std::string exportToString();
```

---

## 3. HivmOpsEditor 已支持的能力

### 3.1 Read 能力

```cpp
SmallVector<HivmOpInfo> listOps();
std::map<std::string, unsigned> opCounts();
void printSummary(raw_ostream &os);
```

这可以支撑 V4.0 的真实 backend：

```text
--inventory
--print-capabilities
--roundtrip
```

### 3.2 Create 能力

HivmOpsEditor 已支持大量 HIVM op 创建接口，包括：

```text
load / store / copy / fixpipe / nd2nz / nz2nd
vexp / vabs / vln / vrelu / vadd / vsub / vmul / vdiv / vmax / vmin / vreduce 等 vector op
mmadL1 / batchMmadL1 / matmul / mixMatmul / conv1D / conv2D 等 cube/macro op
set_flag / wait_flag / pipe_barrier / sync_block / sync_block_set / sync_block_wait
convert_layout / pointer_cast / bitcast / load_scalar / gather_load / scatter_store / custom / debug
```

这说明官方文档驱动 schema 与源码接口基本方向一致。

### 3.3 Delete/Modify 能力

HivmOpsEditor 支持：

```cpp
void deleteOp(Operation *op);
void deleteAllOpsWithName(llvm::StringRef opName);
void deleteNthOpWithName(llvm::StringRef opName, unsigned n);
void deleteSyncOpsForOp(Operation *computeOp);
void deleteRedundantGMTrips(unsigned count);
void removeRedundantLoadStorePair(unsigned n);
```

也支持若干属性修改：

```cpp
changeElementType
changeMemorySpace
changePipeAttr
changeEventAttr
changeShape
setEventId
setLoadPadMode
setND2NZDstContinuous
setMmadTranspose
...
```

### 3.4 Convenience optimization

源码中已有三个 convenience 方法：

```cpp
removeRedundantLoadStorePair(unsigned n);
fuseConsecutiveComputeOps();
insertDoubleBuffering(Value src, Value ub0, Value ub1, PipeAttr setPipe, PipeAttr waitPipe, EventAttr eventId);
```

这说明 vTriton 侧已经有一些“优化驱动编辑”的雏形。

---

## 4. 需要注意的源码风险

### 4.1 HivmOpsEditor 依赖 BiShengIR HIVM

`HivmOpsEditor.h/.cpp` 被包在：

```cpp
#ifdef TRITONSIM_HAS_BISHENGIR_HIVM
...
#endif
```

也就是说，如果没有开启 `TRITONSIM_HAS_BISHENGIR_HIVM`，HivmOpsEditor 实际不会参与编译。

CMake 中 `hivm-crud` 也是：

```cmake
if(TRITONSIM_HAS_BISHENGIR_HIVM AND EXISTS ".../hivm-crud.cpp")
  add_llvm_executable(hivm-crud ...)
endif()
```

因此，后续真实编译的关键不是 Windows CMD 本身，而是是否能提供 BiShengIR/AscendNPU-IR 的头文件、生成 include 和库。

### 4.2 insertDoubleBuffering 目前不是 production double-buffer

源码中的 `insertDoubleBuffering` 会在函数 entry 起始处插入两组 set/wait/load，但注释中明确写了 event id 简化复用：

```cpp
// For ev1, we need to create a new event with id+1
// Since EventAttr doesn't have a simple way to increment,
// we'll reuse the same event for simplicity
```

这说明它更像 prototype，不应直接作为 production MultiBufferPlan rewrite。

### 4.3 deleteRedundantGMTrips 逻辑较粗

`deleteRedundantGMTrips` 目前逻辑大致是：遍历 LoadOp，如果 load 的 dst 只有一个 user，就删除 load 以及其后到 user 前的 set_flag/wait_flag。

这不是严格的 GM round-trip SSA/alias 证明，不能直接代表安全的复杂 kernel GM deletion。

### 4.4 hivm-crud 是很好的参考，但不是最终 backend

`hivm-crud.cpp` 已经展示了如何：

```text
读取输入 MLIR
构造 HivmOpsEditor
printSummary
add set_flag/wait_flag
delete set_flag/wait_flag
replace vadd -> vsub
roundtrip 输出
remove-gm-trips
```

但它当前只有 `read|add|delete|modify|roundtrip` 模式，还没有 V4.0 需要的：

```text
--print-capabilities
--inventory --report xxx.json
--verify-only
--dry-run --contract xxx.json
--mutate --contract xxx.json
```

所以后续可以基于 hivm-crud 的编译方式和 API 用法，实现真正的 `hivm-operation-backend`。

---

## 5. CMake 接入结论

vTriton 的 `tools/CMakeLists.txt` 已经注册了：

```text
tritonsim-hivm
hivm-crud
```

其中 `hivm-crud` 的链接方式是：

```cmake
target_link_libraries(hivm-crud
  PRIVATE
  AscendModelTransforms
  ${TRITONSIM_BISHENGIR_HIVM_LIBS}
  MLIRIR
  MLIRParser
  MLIRSupport
  LLVMSupport
)
```

因此，V4.0 的 `hivm-operation-backend` 最合理的接入方式是模仿 `hivm-crud`：

```text
1. 新增 tools/hivm-operation-backend/hivm-operation-backend.cpp
2. 在 tools/CMakeLists.txt 中增加 add_llvm_executable(hivm-operation-backend ...)
3. 链接 AscendModelTransforms 和 ${TRITONSIM_BISHENGIR_HIVM_LIBS}
4. include ${TRITONSIM_BISHENGIR_INCLUDE_DIRS}
```

---

## 6. tritonsim-hivm 的可用验收能力

`tritonsim-hivm.cpp` 支持以下关键参数：

```text
--npuir-file
--hardware-config
--arg-bindings
--scheduler static|des
--perfetto-trace-file
--des-graph-file
--remove-pipe-barrier-index
--edited-npuir-file
```

这说明后续真实 rewrite 后，可以用它做结构验收：

```text
original.hivm.mlir -> original_des.json / original_trace.json
optimized.hivm.mlir -> optimized_des.json / optimized_trace.json
```

然后比较：

```text
op count
barrier/event 数量
load/store 数量
DES graph dependency
trace timeline
```

---

## 7. 对四个 Plan 的修正建议

### SyncPlan

源码确认 HivmOpsEditor 已支持：

```text
addSetFlagBefore / addWaitFlagBefore / addPipeBarrierBefore / addSyncBlockBefore / addSyncBlockSet/Wait
changePipeAttr / changeEventAttr / setEventId
```

因此 SyncPlan 可以优先做真实 backend dry-run。第一阶段建议只做：

```text
existing event liveness check
pipe_barrier candidate scan
single barrier -> event pair dry-run
```

不要直接批量插入 set/wait。

### MultiBufferPlan

源码中没有成熟的 buffer clone/use-replacement API；`insertDoubleBuffering` 只是 prototype。

因此 MultiBufferPlan 暂时仍应走：

```text
candidate scan -> dry-run contract -> backend proof
```

如果要真做，需要新增 HivmOpsEditor 方法：

```text
cloneMemrefLikeValue / createPointerCastOrAllocClone
replaceUsesInScope
verifyAllUsesAccounted
capacityRecheckHook
```

### CVPipelinePlan

源码支持创建 load/copy/nd2nz/mmad/vector/fixpipe/store/sync op，但没有成熟的 stage reorder / move operation API。

因此 CVPipelinePlan 第一阶段仍只做 candidate/readiness，不应直接 mutation。

### TilingPlan

源码没有 loop split/index remap/tail mask 的高层 API。TilingPlan 仍应保持 report/hint only。

---

## 8. 下一步最合理的实现任务

基于源码分析，下一步不应该立刻让用户配置 CMake，而是先改 V4.0 backend skeleton，使其贴近真实 vTriton 源码。

建议新增/修正：

```text
1. vtriton_hivm_operation_backend/hivm_operation_backend.cpp
   - 模仿 hivm-crud 的 parse/load/export 写法
   - 支持 --print-capabilities
   - 支持 --inventory --report json
   - 支持 --roundtrip
   - 支持 --verify-only
   - 支持 --dry-run --contract json
   - mutation 暂时只允许 guarded single action

2. vtriton_hivm_operation_backend/CMakeLists.txt
   - 模仿 tools/CMakeLists.txt 中 hivm-crud 的 link 方式

3. docs/16_hivm_operation_backend_api_mapping_CN.md
   - 把 V4.0 contract action 映射到 HivmOpsEditor 方法
```

---

## 9. 当前结论

`vTriton lite.zip` 是够用的。源码证明：

```text
1. HivmOpsEditor 真实存在；
2. HivmOpsEditor 已有 read/create/delete/modify/export 能力；
3. hivm-crud 已经是一个可参考的 CLI wrapper；
4. tritonsim-hivm 已经能输出 DES graph / Perfetto trace；
5. 真实编译依赖 TRITONSIM_HAS_BISHENGIR_HIVM，也就是 BiShengIR/AscendNPU-IR 环境；
6. 四个 Plan 中 SyncPlan 最接近真实 backend 接入，MultiBufferPlan 还缺成熟 buffer clone/use replacement API，CVPipeline/Tiling 暂时不能直接 production mutation。
```
