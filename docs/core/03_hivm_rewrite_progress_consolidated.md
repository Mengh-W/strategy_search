# 03 HIVM Rewrite 当前进展合并版

## 当前已经实现

### 1. 策略搜索
项目可以围绕四类 Plan 生成候选并排序：

- TilingPlan：tile shape、block 并行、loop order、tail/reduce 相关参数。
- MultiBufferPlan：double buffer、per-buffer multiplier、stage buffer、load/store overlap。
- CVPipelinePlan：Cube/Vector overlap、pipeline stage、producer-consumer distance。
- SyncPlan：barrier/event、GraphSyncSolver、event reuse、sync 粒度和移动策略。

输出核心文件包括 `selected_strategy.json`、`selected_plan.json`、`cost_breakdown.json`、`strategy_search_report.html`。

### 2. Annotation / Hint 写回
已经可以生成：

- `optimized.annotated.hivm.mlir`
- `optimized.safe_structural.hivm.mlir`
- `optimized.structural.hivm.mlir`

其中 annotation 主要写 `hivm.strategy.*` attribute；safe structural hint 主要写 multi-buffer、`hivm.nbuf`、`hivm.cv.*` 等提示信息。

### 3. 小范围真实 sync/barrier 改写
C++ HIVM Rewrite Bridge 已经能做小范围 op sequence rewrite，例如把粗粒度 `barrier_all` 替换为方向性 `set_flag / wait_flag`，以及在 CV 边界前插入同步 hint/sequence。

### 4. 受限正例真改写
`tools/restricted_hivm_true_rewriter.py` 已经能在受限正例上做：

- Q-load hoist：把 loop 内重复的 Q load / nd2nz 搬到 loop 外。
- GM round-trip deletion：在非常受限的 GM store/reload 正例中删除冗余 round-trip。

这证明项目具备真改写雏形，但不能扩大解释成复杂真实 kernel 的 production rewrite。

### 5. 复杂 rewrite 门禁
已经生成 dependency graph、event liveness、buffer liveness、capacity recheck、GM alias、GM memory SSA、Q-load hoist decision、rewrite legality gate 等报告。原则是：不能证明安全，就不执行复杂 rewrite。

### 6. vTriton/HivmOpsEditor 后端接入骨架
项目已经包含 `vtriton_hivm_operation_backend/`、构建脚本和验收脚本，用于接入真实 vTriton 源码中的 HivmOpsEditor 能力。

## 还没有完成

不能宣称已经完成的部分：

- 真实复杂 kernel 的 production Q-load hoist；
- 真实复杂 kernel 的 production GM round-trip deletion；
- real double-buffer ping-pong rewrite；
- full CVPipeline overlap rewrite；
- real tiling loop lowering；
- msprof 真机性能验证；
- 完整生产级 MLIR/HivmOpsEditor compiler pass。

## 当前最该做
下一步不是继续堆文档，而是在真实 vTriton 环境中编译并验收 `hivm-operation-backend`。验收顺序建议是：

1. `--print-capabilities`
2. `--inventory`
3. `--roundtrip`
4. `--verify-only`
5. `--dry-run`
6. `--mutate --mutation-kind gm_roundtrip_deletion`
7. 如果有 `tritonsim-hivm`，继续跑 DES/trace 对比。

## 后续里程碑
1. backend 编译通过。
2. no-op roundtrip / verify 通过。
3. 受限 GM round-trip deletion 通过。
4. 扫真实样例 pattern。
5. Q-load hoist Operation-level prototype。
6. DES/trace 验证。
7. 真实复杂 kernel 的保守 rewrite。
8. 最后再考虑 double-buffer / CV overlap / tiling lowering。
