# V5.6 四 Plan operation-level rewrite MVP 说明

## 目标

V5.6 的目标从 V5.5 的 `production-candidate rewrite` 进一步收紧为：

```text
selected_plan.json
+ input.hivm.mlir
→ 四个 Plan 都发生 operation-level mutation
→ optimized.four_plan_operation_rewrite.hivm.mlir
→ operation_parameter_coverage.json
```

它不再满足于 metadata、readiness 或只生成 candidate 注释，而是要求每个 Plan 的寻优参数都映射到一个具体 operation rewrite action。

## 当前新增入口

```bash
python tools/run_four_plan_operation_rewrite.py \
  --ir sample_input/fa_best.hivm.mlir \
  --selected-plan artifacts/latest_smoke_run/selected_plan.json \
  --output-dir artifacts/v56_four_plan_operation_rewrite
```

快捷脚本：

```bash
bash scripts/run_v56_four_plan_operation_rewrite.sh
```

Windows：

```bat
scripts\run_v56_four_plan_operation_rewrite.cmd
```

## 四个 Plan 当前如何体现为 operation mutation

| Plan | V5.6 operation-level MVP 行为 |
|---|---|
| TilingPlan | 插入 M/N/K outer tile loop scaffold，按照 `loop_order` materialize 外层 tile loop 顺序；插入 tail/reduction/layout guard；同时按 `tile_m/tile_n/tile_k` 改写 local memref operation/type shape。 |
| MultiBufferPlan | 生成 ping/pong slot，clone buffer 定义，并对 selected producer/consumer use 做替换。 |
| CVPipelinePlan | 识别 load/view→compute→store window，插入 load→compute 与 compute→store 的 set/wait sync edges，并做 pipeline group 标记和可选 slot binding。 |
| SyncPlan | 将已有 set_flag/wait_flag 归一化为显式 event operation，并保留 event policy 选择。 |

## 输出产物

核心产物：

```text
artifacts/v56_four_plan_operation_rewrite/optimized.four_plan_operation_rewrite.hivm.mlir
```

带参数覆盖 metadata 的版本：

```text
artifacts/v56_four_plan_operation_rewrite/optimized.four_plan_operation_rewrite.with_coverage.hivm.mlir
```

参数到 operation action 的覆盖表：

```text
artifacts/v56_four_plan_operation_rewrite/operation_parameter_coverage.json
```

汇总报告：

```text
artifacts/v56_four_plan_operation_rewrite/four_plan_operation_rewrite_summary.json
```

## 和 V5.5 的区别

V5.5 主要是“production-candidate”：四个 Plan 都有可见 mutation，但 TilingPlan 还主要是 type/shape candidate，不能说明 tiling 参数完整体现到了控制流。

V5.6 新增 Tiling semantic loop rewrite：

```text
tile_m/tile_n/tile_k + loop_order
→ scf.for %m_outer / %n_outer / %k_outer tile loop scaffold
```

并且显式把：

```text
tail_strategy
reduce_tile_policy
layout_aware_tile
```

落成 tile body 内的 guard request，供 Linux backend/HivmOpsEditor 绑定真实 shape、slice offset、tail mask 与 partial accumulator。

## 仍然不能越界声称的事情

V5.6 仍然不是“已经证明 Linux 可编译可运行”。原因是：

```text
1. %cM/%cN/%cK 等符号 upper bound 需要 backend 绑定到真实 problem shape；
2. load/store slice offset、tail mask、partial accumulation 需要 MLIR/HIVM verifier 检查；
3. MultiBuffer use-def 和 CVPipeline stage movement 需要真实 dominance/liveness 验证；
4. SyncPlan 的 official op syntax 和 event liveness 需要 Linux backend 验证。
```

因此汇报口径应该是：

> V5.6 已经把四个 Plan 的寻优参数推进到 operation-level MVP rewrite，并输出了 optimized HIVM candidate 与参数到 operation action 的覆盖表。它已经不是 metadata-only，也不只是 readiness；但仍需要在 Ascend Linux 环境中完成 parse、roundtrip、verifier、backend compile、correctness 和 msprof，才能正式声称性能提升。

## Linux 验证顺序

```text
1. baseline HIVM parse / compile
2. optimized.four_plan_operation_rewrite.hivm.mlir parse
3. HivmOpsEditor roundtrip
4. MLIR/HIVM verifier
5. backend compile
6. correctness check
7. baseline msprof
8. optimized msprof
9. median latency / cycles 对比
```
