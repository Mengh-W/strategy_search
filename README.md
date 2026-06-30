# HIVM Strategy Search Demo V5.3.1 — Backend-Contract-Ready Pre-Linux Edition

当前版本：`V5.9-four-plan-semantic-rewrite-syntax-schedule-hardening`。


> **V5.9 update:** 当前发布包在 V5.8 的 TilingPlan / CVPipelinePlan semantic rewrite 基础上，新增 syntax/schedule hardening：修正 FA-like M/N/K 常量推断、修复 nested memref 闭合、归一化 event operation，并输出 `optimized.four_plan_operation_rewrite.v59_syntax_hardened.hivm.mlir` 作为优先 Linux backend 验证文件。仍然不能 claim 已通过真实 Linux compile/run/msprof。

本项目是一个围绕 HIVM / NPU-IR 的四参数 Plan 寻优与 rewrite 原型。它现在已经从“只生成 optimized HIVM artifact 的 portable rewrite demo”，推进到“可以生成 backend contract，并用 fake backend 验收接口链路的 backend-contract-ready prototype”。

它仍然不是 production-level HIVM compiler pass。当前版本没有声称已经通过真实 BiShengIR parser、真实 MLIR verifier、真实 HivmOpsEditor roundtrip、真实 vTriton DES/trace 或 msprof 真机性能验证。

一句话概括当前状态：

```text
输入 HIVM / NPU-IR MLIR
  -> 构造 TilingPlan / MultiBufferPlan / CVPipelinePlan / SyncPlan 参数空间
  -> cost model + hardware gate 寻优
  -> 输出 selected_plan.json
  -> 将 selected_plan 强绑定回同一份输入 IR
  -> 生成 portable/restricted rewritten HIVM artifact
  -> 生成 backend contract
  -> 用 fake backend 验证 contract / dry-run / roundtrip / acceptance 流程
  -> 等待真实 Linux + vTriton / BiShengIR / CANN 环境接棒验证
```

---

## 1. 当前项目能说什么，不能说什么

### 1.1 可以说

```text
当前项目已经完成四参数 Plan 的寻优闭环。
当前项目能输出 selected_plan.json，并将它强绑定回当前输入 IR。
当前项目能生成 portable/restricted rewrite artifact。
当前项目能生成 backend-facing contract，描述真实 HivmOpsEditor/vTriton backend 后续应执行的 action。
当前项目已经具备 fake backend、dry-run、roundtrip、guarded mutation、acceptance harness 的本地验收链路。
当前项目已经完成 Linux 真实后端前的 Python 层工程收尾。
```

### 1.2 不能说

```text
不能说四个 Plan 已完成 production-level HivmOpsEditor rewrite。
不能说所有参数都已完成 operation-level lowering。
不能说 rewritten HIVM 已通过真实 BiShengIR parser / MLIR verifier。
不能说 rewritten HIVM 已通过真实 vTriton DES/trace。
不能说 predicted speedup 等于 msprof 真机 speedup。
不能说 fake backend 通过就等价于真实后端通过。
```

### 1.3 当前最准确定位

```text
Four-plan strategy search + portable/restricted rewrite + backend-contract-ready prototype.
Ready for Linux/vTriton/BiShengIR handoff, but not production verified.
```

---

## 2. 四个 Plan 当前能力

| Plan | 当前实现 | 当前等级 | 还没做到 |
|---|---|---|---|
| `TilingPlan` | 将 tile shape、loop order、tail policy 等写入 trace metadata / annotation | `TRACE_METADATA_REWRITE` | 尚未真实改 loop bound、index、tail mask、memref shape |
| `MultiBufferPlan` | 插入 ping/pong slot，做局部 producer/consumer use replacement，生成 backend contract action | `RESTRICTED_STRUCTURAL_REWRITE` + backend contract | 尚未完成跨 iteration parity、alias/liveness/capacity proof、真实 operation-level use replacement |
| `CVPipelinePlan` | 插入 pipeline marker 与 load->compute、compute->store event pair，生成 pipeline intent | `RESTRICTED_STRUCTURAL_REWRITE` + metadata | 尚未完成 operation movement、loop skew、prologue/steady/epilogue lowering |
| `SyncPlan` | 对安全 candidate 生成 set_flag/wait_flag event pair；blocked action 会诚实失败 | `RESTRICTED_STRUCTURAL_REWRITE` + safety audit | 尚未完成真实 event liveness verifier、sync motion、redundant sync deletion |

