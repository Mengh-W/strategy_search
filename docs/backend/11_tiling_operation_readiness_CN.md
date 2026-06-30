# V5.4 TilingPlan Operation Readiness 推进说明

## 1. 本次推进的边界

本次没有冒险做 Python 文本级 loop/index/slice 改写，而是把 TilingPlan 从原来的 `REPORT_AND_HINT_ONLY` 推进到 **Linux backend anchor/dry-run validation** 阶段。

也就是说，现在 TilingPlan 不再只是写 metadata 或报告 tile 参数，而是会生成一份 backend 可以消费的 dry-run operation plan，用来在 Linux / Ascend backend 环境里检查：

- loop anchor 是否能定位；
- load/store/compute op 是否能定位；
- buffer shape 是否支持 axis evidence；
- `tile_m/tile_n/tile_k` 是否能映射为 loop split 请求；
- `tail_strategy` 是否需要 tail guard；
- `reduce_tile_policy` 是否需要 partial accumulation 证明；
- `loop_order` 是否需要 loop permutation legality check。

当前仍然不宣称 production operation rewrite 已完成，因为真正改 loop bound、index expression、memref slice、tail mask 和 reduction accumulation 必须交给 MLIR/HivmOpsEditor backend 验证。

## 2. 新增模块

新增文件：

```text
strategy_search/tiling_operation_readiness.py
tools/run_tiling_operation_readiness.py
scripts/run_v54_tiling_operation_readiness.sh
scripts/run_v54_tiling_operation_readiness.cmd
tests/test_v54_tiling_operation_readiness.py
```

核心输出目录示例：

```text
artifacts/v54_tiling_operation_readiness/
  hivm_ir_inventory.official.json
  tiling_operation_readiness.json
  tiling_operation_dry_run_plan.json
  tiling_parameter_readiness.json
  tiling_operation_readiness_summary.json
```

## 3. 当前 TilingPlan 参数 readiness 分级

| 参数 | 当前推进到的阶段 | 含义 |
|---|---|---|
| `tile_m` | Level 2 dry-run operation plan | 生成 M 方向 loop split 和 slice rewrite 请求 |
| `tile_n` | Level 2 dry-run operation plan | 生成 N 方向 loop split 和 slice rewrite 请求 |
| `tile_k` | Level 2 dry-run operation plan | 生成 K/reduction 方向 split 和 partial accumulation 证明请求 |
| `loop_order` | Level 1 backend anchor validation | 检查 loop permutation 合法性，暂不直接 mutation |
| `tail_strategy` | Level 1 backend anchor validation | 检查 tail guard/mask/pad 语义，暂不直接 mutation |
| `reduce_tile_policy` | Level 1 backend anchor validation | 检查 reduction accumulation 策略，暂不直接 mutation |
| `layout_aware_tile` | Level 1 backend anchor validation | 检查 layout-sensitive tile shape 证据，暂不直接 mutation |

## 4. 和旧版 TilingPlan 的区别

旧版 TilingPlan 的状态是：

```text
REPORT_AND_HINT_ONLY_V1
```

本次之后，TilingPlan 可以输出：

```text
READY_FOR_LINUX_BACKEND_ANCHOR_DRY_RUN
```

这表示它已经有 Linux backend 预验证入口，但仍然不是 production rewrite。

## 5. 如何运行

Linux / macOS：

```bash
bash scripts/run_v54_tiling_operation_readiness.sh \
  sample_input/fa_best.hivm.mlir \
  artifacts/latest_smoke_run/selected_plan.json \
  artifacts/v54_tiling_operation_readiness
```

Windows：

```bat
scripts\run_v54_tiling_operation_readiness.cmd ^
  sample_input\fa_best.hivm.mlir ^
  artifacts\latest_smoke_run\selected_plan.json ^
  artifacts\v54_tiling_operation_readiness
```

也可以重新生成四 Plan readiness：

```bash
python tools/build_four_plan_rewrite_readiness.py \
  --ir sample_input/fa_best.hivm.mlir \
  --selected-plan artifacts/latest_smoke_run/selected_plan.json \
  --output-dir artifacts/latest_rewrite_readiness_v54
```

## 6. 样例运行结果

在 `sample_input/fa_best.hivm.mlir` 和 `artifacts/latest_smoke_run/selected_plan.json` 上，本次生成的 summary 为：

```json
{
  "overall_status": "READY_FOR_LINUX_BACKEND_ANCHOR_DRY_RUN",
  "parameter_count": 7,
  "ready_for_linux_dry_run_count": 7,
  "loop_anchor_count": 1,
  "compute_anchor_count": 7,
  "load_anchor_count": 3,
  "store_anchor_count": 1,
  "axis_evidence_confidence": "MEDIUM",
  "production_rewrite_claim_allowed": false
}
```

这说明：TilingPlan 的 7 个寻优参数都已经纳入 Linux dry-run/prevalidation 路径，但还不能说已经完成真实 operation mutation。

## 7. 下一步真正要在 Linux 上验证什么

Linux backend 侧需要验证：

1. MLIR parser 能否稳定解析 dry-run plan 里的 loop / compute / load / store anchors；
2. backend 能否把 logical M/N/K 轴映射到真实 induction variable 和 indexing map；
3. backend 能否构造 loop split；
4. backend 能否同步改写 load/store slice 和 compute shape；
5. backend 能否正确处理 tail mask 或 padding；
6. backend 能否证明 `tile_k` 改写不破坏 partial accumulation；
7. 单参数 guarded mutation 后 roundtrip + verifier 通过。

通过这些检查后，TilingPlan 才能从 dry-run readiness 进入真正 operation-level rewrite。
