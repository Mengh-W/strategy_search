# HIVM Bridge Adapter（推荐名称）

本目录是 `vtriton_adapter/` 的推荐新命名版本。

当前后端的准确定位是：

```text
HIVM Rewrite Bridge / HIVM Bridge Adapter
```

它是一个 standalone C++ bridge，用于把 Python 侧生成的 `structural_edit_script.json` 应用到 HIVM/NPUIR 文本上，并输出 `optimized.structural.hivm.mlir` 和 rewrite report。

它不是完整的 `vTriton-backed` production pass。当前没有直接调用 vTriton 的 `HivmOpsEditor` 或 MLIR `PatternRewriter`。旧目录 `vtriton_adapter/` 暂时保留，仅作为兼容旧测试和脚本的 alias。

## 当前真实支持

- `replace_barrier_all_with_directional_sync`
- `insert_sync_before_first_vector_op`
- `remove_redundant_gm_roundtrip`：仅 precheck / deferred，不真实删除

## 后续目标

Phase 4A 会把这个 bridge 的能力逐步迁移到目标 parser / HivmOpsEditor / MLIR Operation-level backend。
