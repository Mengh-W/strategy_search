# V5.2：TilingPlan restricted metadata rewrite

本版本将 TilingPlan 从 V4.11 的 feasibility scan 推进到受限但真实的 IR rewrite。由于当前没有真实 BiShengIR/vTriton/HivmOpsEditor verifier，本版本不改复杂 loop/index/memref shape/tail mask，而是执行 metadata-level portable/restricted rewrite：从 `selected_plan.json` 中读取 `tile_m/tile_n/tile_k`，在 IR 的入口常量区域插入显式 tile metadata constants 与 `annotation.mark`，并输出 optimized MLIR、rewrite report、validation 与 diff。

## 当前支持

- 读取 selected tiling knobs：`tile_m`、`tile_n`、`tile_k`、`loop_order`、`tail_strategy`；
- 扫描 IR 中已有 tile-like constants，作为 evidence；
- 在安全 anchor 后插入：
  - `%hivm_tile_m_v52 = arith.constant ... : index`
  - `%hivm_tile_n_v52 = arith.constant ... : index`
  - `%hivm_tile_k_v52 = arith.constant ... : index`
  - 对应 `annotation.mark`；
- 输出 `optimized.tiling_rewritten.hivm.mlir`；
- 输出 portable validation，确认 metadata 真实插入且没有声称 loop/index 改写。

## 暂不支持

- 不改 loop bounds；
- 不改 affine/index expression；
- 不改 memref shape；
- 不改 load/store offset；
- 不改 tail mask；
- 不做 production-level verifier claim。

这是刻意的保守设计：没有真实 verifier 时，TilingPlan 最容易写出结构上像 MLIR、语义上不可接受的 IR。因此 V5.2 先实现 metadata-level portable/restricted rewrite，为后续真实 loop/index lowering 做锚点。

## Windows CMD

```cmd
scripts\run_v52_tiling_true_rewrite.cmd
```

指定参数：

```cmd
scripts\run_v52_tiling_true_rewrite.cmd ^
  sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir ^
  artifacts\latest_smoke_run\selected_plan.json ^
  artifacts\v52_tiling_true_rewrite
```

## 输出

```text
optimized.tiling_rewritten.hivm.mlir
tiling_anchor_scan.json
tiling_true_rewrite_actions.json
tiling_true_rewrite_report.json
tiling_true_rewrite_validation.json
tiling_true_rewrite_diff.json
tiling_true_rewrite_summary.json
```

## 验收口径

可以说：TilingPlan 已经完成 restricted metadata rewrite，能够根据 selected_plan 将 tile metadata 写入 IR，并生成 optimized MLIR。

不能说：TilingPlan 已完成 production loop/index lowering。真实 loop/index/tail rewrite 仍需 BiShengIR/vTriton/HivmOpsEditor verifier、DES/trace 与真机验证。
