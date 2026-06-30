# 38 Linux 真实后端前完成事项与交接清单

版本：`V5.3.1-backend-contract-ready-prelinux-lf-hygiene`。

本文档回答一个核心问题：在只有 Windows / WSL / 普通 Python 环境、没有真实 BiShengIR / vTriton / CANN / msprof 的情况下，当前项目还能做到哪一步；哪些任务已经完成；下一步交给 Linux 真实后端环境时应该怎么验收。

---

## 1. 当前已完成的 Linux 前任务

### 1.1 工程自洽

已经完成：

```text
修复 .py 后端脚本调用方式，避免依赖可执行权限；
新增 scripts/run_backend_fake_ci.sh；
新增 scripts/run_multibuffer_ci.sh；
新增 scripts/run_pre_linux_ci.sh；
新增 scripts/clean_release_package.sh；
更新 README.md；
更新 docs/00_DOCUMENTATION_INDEX_CN.md；
更新 docs/core/33_technical_report_optimization_CN.md；
更新 docs/core/34_technical_report_rewrite_CN.md；
更新 CLEAN_PACKAGE_SUMMARY.json；
更新 VERSION；
清理根目录临时调试脚本；
清理 __pycache__、*.pyc、.pytest_cache。
```

### 1.2 主链路 CI

命令：

```bash
bash scripts/run_v531_fast_ci.sh
```

目标：验证 search、rewrite、honest e2e、Sync/CVPipeline/Tiling/MultiBuffer 基础链路没有被破坏。

### 1.3 fake backend CI

命令：

```bash
bash scripts/run_backend_fake_ci.sh
```

目标：验证 Python -> backend contract -> fake backend -> report summary 这条接口链路是通的。

覆盖内容：

```text
backend contract generation；
backend contract runner；
dry-run analyzer；
fake DES trace execution；
roundtrip verifier harness；
operation dry-run harness；
guarded mutation harness；
Phase 6 real-backend readiness harness；
vTriton adapter skeleton；
backend acceptance harness。
```

### 1.4 pre-Linux 总门禁

推荐命令：

```bash
bash scripts/run_v531_fast_ci.sh
bash scripts/run_multibuffer_ci.sh
bash scripts/run_phase5b_roundtrip_ci.sh
bash scripts/run_backend_fake_ci.sh
bash scripts/run_phase6_positive_ci.sh
```

五条命令分别通过后，可以说：

```text
当前项目已经完成 Linux 真实后端前的 Python/fake-backend 工程闭环。
```

但不能说：

```text
当前项目已经通过真实 BiShengIR / vTriton / msprof 验证。
```

---

## 2. 当前本地环境能验证什么

Windows / WSL / 普通 Linux Python 环境能验证：

```text
Python 寻优流程是否能跑；
selected_plan.json 是否能生成；
selected_plan 是否强绑定当前输入 IR；
portable/restricted rewrite artifact 是否能生成；
honest e2e 是否能诚实返回成功或失败；
backend contract 是否能生成；
fake backend 是否能执行 capability / inventory / roundtrip / verify-only / dry-run / mutate；
测试 harness 是否能区分 fake backend 和 real backend；
文档口径是否准确。
```

不能验证：

```text
真实 HIVM 语法是否被 BiShengIR parser 接受；
真实 MLIR verifier 是否通过；
真实 HivmOpsEditor operation mutation 是否正确；
真实 DES/trace 是否无死锁；
真实 CANN compile/runtime 是否可运行；
真实 msprof profile 是否加速。
```

---

## 3. 交给 Linux/vTriton 环境前的包要求

发布包中应保留：

```text
README.md
VERSION
CHANGELOG.md
CLEAN_PACKAGE_SUMMARY.json
pytest.ini
configs/
docs/
sample_input/
scripts/
strategy_search/
tests/
tools/
vtriton_adapter/
vtriton_hivm_operation_backend/
```

发布包中不应包含：

```text
__pycache__/
*.pyc
.pytest_cache/
_debug_parse.py
_test_editor_integration.py
_test_full.py
_test_real_parser.py
_test_roundtrip.py
_test_structural_rewrite_integration.py
```

打包前运行：