当前 rewrite 分三层：

```text
TRACE_METADATA_REWRITE
  参数写入 metadata / annotation，支持追踪和后续 lowering。

RESTRICTED_STRUCTURAL_REWRITE
  在 portable 文本层面对 IR 做可见结构变化，例如 event pair、ping/pong slot、pipeline marker。

PRODUCTION_OPERATION_REWRITE
  通过真实 HivmOpsEditor / MLIR operation mutation，并通过 parser、verifier、DES/trace、compile、msprof。
  当前尚未完成。
```

---

## 3. 运行环境建议

### 3.1 Windows 用户

Windows 原生可以做文档、普通 Python 运行和部分测试。推荐安装 WSL Ubuntu 来跑脚本和 pytest，因为项目里有 bash 脚本、路径和权限相关逻辑。

推荐流程：

```bash
wsl --install
```

进入 Ubuntu 后安装基础依赖：

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git unzip zip build-essential cmake ninja-build
```

建议把项目放在 WSL 的 Linux 文件系统里，例如：

```bash
mkdir -p ~/hivm
cd ~/hivm
unzip /mnt/c/Users/<你的用户名>/Downloads/vTRiton_search.zip
cd vTRiton_search
```

不建议长期在 `/mnt/c/...` 下跑测试，速度慢，也容易遇到权限差异。

### 3.2 Linux 真实后端环境

真实 BiShengIR / vTriton / CANN / msprof 验证需要 Linux 环境，通常是公司开发机或昇腾服务器。普通 Windows 电脑无法完成这部分。

需要的真实环境包括：

```text
vTriton 源码和 build 目录
BiShengIR / MLIR parser / verifier 工具
真实 HivmOpsEditor 或 operation backend
tritonsim-hivm 或等价 DES/trace 工具
CANN Toolkit / Ascend Driver / Ascend Runtime
msprof / npu-smi
真实 Ascend NPU 设备
```

---

## 4. 最推荐的本地验证命令

### 4.1 快速主链路 CI

```bash
bash scripts/run_v531_fast_ci.sh
```

覆盖：

```text
bound search + rewrite wrapper
DES profile path
SyncPlan event rewrite / validator / audit
CVPipelinePlan / TilingPlan / MultiBufferPlan portable rewrite
V5.3 parameter coverage
four-plan rewrite CLI
```

### 4.2 MultiBuffer 专项 CI

```bash
bash scripts/run_multibuffer_ci.sh
```

覆盖：

```text
MultiBuffer rewrite readiness；
MultiBuffer stage boundary；
MultiBuffer restricted true rewrite action。
```

这个脚本把 MultiBuffer 的专项验证从 fast CI 中拆出来，避免默认 smoke run 过重，同时保证交接前有明确门禁。

### 4.3 fake backend CI

```bash
bash scripts/run_backend_fake_ci.sh
```

覆盖：

```text
backend contract generation
backend contract runner
fake backend capability / inventory / roundtrip / verify-only / dry-run / guarded mutate
Phase 4B DES trace fake execution
Phase 5B/5C/5D/5E/5F fake backend checks
Phase 6A/6B/6C/6D/6E/6F pre-real-backend acceptance harness
```

注意：这个脚本通过只说明 Python 到 fake backend 的接口链路通了，不说明真实 HIVM 合法。

### 4.4 Linux 前完整本地门禁

推荐在 Windows/WSL 中分五个 fresh shell 运行：

```bash
bash scripts/run_v531_fast_ci.sh
bash scripts/run_multibuffer_ci.sh
bash scripts/run_phase5b_roundtrip_ci.sh
bash scripts/run_backend_fake_ci.sh
bash scripts/run_phase6_positive_ci.sh
```

`bash scripts/run_pre_linux_ci.sh` 默认是 checklist launcher，只打印这些命令；如果确实想串行执行，可运行 `bash scripts/run_pre_linux_ci.sh --run`。默认打印模式是为了避免部分 Windows/WSL/Python 组合在连续链式 pytest 后出现 interpreter cleanup 挂住。

### 4.5 缺陷 HIVM 样例测试报告

当前包包含 14 个 synthetic defect HIVM/NPUIR 样例，用于验证 analytical cost model 是否能识别明显错误方向，例如小 tile、多 barrier、无 overlap、UB overflow、已有 ping-pong 但同步仍差等情况。

完整测试报告见：

```text
docs/test_report/01_defect_hivm_cost_model_test_report_CN.md
```

快速检查命令：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_defect_injection_cases.py -m regression
```

