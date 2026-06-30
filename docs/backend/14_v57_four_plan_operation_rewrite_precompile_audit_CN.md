# V5.7 四 Plan operation rewrite 的 Linux precompile hardening

## 目标

V5.6 已经可以把 TilingPlan、MultiBufferPlan、CVPipelinePlan、SyncPlan 串成一个 operation-level MVP rewrite pipeline，并输出：

```text
optimized.four_plan_operation_rewrite.hivm.mlir
```

但 V5.6 的问题是：它能说明“四个 Plan 都发生了 operation-level action”，却不能提前发现一些明显会阻塞 Linux backend 编译的问题，例如：

- SSA 值重复定义；
- `%cM/%cN/%cK/%c32` 等 tile loop 常量没有物化；
- memref alloc type 与后续 operation use type 不一致；
- 四个 Plan 的关键 rewrite marker 缺失；
- brace/module/function 结构损坏。

V5.7 的目标不是声称已经 Linux 可编译，而是新增一个更严格的 **precompile audit gate**：在把 optimized HIVM 交给 Ascend Linux backend 前，先本地检查这些明显 blocker。

## 新增模块

```text
strategy_search/operation_rewrite/linux_precompile_audit.py
```

核心能力：

```text
1. infer_problem_bounds_from_signature
2. materialize_missing_index_constants
3. audit_linux_precompile_candidate
4. write_v57_precompile_audit_outputs
```

## 输出文件

默认运行：

```bash
bash scripts/run_v57_four_plan_operation_rewrite_precompile_audit.sh
```

会输出：

```text
artifacts/v57_four_plan_operation_rewrite_precompile_audit/
  optimized.four_plan_operation_rewrite.hivm.mlir
  optimized.four_plan_operation_rewrite.precompile_hardened.hivm.mlir
  v57_constant_materialization_report.json
  v57_linux_precompile_audit.json
  four_plan_operation_rewrite_summary.json
```

其中：

- `optimized.four_plan_operation_rewrite.hivm.mlir`：V5.6/V5.7 原始四 Plan operation rewrite 结果；
- `optimized.four_plan_operation_rewrite.precompile_hardened.hivm.mlir`：补了部分 index/tile 常量后的候选文件；
- `v57_linux_precompile_audit.json`：本地 precompile audit 报告；
- `four_plan_operation_rewrite_summary.json`：汇总四 Plan rewrite 与 precompile audit 状态。

## V5.7 能验证什么

V5.7 可以提前验证：

```text
1. 四个 Plan 的 operation-level marker 是否都存在；
2. brace/module/function 基本结构是否完整；
3. 是否存在重复 SSA 定义；
4. 是否存在明显未定义的 SSA symbol；
5. memref 声明 type 和 operation use type 是否明显不一致；
6. 是否已经将部分 `%cM/%cN/%cK/%c32` 等 tile loop 常量物化。
```

## V5.7 不能验证什么

V5.7 仍然不能替代：

```text
1. 官方 HIVM parser；
2. MLIR verifier；
3. HivmOpsEditor roundtrip；
4. Ascend backend compile；
5. correctness check；
6. msprof 性能对比。
```

所以即使 `v57_linux_precompile_audit.json` 通过，也只能说：

> optimized HIVM 已经通过本地 precompile blocker 检查，可以更干净地交给 Linux backend 验证。

不能说：

> optimized HIVM 已经 Linux 可编译、可运行、可证明性能提升。

## 对当前样例的意义

如果 audit 报出 blocker，例如 duplicate SSA 或 memref type mismatch，说明当前 operation rewrite 还不应该直接拿去 msprof，而应该先修复对应 Plan 的 rewrite 逻辑。

这比 V5.6 更进一步：V5.6 只说明“四 Plan 都改了”，V5.7 开始回答“改完之后有没有明显编译前 blocker”。


## 当前样例结果

在默认样例 `sample_input/fa_best.hivm.mlir` + `artifacts/latest_smoke_run/selected_plan.json` 上，V5.7 已经能生成 hardened candidate，并通过本地 precompile audit：

```json
{
  "passed_portable_precompile_audit": true,
  "duplicate_ssa_definition_count": 0,
  "undefined_symbol_count": 0,
  "memref_type_mismatch_count": 0
}
```

这说明当前默认样例的四 Plan operation rewrite 产物已经消除了本地可检测的明显编译前 blocker。下一步应把：

```text
artifacts/v57_four_plan_operation_rewrite_precompile_audit/optimized.four_plan_operation_rewrite.precompile_hardened.hivm.mlir
```

交给 Ascend Linux 环境执行官方 parse、roundtrip、verifier、backend compile 和 correctness check。
