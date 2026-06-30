# V5.0 MultiBufferPlan Restricted True Rewrite

## 1. 本版目标

V5.0 的目标是把 MultiBufferPlan 从 V4.8/V4.9 的 `readiness / stage-boundary / mutation plan scaffold` 推进到真正会修改 IR 的 portable rewrite。

本版不是只加注释，也不是只生成 JSON plan，而是会输出一个新的：

```text
optimized.multibuffer_rewritten.hivm.mlir
```

其中会真实出现：

```text
ping / pong buffer slot
producer use replacement
consumer use replacement
fallback original buffer preserved
```

## 2. Rewrite 策略

当前采用 `restricted additive ping-pong rewrite`：

1. 选择 V4.9 stage-boundary 中 READY/REVIEW 的 buffer candidate；
2. 在原 buffer definition 后面插入 ping/pong slot 定义；
3. 将选中的 producer line 和 consumer line 中的原 buffer symbol 替换为 ping slot；
4. pong slot 暂时作为后续 CVPipeline cross-iteration binding 的预留 slot；
5. 原始 buffer 不删除，作为 fallback 保留；
6. 输出 rewrite report、replacement report、diff report 和 portable validation。

## 3. 为什么先 additive rewrite

没有真实 BiShengIR/vTriton/HivmOpsEditor verifier 时，直接删除原 buffer、移动 operation、改 loop parity 都有较高风险。因此 V5.0 的第一版真 rewrite 采取保守策略：

```text
新增 slot > 局部替换 use > 保留 fallback > 结构验证
```

这样至少可以保证 IR 中出现真实结构变化，同时又不做高风险 destructive mutation。

## 4. 输出文件

默认输出目录：

```text
artifacts/v50_multibuffer_true_rewrite/
```

核心输出：

```text
optimized.multibuffer_rewritten.hivm.mlir
multibuffer_true_rewrite_report.json
multibuffer_true_rewrite_validation.json
multibuffer_true_rewrite_diff.json
multibuffer_true_rewrite_summary.json
multibuffer_true_rewrite_actions.json
multibuffer_stage_boundary_report.json
multibuffer_stage_mutation_plan.json
```

## 5. Windows CMD 运行

```cmd
cd /d D:\hivm\HIVM_strategy_search_demo_V5.0
scripts\run_v50_multibuffer_true_rewrite.cmd
```

指定参数：

```cmd
scripts\run_v50_multibuffer_true_rewrite.cmd ^
  sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir ^
  artifacts\latest_smoke_run\selected_plan.json ^
  artifacts\v50_multibuffer_true_rewrite ^
  80 ^
  3
```

最后一个参数表示最多执行多少个 portable/restricted rewrite action。默认 3，建议在没有真实 verifier 的情况下不要一次改太多。

## 6. Smoke 结果

在 `chunk_kda_kernel_clean.npuir.mlir` 上默认运行结果：

```json
{
  "version": "V5.0-multibuffer-restricted-true-rewrite",
  "stage_candidate_count": 80,
  "stage_ready_count": 20,
  "true_rewrite_action_count": 3,
  "mutation_performed": true,
  "rewritten_action_count": 3,
  "replacement_count": 6,
  "num_multibuffer_related_diff_lines": 30,
  "passed_portable_validation": true,
  "semantic_mutation_performed": true,
  "production_rewrite_claim_allowed": false
}
```

## 7. 当前边界

V5.0 可以说 MultiBufferPlan 已经进入真正 rewrite 阶段，因为它实际修改 IR，生成新的 optimized MLIR，并完成 replacement/validation/diff。

但仍不能 claim production rewrite，因为：

1. 当前是 portable text-level rewrite，不是 Operation-level HivmOpsEditor mutation；
2. ping/pong slot 目前是 additive alias 形式，尚未经过真实 capacity gate；
3. loop parity / cross-iteration binding 还没有真正实现；
4. 没有真实 MLIR verifier；
5. 没有 DES/trace/msprof 验证。

## 8. 下一步

下一步建议推进：

```text
V5.1 CVPipelinePlan portable/restricted rewrite
```

它应该复用 V5.0 的 ping/pong slot，将 CVPipeline window 里的 load/compute/store 绑定到 pipeline group，并插入/复用 SyncPlan event。