live optimizer 实跑需要显式打开：

```bash
RUN_DEFECT_LIVE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -m slow tests/test_defect_injection_cases.py
```

报告结论只代表 Python/fake-backend 层面对 synthetic defects 的方向识别能力，不等价于 msprof 真机 speedup。

---

## 5. 寻优 + rewrite 强绑定入口

优先使用这个入口，不要手工拿历史 `selected_plan.json` 去 rewrite 新输入。

```bash
python tools/run_search_and_four_plan_rewrite.py \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --cost-model-config configs/cost_model_conservative.json \
  --cost-risk-mode conservative \
  --candidate-space standard \
  --output-dir artifacts/v531_bound_search_rewrite
```

它会执行：

```text
当前输入 IR
  -> auto_strategy_search.py
  -> 01_search/selected_plan.json
  -> four-plan portable/restricted rewrite
  -> 02_four_plan_rewrite/optimized.four_plan_true_rewritten.hivm.mlir
  -> bound_search_rewrite_summary.json
```

### 5.1 honest e2e 语义

只有同时满足下面条件时，整体 e2e 才算通过：

```text
search_returncode == 0
rewrite_returncode == 0
rewrite_summary_loaded == true
all_portable_validations_passed == true
```

输出中最重要的字段：

```text
selected_plan_bound_to_same_input
  只说明 rewrite 使用的是本轮 search 生成的 plan，不是历史 plan。

rewrite_process_succeeded
  说明 rewrite 子进程返回 0。

all_portable_validations_passed
  说明项目内 portable validation 通过，但不能替代真实 MLIR verifier。

end_to_end_passed
  只有 search、rewrite、summary、portable validation 全部通过时才为 true。
```

如果 `selected_plan_bound_to_same_input = true` 但 `end_to_end_passed = false`，说明 plan 绑定是对的，但 rewrite 或 validation 仍然失败。当前项目会诚实返回非 0，不再包装成成功。

---

## 6. backend contract 是什么

backend contract 是 Python 寻优/rewrite 系统交给真实后端的“施工单”。它不是新的 IR，也不是性能证据。

它描述：

```text
要定位哪些 HIVM op
要检查哪些 buffer / sync / pipeline action
哪些 action 只能 dry-run
哪些 action 可以 guarded mutate
需要 backend 输出哪些 report
通过标准是什么
```

相关入口：

```bash
python tools/build_four_plan_backend_contract.py \
  --ir sample_input/fa_best.hivm.mlir \
  --selected-plan artifacts/latest_smoke_run/selected_plan.json \
  --output-dir artifacts/latest_backend_contract
```

执行 fake backend contract：

```bash
python tools/execute_backend_contract.py \
  --backend tools/fake_hivm_operation_backend.py \
  --ir sample_input/fa_best.hivm.mlir \
  --contract artifacts/latest_backend_contract/four_plan_backend_contract.json \
  --output-dir artifacts/backend_contract_execution
```

fake backend 的作用是验证接口和报告格式。真正的 production claim 必须用真实 backend 替换 fake backend。

---

## 7. 真实 Linux/vTriton 环境接棒步骤

本地 pre-Linux CI 通过后，下一步应在 Linux/vTriton/BiShengIR 环境中做真实验证。

### 7.1 编译真实 backend

```bash
bash scripts/phase6e_build_hivm_operation_backend.sh \
  /path/to/vTriton \
  /path/to/vTriton/build
```

期望得到：

```text
/path/to/vTriton/build/bin/hivm-operation-backend
```

### 7.2 跑真实 backend acceptance

```bash
bash scripts/phase6f_accept_compiled_backend.sh \
  /path/to/vTriton/build/bin/hivm-operation-backend \
  sample_input/phase6_positive_fixtures/restricted_gm_roundtrip_positive.hivm.mlir \
  phase6f_backend_acceptance_out \
  /path/to/vTriton/build/bin/tritonsim-hivm
```

验收目标：

```text
backend 能 print capabilities
backend 能 inventory IR
backend 能 roundtrip IR
backend 能 verify-only
backend 能 dry-run contract
backend 能 guarded mutate
mutation 后 IR 仍能 verify
```

### 7.3 后续真实验证

真实 backend acceptance 之后，才进入：

```text
BiShengIR parser / MLIR verifier
HivmOpsEditor roundtrip
vTriton DES / trace
CANN compile/runtime
msprof 真机 profile
cost model 校准
```

