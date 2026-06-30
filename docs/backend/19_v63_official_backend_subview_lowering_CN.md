# V6.3 official-backend subview lowering hardening

V6.3 目标是修复 V6.2 对照官方文档时暴露出的明显 handoff blocker：`hivm.hir.load/store` 的 src/dst shape 不一致、tile offset 仅作为字符串属性、`annotation.mark`/private debug attribute 可能不是官方 backend 可接受内容。

## 核心改动

1. 对 shape 不一致的 `hivm.hir.load`，在 load 前插入 `memref.subview`，使 GM tile operand 与 local buffer shape 对齐。
2. 对 shape 不一致的 `hivm.hir.store`，在 store 前对 GM 输出插入 `memref.subview`，使输出 tile operand 与 local source shape 对齐。
3. strip 私有版本属性和调试属性，例如 `hivm.v60_*`、`hivm.tile_*`、`hivm.pipeline_*` 等。
4. 将 CVPipeline 的物理调度要求写入 backend contract，而不是仅靠字符串属性宣称已经完成 physical op movement。
5. 新增 `v63_official_compare_audit.json`，检查 portable 层面的明显 blocker。

## 输出

```text
optimized.four_plan_official_backend_subview_lowered.hivm.mlir
v63_subview_lowering_report.json
v63_private_attr_strip_report.json
v63_official_compare_audit.json
v63_backend_contract.json
```

## 边界

V6.3 不是最终真机验证结果。它只是让 rewrite 后 HIVM 更接近官方 Linux backend handoff 输入。最终仍需要真实环境中的 parse、roundtrip、verifier、compile、correctness check 和 msprof。
