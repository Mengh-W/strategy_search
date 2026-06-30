# 04 Backend 下一步 Runbook

## 目标
把 `vtriton_hivm_operation_backend/` 中的 backend skeleton 放进真实 vTriton 构建环境，确认它能编译、能读写 HIVM IR、能跑 no-op roundtrip、能执行受限 GM deletion smoke test。

## 编译
```bash
bash scripts/phase6e_build_hivm_operation_backend.sh /path/to/vTriton /path/to/vTriton/build
```

期望产物：

```text
/path/to/vTriton/build/bin/hivm-operation-backend
```

## 验收
```bash
bash scripts/phase6f_accept_compiled_backend.sh   /path/to/vTriton/build/bin/hivm-operation-backend   sample_input/phase6_positive_fixtures/restricted_gm_roundtrip_positive.hivm.mlir   phase6f_backend_acceptance_out   /path/to/vTriton/build/bin/tritonsim-hivm
```

## 必须收集的结果
- 编译日志。
- `--print-capabilities` 输出。
- `inventory.json`。
- `roundtrip.json`。
- `verify.json`。
- `gm_mutation.json`。
- 如果可用，再收集 DES graph / Perfetto trace。

## 失败时优先排查
1. CMake include path 是否指到 vTriton 正确目录。
2. HivmOpsEditor namespace / API 名称是否和真实源码一致。
3. MLIR / LLVM link libraries 是否缺失。
4. backend CLI 参数是否和验收脚本约定一致。
5. roundtrip 输出是否仍能被 vTriton verifier 解析。