---

## 8. 发布包清理

打包前运行：

```bash
bash scripts/clean_release_package.sh
```

它会删除：

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

当前发布包不应包含 Python 缓存和根目录临时调试脚本。

---

## 9. 推荐阅读文档

文档已经按用途整理，`docs/` 根目录只保留索引。推荐从下面几个入口读：

```text
docs/00_DOCUMENTATION_INDEX_CN.md
```

```text
docs/core/33_technical_report_optimization_CN.md
```

```text
docs/core/34_technical_report_rewrite_CN.md
```

```text
docs/core/38_pre_linux_completion_and_handoff_CN.md
```

历史阶段报告已经统一放到：

```text
docs/archive/rewrite_history/
```

正常交接优先看 `docs/core/`、`docs/backend/` 和 `docs/calibration/`，不要从历史阶段报告开始读。

## 10. 当前状态总结

```text
已经完成：
  Python 寻优主链路
  selected_plan 强绑定 rewrite
  portable/restricted rewrite artifact
  honest e2e 返回语义
  backend contract 生成
  fake backend dry-run / roundtrip / guarded mutation / acceptance 测试
  pre-Linux CI 脚本
  文档口径整理和发布包清理脚本

仍需真实环境完成：
  BiShengIR parser
  MLIR verifier
  HivmOpsEditor operation-level roundtrip
  vTriton DES/trace
  CANN compile/runtime
  msprof 真机 profile
  cost model 真机校准
```

### 扩展缺陷 HIVM 回归

当前包内置 14 个 synthetic defect HIVM/NPUIR 样例，位于 `tests/defect_inputs/`，用于检查 cost model 是否能识别小 tile、UB overflow、barrier-heavy、缺少 overlap、已有局部 ping-pong 但整体仍低效、tail-unfriendly tile 等方向。

轻量回归：

```bash
python -m pytest -q tests/test_defect_injection_cases.py -m regression
```

新增 J/K/L/M/O 的摘要见 `docs/core/06_extended_defect_cost_model_validation_CN.md`；14 个样例的完整实跑测试报告见 `docs/test_report/01_defect_hivm_cost_model_test_report_CN.md`。


### V5.4 TilingPlan operation-readiness

TilingPlan is no longer only a metadata/report hint path.  The project now includes a conservative Linux prevalidation layer that maps selected TilingPlan knobs to concrete anchor checks and dry-run operation requests:

```bash
python tools/run_tiling_operation_readiness.py \
  --ir sample_input/fa_best.hivm.mlir \
  --selected-plan artifacts/latest_smoke_run/selected_plan.json \
  --output-dir artifacts/v54_tiling_operation_readiness
```

The generated reports include loop anchors, load/store anchors, compute anchors, buffer shape evidence, M/N/K axis evidence, loop-split requests, slice-rewrite requests, tail-guard requests, and reduction proof requests.  This means `tile_m`, `tile_n`, `tile_k`, `loop_order`, `tail_strategy`, `reduce_tile_policy`, and `layout_aware_tile` all have a Linux dry-run/prevalidation path.

Important boundary: Python still does not perform production loop/index/memref-slice/tail-mask mutation.  Real operation-level tiling rewrite must be enabled only inside the MLIR/HivmOpsEditor backend after roundtrip and verifier checks.

### V5.5 四 Plan production-candidate rewrite

如果目标是把寻优后的四个 Plan 都写回 HIVM，并生成一个可交给 Linux backend 验证的 optimized candidate，可以运行：

```bash
bash scripts/run_v55_four_plan_production_candidate_rewrite.sh \
  sample_input/fa_best.hivm.mlir \
  artifacts/latest_smoke_run/selected_plan.json \
  artifacts/v55_four_plan_production_candidate_rewrite
```

主输出：

```text
artifacts/v55_four_plan_production_candidate_rewrite/optimized.four_plan_production_candidate.hivm.mlir
```

该 pipeline 要求 TilingPlan、MultiBufferPlan、CVPipelinePlan、SyncPlan 都产生 visible mutation；但最终是否能用于真机 msprof 对比，仍需要在 Ascend Linux 环境中完成 MLIR/HIVM parse、roundtrip、verifier、backend compile 和 correctness check。详见 `docs/backend/12_four_plan_production_candidate_rewrite_CN.md`。

## V5.6 四 Plan operation-level rewrite MVP

如果目标是把寻优后的四个 Plan 策略真实写回 HIVM，并生成可提交 Linux backend 验证的 optimized HIVM candidate，请使用：

