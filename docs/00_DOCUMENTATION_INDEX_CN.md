# 文档索引

当前版本：`V5.3.1-backend-contract-ready-prelinux-lf-hygiene`。

这个目录已经按“当前必读 / 后端交接 / 校准 / 历史归档”重新整理。根目录只保留本索引，避免阶段性报告全部堆在 `docs/` 第一层。

---

## 1. 推荐阅读顺序

| 顺序 | 文档 | 用途 |
|---:|---|---|
| 1 | `README.md` | 当前能力、运行方式、pre-Linux CI、真实验证边界 |
| 2 | `docs/core/33_technical_report_optimization_CN.md` | 寻优系统：四参数 Plan、cost model、搜索流程、硬件边界 |
| 3 | `docs/core/34_technical_report_rewrite_CN.md` | rewrite 系统：portable/restricted rewrite、backend contract、fake backend、真实后端边界 |
| 4 | `docs/core/38_pre_linux_completion_and_handoff_CN.md` | Linux 真实后端前已完成事项、CI 命令、交接清单 |
| 5 | `docs/backend/09_four_plan_backend_contract_CN.md` | 四 Plan backend contract 的设计与验收口径 |
| 6 | `docs/backend/10_backend_contract_execution_CN.md` | backend contract runner 与 fake/real backend 执行方式 |
| 7 | `docs/core/03_hivm_rewrite_progress_consolidated.md` | 当前 rewrite 进展的合并版说明 |
| 8 | `docs/core/04_backend_next_steps_runbook.md` | Linux/vTriton/BiShengIR/CANN 接棒操作清单 |
| 9 | `docs/core/05_output_artifacts_guide.md` | 输出目录和 artifact 应该怎么看 |
| 10 | `docs/core/06_extended_defect_cost_model_validation_CN.md` | 扩展缺陷 HIVM 样例与 cost model 识别方向验证 |
| 11 | `docs/test_report/01_defect_hivm_cost_model_test_report_CN.md` | 14 个缺陷 HIVM 样例的完整实跑测试报告 |

---

## 2. 目录结构

```text
docs/
  00_DOCUMENTATION_INDEX_CN.md        # 当前文档入口
  core/                               # 当前版本必读核心文档
  backend/                            # backend contract / fake-real backend 执行说明
  calibration/                        # e2e 与 prefill 校准说明
  test_report/                        # 测试报告与 defect live-run 结果
  archive/                            # 历史阶段报告与旧版合并文档
    rewrite_history/                  # V4.x-V5.x 阶段性 rewrite 记录
```

### `docs/core/`

| 文档 | 内容 |
|---|---|
| `01_project_plain_explanation_CN.md` | 项目的通俗解释 |
| `02_code_audit_CN.md` | 代码审核记录 |
| `03_hivm_rewrite_progress_consolidated.md` | rewrite 进展合并说明 |
| `04_backend_next_steps_runbook.md` | Linux 真实后端下一步怎么跑 |
| `05_output_artifacts_guide.md` | 输出 artifact 阅读指南 |
| `06_extended_defect_cost_model_validation_CN.md` | 扩展缺陷 HIVM 样例与 cost model 验证 |
| `33_technical_report_optimization_CN.md` | 寻优技术报告 |
| `34_technical_report_rewrite_CN.md` | rewrite 技术报告 |
| `38_pre_linux_completion_and_handoff_CN.md` | pre-Linux 完成与交接清单 |

### `docs/backend/`

| 文档 | 内容 |
|---|---|
| `09_four_plan_backend_contract_CN.md` | 四 Plan backend contract 设计 |
| `10_backend_contract_execution_CN.md` | contract runner 与 fake/real backend 执行 |

### `docs/calibration/`

| 文档 | 内容 |
|---|---|
| `35_v531_honest_e2e_and_docs_update_CN.md` | honest e2e 与文档边界更新 |
| `36_e2e_initial_cost_model_calibration_CN.md` | 初始 e2e cost model 校准 |
| `37_merged_e2e_prefill_cost_model_config_CN.md` | e2e 与 prefill 校准合并配置 |

### `docs/test_report/`

| 文档 | 内容 |
|---|---|
| `01_defect_hivm_cost_model_test_report_CN.md` | 14 个缺陷 HIVM 样例的缺陷定位、live optimizer 寻优过程与 cost model 方向识别报告 |

### `docs/archive/`

历史阶段报告统一移入归档目录。正常交接和汇报不建议优先阅读这些文件；只有追溯某个阶段的设计演化时再看。

---

## 3. 当前项目状态一句话

```text
V5.3.1 当前已经从 portable rewrite prototype 推进到 backend-contract-ready prototype：
本地能完成 search、selected_plan、restricted rewrite artifact、backend contract、fake backend acceptance；
下一步需要在 Linux/vTriton/BiShengIR/CANN 环境中完成真实 parser、verifier、roundtrip、DES/trace 和 msprof 验证。
```

---

## 4. 术语口径

| 术语 | 当前项目中的含义 |
|---|---|
| `selected_plan` | 寻优阶段选出的四参数 Plan，是 rewrite 阶段唯一应消费的策略输入 |
| `selected_plan_bound_to_same_input` | rewrite 使用的是本轮 search 生成的 plan，而不是历史 artifact |
| `rewrite_process_succeeded` | 四 Plan rewrite 子进程返回 0 |
| `all_portable_validations_passed` | 项目内 portable validation 通过；不能替代真实 MLIR verifier |
| `end_to_end_passed` | search、rewrite、summary、portable validation 同时通过 |
| `backend contract` | Python 侧交给真实 HivmOpsEditor/vTriton backend 的施工单，不是新的 IR |
| `fake backend` | 本地测试用后端，只验证 CLI/report/dry-run/mutate 流程，不证明真实 HIVM 合法 |
| `TRACE_METADATA_REWRITE` | 参数以 metadata/annotation 形式写入 IR，支持追踪和后续 lowering |
| `RESTRICTED_STRUCTURAL_REWRITE` | 参数驱动了 portable/text-level IR 结构变化，但还不是 production operation mutation |
| `PRODUCTION_OPERATION_REWRITE` | 真实 HivmOpsEditor/MLIR operation mutation，并通过 parser/verifier/DES/msprof；当前尚未完成 |

---

## 5. 本地建议跑的 CI

```bash
bash scripts/run_pre_linux_ci.sh --run
```

它会依次覆盖：fast CI、MultiBuffer 专项、roundtrip、backend fake、phase6 positive。通过后可以说：

```text
当前项目已经完成 Linux 真实后端前的 Python/fake-backend 工程闭环。
```

但仍不能说：

```text
当前项目已经完成真实 BiShengIR/vTriton/msprof 验证。
```
