# 缺陷注入 MLIR 测试报告

本报告汇总 9 个合成缺陷 MLIR 样例的测试结果。测试目标不是证明真实硬件加速，而是验证当前 strategy-level analytical search demo 是否能识别明显低效/非法方向，并在 cost model 下选择更合理的四类 Plan。

## 1. 测试设计

9 个样例被加入 `tests/defect_inputs/`，对应的期望与审计结果被加入 `tests/defect_expected/defect_run_summary.json`，pytest 用例位于 `tests/test_defect_injection_cases.py`。

| 类别 | 文件 | 构造缺陷 | 期望验证 |
|---|---|---|---|
| A | `defect_A_small_tile_f32_barrier.mlir` | 小 BN tile、f32 score、独立 p buffer、粗粒度 barrier | 是否调整 tile、启用 buffer/pipeline/sync 优化 |
| B | `defect_B_large_tile_ub_overflow.mlir` | 超大 tile、UB overflow、容量不可行 | hardware gate 是否拒绝非法 current IR 并回退合法候选 |
| C | `defect_C_barrier_heavy_sync_stall.mlir` | tile 尚可但 barrier-heavy，同步停顿明显 | SyncPlan 是否往 graph sync / event reuse 方向移动 |
| D | `defect_D_no_overlap_good_tile.mlir` | tile 尚可但缺少 double buffer / CV overlap | 不是只改 tile，也应启用 overlap 相关 Plan |
| E | `defect_E_small_tile_many_sync_f32_redundantQ.mlir` | 小 tile + f32 + 冗余 Q 搬运 + 多 barrier + 冗余写回 | 多种缺陷叠加时是否综合优化四类 Plan |
| F | `defect_F_large_tile_overflow_sync_pressure.mlir` | 大 tile overflow + 额外 buffer + 重复 Q 搬运 + 同步压力 | 复合容量超限时是否仍由 hardware gate 拦截 |
| G | `defect_G_existing_pingpong_but_bad_sync_dtype.mlir` | 已有局部双份缓冲痕迹，但 dtype / sync / vector / tile 仍差 | 已有局部优化时是否继续优化其他瓶颈 |
| H | `defect_H_event_sync_but_small_tile_no_overlap.mlir` | 已有 event sync，但小 tile 和 overlap 仍差 | 已有 event sync 时是否继续优化 tile/buffer/pipeline |
| I | `defect_I_medium_tile_memory_pressure_vector_heavy.mlir` | 中等 tile，但 f32、额外 buffer、vector-heavy、同步压力叠加 | 非极端混合瓶颈是否能被识别 |

## 2. 当前测试命令与结果

```bash
python -m pytest -q
# 37 passed

python -m pytest -q tests/test_defect_injection_cases.py -m regression
# 18 passed, 9 skipped

python -m pytest -q -m slow
# 3 passed, 9 skipped
```

说明：默认测试会跳过 `slow`。9 个 live defect search 用例是 opt-in，默认 skip；这是为了避免日常 CI 每次都重复跑完整搜索。需要重新实跑 9 个缺陷搜索时，可设置：

```bash
RUN_DEFECT_LIVE=1 python -m pytest -q -m slow tests/test_defect_injection_cases.py
```

当前报告中的数值来自已实跑并固化的缺陷注入审计结果。

## 3. 结果汇总

| Case | Current tile | Current feasible | Current cycles | Best tile | DB | CV stage | Sync | Best cycles | Speedup | Risk |
|---|---:|---|---:|---:|---|---:|---|---:|---:|---|
| defect_A_small_tile_f32_barrier | 64x32x128 | True / ok | 1084.034 | 32x64x128 | True | 2 | graph_sync_solver | 458.503 | 2.364x | HIGH |
| defect_B_large_tile_ub_overflow | 128x256x128 | False / UB overflow | 5437.001 | 64x64x128 | True | 2 | graph_sync_solver | 613.071 | N/A | HIGH |
| defect_C_barrier_heavy_sync_stall | 64x64x128 | True / ok | 2252.966 | 32x64x128 | True | 2 | graph_sync_solver | 825.115 | 2.730x | HIGH |
| defect_D_no_overlap_good_tile | 64x64x128 | True / ok | 1352.966 | 32x64x128 | True | 2 | graph_sync_solver | 458.503 | 2.951x | HIGH |
| defect_E_small_tile_many_sync_f32_redundantQ | 64x32x128 | True / ok | 1704.923 | 32x64x128 | True | 2 | graph_sync_solver | 698.747 | 2.440x | HIGH |
| defect_F_large_tile_overflow_sync_pressure | 128x256x128 | False / UB overflow | 6671.235 | 64x64x128 | True | 2 | graph_sync_solver | 1025.558 | N/A | HIGH |
| defect_G_existing_pingpong_but_bad_sync_dtype | 96x96x128 | True / ok | 2509.547 | 16x176x128 | True | 2 | graph_sync_solver | 1103.274 | 2.275x | HIGH |
| defect_H_event_sync_but_small_tile_no_overlap | 64x32x128 | True / ok | 841.813 | 32x64x128 | True | 2 | graph_sync_solver | 431.746 | 1.950x | HIGH |
| defect_I_medium_tile_memory_pressure_vector_heavy | 64x64x128 | True / ok | 1820.083 | 32x64x128 | True | 2 | graph_sync_solver | 699.560 | 2.602x | HIGH |

## 4. 通过测试说明了什么

1. **四类 Plan 联动生效。** 9 个 case 的 best strategy 都启用了 `double_buffer=True`、`cv_pipeline_stage=2`、`sync_policy=graph_sync_solver` 和 `event_reuse=True`，说明搜索结果不是只动单一 tile，而是同时利用 MultiBufferPlan、CVPipelinePlan 和 SyncPlan。

2. **hardware gate 能识别容量非法输入。** `defect_B` 和 `defect_F` 的 current IR 均被判定为 `UB overflow`，speedup 不计算为合法 baseline；搜索结果回退到更小的合法 tile。

3. **已有局部优化不会让搜索器停止。** `defect_G` 已有局部双份缓冲痕迹，`defect_H` 已有 event sync，但搜索器仍继续调整 tile、CV stage 和 sync policy。

4. **复合缺陷能被综合处理。** E–I 不是单点问题，而是 tile、dtype、buffer、sync、vector-heavy、memory pressure 叠加；记录结果显示模型能给出一致的优化方向。


## 5. 不能证明什么

这些测试仍然是 analytical model / demo-level 验证，不能证明真实 NPU 上一定加速，也不能证明 GraphSyncSolver 一定 deadlock-free，不能证明 CVPipelinePlan 一定能被 compiler pass 改写实现。真实闭环仍需要：optimized HIVM rewrite、编译运行、msprof profiling、cost calibration 和 legality checker。

## 6. 后续建议

- 把 live defect suite 做成独立脚本，用于刷新 `tests/defect_expected/defect_run_summary.json`。
- 增加 parser 注释剥离，避免注释文本污染 `ping/pong`、`cv_pipeline` 等结构识别。
- 对 `defect_G` 这类产生 `16x176x128` 的候选增加真实硬件/编译约束，例如 alignment、preferred tile whitelist、tail handling 和 pass 可生成性。
