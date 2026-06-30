# V4.8 MultiBufferPlan rewrite readiness

版本：`V4.8-multibuffer-rewrite-readiness`

## 目标

V4.7 已经把 SyncPlan 的 portable rewrite 做到可改、可审计、可迁移。V4.8 开始推进 MultiBufferPlan，但不直接伪造 buffer clone/use replacement，因为真实 HIVM 里 buffer 形态不是只有 `memref.alloc`，而是大量出现：

- `hivm.hir.pointer_cast`
- `memref.subview`
- `memref.reinterpret_cast`
- `memref.cast`
- `hivm.hir.nd2nz`
- `hivm.hir.fixpipe`
- `hivm.hir.load/store`

所以 V4.8 的目标是先完成 MultiBufferPlan 的工程化前置闭环：识别 buffer-like anchor、排序候选、生成 mutation plan、输出可审计报告，并给未来 HivmOpsEditor mutation 提供同构 action list。

## 新增输出

运行后会生成：

```text
multibuffer_rewrite_readiness.json
multibuffer_mutation_plan.json
multibuffer_annotated_not_mutated.hivm.mlir
multibuffer_annotation_report.json
multibuffer_rewrite_readiness_summary.json
```

其中 `multibuffer_annotated_not_mutated.hivm.mlir` 只插入注释，不改语义。

## 为什么不直接 rewrite buffer？

MultiBuffer 的真实 rewrite 不是简单插两行文本。它需要：

1. 确定 producer/consumer stage；
2. 确定 loop iteration parity，例如 `i % 2`；
3. clone 或创建 ping-pong buffer slot；
4. 按 stage 替换 use；
5. 插入或复用 SyncPlan event；
6. 重新检查容量边界；
7. 用真实 MLIR verifier 和 DES/trace 验证。

没有真实 HivmOpsEditor verifier 时，直接文本替换容易产出“看起来像 HIVM，但语义不合法”的 IR。因此 V4.8 的边界是：**rewrite readiness + mutation plan，不做语义性 buffer mutation。**

## Windows CMD

```cmd
scripts\run_v48_multibuffer_rewrite_readiness.cmd
```

指定输入：

```cmd
scripts\run_v48_multibuffer_rewrite_readiness.cmd ^
  sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir ^
  artifacts\latest_smoke_run\selected_plan.json ^
  artifacts\v48_multibuffer_rewrite_readiness ^
  50 ^
  20
```

## 当前结论

V4.8 表示 MultiBufferPlan 已经开始进入 rewrite 主线，但目前是 readiness / mutation-plan 阶段，不 claim production mutation。

准确表述：

> 当前已经实现 MultiBufferPlan 的 buffer-like anchor 检测、候选排序、风险评估、mutation plan 生成和 HivmOpsEditor 迁移接口清单；暂不执行真实 buffer clone/use replacement，后续需要真实 Operation-level verifier、dominance/alias 分析和 stage-boundary 分析。
