# 05 输出目录说明

清理版不再保留几十个历史 output 目录，只保留一个精选 smoke run：

```text
artifacts/latest_smoke_run/
```

推荐阅读顺序：

1. `selected_strategy.json`：当前模型选出的最佳策略。
2. `selected_plan.json`：四类 Plan 的具体参数。
3. `cost_breakdown.json`：成本分项。
4. `kernel_cost_profile.json`：从 MLIR/产物结构抽取出的 cost profile。
5. `hardware_boundary_audit.json`：硬件边界检查。
6. `optimized.annotated.hivm.mlir`：annotation 写回结果。
7. `optimized.safe_structural.hivm.mlir`：safe hint 写回结果。
8. `optimized.structural.hivm.mlir`：结构改写候选结果。
9. `phase_reports/`：Phase6 相关验收/后端报告。

注意：这里的输出用于说明流程能跑通，不代表真机性能已经被验证。
