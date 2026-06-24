# 测试体系说明

本项目的测试目标不是证明真实 NPU 性能提升，而是保证 strategy-search demo 的工程行为稳定、可回归、可维护。

## 1. 测试分层

| 层级 | marker | 默认运行 | 目的 |
|---|---|---:|---|
| Unit | `unit` | 是 | 检查 parser、cost model 局部公式、hardware gate 和 package facade |
| Smoke | `smoke` | 是 | 跑小 sample kernel，验证主流程和报告输出不坏 |
| Regression | `regression` | 部分默认 / 部分 slow | 锁住 Stage2a/Stage2b/Stage2c 的搜索稳定性行为 |
| Slow | `slow` | 否 | Beam vs compact exhaustive / random baseline 等较重审计 |

`pytest.ini` 默认使用：

```bash
-m "not slow"
```

因此日常 CI 不会运行最重的 search-quality audit。

## 2. 推荐命令

日常开发：

```bash
python -m pytest
```

只跑快速单元测试：

```bash
python -m pytest -m "unit and not slow"
```

只跑 smoke：

```bash
python -m pytest -m "smoke and not slow"
```

跑慢速搜索质量审计：

```bash
python -m pytest -m slow
```

跑全部 pytest 测试：

```bash
python -m pytest -m "unit or smoke or regression or slow"
```

兼容旧的 unittest 入口：

```bash
python -m unittest discover -s tests -v
```

注意：unittest 不理解 pytest marker，因此会把 slow 测试也一起运行。

## 3. 新增的关键测试

### Plan 参数敏感性测试

新增 `tests/test_cost_model_unit.py`，专门检查四类 Plan 的主要参数是否真的进入 cost / gate：

| 测试 | 防止的问题 |
|---|---|
| TilingPlan 改变 tile count 和局部 memory | tile 参数只在字段里变化，但 cost 不变 |
| block_dim 改变 effective parallelism | block 并行度不影响 cost |
| MultiBufferPlan 降低 exposed load/store，同时提高 live memory | double buffer 只给收益、不占资源，或完全不影响模型 |
| CVPipelinePlan 改变 Cube/Vector overlap，并产生估计合法性风险 | CV stage 只出现在报告里，不影响模型 |
| SyncPlan 改变 sync cost，并产生 graph/event 风险 | graph_sync_solver/event reuse 收益没有进入 cost 或风险没体现 |
| hardware gate 边界测试 | 容量刚好等于上限和超过上限的行为不稳定 |

### 搜索稳定性测试

原有 `tests/test_strategy_search_smoke.py` 保留 Stage2a/Stage2b/Stage2c 的回归测试，并将较重的搜索质量审计标记为 `slow`。

## 4. 当前测试边界

这些测试仍然不能证明：

1. selected strategy 能被真实 compiler lowering；
2. graph sync solver 一定 deadlock-free；
3. predicted cycles 等于 msprof 实测 cycles；
4. optional DES/trace profile 一定来自同一个真实 kernel。

它们解决的是工程稳定性问题：防止参数失效、搜索退化、报告字段丢失、硬件 gate 失效。

## 缺陷注入测试（synthetic bad MLIR regression）

本仓库现在包含 9 个带明确缺陷的 synthetic MLIR 样例：

```text
tests/defect_inputs/
tests/defect_expected/defect_run_summary.json
tests/test_defect_injection_cases.py
DEFECT_INJECTION_TEST_REPORT.md
```

这些样例覆盖小 tile、UB overflow、barrier-heavy、缺少 double buffer/CV overlap、已有局部优化但整体仍差、以及多种瓶颈叠加等情况。

默认测试会验证缺陷文件、parser 恢复出的 current IR tile/sync 信息，以及已记录搜索结果是否朝正确方向优化：

```bash
python -m pytest -q tests/test_defect_injection_cases.py -m regression
```

当前结果：

```text
18 passed, 9 skipped
```

其中 9 个 skipped 是 opt-in live search 测试。需要重新实跑 9 个缺陷样例时：

```bash
RUN_DEFECT_LIVE=1 python -m pytest -q -m slow tests/test_defect_injection_cases.py
```

注意：缺陷注入测试证明的是 analytical cost model 下的方向合理性，不证明真实硬件加速。真实验证仍需要 optimized HIVM rewrite、编译运行和 msprof profiling 闭环。
