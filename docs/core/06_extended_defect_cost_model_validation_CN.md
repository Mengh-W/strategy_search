# 扩展缺陷 HIVM 样例与 Cost Model 识别方向验证

版本：`V5.3.1-backend-contract-ready-prelinux-lf-hygiene`

本文档记录在原有 9 个 synthetic defect HIVM/NPUIR 样例基础上，新增 5 个扩展缺陷样例后的测试结果。目标不是证明真实 NPU 性能收益，而是验证当前解析式 cost model 与 hardware gate 是否能对明显低效/非法的 IR 结构给出合理的优化方向。

---

## 1. 新增样例位置

新增文件位于：

```text
tests/defect_inputs/
```

新增 5 个样例：

| 编号 | 文件 | 主要缺陷 |
|---|---|---|
| J | `defect_J_tiny_tile_nested_barrier_f32.mlir` | 极小 16x16 tile、嵌套循环、f32 score、大量 barrier、额外 UB buffer、vector-heavy |
| K | `defect_K_oversized_m128n192_f32_overflow.mlir` | 128x192 大 tile、f32 score、额外 UB buffer，触发 UB overflow |
| L | `defect_L_good_tile_event_mismatch_vector_heavy.mlir` | 已有 ping-pong 痕迹，但 event set/wait 不匹配、vector-heavy、f32 路径仍重 |
| M | `defect_M_tail_unfriendly_n176_no_overlap.mlir` | 32x176 非常规 N tile、缺少 double buffer / CV overlap、barrier 较多 |
| O | `defect_O_pingpong_but_many_barriers_extra_buffers.mlir` | 已有 ping-pong，但 barrier 很多、额外 buffer 多、vector-heavy |

说明：原计划中曾临时构造过一个 `K=64` 的小 K 样例，但它会显著放大搜索空间和运行时间，不适合纳入默认回归，因此未加入最终包。

---

## 2. 更新后的测试资产

| 文件 | 作用 |
|---|---|
| `tests/defect_inputs/defect_*.mlir` | 缺陷 HIVM/NPUIR 输入样例，当前共 14 个 |
| `tests/defect_expected/defect_run_summary.json` | 14 个样例的合并期望结果 |
| `tests/defect_expected/new_defect_run_summary.json` | 新增 J/K/L/M/O 的单独实跑摘要 |
| `tests/test_defect_injection_cases.py` | 默认轻量回归测试；验证 parser 结果和 recorded optimization direction |

默认测试不会每次重跑完整 search，而是读取 summary 做轻量回归。需要重新实跑所有 defect 搜索时，可使用：

```bash
RUN_DEFECT_LIVE=1 python -m pytest -q -m slow tests/test_defect_injection_cases.py
```

---

## 3. 新增样例实跑结果

本轮使用命令模板：

```bash
python auto_strategy_search.py \
  --kernel tests/defect_inputs/<case>.mlir \
  --hardware-config configs/ascend_910b.json \
  --cost-model-config configs/cost_model_conservative.json \
  --cost-risk-mode conservative \
  --output-dir <out>
```

结果如下：

| case | current tile | current feasible | current cycles | best tile | best DB | best CV | best sync | best cycles | predicted direction |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|
| `defect_J_tiny_tile_nested_barrier_f32` | 16x16x128 | True | 5918.171 | 32x64x128 | True | 2 | graph_sync_solver | 1087.578 | 5.442x |
| `defect_K_oversized_m128n192_f32_overflow` | 128x192x128 | False / UB overflow | 6495.883 | 32x64x128 | True | 2 | graph_sync_solver | 711.419 | N/A |
| `defect_L_good_tile_event_mismatch_vector_heavy` | 64x96x128 | True | 1467.427 | 32x64x128 | True | 2 | graph_sync_solver | 778.808 | 1.884x |
| `defect_M_tail_unfriendly_n176_no_overlap` | 32x176x128 | True | 2756.537 | 32x64x128 | True | 2 | graph_sync_solver | 711.949 | 3.872x |
| `defect_O_pingpong_but_many_barriers_extra_buffers` | 96x64x128 | True | 2461.289 | 32x64x128 | True | 2 | graph_sync_solver | 1123.573 | 2.191x |

---

## 4. 结论

### 4.1 能识别的方向

新增样例覆盖了 5 类之前样例里还不够充分的情况：

1. **极小 tile + 嵌套循环 + 多 barrier**：`defect_J` 被明显拉向更大的有效 tile、double buffer、CV stage 2 和 graph sync。
2. **容量非法大 tile**：`defect_K` 的 current IR 被判定为不可行，summary 中标记为 `UB overflow`，搜索结果回退到合法 tile。
3. **已有局部 ping-pong 但同步/向量路径仍差**：`defect_L` 和 `defect_O` 说明已有局部 double-buffer 痕迹不会让搜索器停止，仍会继续优化 CVPipeline 和 SyncPlan。
4. **非常规 N tile / tail-unfriendly tile**：`defect_M` 从 32x176x128 被拉回 32x64x128，说明当前模型会倾向于更稳定的标准 tile 形状。
5. **复合缺陷叠加**：J/L/O 同时包含 dtype、sync、buffer、vector-heavy 等多种缺陷，搜索方向仍一致。

### 4.2 仍需谨慎的地方

这些结果只能说明：

```text
当前 analytical cost model 能对 synthetic defect IR 给出方向上合理的搜索结果。
```

不能说明：

```text
这些 predicted speedup 等于真实 msprof speedup；
这些 rewritten artifact 已经通过真实 BiShengIR/MLIR verifier；
这些 graph_sync_solver/event_reuse 策略一定能被真实后端安全 lowering。
```

特别是 `graph_sync_solver` 和 `event_reuse` 的最终安全性，仍需要真实 HivmOpsEditor / vTriton backend / verifier / DES / msprof 验证。

---

## 5. 本轮回归结果

轻量 defect regression：

```text
28 passed, 14 skipped
```

其中：

- 28 passed = 14 个样例 x 2 个轻量测试；
- 14 skipped = live optimizer 搜索为 opt-in slow 测试，默认跳过。

本轮也重新跑了 pre-Linux 主门禁，结果仍通过。