```bash
python tools/run_four_plan_operation_rewrite.py \
  --ir sample_input/fa_best.hivm.mlir \
  --selected-plan artifacts/latest_smoke_run/selected_plan.json \
  --output-dir artifacts/v56_four_plan_operation_rewrite
```

或：

```bash
bash scripts/run_v56_four_plan_operation_rewrite.sh
```

核心输出：

```text
artifacts/v56_four_plan_operation_rewrite/optimized.four_plan_operation_rewrite.hivm.mlir
artifacts/v56_four_plan_operation_rewrite/operation_parameter_coverage.json
artifacts/v56_four_plan_operation_rewrite/four_plan_operation_rewrite_summary.json
```

V5.6 的重点不是 metadata/readiness，而是每个 Plan 都映射到 operation-level MVP action：

- TilingPlan：M/N/K outer tile loop scaffold、loop order materialization、tail/reduction/layout guard，以及 local memref operation/type shape rewrite。
- MultiBufferPlan：ping/pong slot clone 与 producer/consumer use-def 替换。
- CVPipelinePlan：pipeline sync edges、pipeline group 和 slot binding。
- SyncPlan：set_flag/wait_flag event operation normalization。

注意：V5.6 仍然不声称已经 Linux 可编译可运行。它输出的是 operation-level optimized HIVM candidate，必须继续在 Ascend Linux 环境中做 parse、roundtrip、verifier、backend compile、correctness check 和 msprof 对比。


## V5.7：四 Plan operation rewrite + Linux precompile hardening

当前主线已经推进到：

```text
input.hivm.mlir
+ selected_plan.json
→ optimized.four_plan_operation_rewrite.hivm.mlir
→ optimized.four_plan_operation_rewrite.precompile_hardened.hivm.mlir
→ v57_linux_precompile_audit.json
```

V5.7 在 V5.6 四 Plan operation-level MVP rewrite 的基础上，新增本地 precompile audit gate：

- TilingPlan：继续生成 tile loop scaffold、tail/reduction/layout guard、local memref type/shape rewrite，并补充 `%cM/%cN/%cK/%c32` 等 tile/index 常量物化；
- MultiBufferPlan：继续生成 ping/pong alloc clone 与 producer/consumer use-def rewrite；
- CVPipelinePlan：继续生成 pipeline group、load→compute 与 compute→store sync edge；
- SyncPlan：继续生成 set_flag/wait_flag event normalization；
- V5.7 新增检查 duplicate SSA、undefined symbol、memref type mismatch、operand type harmonization、brace balance 与四 Plan marker。

运行：

```bash
bash scripts/run_v57_four_plan_operation_rewrite_precompile_audit.sh
```

重要边界：V5.7 仍不声称已经 Linux 可编译。它只是把四 Plan operation rewrite 进一步推进到“本地 precompile blocker 可见”的阶段。最终仍需要 Ascend Linux 上的 parser、roundtrip、verifier、backend compile、correctness check 与 msprof。


## V5.8：TilingPlan / CVPipelinePlan semantic rewrite hardening

V5.8 在 V5.7 的四 Plan operation rewrite + precompile audit 基础上，继续推进两个最关键缺口：

- **TilingPlan**：新增 M/N/K axis binding、per-operation tile-slice binding、tail_strategy mask/pad semantic binding、reduce_tile_policy partial-accumulator semantic binding。
- **CVPipelinePlan**：新增 stage graph、prologue/steady/epilogue schedule binding、producer_consumer_distance tile-offset binding、stage_buffer_policy slot-binding 语义。

运行：

```bash
bash scripts/run_v58_tiling_cvpipeline_semantic_rewrite.sh
```

关键输出：

```text
artifacts/v58_tiling_cvpipeline_semantic_rewrite/optimized.four_plan_operation_rewrite.precompile_hardened.hivm.mlir
artifacts/v58_tiling_cvpipeline_semantic_rewrite/stages/01_tiling_semantic_operation_rewrite/tiling_axis_binding.json
artifacts/v58_tiling_cvpipeline_semantic_rewrite/stages/03_cvpipeline_operation_rewrite/cvpipeline_stage_graph.json
```

边界：V5.8 仍不宣称已经 Linux backend 编译通过。它生成的是更完整的 semantic operation rewrite candidate，必须在 Ascend Linux 上继续跑 parse / roundtrip / verifier / compile / correctness / msprof。