```bash
bash scripts/clean_release_package.sh
```

---

## 4. Linux 真实后端需要什么

### 4.1 vTriton / HivmOpsEditor

需要：

```text
vTriton source tree；
vTriton build directory；
HIVM dialect / op definition / parser / printer；
HivmOpsEditor 或等价 operation-level edit API；
hivm-operation-backend 可执行文件；
tritonsim-hivm 或等价 DES/trace 工具。
```

### 4.2 BiShengIR / MLIR

需要：

```text
bishengir-compile 或等价 parser/compile 工具；
MLIR verifier 或 dialect verifier；
能执行 verify-only / parse-only 的命令。
```

### 4.3 CANN / Ascend / msprof

真机 profile 需要：

```text
CANN Toolkit；
Ascend Driver；
Ascend Runtime；
msprof；
npu-smi；
真实 Ascend 设备，例如 910B / 910B3 / 910C。
```

---

## 5. Linux 环境第一组命令

### 5.1 编译真实 backend

```bash
bash scripts/phase6e_build_hivm_operation_backend.sh \
  /path/to/vTriton \
  /path/to/vTriton/build
```

期望得到：

```text
/path/to/vTriton/build/bin/hivm-operation-backend
```

### 5.2 跑真实 backend acceptance

```bash
bash scripts/phase6f_accept_compiled_backend.sh \
  /path/to/vTriton/build/bin/hivm-operation-backend \
  sample_input/phase6_positive_fixtures/restricted_gm_roundtrip_positive.hivm.mlir \
  phase6f_backend_acceptance_out \
  /path/to/vTriton/build/bin/tritonsim-hivm
```

验收标准：

```text
backend 能 print capabilities；
backend 能 inventory IR；
backend 能 roundtrip IR；
backend 能 verify-only；
backend 能 dry-run contract；
backend 能 guarded mutate；
mutation 后 IR 仍能 verify；
如果提供 tritonsim-hivm，则 DES/trace smoke 能运行。
```

---

## 6. Linux 后的分阶段验收

### 6.1 Parser / verifier

目标：证明 optimized HIVM artifact 能被真实工具读入和验证。

输出建议：

```text
artifacts/official_parser_verifier/
  parser_stdout.log
  parser_stderr.log
  verifier_stdout.log
  verifier_stderr.log
  verifier_summary.json
```

### 6.2 HivmOpsEditor roundtrip

目标：证明不是文本硬拼，而是能用真实 operation-level API 完成 read -> mutate -> print -> read -> verify。

输出建议：

```text
artifacts/hivmopseditor_roundtrip/
  roundtrip_original.hivm.mlir
  roundtrip_mutated.hivm.mlir
  roundtrip_report.json
  post_mutation_verify.json
```

### 6.3 DES / trace

目标：不上真机先检查执行轨迹、event dependency、producer/consumer 顺序和 deadlock 风险。

输出建议：

```text
artifacts/des_trace_validation/
  baseline_trace.json
  optimized_trace.json
  dependency_graph.json
  trace_compare_report.json
  des_summary.json
```

### 6.4 msprof 真机 profile

目标：验证 baseline 与 optimized 的真实性能差异。

输出建议：

```text
artifacts/msprof_validation/
  baseline_msprof/
  optimized_msprof/
  op_summary_baseline.csv
  op_summary_optimized.csv
  compare_report.json
  speedup_summary.md
```

---

## 7. 当前交接口径

可以对外说：

```text
当前版本已经完成 Linux 真实后端前的本地工程闭环：
四参数 Plan 寻优、selected_plan 强绑定、portable/restricted rewrite artifact、backend contract、fake backend dry-run/roundtrip/mutation/acceptance、pre-Linux CI 均已整理完成。
```

不能对外说：

```text
当前版本已经完成真实 BiShengIR parser / MLIR verifier；
当前版本已经完成真实 HivmOpsEditor operation rewrite；
当前版本已经通过真实 vTriton DES/trace；
当前版本已经通过 msprof 证明真机加速。
```

下一步目标：

```text
将 fake backend 替换为真实 vTriton/HivmOpsEditor backend，完成 parser、verifier、roundtrip、DES/trace 和 msprof 的分阶段验收。
```
