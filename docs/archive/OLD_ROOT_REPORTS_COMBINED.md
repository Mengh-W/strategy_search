# 历史根目录 Markdown 报告合并归档

这些内容来自原始仓库根目录的零散阶段报告。为避免根目录堆满几十个 md，清理版已合并到本文件。正式阅读请优先看 docs/ 下的 01-05 当前文档。



---

## AUDIT_CORRECTION_REPORT.md

# Phase 2 / Phase 3 审核修正报告

## 1. 本次修正目的

本次修正不是新增危险 rewrite，而是修正此前文档和汇报口径中容易误导的地方，让项目状态更准确、可交付、也更容易向非细节背景的领导解释。

## 2. 修正的问题

### 问题一：`vTriton-compatible` 表述过强

此前部分文档容易让人误解为当前已经完成完整的 目标 vTriton/HivmOpsEditor 后端接入。实际当前状态是：

```text
已完成：vTriton-compatible standalone C++ rewrite bridge
未完成：完整 HivmOpsEditor / MLIR Operation-level backend
```

因此统一修正为：

```text
vTriton-compatible C++ bridge
目标 vTriton/HivmOpsEditor production target
```

只有真正接入 HivmOpsEditor / MLIR parser 后，才称为 production vTriton-compatible backend。

### 问题二：GM round-trip 删除状态不够清楚

此前规划里将 `remove_redundant_gm_roundtrip` 列入第一批正式 rewrite，容易让人以为当前已经实现删除。实际当前只做：

```text
GM round-trip candidate detection
GM MemorySSA-like gate
GM deletion decision report
```

当前仍然不删除 GM load/store。真实删除必须等 Phase 4+，并通过 alias / dependency / observable-boundary / DES-trace validation。

### 问题三：Python fallback 和 C++ backend 能力混在一起

当前 C++ bridge 已真实支持：

```text
replace_barrier_all_with_directional_sync
insert_sync_before_first_vector_op
```

Python fallback / proof gate 中存在但 C++ backend 尚未支持 production mutation 的能力包括：

```text
hoist_invariant_q_load_from_simple_loop
```

文档中已明确区分：

```text
external_backend_actual_changes
python_fallback_or_local_proof_only
missing_backend_coverage
```

### 问题四：Phase 3 checker 不是正式 correctness proof

Phase 3 当前建立的是 conservative local evidence foundation，包括：

```text
op inventory
dependency graph v1
event liveness
buffer liveness
GM alias
GM MemorySSA-like gate
Q-load hoist local proof gate
DES/trace wrapper
```

这些报告可用于审计、筛选候选和防止明显错误，但不是 target compiler proof。文档中已统一改为：

```text
local evidence / local proof gate / conservative precheck
```

不再表述为完整正式证明。

## 3. 当前准确状态

### Phase 2 状态

Phase 2 已完成工程闭环：

```text
strategy -> edit script -> C++ bridge -> optimized.structural.hivm.mlir -> report / validation / manifest
```

C++ bridge 已能真实改 IR op sequence：

```text
2 个 barrier_all 替换为 directional set/wait
1 个 CV boundary 前插入 set/wait
```

但 Phase 2 不是完整 production compiler pass。

### Phase 3 状态

Phase 3 已完成分析基础：

```text
op inventory / dependency / event / buffer / GM alias / MemorySSA-like / hoist gate / DES-trace wrapper / closure
```

但危险 mutation 仍然锁定：

```text
GM round-trip deletion: locked
Q-load hoist production mutation: locked
real double-buffer: locked
full CV overlap: locked
real tiling lowering: locked
```

## 4. 下一步建议

下一步不建议直接做 real double-buffer 或 full CV overlap。推荐先进入：

```text
Phase 4A: target parser / HivmOpsEditor integration hardening
```

目标是把当前 line-scanner / standalone bridge 证据升级到 MLIR Operation-level / HivmOpsEditor 级证据。


---

## CHANGELOG.md

## V3.3.2 Phase-6F - Backend Acceptance Closure

- Added `phase6f_backend_acceptance_report.json`, `phase6f_smoke_command_matrix.json`, `phase6_closure_report.json`, and `phase6f_analysis_summary.json`.
- Added compiled backend acceptance gate for a real HivmOpsEditor/MLIR `hivm-operation-backend`.
- The gate requires capability JSON, real-backend identity, inventory/roundtrip/verify modes, dry-run mode, limited GM deletion mode, and at least one fixture smoke test.
- Production complex mutation remains locked without an accepted compiled backend.


## V3.3.2 Phase-6D - vTriton Source-aware HivmOpsEditor Backend Adapter

- Consumed user-provided vTriton source tree through `--vtriton-source-root`.
- Added `vtriton_hivm_operation_backend/`, a C++ adapter skeleton intended to build inside vTriton and include the real `AscendModel/Transforms/HivmOpsEditor.h`.
- Added Phase-6D reports: source integration report, backend files manifest, backend adapter plan, and analysis summary.
- Added installer script `scripts/phase6d_install_backend_adapter.sh`.
- Kept Q-load hoist production mutation disabled until a true dominance/region-motion implementation exists.


## V3.3.2 Phase-6C - Restricted True IR Rewrite Positive Cases

- 新增 `tools/restricted_hivm_true_rewriter.py`，在明确标记的受限 fixture 上执行真实文件级 IR 改写。
- 新增 Q-load hoist 受限正例：将简单 loop 内的 `hivm.hir.load + hivm.hir.nd2nz` 移到 loop 外。
- 新增 GM round-trip deletion 受限正例：在 reload 结果未使用且同 GM base 的 tiny pattern 中注释删除冗余 store/reload。
- 新增 Phase-6C 报告：`phase6c_restricted_true_rewrite_report.json`、`phase6c_analysis_summary.json`、`phase6c_leadership_summary.json`。
- 明确边界：这是 restricted true rewrite，不是 production MLIR/HivmOpsEditor backend；复杂真实 kernel 仍 locked。

# Changelog

## V3.3.2 Phase-6B - vTriton positive fixture harness

- Added Phase-6B reports: `phase6b_positive_case_validation_report.json`, `phase6b_fixture_acceptance_matrix.json`, `phase6b_analysis_summary.json`.
- Added `phase6b_real_backend_validation_commands.sh`, a real-backend execution script for vTriton/HivmOpsEditor and `tritonsim-hivm`.
- Added `--phase6-positive-fixtures` CLI option for concrete HIVM/NPUIR positive-case triage.
- Bundled user-provided fixture samples under `sample_input/phase6_positive_fixtures/` and two restricted positive fixtures for Q-load hoist / GM round-trip deletion gates.
- Production mutation remains locked until a real Operation-level backend and real `tritonsim-hivm` are supplied.


## V3.3.2 Phase-6A - Real Operation Backend Integration Readiness

- Added `strategy_search/phase6_analysis.py`.
- Added Phase-6A reports: `phase6a_real_backend_integration_report.json`, `phase6a_backend_acceptance_matrix.json`, `phase6a_required_inputs.json`, and `phase6a_analysis_summary.json`.
- Added `--vtriton-source-root` CLI option to record/check the real vTriton or HivmOpsEditor source context.
- Added strict acceptance checks for a real MLIR/HivmOpsEditor Operation backend; fake/mock/fixture backends remain rejected as production evidence.
- Added `HIVM_REWRITE_PHASE6A_PROGRESS_REPORT.md` and `PHASE6A_LEADERSHIP_BRIEF.md`.
- Production Q-load hoist, GM deletion, double-buffer, CV overlap, and tiling remain locked until a real backend, verifier, DES/trace, and positive fixture are supplied.


## V3.3.2 Phase-5E - Limited GM Round-trip Deletion Gate

- Added a guarded Phase-5E gate for limited GM round-trip deletion.
- Added `phase5e_limited_gm_roundtrip_deletion_report.json`, `phase5e_gm_deletion_safety_report.json`, and `phase5e_analysis_summary.json`.
- Extended the fake Operation backend fixture to accept `--mutate --mutation-kind gm_roundtrip_deletion` while explicitly refusing production deletion.
- Added `tests/test_phase5e_gm_deletion_gate.py`.
- GM deletion remains locked unless Phase-3C candidates pass and a real MLIR/HivmOpsEditor backend proves alias, memory-effect, observable-boundary, verifier and DES/trace safety.


## V3.3.2 Phase-5D - Guarded Operation-level Mutation Execution Gate

- Added Phase-5D guarded Q-load hoist mutation execution gate.
- Added `phase5d_guarded_mutation_execution_report.json`, `phase5d_mutation_safety_report.json`, and `phase5d_analysis_summary.json`.
- Added a future backend CLI contract for `--mutate --mutation-kind q_load_hoist`.
- Updated the fake Operation backend fixture to exercise the mutation command/report contract while explicitly refusing production mutation.
- Production mutation remains locked unless a real MLIR/HivmOpsEditor backend proves dominance, region motion, verifier success and DES/trace validation.


## V3.3.2 Phase-5C - Operation-level dry-run execution gate

- Added Phase-5C dry-run execution reports for future HivmOpsEditor / MLIR Operation backend.
- Added `phase5c_operation_level_dry_run_report.json`, dominance and region-motion precheck reports.
- Extended fake operation backend fixture to return per-action dry-run evidence without mutation.
- Production mutation remains disabled.

# V3.3.2 Phase-5B - Operation backend no-op roundtrip / verifier gate

- Added Phase-5B reports: `phase5b_roundtrip_verifier_gate_report.json`, `phase5b_backend_execution_plan.json`, and `phase5b_analysis_summary.json`.
- Added `tools/fake_hivm_operation_backend.py` as a CI/demo fixture for the Operation-backend CLI contract. It is not a real MLIR parser or verifier.
- Added backend execution support for `--inventory`, `--roundtrip`, and `--verify-only` modes when a future `--hivm-operation-backend` is configured.
- Kept all production mutations locked. Phase-5B is a no-op stability gate only; Q-load hoist, GM deletion, double-buffer, CV overlap and tiling remain disabled.
- Added tests for pending backend and fake-backend pass cases.

# Changelog

## V3.3.2 Phase-5A - Operation Backend Readiness / Inventory Alignment

- Added `strategy_search.phase5_analysis` as the Phase-5A report-only integration layer.
- Emits `phase5a_operation_backend_readiness_report.json`, `phase5a_inventory_alignment_report.json`, and `phase5a_analysis_summary.json` when structural rewrite is enabled.
- Added optional CLI probes `--hivm-operation-backend` and `--mlir-opt`; these are capability/readiness probes only and do not unlock production mutation.
- Defines the official-docs-aligned backend contract for future HivmOpsEditor / MLIR Operation-level integration: `--print-capabilities`, `--inventory`, `--roundtrip`, `--verify-only`, and `--dry-run`.
- Emits a local conservative inventory baseline for future comparison with a real Operation-walk backend.
- Keeps all production mutations locked: Q-load hoist, GM round-trip deletion, real double-buffer, full CV overlap, and real tiling lowering remain disabled until real backend inventory, roundtrip, verifier, dry-run, DES/trace and later msprof evidence are available.
- Added `HIVM_REWRITE_PHASE5A_PROGRESS_REPORT.md` and `PHASE5A_LEADERSHIP_BRIEF.md`.

## V3.3.2 Phase-4E - Phase 4 closure and Phase 5 handoff

- Added `phase4_closure_report.json` and `phase4e_analysis_summary.json`.
- Closed the Phase-4 bridge-validation / DES-trace / guarded-Q-hoist / official-dry-run-contract sequence without enabling risky production mutations.
- Added a Phase-5 entry-gate matrix for real HivmOpsEditor / MLIR Operation-level backend, verifier, DES/trace and msprof validation.
- Added `HIVM_REWRITE_PHASE4E_CLOSURE_REPORT.md` and `PHASE4E_LEADERSHIP_BRIEF.md`.

## V3.3.2 Phase-4C - guarded Q-load hoist prototype gate

- Added `phase4c_q_load_hoist_prototype_report.json`, `phase4c_q_load_hoist_candidate_script.json`, and `phase4c_analysis_summary.json`.
- Promotes locally-proven Phase-3D Q-load hoist candidates into a guarded backend dry-run worklist when Phase-4A/4B, event-liveness, and capacity gates are clean.
- Does not perform unsafe text-level region motion; production Q-load hoist remains locked until target parser / HivmOpsEditor region-motion proof is available.
- Added `HIVM_REWRITE_PHASE4C_PROGRESS_REPORT.md` and `PHASE4C_LEADERSHIP_BRIEF.md`.


## V3.3.2 Phase-4B - DES/trace execution gate

- Added `phase4b_des_trace_execution_report.json`, `phase4b_analysis_summary.json`, and `phase4b_validation_commands.sh`.
- Added a stricter DES/trace gate on top of the Phase-3E wrapper: both original and optimized IR must run through `tritonsim-hivm`, return zero, and produce parseable DES/Perfetto JSON artifacts.
- Added `tools/fake_tritonsim_hivm.py` as a CI/demo fixture only; it is not a performance simulator.
- High-risk mutations remain locked unless real target parser/DES/trace and later msprof evidence are available.


## V3.3.2 Phase-4A - HIVM Rewrite Bridge Hardening

- 新增 `strategy_search.phase4_analysis`。
- 新增 `target_parser_validation_report.json` 和 `phase4a_analysis_summary.json`。
- 当前后端统一定位为 HIVM Rewrite Bridge；`vTriton adapter` 仅作为兼容旧称。
- Phase 4A 只做 target parser / bridge readiness audit，不解锁 GM 删除、Q-load production hoist、double-buffer、CV overlap 或 tiling lowering。
- 新增 `HIVM_REWRITE_PHASE4A_PROGRESS_REPORT.md` 和 `PHASE4A_LEADERSHIP_BRIEF.md`。

# V3.3.2 Phase-3F - Phase 3 Closure and Phase 4 Handoff

- Added `phase3_closure_report.json` and `phase3f_analysis_summary.json`.
- Consolidated Phase-3A..3E evidence into a Phase 4 handoff matrix.
- Kept dangerous mutations locked by default: GM deletion, production Q-load hoist, real double-buffer, full CV overlap, tiling lowering.
- Added `HIVM_REWRITE_PHASE3F_CLOSURE_REPORT.md` and `PHASE3_CLOSURE_AND_PHASE4_PLAN.md`.

## V3.3.2 Phase-3C - GM MemorySSA-like legality gate

- 新增 `gm_memory_ssa_report.json`，以保守 MemorySSA-like 方式记录 GM MemoryDef / MemoryUse、唯一 reaching-def、unknown side-effect 和 observable boundary 阻断信息。
- 新增 `gm_roundtrip_deletion_decision.json`，对 Phase-3B 发现的 GM round-trip candidate 执行 same-GM、MemorySSA、unknown side-effect、observable-boundary、static offset/slice 等 gate 判断。
- 新增 `rewrite_legality_gate_report.json`，统一汇总未来危险 rewrite 的开关状态；默认原则为 cannot prove safe -> do not rewrite。
- Phase-3C 仍不强制删除 GM load/store；缺少 target offset/slice proof 或 observable-boundary 证明时，GM 删除继续 deferred。


## V3.3.1 structure-aware cycle correction

- 将 artifact kernel profile 从较宽的 reward/penalty 权重收敛为分项 cycle correction factors。
- 结构证据现在主要修正对应分项：memory -> load/store/workspace，scalar -> scalar/control，sync -> sync cost，alignment -> vector/fix。
- overlap/CV overlap 只保留窄范围 confidence 修正，降低 scalar/sync-heavy 证据的 double counting 风险。
- DES/MLIR ratio 融合从 product-artifact-heavy 改为更保守的 MLIR 60% + product 40%。
- 更新 README 与 cost model PDF，明确 predicted_cycles 是 corrected total cycle estimate，不是 profiling-calibrated hardware cycles。

## V3.3 naming/doc alignment - artifact inputs are not profiling

- 新增推荐 CLI 名称：`--artifact-des-graph` 与 `--artifact-trace`。
- 将旧参数 `--des-profile` / `--trace-profile` 标记为兼容 alias，避免误解为实机 profiling。
- 明确 V3.3 默认路径：`--artifact-kernel-profile on` + `--des-calibration-mode off`。
- 更新 README、optional_profiles_README、cost model 设计说明和超参数说明：V3.3 只用 MLIR + MLIR-derived artifacts 的结构字段，不使用 DES makespan/global scale。
- 保留 `--des-calibration-mode single_trace_prior` 作为 legacy/offline experiment，不再作为主路线文档口径。


## V3.2-stage2f-doc-alignment

- Updated cost model formula documents and rendered PDF to match `V3.2-risk-aware`, including `legality_risk_penalty` / `C_risk`.
- Updated cost model hyperparameter documents to include risk-aware penalties and recommended conservative/balanced/aggressive usage.
- Updated optional profile documentation from V2.7 wording to V3.2 wording while preserving historical note.
- Updated README/TESTING pytest marker commands to avoid accidentally selecting `slow` tests through class-level `smoke` markers.
- Updated CLI help and report-facing strings for cost-model config and V3.2 optional DES/trace profile wording.


## V3.2-stage2d-test-hardening

- 新增 `pytest.ini`，默认跳过 `slow` 搜索质量审计，避免日常测试/CI 被完整搜索拖慢。
- 新增 `tests/test_cost_model_unit.py`，覆盖 TilingPlan、MultiBufferPlan、CVPipelinePlan、SyncPlan、block_dim 和硬件 gate 的参数敏感性。
- 为较重的 Beam vs compact exhaustive / random baseline 审计测试添加 `@pytest.mark.slow`。
- 新增 `TESTING.md`，说明 unit / smoke / regression / slow 的测试分层和推荐运行命令。
- README 的测试章节同步更新为 pytest 分层测试入口，同时保留 unittest discover 兼容说明。


## V3.2-stage2a-search-space-stability

- Added stable `strategy_signature`, `layer1_signature`, and tile signatures.
- Ensured `expanded/full` auto search spaces explicitly contain standard tile candidates.
- Added standard Layer-1 survivor pinning for denser candidate spaces.
- Added exact candidate dedup before legality/cost evaluation and post-relax dedup before Top-K selection.
- Added `search_audit.json` and report-level Stage2a stability summary.
- Added regression tests for search-space containment, signature behavior, and candidate dedup audit.

# CHANGELOG

## V2.8.7：Compiler-like GM workspace fallback

- 将 `gm_workspace` 从普通 stage-buffer 候选改为真实编译语义下的 off-chip fallback / spill 路径。
- 新增 `gm_workspace_fallback_legality()`：默认要求 `ub_stage` / `l1_reuse` / `none` 等片上方案均不可行时，才允许 `stage_buffer_policy=gm_workspace`。
- `feasible_with_relax()` 在 GM fallback gate 失败时会 relax 回片上 stage-buffer 策略，避免把 GM workspace 当作首选优化。
- GM workspace cost 改为保守 MTE 竞争模型：workspace read/write 不再作为独立 lane 被 `max()` 隐藏，而是以 `workspace_exposed` 叠加到 steady tile time。
- `workspace_model` 新增/收紧：`penalty_factor`、`require_onchip_infeasible`、`max_workspace_utilization`，默认 `startup_cycles=350`、`overlap_ratio=0.10`。
- 新增单元测试 `test_gm_workspace_is_fallback_not_primary_candidate`，验证片上方案可行时 GM workspace 会被拒绝。

## V2.8.6 - GM workspace modeling

- 新增 `gm_ws` 资源 scope，`feasibility()` 现在同时检查 UB/L1/L0A/L0B/L0C/GM workspace。
- 新增 `workspace_model` 配置，支持 `gm_workspace` 容量预算、handoff tensor 数、read/write multiplier、startup cycles 和 overlap ratio。
- `stage_buffer_policy` 新增 `gm_workspace` 候选，用于将 CV pipeline handoff/stage buffer 放入 GM/HBM workspace。
- `estimate_max_live()` 现在返回 `gm_ws`，报告和 audit 中展示 GM workspace live bytes。
- cost model 新增 `per_tile_workspace_exposed`、`gm_workspace_bytes`、`gm_workspace_bytes_per_tile_total` 和 `workspace_detail`。
- README 补充 GM workspace 的 hard gate、workspace traffic cost 和公式说明。

---


## V2.8.5 - Penalty calibration and continuous regularization

- 将 `shape_regularization_penalty` 从固定大额跳变改为连续、低权重、可封顶的 soft regularization。
- `irregular_tile_n` 不再因为不在 preferred list 中直接获得固定大 penalty，而是根据到最近 preferred tile 的距离比例连续惩罚。
- `tail_penalty` 不再只要出现尾块就固定加分，而是根据尾块比例连续惩罚。
- `large_tile_n_penalty` 保持连续 soft-cap 形式，并增加 cap。
- `memory_pressure_penalty` 保持二次连续形式，但加入 per-scope cap，避免未 overflow 候选被单个资源压力软惩罚主导。
- 更新 README 中 cost model 与 penalty 的说明口径。

# CHANGELOG

本文件合并整理了项目从 V2.0 到当前版本的主要变化。历史版本文件已合并到本文件，避免仓库根目录出现多个分散 changelog。

---

## V2.8.3：Current-IR Estimated Reference

- 删除旧的 `baseline_like_strategy` / `predicted_speedup_vs_baseline_like` 报告口径。
- 新增 `current_ir_estimated_strategy`，从输入 IR 当前可见特征恢复当前策略状态。
- 新增 `current_ir_estimated_predicted_cycles`。
- 新增 `predicted_speedup_vs_current_ir_estimated`。
- HTML/Markdown 报告改为比较：当前输入 IR 估计 vs 最优候选。
- 若当前 IR 在解析硬件 gate 下不可行，speedup 输出为 `N/A` / `null`，只保留 cost 和资源压力诊断。
- 单元测试同步验证 current-IR reference 语义。

Current-IR 恢复规则：

- `multi_buffer = 2` 或 ping/pong 结构 → `double_buffer=True`。
- `cube_loop` / `vector_loop` → `cv_pipeline_stage=2`。
- 显式 `set_flag` / `wait_flag` / `pipe_barrier` → 作为 keep-existing 同步开销计入 current IR cost。
- 无显式 sync op 的 optimized IR → current sync cost 较低。
- 输入 IR 中解析出的 tile shape → 用作 current tile 估计。

---

## V2.8.2：中文报告可视化与优化前后对比

- HTML 报告新增当前输入 IR 与最优候选核心对比。
- 增强 UB/L1/L0A/L0B/L0C 资源利用率展示。
- 增强 cost breakdown 对比，覆盖 load、store、Cube/Vector pipeline、warmup/drain、sync、memory pressure、shape penalty 等项。
- 新增 Top-K 候选 predicted cycles 条形可视化。
- Markdown 报告同步加入核心指标对比、资源占用对比和 cost breakdown 对比表。

---

## V2.8.1：中文报告增强

- `strategy_search_report.html` 改为中文展示页。
- `strategy_search_report.md` 改为中文 Markdown 报告。
- 更新 smoke test 对 HTML 报告关键字段的检查。
- 仍保持当前 scope：不做 IR rewrite，不加入瓶颈分析，不加入 discrete memory access 建模。

---

## V2.8：报告展示与测试体系

- 新增 `strategy_search_report.html`。
- 新增 `tests/test_strategy_search_smoke.py`，覆盖 sync parser、CLI end-to-end 输出、Top-K 排序、最优策略可行性。
- 新增 `sample_input/fa_bad_inefficient.hivm.mlir` 作为确定性 no-profile search sanity check。
- Sync parser 同时支持 bare HIVM sync op 与 HIR-style sync op。
- HTML 报告包含 KPI、静态 kernel 特征、搜索空间摘要、selected strategy、硬件边界、cost breakdown、Top-K candidates 和 scope notes。

---

## V2.7.1：Conservative Analytical Cost Model

- 在 `configs/ascend_910b.json` 和 `configs/ascend_910b3_hypothetical.json` 中加入 `cost_model_safety`。
- 使用 scope-aware memory pressure penalty 替代单一压力惩罚。
- 加入 irregular `tile_n`、tail tile、very large `tile_n` 的 soft shape regularization。
- 加入 pressure-aware overlap degradation，UB/L0B 压力升高时降低乐观 overlap。
- 加入中等工程 tile-N 候选 `{96,160,192}`。
- Layer-1 beam 按 tile shape 去重，避免重复大 tile 子参数挤占候选。

---

## V2.7：JSON Profile-Guided Search

- 新增可选结构化输入：`--des-profile` 和 `--trace-profile`。
- 保留 `--desgraph` / `--trace` 作为向后兼容别名。
- `--source` 仅兼容旧参数，当前版本忽略 Python/Triton 源码解析。
- 新增 CVPipelinePlan 模板 `P_PREFILL_LARGE_SBS_REUSE`，吸收人工 review 后的 sparse-prefill A5 优化思想。
- 更新 Layer-2 合法性：通用 staged CV 仍依赖 double buffer，但 `P_PREFILL_LARGE_SBS_REUSE` 作为显式例外。
- README 中明确 JSON profile 是正式可选输入，Python source 不是稳定结构化输入。

---

## V2.6：Template-bundled CVPipelinePlan

- 将 CVPipelinePlan 从完整子参数笛卡尔积改为语义模板候选。
- 默认 CV templates 包括 `P0_no_cv_pipeline`、`P1_stage2_basic`、`P2_stage2_balanced`、`P2_stage2_balanced_ub_stage`、`P2_stage2_mixed_vector_heavy`、`P3_stage4_aggressive`。
- `alloc_overlap()` 不再枚举 CV 子参数完整笛卡尔积。
- per-buffer multiplier candidates 按 `db=False/True` 缓存。
- 增加 `layer2_raw_eval_cap_per_layer1`。
- 默认 `layer3_top_w` 从 48 降到 12，避免复杂 `.npuir.mlir` 输入下候选爆炸。

---

## V2.5：Per-Buffer MultiBufferPlan

- 新增 `buffer_multipliers_json` 到 `StrategyConfig`。
- 自动从 MLIR buffer lifetime evidence 中提取 eligible local buffers。
- 对代表性 local buffer 生成 `nbuf_b ∈ {1,2}` 的 per-buffer multiplier 候选。
- 新增候选控制参数：`max_per_buffer_multibuffer_buffers`、`max_buffers_with_multiplier_2`、`max_per_buffer_multiplier_candidates`。
- maxLive gate 纳入 per-buffer 额外副本带来的容量压力。
- per-buffer multiplier 对 load/store overlap 提供软收益。
- selected plans 输出 buffer multiplier 相关字段。

---

## V2.4：Closest-HIVM Four-Plan Parameter Model

- 聚焦四类优化 plan：`TilingPlan`、`MultiBufferPlan`、`CVPipelinePlan`、`SyncPlan`。
- 扩展 searchable knobs：
  - TilingPlan：`tile_m`、`tile_n`、`tile_k`、`loop_order`、`tail_strategy`、`reduce_tile_policy`、`layout_aware_tile`。
  - MultiBufferPlan：`double_buffer`、`multibuffer_template`、`ub_multiplier`、`l1_multiplier`、`stage_buffer_policy`。
  - CVPipelinePlan：`cv_pipeline_stage`、`cv_pipeline_template`、`enable_mixed_cv`、`tile_mix_cube_loop`、`tile_mix_vector_loop`、`auto_cv_balance`、`producer_consumer_distance`。
  - SyncPlan：`sync_policy`、`sync_template`、`barrier_level`、`event_reuse`、`sync_granularity`、`event_id_policy`、`sync_motion`。
- 固定或派生非核心参数：fusion、memory reuse、cv split ratio、DMA policy、block_dim。
- 新增 `cost_breakdown.json`。
- 增强 scope-aware memory modeling。

---

## V2.3：Generic HIVM Plan-Knob Search

- 将更多 HIVM evidence 从“只展示”变成真实 search knobs。
- 新增 TilingPlan、MultiBufferPlan、CVPipelinePlan、SyncPlan 的多项可搜索字段。
- cost model 开始让 loop order、tail strategy、CV template、sync template 等字段影响估计 cost。

---

## V2.2：Generic HIVM Structure-Aware Search

- 去除 FA-specific 定位，转为 generic HIVM structure-aware 实现。
- 新增 `generic_hivm_structure`、`candidate_tiles_from_cube_ops`、`primary_tile_candidate`、`cube_shape_evidence` 等通用证据。
- ping/pong multibuffer 和 event sync parser 保持 generic。

---

## V2.0：Four-Plan Search Route

- 移除旧九参数命令行路径。
- 搜索聚焦四个结构化 plan：TilingPlan、MultiBufferPlan、CVPipelinePlan、SyncPlan。
- fusion、memory reuse、CV split ratio、DMA policy 固定或派生。
- README 围绕 plan-based parameter optimization 重写。

## V3.0.1 - Param-sensitive cost model patch

- 将 template / hint 类参数显式接入 analytical cost model，避免它们只出现在报告中但不影响 predicted_cycles。
- `multibuffer_template` 现在影响 load/store overlap，并引入 per-tile schedule overhead。
- `cv_pipeline_template`、`tile_mix_cube_loop`、`tile_mix_vector_loop`、`producer_consumer_distance` 现在影响 CV overlap、warmup/drain 和 template schedule overhead。
- `sync_template` 现在影响 estimated barrier/event 数量、stall factor 和 fixed sync overhead。
- `event_id_policy`、`sync_motion` 保留原有 stall 影响，并在 sync breakdown 中显式记录。
- cost breakdown 新增 `template_schedule_overhead`、`mb_template_overhead`、`cv_template_overhead`、`tile_mix_penalty_cycles`、`producer_consumer_penalty_cycles`。
- cost model version 更新为 `V3.0.1-param-sensitive-cost-model`。

## V3.3.2 Phase-2H — Phase-2 Closure and Phase-3 Handoff

- Added `build_phase2_closure_report()` and automatic `phase2_closure_report.json` emission when structural rewrite is enabled.
- Added `PHASE2_CLOSURE_AND_PHASE3_PLAN.md` and `HIVM_REWRITE_PHASE2H_CLOSURE_REPORT.md`.
- Closed Phase 2 as an operation-level rewrite bridge stage: edit script, legality precheck, C++ bridge, validation summary, adapter manifest, and closure report.
- Defined Phase 3 entrypoint: dependency graph and event-liveness foundation before GM deletion, double-buffer, full CV overlap, or tiling lowering.
- Added tests for Phase-2H closure report and CLI output.

## V3.3.2 Phase-3A - Dependency / Event Analysis Foundation

- Added `strategy_search.phase3_analysis`.
- Emits `hivm_op_semantics_registry.json`, `hivm_ir_inventory.json`, `dependency_graph_report.json`, `event_liveness_report.json`, and `phase3a_analysis_summary.json` when structural rewrite is enabled.
- Builds a conservative HIVM op inventory with role/pipe/event/memory classifications.
- Builds conservative RAW/WAW/WAR, event set/wait, and coarse barrier dependency edges.
- Builds event liveness reports for set/wait pairing and local event live ranges.
- Does not authorize new dangerous mutation. GM deletion, Q-load hoist proof, real double-buffer, full CV overlap, and tiling lowering remain locked pending Phase-3B/3C analysis.

## V3.3.2 Phase-3B - Buffer Liveness / GM Alias Foundation

- Extended `strategy_search.phase3_analysis` with buffer liveness, local capacity recheck, and GM alias precheck.
- Emits `buffer_liveness_report.json`, `capacity_recheck_report.json`, `gm_alias_report.json`, and `phase3b_analysis_summary.json` when structural rewrite is enabled.
- Classifies buffers by role: stream buffer, softmax/score buffer, accumulator, output, GM input/boundary, GM output/boundary, and unknown local buffer.
- Adds conservative local capacity recheck using default Ascend 910B UB/L1/L0 limits.
- Adds GM access inventory and same-GM store→load candidate detection, but keeps GM deletion locked pending Phase-3C MemorySSA-like proof.
- Adds tests for Phase-3B reports.

## V3.3.2 Phase-3D - Loop-invariant load hoist proof gate

- Added `loop_invariant_load_hoist_report.json` for conservative Q/stream-load hoist candidates.
- Added `q_load_hoist_decision.json` with explicit local proof gates and deferred production mutation status.
- Added `phase3d_analysis_summary.json`.
- Added tests for Phase-3D hoist candidate detection and output emission.
- Production hoist remains locked until target parser / vTriton HivmOpsEditor confirms region-motion legality.

## V3.3.2 Phase-3E - tritonsim-hivm DES / Trace Validation Wrapper

- Extended `try_run_tritonsim_validation()` to request DES graph and Perfetto trace artifacts via `--des-graph-file` and `--perfetto-trace-file` when a local `tritonsim-hivm` binary is configured.
- Added Phase-3E validation reports: `vtriton_des_trace_validation_report.json`, `phase3e_analysis_summary.json`, and `trace_comparison_report.html`.
- Added local original/optimized inventory and dependency comparison inside the Phase-3E report so the output remains useful even when external vTriton validation is pending.
- Added tests for Phase-3E pending validation and output emission.
- Phase-3E does not unlock dangerous mutations; GM deletion, production Q-load hoist, real double-buffer, full CV overlap, and real tiling lowering remain locked until target DES/trace and later runtime/msprof validation pass.

## 3.3.2-phase3f-scope-clarified-phase4-plan

- Renamed the current structural rewrite component in documentation from over-strong `vTriton-backed` wording to the more accurate `HIVM Rewrite Bridge` / `HIVM Bridge Adapter`.
- Added `hivm_bridge_adapter/` as the preferred-name directory while keeping `vtriton_adapter/` as a backward-compatible alias for existing tests and scripts.
- Added `hivm_bridge_manifest.json` as the preferred manifest alias while retaining `vtriton_adapter_manifest.json` for compatibility.
- Added `NAMING_AND_SCOPE_CLARIFICATION.md` to explain that the current backend is a standalone bridge compatible with future vTriton/HivmOpsEditor integration, not a fully vTriton-backed production pass.
- Added `PHASE4_EXECUTION_PLAN.md` with Phase 4A–4E tasks, expected difficulties, and mitigation strategies.
- Clarified that Phase 4 should first harden target parser / HivmOpsEditor / DES-trace validation before attempting real double-buffer, full CV overlap, or real tiling lowering.


## V3.3.2 Phase-4D - Official-docs-aligned dry-run contract

- Added Phase-4D Operation-level dry-run contract artifacts.
- Added `phase4d_operation_rewrite_dry_run_report.json`, `phase4d_hivmopseditor_dry_run_plan.json`, `phase4d_official_mlir_compliance_report.json`, and `phase4d_analysis_summary.json`.
- Kept Q-load hoist production mutation locked; no text-level region motion is performed.
- Added official MLIR rewrite/legality/dominance policy notes for future HivmOpsEditor/MLIR backend integration.


## V3.3.2 Phase-5F：Phase 5 收口与 Phase 6 计划

- 新增 `phase5_closure_report.json`、`phase5f_analysis_summary.json`、`phase5f_leadership_summary.json`。
- 明确 Phase 5 完成的是 Operation-level backend 接入前的合同与门禁阶段，不声称 production Q-load hoist 或 GM deletion 已经实现。
- 新增 `HIVM_REWRITE_PHASE5F_CLOSURE_REPORT.md`、`PHASE5F_LEADERSHIP_BRIEF.md`、`PHASE5_CLOSURE_AND_PHASE6_PLAN.md`。
- Phase 6 建议聚焦真实 HivmOpsEditor / MLIR Operation backend 接入，以及受限 Q-load hoist / GM deletion 正例验证。

## V3.3.2 Phase-6E - vTriton Local Build Integration Pack

- Added Phase-6E outputs:
  - `phase6e_vtriton_local_integration_report.json`
  - `phase6e_backend_build_plan.json`
  - `phase6e_analysis_summary.json`
- Added local vTriton integration/build scripts:
  - `scripts/phase6e_apply_vtriton_backend_patch.py`
  - `scripts/phase6e_build_hivm_operation_backend.sh`
  - `scripts/phase6e_smoke_test_backend.sh`
- Updated `vtriton_hivm_operation_backend/CMakeLists.txt` to follow the real vTriton tool build style using `add_llvm_executable` and `TRITONSIM_HAS_BISHENGIR_HIVM` gating.
- Added Phase-6E documentation:
  - `HIVM_REWRITE_PHASE6E_PROGRESS_REPORT.md`
  - `PHASE6E_LEADERSHIP_BRIEF.md`
- No broad production mutation is unlocked. Phase-6E prepares the local build/integration path for the real HivmOpsEditor backend.


---

## CVPIPELINE_SAFE_HINT_REWRITE_REPORT.md

# CVPipelinePlan Safe Hint Rewrite 实现报告

## 1. 实现结论

本版本在 Step-2 safe structural rewrite 的基础上，新增了 **CVPipelinePlan 安全 hint rewrite**。

它完成的是：

```text
selected_strategy 中的 CVPipelinePlan
        ↓
已有 HIVM/NPUIR op anchor 上的 hivm.cv.* 属性
        ↓
cv_pipeline_rewrite_report.json / pass_pipeline_config.json / strategy_edit_script.json
```

它没有做真实 cube/vector/fixpipe/store 重排，因此仍然属于安全 rewrite 阶段。

## 2. 新增能力

新增文件/输出：

```text
cv_pipeline_rewrite_report.json
```

新增测试：

```text
tests/test_rewrite_cvpipeline_hint.py
```

新增核心函数：

```python
_extract_cv_op_inventory()
_apply_safe_cv_pipeline_rewrite()
build_cv_pipeline_rewrite_report()
```

## 3. 支持识别的 op role

当前会把已有 HIVM op 分成以下角色：

| role | 典型 op |
|---|---|
| load | hivm.hir.load, hivm.hir.nd2nz |
| cube | hivm.hir.mmad, hivm.hir.mmadL1 |
| fixpipe | hivm.hir.fixpipe |
| vector | hivm.hir.vadd, hivm.hir.vsub, hivm.hir.vexp, hivm.hir.vreduce, hivm.hir.vdiv, hivm.hir.cast |
| store | hivm.hir.store, hivm.hir.nz2nd |
| sync | hivm.hir.set_flag, hivm.hir.wait_flag, hivm.hir.pipe_barrier, hivm.hir.barrier |

## 4. conservative / balanced 行为

### conservative

只给以下 op 加 CVPipeline hint：

```text
cube / fixpipe / vector
```

不标记 load/store 边界。

### balanced / aggressive

除了 `cube / fixpipe / vector`，还会标记：

```text
load / store
```

这样后续真实 compiler pass 更容易识别 stage 边界。

## 5. 写入 IR 的属性示例

原始 IR：

```mlir
hivm.hir.mmadL1 ins(%a_l1, %b_l1) outs(%c_l0c)
hivm.hir.fixpipe ins(%c_l0c) outs(%cv_ub)
hivm.hir.vadd ins(%cv_ub, %cv_ub) outs(%cv_ub)
```

改写后：

```mlir
hivm.hir.mmadL1 {hivm.cv.pipeline_hint = true, hivm.cv.role = "cube", hivm.cv.stage = 2 : i64, hivm.cv.template = "P2_stage2_balanced", hivm.cv.producer_consumer_distance = 1 : i64, hivm.cv.cube_loop = 1 : i64, hivm.cv.vector_loop = 1 : i64, hivm.cv.enable_mixed_cv = false, hivm.cv.auto_balance = true, hivm.cv.anchor_index = 0 : i64} ins(%a_l1, %b_l1) outs(%c_l0c)

hivm.hir.fixpipe {hivm.cv.pipeline_hint = true, hivm.cv.role = "fixpipe", hivm.cv.stage = 2 : i64, hivm.cv.template = "P2_stage2_balanced", ...} ins(%c_l0c) outs(%cv_ub)

hivm.hir.vadd {hivm.cv.pipeline_hint = true, hivm.cv.role = "vector", hivm.cv.stage = 2 : i64, hivm.cv.template = "P2_stage2_balanced", ...} ins(%cv_ub, %cv_ub) outs(%cv_ub)
```

## 6. 安全边界

本版本明确不做：

```text
不重排 cube/vector/fixpipe/store op
不插入 set_flag / wait_flag
不删除或移动 barrier
不复用 event id
不复制 stage buffer
不实现真实 producer-consumer overlap
不声称已经得到真实加速
```

所以它是：

```text
CVPipelinePlan → op-level machine-readable hint
```

不是：

```text
CVPipelinePlan → real C/V overlapped schedule
```

## 7. 新增报告内容

`cv_pipeline_rewrite_report.json` 会记录：

```json
{
  "op_inventory": {
    "role_counts": {
      "load": 3,
      "cube": 1,
      "fixpipe": 1,
      "vector": 1,
      "store": 1,
      "sync": 7
    },
    "has_cv_pipeline_opportunity": true
  },
  "applied_changes_summary": {
    "cv_op_hints_added": 7,
    "changed_role_counts": {
      "load": 3,
      "cube": 1,
      "fixpipe": 1,
      "vector": 1,
      "store": 1
    }
  },
  "capabilities": {
    "cv_op_level_hint_attrs": true,
    "cv_pipeline_structural_reorder": false,
    "event_wait_insertion_for_cv_overlap": false,
    "buffer_duplication_for_cv_stage": false
  }
}
```

## 8. 测试结果

完整测试结果：

```text
48 passed
```

新增测试覆盖：

```text
1. conservative 模式只标记 cube/fixpipe/vector，不标记 load/store
2. balanced 模式额外标记 load/store 边界
3. cv_pipeline_stage=1 时生成 report，但不添加 op-level hint
```

## 9. 后续真实 CVPipeline rewrite 还需要什么

如果要从 hint rewrite 进入真实 structural rewrite，需要补：

```text
1. cube/fixpipe/vector/store dependency graph
2. buffer live-range analysis
3. stage buffer 分配和复用规则
4. set_flag / wait_flag 插入合法性
5. event id 生命周期验证
6. 重排前后结果一致性验证
7. vTriton compile / DES-after / msprof 对比
```

所以当前版本可以作为真实 CVPipeline compiler pass 的输入准备层，但还不是最终 lowering pass。


---

## DEFECT_INJECTION_TEST_REPORT.md

# 缺陷注入 MLIR 测试报告

本报告汇总 9 个合成缺陷 MLIR 样例的测试结果。测试目标不是证明真实硬件加速，而是验证当前 strategy-level analytical search demo 是否能识别明显低效/非法方向，并在 cost model 下选择更合理的四类 Plan。

## 1. 测试设计

9 个样例被加入 `tests/defect_inputs/`，对应的期望与审计结果被加入 `tests/defect_expected/defect_run_summary.json`，pytest 用例位于 `tests/test_defect_injection_cases.py`。

| 类别 | 文件 | 构造缺陷 | 期望验证 |
|---|---|---|---|
| A | `defect_A_small_tile_f32_barrier.mlir` | 小 BN tile、f32 score、独立 p buffer、粗粒度 barrier | 是否调整 tile、启用 buffer/pipeline/sync 优化 |
| B | `defect_B_large_tile_ub_overflow.mlir` | 超大 tile、UB overflow、容量不可行 | hardware gate 是否拒绝非法 current IR 并回退合法候选 |
| C | `defect_C_barrier_heavy_sync_stall.mlir` | tile 尚可但 barrier-heavy，同步停顿明显 | SyncPlan 是否往 graph sync / event reuse 方向移动 |
| D | `defect_D_no_overlap_good_tile.mlir` | tile 尚可但缺少 double buffer / CV overlap | 不是只改 tile，也应启用 overlap 相关 Plan |
| E | `defect_E_small_tile_many_sync_f32_redundantQ.mlir` | 小 tile + f32 + 冗余 Q 搬运 + 多 barrier + 冗余写回 | 多种缺陷叠加时是否综合优化四类 Plan |
| F | `defect_F_large_tile_overflow_sync_pressure.mlir` | 大 tile overflow + 额外 buffer + 重复 Q 搬运 + 同步压力 | 复合容量超限时是否仍由 hardware gate 拦截 |
| G | `defect_G_existing_pingpong_but_bad_sync_dtype.mlir` | 已有局部双份缓冲痕迹，但 dtype / sync / vector / tile 仍差 | 已有局部优化时是否继续优化其他瓶颈 |
| H | `defect_H_event_sync_but_small_tile_no_overlap.mlir` | 已有 event sync，但小 tile 和 overlap 仍差 | 已有 event sync 时是否继续优化 tile/buffer/pipeline |
| I | `defect_I_medium_tile_memory_pressure_vector_heavy.mlir` | 中等 tile，但 f32、额外 buffer、vector-heavy、同步压力叠加 | 非极端混合瓶颈是否能被识别 |

## 2. 当前测试命令与结果

```bash
python -m pytest -q
# 37 passed

python -m pytest -q tests/test_defect_injection_cases.py -m regression
# 18 passed, 9 skipped

python -m pytest -q -m slow
# 3 passed, 9 skipped
```

说明：默认测试会跳过 `slow`。9 个 live defect search 用例是 opt-in，默认 skip；这是为了避免日常 CI 每次都重复跑完整搜索。需要重新实跑 9 个缺陷搜索时，可设置：

```bash
RUN_DEFECT_LIVE=1 python -m pytest -q -m slow tests/test_defect_injection_cases.py
```

当前报告中的数值来自已实跑并固化的缺陷注入审计结果。

## 3. 结果汇总

| Case | Current tile | Current feasible | Current cycles | Best tile | DB | CV stage | Sync | Best cycles | Speedup | Risk |
|---|---:|---|---:|---:|---|---:|---|---:|---:|---|
| defect_A_small_tile_f32_barrier | 64x32x128 | True / ok | 1084.034 | 32x64x128 | True | 2 | graph_sync_solver | 458.503 | 2.364x | HIGH |
| defect_B_large_tile_ub_overflow | 128x256x128 | False / UB overflow | 5437.001 | 64x64x128 | True | 2 | graph_sync_solver | 613.071 | N/A | HIGH |
| defect_C_barrier_heavy_sync_stall | 64x64x128 | True / ok | 2252.966 | 32x64x128 | True | 2 | graph_sync_solver | 825.115 | 2.730x | HIGH |
| defect_D_no_overlap_good_tile | 64x64x128 | True / ok | 1352.966 | 32x64x128 | True | 2 | graph_sync_solver | 458.503 | 2.951x | HIGH |
| defect_E_small_tile_many_sync_f32_redundantQ | 64x32x128 | True / ok | 1704.923 | 32x64x128 | True | 2 | graph_sync_solver | 698.747 | 2.440x | HIGH |
| defect_F_large_tile_overflow_sync_pressure | 128x256x128 | False / UB overflow | 6671.235 | 64x64x128 | True | 2 | graph_sync_solver | 1025.558 | N/A | HIGH |
| defect_G_existing_pingpong_but_bad_sync_dtype | 96x96x128 | True / ok | 2509.547 | 16x176x128 | True | 2 | graph_sync_solver | 1103.274 | 2.275x | HIGH |
| defect_H_event_sync_but_small_tile_no_overlap | 64x32x128 | True / ok | 841.813 | 32x64x128 | True | 2 | graph_sync_solver | 431.746 | 1.950x | HIGH |
| defect_I_medium_tile_memory_pressure_vector_heavy | 64x64x128 | True / ok | 1820.083 | 32x64x128 | True | 2 | graph_sync_solver | 699.560 | 2.602x | HIGH |

## 4. 通过测试说明了什么

1. **四类 Plan 联动生效。** 9 个 case 的 best strategy 都启用了 `double_buffer=True`、`cv_pipeline_stage=2`、`sync_policy=graph_sync_solver` 和 `event_reuse=True`，说明搜索结果不是只动单一 tile，而是同时利用 MultiBufferPlan、CVPipelinePlan 和 SyncPlan。

2. **hardware gate 能识别容量非法输入。** `defect_B` 和 `defect_F` 的 current IR 均被判定为 `UB overflow`，speedup 不计算为合法 baseline；搜索结果回退到更小的合法 tile。

3. **已有局部优化不会让搜索器停止。** `defect_G` 已有局部双份缓冲痕迹，`defect_H` 已有 event sync，但搜索器仍继续调整 tile、CV stage 和 sync policy。

4. **复合缺陷能被综合处理。** E–I 不是单点问题，而是 tile、dtype、buffer、sync、vector-heavy、memory pressure 叠加；记录结果显示模型能给出一致的优化方向。


## 5. 不能证明什么

这些测试仍然是 analytical model / demo-level 验证，不能证明真实 NPU 上一定加速，也不能证明 GraphSyncSolver 一定 deadlock-free，不能证明 CVPipelinePlan 一定能被 compiler pass 改写实现。真实闭环仍需要：optimized HIVM rewrite、编译运行、msprof profiling、cost calibration 和 legality checker。

## 6. 后续建议

- 把 live defect suite 做成独立脚本，用于刷新 `tests/defect_expected/defect_run_summary.json`。
- 增加 parser 注释剥离，避免注释文本污染 `ping/pong`、`cv_pipeline` 等结构识别。
- 对 `defect_G` 这类产生 `16x176x128` 的候选增加真实硬件/编译约束，例如 alignment、preferred tile whitelist、tail handling 和 pass 可生成性。


---

## ENGINEERING_STRUCTURE_STAGE3.md

# Stage 3 工程结构化说明

本阶段目标是让代码仓从“单文件脚本 demo”逐步变成“可长期维护的 Python 项目”。

## 已完成

1. `auto_strategy_search.py` 改为兼容入口。
   - 旧命令 `python auto_strategy_search.py ...` 仍然可用。
   - 旧测试里 `import auto_strategy_search as search` 仍然可用。

2. 新增并开始物理拆分 `strategy_search/` 包结构。
   - `core.py`：保留 parser/search/cost/hardware 主流程实现，保证行为不漂移。
   - `plans.py`：已物理迁移 Plan / Feature dataclass 与基础常量，不再从 core facade 导出。
   - `report.py`：已物理迁移 Markdown/HTML 报告生成函数。
   - `rewrite.py`：已物理迁移 annotation / safe-structural rewrite 与 vTriton sidecar 生成函数。
   - `parser.py`：IR 解析 facade。
   - `hardware.py`：硬件容量和 feasibility facade。
   - `cost_model.py`：risk-aware cost model facade。
   - `search.py`：candidate generation / beam search facade。
   - `cli.py`：`python -m strategy_search.cli` 入口。

3. 新增 package facade 测试。
   - 验证 `strategy_search.cost_model.estimate_cost` 等模块 API 与旧 wrapper 兼容。

4. CLI 测试改为 `standard` candidate-space，降低 CI 冒烟测试时间；完整 expanded 搜索仍然支持，用于正式实验。

## 为什么不是一次性完全拆分 core.py？

当前 `auto_strategy_search.py` 原始文件包含 parser、search、cost model、report、rewrite 等 5000 行逻辑，函数之间存在大量直接调用。如果一次性物理拆分所有函数，容易引入行为漂移，导致前后结果无法对齐。

因此本阶段采用“兼容优先”的两步策略：

```text
第一步：建立包结构和模块 API 边界，保证旧命令和旧测试都能跑。
第二步：已先迁移 dataclass、report、rewrite 三类低耦合模块。
第三步：后续继续把 hardware/cost_model/search/parser 从 core.py 中物理迁移出去，并为每个模块补单元测试。
```

## 后续建议

下一步建议继续物理拆分：

1. `hardware.py`：先迁移 memory cap、alignment、footprint、feasibility 等纯函数；注意 `tile_buffers()` 仍依赖 per-buffer 搜索函数，需要一起解耦。
2. `cost_model.py`：在 golden output 回归测试补齐后迁移，避免 cost breakdown 漂移。
3. `search.py`：迁移 search-space generation 和 beam search，同时加入 expanded 包含 standard 的稳定性改造。
4. `parser.py`：最后迁移，原因是 parser 与 artifact evidence/current IR estimate 依赖较多。


---

## HIVM_REWRITE_PHASE1_PROGRESS_REPORT.md

# HIVM IR Rewrite Phase-1 Progress Report

## Goal

Start moving from hint rewrite toward an official-documentation-aligned structural
rewrite pipeline.

## What was implemented

### 1. Structural Edit Script Schema

Added:

```text
strategy_search/structural_edit_schema.py
```

This defines:

```text
- supported edit types
- mutation kinds
- required top-level fields
- legality contract
- safety levels
- hard boundaries
```

The generated script now includes:

```text
- official_rewrite_guidance
- legality_contract
- per-edit legality.required_gates
- per-edit mutation_kinds
- schema_validation
```

### 2. Runtime outputs

When structural rewrite is enabled, the project now emits:

```text
structural_edit_script.json
structural_edit_schema.json
structural_edit_validation_report.json
structural_rewrite_report.json
optimized.structural.hivm.mlir
```

### 3. vTriton adapter scaffold

Added:

```text
vtriton_adapter/hivm_strategy_rewrite.cpp
vtriton_adapter/README.md
```

This is the target C++/MLIR/vTriton boundary for production rewrite. It is not a
full backend yet; it documents the intended CLI and implementation structure.

### 4. Tests

Added:

```text
tests/test_structural_edit_schema.py
```

This verifies that generated edit scripts conform to the project schema and carry
legality information.

## Current status

Current version has completed:

```text
Phase 1A: edit script schema standardization
Phase 1B: legality contract embedding
Phase 1C: vTriton backend scaffold
```

Not yet completed:

```text
Phase 2: actual C++ HivmOpsEditor backend
Phase 3: dependency graph and buffer live-range legality checker
Phase 4: automated vTriton DES/trace validation
```

## Next recommended step

Implement the first real C++/vTriton backend edit:

```text
replace_barrier_all_with_directional_sync
```

because it has a clear local anchor, visible IR diff, and direct connection to
SyncPlan.


---

## HIVM_REWRITE_PHASE2A_PROGRESS_REPORT.md

# HIVM Rewrite Phase 2A Progress Report

## 本阶段目标

本阶段继续推进 HIVM IR rewrite 工程，但不继续扩大 Python 文本级 hack，而是按照官方 MLIR rewrite 思路把结构改写后端边界标准化。

官方工程原则在项目中落实为：

1. **Operation-level mutation**：正式后端应通过 vTriton/HivmOpsEditor 或 MLIR PatternRewriter/RewriterBase 风格 API 修改 IR，而不是长期依赖 Python 正则文本替换。
2. **显式 legality model**：每个结构改写 edit 都必须有 legality contract、required gates、fallback reason 和 report。
3. **后端可替换**：Python 寻优器只生成 strategy 和 edit script；真正修改 HIVM 的后端可以是 Python fallback、vTriton hivm-crud 或未来的 hivm-strategy-rewrite。
4. **验证闭环**：改写后必须支持 tritonsim-hivm / DES / trace 验证入口，不能只看文本 diff 就声称性能提升。

## 本阶段新增能力

### 1. Structural backend execution plan

新增输出：

```text
structural_backend_execution_plan.json
```

该文件会记录当前结构改写选择的后端：

```text
auto
python
vtriton
dry_run
```

默认 `auto` 的选择逻辑为：

```text
优先使用 --vtriton-strategy-rewriter
其次使用 --vtriton-hivm-crud
否则回退到 Python fallback
```

这使得当前项目已经具备正式接入 vTriton rewrite binary 的接口边界。

### 2. vTriton strategy rewriter adapter 接口

新增 CLI 参数：

```bash
--structural-rewrite-backend auto|python|vtriton|dry_run
--vtriton-strategy-rewriter /path/to/hivm-strategy-rewrite
--vtriton-hivm-crud /path/to/hivm-crud
```

未来正式后端目标 CLI 为：

```bash
hivm-strategy-rewrite \
  --input original.hivm.mlir \
  --edit-script structural_edit_script.json \
  --output optimized.structural.hivm.mlir \
  --report structural_rewrite_report.json
```

当前如果该 binary 不存在，项目会明确记录原因并回退到 Python fallback。

### 3. Python fallback validation report

新增输出：

```text
structural_python_fallback_validation_report.json
```

该报告会比较 rewrite 前后的结构性 op 计数，包括：

```text
barrier_all
set_flag
wait_flag
load
store
cube
fixpipe
vector
```

示例 demo 中得到：

```json
{
  "barrier_all": -2,
  "set_flag": 3,
  "wait_flag": 3
}
```

这说明 Python fallback 的确做了 operation sequence 变化：两个 coarse barrier 被替换，额外插入了方向性 sync。

注意：该 validation 只是轻量级自检，不等价于目标 MLIR parser 或真实 runtime 验证。

### 4. vTriton validation wrapper

新增 CLI 参数：

```bash
--run-vtriton-validation
--tritonsim-hivm /path/to/tritonsim-hivm
```

打开后会生成：

```text
vtriton_validation_report.json
vtriton_validation/input_tritonsim_stdout.txt
vtriton_validation/input_tritonsim_stderr.txt
vtriton_validation/optimized_tritonsim_stdout.txt
vtriton_validation/optimized_tritonsim_stderr.txt
```

如果没有提供 `tritonsim-hivm`，报告会明确写：

```text
no_tritonsim_hivm_configured
```

这样后续接真实 vTriton 环境时，不需要重新设计 CLI。

## 当前运行方式

推荐命令：

```bash
python -m strategy_search.cli \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --enable-ir-rewrite \
  --rewrite-mode both \
  --rewrite-safety balanced \
  --enable-structural-rewrite \
  --structural-rewrite-safety balanced \
  --structural-rewrite-backend auto \
  --run-vtriton-validation \
  --output-dir output_phase2a_demo
```

如果有正式 vTriton rewriter：

```bash
python -m strategy_search.cli \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --enable-ir-rewrite \
  --rewrite-mode both \
  --rewrite-safety balanced \
  --enable-structural-rewrite \
  --structural-rewrite-backend vtriton \
  --vtriton-strategy-rewriter /path/to/hivm-strategy-rewrite \
  --run-vtriton-validation \
  --tritonsim-hivm /path/to/tritonsim-hivm \
  --output-dir output_phase2a_vtriton
```

如果只想生成 edit script，不改 IR：

```bash
--structural-rewrite-backend dry_run
```

## 本阶段新增/修改文件

```text
strategy_search/structural_rewrite.py
strategy_search/rewrite.py
strategy_search/core.py
tests/test_structural_backend_phase2a.py
HIVM_REWRITE_PHASE2A_PROGRESS_REPORT.md
```

新增输出文件：

```text
structural_backend_execution_plan.json
structural_python_fallback_validation_report.json
vtriton_validation_report.json
optimized.structural.python_fallback.hivm.mlir
```

## 测试结果

完整测试结果：

```text
59 passed
```

Demo 运行结果：

```text
selected_backend = python_fallback
barrier_all: 2 -> 0
set_flag: 0 -> 3
wait_flag: 0 -> 3
total structural changes = 4
```

## 当前边界

本阶段仍然没有完成：

```text
real tiling loop lowering
real ping-pong double buffer rewrite
full CV pipeline overlap schedule
event-id reuse
sync motion
完整 dependency graph legality proof
```

这些必须等正式 C++/MLIR/vTriton 后端和 legality checker 建起来以后再做。

## 下一步建议

下一步进入 Phase 2B：实现 `hivm-strategy-rewrite` 的第一版 C++/vTriton 后端。

优先实现三个 edit：

```text
1. replace_barrier_all_with_directional_sync
2. insert_cv_boundary_sync
3. remove_redundant_gm_roundtrip
```

然后接 Phase 3：dependency graph / buffer live range legality checker。


---

## HIVM_REWRITE_PHASE2B_PROGRESS_REPORT.md

# HIVM Rewrite Phase-2B Progress Report

## 本阶段目标

Phase-2A 已经把 structural rewrite 拆成 backend boundary：Python strategy search 生成 `structural_edit_script.json`，后端可以选择 Python fallback、vTriton strategy rewriter、`hivm-crud` 或 dry-run。

Phase-2B 继续推进，但不盲目扩大 rewrite 范围。本阶段重点是：

1. 给每个 structural edit 加本地 legality precheck；
2. 生成 `structural_legality_report.json`；
3. 把 vTriton adapter 从单个 C++ scaffold 扩展为更接近正式工程边界的 C++ 文件组；
4. 明确 Python fallback 只是 prototype，生产后端必须使用 vTriton/HivmOpsEditor/MLIR Operation-level mutation。

## 官方文档约束

本阶段继续按 MLIR 官方 rewrite 思路推进：

- Pattern Rewriter 是 MLIR 的通用 DAG-to-DAG transformation 框架，广泛用于 canonicalization、conversion 和通用 transformation。
- `PatternRewriter` / `RewriterBase` 应负责 rewrite 中的 IR mutation，避免绕过 rewrite driver 导致状态失效。
- Dialect Conversion 强调 Conversion Target + Rewrite Patterns + optional Type Converter 的 explicit legality model。

项目中对应的工程规则是：

```text
match explicit op anchor
  -> run local legality precheck
  -> emit/edit through backend-owned API
  -> record applied/skipped evidence
  -> validate with target MLIR/vTriton parser and DES/trace
```

## 新增文件

```text
strategy_search/structural_legality.py
vtriton_adapter/CMakeLists.txt
vtriton_adapter/HivmStrategyEditScript.h
vtriton_adapter/HivmLegalityCheck.h
vtriton_adapter/hivm_strategy_rewrite.cpp
tests/test_structural_legality_phase2b.py
```

## 新增输出

打开 `--enable-structural-rewrite` 后，现在额外生成：

```text
structural_legality_report.json
```

该报告包含：

```text
anchor_analysis:
  barrier_all_lines
  cube_lines
  fixpipe_lines
  vector_lines
  cv_boundary_candidates
  q_hoist_candidates
  duplicate_sync_pairs

edit_prechecks:
  每个 edit 的 local_precheck passed/failed
  evidence
  required_gates_from_script
  mutation_kinds
```

## 当前已支持的本地 precheck

| Edit | Precheck |
|---|---|
| `replace_barrier_all_with_directional_sync` | 检查显式 `barrier {mode="ALL"}` 或 `pipe_barrier[<PIPE_ALL>]` anchor |
| `insert_sync_before_first_vector_op` | 检查 cube/fixpipe 后是否存在未立即同步的 vector op |
| `hoist_invariant_q_load_from_simple_loop` | 检查简单 `scf.for` 内是否存在 `%Q_gm -> %q_ub -> %q_l1` 且不使用 induction variable |
| `remove_adjacent_duplicate_sync_pairs` | aggressive 模式下检查相邻重复 set/wait |
| `remove_redundant_gm_roundtrip` | 暂时 deferred，等待 vTriton/HivmOpsEditor 后端和 GM base checker |

## 边界声明

`structural_legality_report.json` 不是 correctness proof。它只是 Python 侧本地预检，作用是避免完全无证据的 rewrite。正式正确性仍需要：

```text
1. target MLIR/vTriton parser validation
2. dependency graph legality checker
3. buffer live-range checker
4. event live-range checker
5. DES/trace/msprof validation
```

## 下一阶段建议

Phase-2C 应该优先实现：

```text
1. vTriton adapter 中的 JSON edit-script parser
2. C++ backend 中第一个真实 Operation-level edit：replace_barrier_all_with_directional_sync
3. 生产后端返回 structural_rewrite_report.json
4. Python CLI 在 vTriton backend 成功时使用 C++ 输出，否则 fallback
```

暂时仍不建议直接做 real double-buffer、real CV overlap 或 real tiling lowering。


---

## HIVM_REWRITE_PHASE2C_PROGRESS_REPORT.md

# HIVM Rewrite Phase 2C Progress Report

## 1. 本阶段目标

Phase 2C 的目标是把 structural rewrite 从“只有 Python fallback 能执行”推进到“存在一个可执行的 C++/vTriton adapter 后端边界”。本阶段优先实现风险最低、anchor 最明确的一类真实结构改写：

```text
replace_barrier_all_with_directional_sync
```

即将显式粗粒度同步：

```mlir
hivm.hir.barrier {mode = "ALL"}
```

改写为方向性同步：

```mlir
hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_M>, <EVENT_IDk>]
hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_M>, <EVENT_IDk>]
```

这一步是真实 operation sequence change，不是 attribute/hint rewrite。

---

## 2. 官方指引如何落地

本阶段继续遵守 MLIR 官方 rewrite 工程原则：

1. 正式 IR mutation 的生产形态应通过 `PatternRewriter/RewriterBase` 或等价的 pass-owned operation API 完成。
2. Dialect Conversion 思路要求有显式 legality model，不能在没有合法性判断时盲目转换。
3. 当前 C++ adapter 是 **standalone strict bridge**，用于打通工程链路；最终生产版本仍应迁移到 vTriton/HivmOpsEditor 或 MLIR pass 中。

因此，本阶段没有声称完成完整 production compiler pass，而是完成：

```text
structural_edit_script.json
    -> C++ hivm-strategy-rewrite bridge
    -> optimized.structural.hivm.mlir
    -> structural_rewrite.external_vtriton_report.json
```

---

## 3. 新增/修改文件

### 3.1 C++ rewrite bridge

新增/强化：

```text
vtriton_adapter/hivm_strategy_rewrite.cpp
vtriton_adapter/CMakeLists.txt
```

现在 `hivm_strategy_rewrite.cpp` 不再只是 scaffold。它可以独立编译：

```bash
g++ -std=c++17 vtriton_adapter/hivm_strategy_rewrite.cpp -o build_phase2c/hivm-strategy-rewrite
```

并支持：

```bash
build_phase2c/hivm-strategy-rewrite \
  --input original.hivm.mlir \
  --edit-script structural_edit_script.json \
  --output optimized.structural.hivm.mlir \
  --report structural_rewrite.external_vtriton_report.json
```

### 3.2 Python backend selection 修正

修正：

```text
--structural-rewrite-backend vtriton
```

现在如果传入：

```text
--vtriton-strategy-rewriter /path/to/hivm-strategy-rewrite
```

会正确选择：

```text
selected_backend = vtriton_strategy_rewriter
```

而不是错误回退到 Python fallback。

### 3.3 报告语义修正

当外部 C++ backend 成功执行时，`structural_rewrite_report.json` 现在会区分：

```text
changes_summary_source = external_vtriton_strategy_rewriter
changes_summary = 外部 C++ backend 实际改写
python_fallback_planned_changes_summary = Python fallback 原计划改写
```

这样不会把 Python fallback 的 4 个计划变化误报成外部 C++ backend 实际完成的变化。

---

## 4. 当前 C++ backend 支持范围

### 已支持

```text
replace_barrier_all_with_directional_sync
```

支持 anchor：

```text
hivm.hir.barrier {mode = "ALL"}
hivm.hir.pipe_barrier[<PIPE_ALL>]
hivm.pipe_barrier[<PIPE_ALL>]
```

### 暂不支持

```text
insert_sync_before_first_vector_op
hoist_invariant_q_load_from_simple_loop
remove_redundant_gm_roundtrip
real double-buffer rewrite
real CV pipeline overlap
real tiling loop rewrite
```

这些仍保留在 Python fallback 或后续 Phase 3/4 中推进。

---

## 5. Demo 结果

Demo 命令：

```bash
python -m strategy_search.cli \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --enable-ir-rewrite \
  --rewrite-mode both \
  --rewrite-safety balanced \
  --enable-structural-rewrite \
  --structural-rewrite-safety balanced \
  --structural-rewrite-backend vtriton \
  --vtriton-strategy-rewriter build_phase2c/hivm-strategy-rewrite \
  --output-dir /mnt/data/phase2c_demo
```

结果：

```json
{
  "changes_summary_source": "external_vtriton_strategy_rewriter",
  "changes_summary": {
    "total_changes": 2,
    "change_counts": {
      "replace_barrier_all_with_directional_sync": 2
    }
  },
  "python_fallback_planned_changes_summary": {
    "total_changes": 4,
    "change_counts": {
      "replace_barrier_all_with_directional_sync": 2,
      "insert_sync_before_first_vector_op": 1,
      "hoist_invariant_q_load_from_simple_loop": 1
    }
  }
}
```

解释：

- 外部 C++ bridge 实际完成 2 个 barrier rewrite。
- Python fallback 原本还能做 CV sync insertion 和 Q-load hoist，但这些没有被 C++ bridge 宣称完成。
- 这保证了报告诚实，不混淆“计划能力”和“外部后端实际能力”。

---

## 6. 测试结果

新增测试：

```text
tests/test_vtriton_adapter_phase2c.py
```

完整测试：

```text
62 passed
```

测试覆盖：

1. C++ bridge 可以用 `g++ -std=c++17` 编译。
2. C++ bridge 可以读取 `structural_edit_script.json`。
3. C++ bridge 可以把 `barrier {mode="ALL"}` 改成 `set_flag/wait_flag`。
4. Python `try_run_external_strategy_rewriter()` 可以正确调用该 C++ bridge。
5. 外部 report 可以记录实际 changes。

---

## 7. 当前边界

Phase 2C 已经比 Phase 2B 更进一步，因为它不再只是 scaffold，而是存在一个可执行 C++ backend bridge。

但它仍然不是最终生产 compiler pass，原因是：

1. 当前 bridge 为 standalone text-anchor bridge，不是 MLIR `Operation*` 级 mutation。
2. 生产版本仍需迁移到 vTriton/HivmOpsEditor 或 MLIR PatternRewriter/RewriterBase。
3. 改写后仍需 target HIVM parser / tritonsim-hivm / DES / trace 验证。
4. 当前只支持 barrier rewrite，不支持复杂 dataflow/schedule rewrite。

---

## 8. 下一步建议

Phase 2D / Phase 3 建议推进：

```text
1. 将 insert_sync_before_first_vector_op 搬进 C++ bridge。
2. 为 C++ bridge 增加更明确的 edit-script parser。
3. 增加 pre/post op count comparison 到 C++ report。
4. 接入 tritonsim-hivm validation wrapper。
5. 开始建设真正 dependency graph / buffer live-range checker。
```

其中最自然的下一步是：

```text
C++ backend 支持 insert_sync_before_first_vector_op
```

它和 CVPipelinePlan 直接相关，且比 Q-load hoist / double-buffer / tiling loop 风险更低。


---

## HIVM_REWRITE_PHASE2D_PROGRESS_REPORT.md

# HIVM Rewrite Phase-2D Progress Report

## 1. 本阶段目标

Phase-2D 的目标是继续把 structural rewrite 从 Python fallback 推进到可执行的 C++/vTriton-style backend。Phase-2C 已经支持 `replace_barrier_all_with_directional_sync`，本阶段新增第二个 C++ backend structural edit：

```text
insert_sync_before_first_vector_op
```

因此当前 C++ bridge 已经可以真实修改 HIVM operation sequence 中的两类同步结构：

```text
1. coarse barrier / PIPE_ALL -> directional set_flag + wait_flag
2. cube/fixpipe -> vector 边界前插入 directional set_flag + wait_flag
```

## 2. 官方工程原则

本阶段仍然遵循官方 MLIR rewrite 工程原则：

```text
1. 真实 IR mutation 应该最终通过 PatternRewriter/RewriterBase 或等价 pass-owned API 执行；
2. 每个 rewrite 应有明确 pattern anchor 和 legality contract；
3. 不能把 Python 字符串替换作为长期 compiler pass；
4. 当前 standalone C++ bridge 是可执行工程边界，不是最终生产级 MLIR pass。
```

因此这版没有扩大到 full CV pipeline overlap，也没有做 event reuse、loop reorder 或 double-buffer lowering。

## 3. 新增能力

### 3.1 Barrier replacement

将：

```mlir
hivm.hir.barrier {mode = "ALL"}
```

替换为：

```mlir
hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_M>, <EVENT_IDk>]
hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_M>, <EVENT_IDk>]
```

### 3.2 CV boundary sync insertion

当 edit script 启用：

```text
insert_sync_before_first_vector_op
```

并且 IR 中存在：

```text
cube/fixpipe anchor
  ...
vector op
```

C++ bridge 会在 vector op 前插入：

```mlir
hivm.hir.set_flag[<PIPE_FIX>, <PIPE_V>, <EVENT_IDk>]
hivm.hir.wait_flag[<PIPE_FIX>, <PIPE_V>, <EVENT_IDk>]
```

这是真实 op sequence 修改，不是 attribute/hint。

## 4. 新增/修改文件

```text
vtriton_adapter/hivm_strategy_rewrite.cpp
vtriton_adapter/README.md
vtriton_adapter/CMakeLists.txt
tests/test_vtriton_adapter_phase2d.py
HIVM_REWRITE_PHASE2D_PROGRESS_REPORT.md
```

## 5. 使用方式

编译 C++ bridge：

```bash
mkdir -p build_phase2d
g++ -std=c++17 vtriton_adapter/hivm_strategy_rewrite.cpp -o build_phase2d/hivm-strategy-rewrite
```

通过 Python CLI 调用：

```bash
python -m strategy_search.cli \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --enable-ir-rewrite \
  --rewrite-mode both \
  --rewrite-safety balanced \
  --enable-structural-rewrite \
  --structural-rewrite-safety balanced \
  --structural-rewrite-backend vtriton \
  --vtriton-strategy-rewriter build_phase2d/hivm-strategy-rewrite \
  --output-dir output_phase2d_demo
```

## 6. 当前边界

当前已经完成：

```text
1. C++ bridge 可编译、可执行；
2. C++ bridge 可读取 structural_edit_script.json；
3. C++ bridge 可执行 barrier replacement；
4. C++ bridge 可执行 CV boundary sync insertion；
5. report 中记录实际 external backend changes；
6. Python fallback 仍保留为 CI 和无 C++ backend 环境下的兜底。
```

当前仍未完成：

```text
1. 还不是 MLIR Operation* / HivmOpsEditor 级 mutation；
2. 还没有 dependency graph legality checker；
3. 还没有 buffer live-range checker；
4. 还没有 remove_redundant_gm_roundtrip 的 GM base checker；
5. 还没有 real double-buffer rewrite；
6. 还没有 full CV overlap schedule；
7. 还没有 real tiling loop lowering。
```

## 7. 下一阶段建议

Phase-2E 建议优先推进：

```text
remove_adjacent_duplicate_sync_pairs
```

或者：

```text
remove_redundant_gm_roundtrip + GM base / dependency legality checker
```

其中 `remove_redundant_gm_roundtrip` 更有性能意义，但必须先补 GM load/store dependency checker，不能直接按文本删除。


---

## HIVM_REWRITE_PHASE2E_PROGRESS_REPORT.md

# HIVM Rewrite Phase-2E Progress Report

## 1. 本阶段目标

Phase-2E 的目标不是扩大高风险 IR mutation，而是把 `remove_redundant_gm_roundtrip` 推进到工程化预检阶段：

```text
structural_edit_script.json
  -> GM round-trip candidate detection
  -> legality/deferred report
  -> C++ bridge precheck-only report
```

这遵守官方 MLIR rewrite 工程原则：真实 IR mutation 应由目标 dialect parser 下的 PatternRewriter/RewriterBase、HivmOpsEditor 或等价 operation-level backend 执行；删除数据搬运 op 之前必须先有 legality proof，而不是文本命中后直接 erase。

## 2. 已完成内容

### 2.1 Python 侧 edit script 标准化增强

`strategy_search/structural_rewrite.py` 现在会在满足 DMA/DoubleBuffer 相关策略时，把下面 edit 作为一等公民写入 `structural_edit_script.json`：

```json
{
  "type": "remove_redundant_gm_roundtrip",
  "enabled": true,
  "anchor": {
    "kind": "nearby_store_load_pair",
    "pattern": "UB/L1 store -> same GM, then same GM load -> UB/L1"
  },
  "legality": {
    "status_before_backend": "deferred_until_target_alias_dependency_check"
  }
}
```

注意：该 edit 当前是 **request + precheck**，不是删除许可。

### 2.2 GM round-trip legality precheck

`strategy_search/structural_legality.py` 新增了保守 GM round-trip 检测：

```text
UB/L1/CBUF -> GM store
nearby same-GM load -> UB/L1/CBUF
中间没有明显 compute/store 阻断
```

输出到：

```text
structural_legality_report.json
```

新增字段包括：

```text
anchor_analysis.op_counts.gm_roundtrip_candidate
anchor_analysis.anchors.gm_roundtrip_candidates
```

每个 candidate 都明确记录：

```text
delete_permission = false
reason = requires alias/dependency proof before deletion
```

### 2.3 C++ bridge 增强

`vtriton_adapter/hivm_strategy_rewrite.cpp` 升级为 Phase-2E bridge：

已支持真实 mutation：

```text
replace_barrier_all_with_directional_sync
insert_sync_before_first_vector_op
```

新增 precheck-only：

```text
remove_redundant_gm_roundtrip
```

C++ bridge 会扫描 same-GM store/load candidate，并在 report 的 `skipped` 里标注 deferred，不会删除 load/store。

## 3. Demo 结果

命令：

```bash
python -m strategy_search.cli \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --enable-ir-rewrite \
  --rewrite-mode both \
  --rewrite-safety balanced \
  --enable-structural-rewrite \
  --structural-rewrite-safety balanced \
  --structural-rewrite-backend vtriton \
  --vtriton-strategy-rewriter build_phase2e/hivm-strategy-rewrite \
  --output-dir output_phase2e_demo
```

C++ external backend 结果：

```json
{
  "bridge_phase": "Phase-2E",
  "applied_changes": 3,
  "change_counts": {
    "replace_barrier_all_with_directional_sync": 2,
    "insert_sync_before_first_vector_op": 1
  },
  "skipped": [
    "remove_redundant_gm_roundtrip: no conservative same-GM store->load candidate found"
  ]
}
```

Legality precheck 结果：

```json
{
  "total_edits": 5,
  "local_precheck_passed": 3,
  "local_precheck_failed_or_deferred": 2,
  "production_backend_required": true
}
```

## 4. 测试结果

新增测试：

```text
tests/test_structural_legality_phase2e.py
```

完整测试：

```text
65 passed
```

## 5. 当前边界

Phase-2E 仍不做：

```text
不删除 GM load/store
不做 alias analysis
不做 full dependency graph
不做 buffer live-range proof
不做 real double-buffer / real CV overlap / real tiling lowering
```

这不是退缩，而是正确边界：GM round-trip 删除属于 erase data-movement op，必须等目标 parser/alias/dependency checker 证明后才能真正执行。

## 6. 第二阶段剩余子阶段建议

当前 Phase 2 已完成：

```text
2A backend boundary
2B legality precheck
2C C++ bridge: barrier rewrite
2D C++ bridge: CV boundary sync insertion
2E GM round-trip candidate precheck/deferred report
```

建议还剩 3 个子阶段：

```text
2F vTriton validation wrapper 加强：自动 compare original/optimized op count、sync count、GM count
2G C++ bridge 接入 MLIR/vTriton/HivmOpsEditor 真 parser 的最小版本，不再只是 standalone bridge
2H Phase-2 closure：统一文档、CLI、报告，把 Phase 2 定义为正式 operation-level rewrite bridge 闭环
```

Phase 2 完成标准：

```text
Python search -> structural_edit_script.json -> C++/vTriton backend -> optimized.structural.hivm.mlir -> validation report
```

其中 C++ backend 至少稳定支持：

```text
barrier_all -> directional sync
CV boundary sync insertion
GM round-trip candidate detection with deletion deferred
```

真正 GM deletion、double buffer、CV overlap 和 tiling lowering 应进入 Phase 3/4/5，而不是继续塞进 Phase 2。


---

## HIVM_REWRITE_PHASE2F_PROGRESS_REPORT.md

# HIVM Rewrite Phase-2F Progress Report: Structural Validation Summary

## 1. 本阶段目标

Phase-2E 已经把 GM round-trip 删除收敛为 candidate detection + deferred legality proof，并且 C++ bridge 已经支持两类真实 op sequence mutation：

1. `replace_barrier_all_with_directional_sync`
2. `insert_sync_before_first_vector_op`

Phase-2F 的目标不是继续扩大 rewrite 类型，而是补齐 **validation wrapper**：每次生成 `optimized.structural.hivm.mlir` 后，自动比较原始 IR 与优化 IR 的结构性 op 计数，并把“后端声称改了什么”和“实际输出 IR 体现了什么”对齐起来。

这符合官方 MLIR rewrite 工程原则：rewrite 应先 match 成功，再通过受控 rewriter/backend 执行 IR mutation，并且所有 mutation 都应可被 driver/backend 追踪和验证；本项目当前用 lightweight validation summary 做 CI/审计兜底，生产级仍需目标 MLIR/vTriton parser 验证。

## 2. 新增能力

新增函数：

```text
strategy_search.structural_rewrite.build_structural_validation_summary
```

新增输出：

```text
structural_validation_summary.json
```

该文件会记录：

```text
op_counts_before
op_counts_after
op_count_delta
claimed_change_counts
evidence_checks
local_legality_summary
tritonsim_validation_status
errors / warnings
```

## 3. 当前 validation 检查项

当前 Phase-2F 会检查：

1. `optimized.structural.hivm.mlir` 是否为空；
2. 如果 report 声称有 changes，输出 IR 是否真的和输入不同；
3. brace count 是否明显不平衡；
4. barrier rewrite 是否带来 `barrier_all` 下降；
5. barrier rewrite / CV sync insertion 是否带来 `set_flag` / `wait_flag` 上升；
6. Q-load hoist 是否异常改变 load/store 数量；
7. 如果没有批准 GM round-trip 删除，却出现 GM load/store 数下降，则给出 warning。

## 4. 当前边界

`structural_validation_summary.json` 不是 correctness proof。它不能证明：

```text
HIVM dialect parse success
dependency legality
buffer live range legality
event live range correctness
numerical correctness
real hardware speedup
```

它的定位是：

```text
轻量级 CI/audit gate，用于检查实际输出 IR 是否反映了 rewrite report 声称的局部结构变化。
```

## 5. Phase 2 当前完成度

已完成：

```text
Phase 2A: backend boundary
Phase 2B: legality precheck
Phase 2C: C++ bridge barrier rewrite
Phase 2D: C++ bridge CV boundary sync insertion
Phase 2E: GM round-trip precheck / deferred deletion
Phase 2F: structural validation summary
```

建议剩余：

```text
Phase 2G: vTriton/HivmOpsEditor parser adapter interface hardening
Phase 2H: Phase-2 closure / docs / CLI semantic cleanup
```

Phase 2 完成后，不应继续把 real double-buffer、full CV overlap、real tiling lowering 塞进 Phase 2；这些应进入 Phase 3+，因为需要 dependency graph、buffer liveness、event liveness 和 target parser proof。


---

## HIVM_REWRITE_PHASE2G_PROGRESS_REPORT.md

# HIVM Rewrite Phase-2G Progress Report

## Phase name

**Phase-2G: vTriton / HivmOpsEditor parser adapter interface hardening**

## Goal

Phase-2G does not add new optimization rewrites.  Its goal is to harden the boundary between the Python strategy-search pipeline and a future production vTriton/HivmOpsEditor or MLIR PatternRewriter backend.

Previous Phase-2 versions could call a standalone C++ strict bridge, but the interface was still implicit: the Python side could run a binary, yet it could not ask what the binary supports or record a stable backend contract.  Phase-2G adds that handshake.

## What changed

### 1. C++ bridge capability handshake

`vtriton_adapter/hivm_strategy_rewrite.cpp` now supports:

```bash
hivm-strategy-rewrite --print-capabilities
```

It returns JSON containing:

```text
schema_version
backend_mode
bridge_phase
interface_version
supported_edits
mutation_edits
precheck_only_edits
required_cli
production_target
```

Current reported phase:

```text
Phase-2G
```

Current supported edits:

```text
replace_barrier_all_with_directional_sync
insert_sync_before_first_vector_op
remove_redundant_gm_roundtrip
```

Only the first two perform mutation.  `remove_redundant_gm_roundtrip` remains precheck-only.

### 2. Python adapter manifest

The Python pipeline now emits:

```text
vtriton_adapter_manifest.json
```

This manifest records:

```text
backend execution plan
external strategy rewriter capabilities
requested enabled edit types
coverage by edit type
missing required edits
binary sha256 identity
required CLI contract
required report schema fields
runtime guards for production backends
```

This makes the backend boundary auditable instead of implicit.

### 3. Backend coverage check

If an external `hivm-strategy-rewrite` binary is provided, the Python side queries its capabilities and compares them against the requested edit script.

If no external backend is available, coverage is recorded as `null`, meaning fallback/runtime selection decides.

### 4. Tests

Added:

```text
tests/test_vtriton_adapter_phase2g.py
```

The tests cover:

```text
C++ bridge compilation
--print-capabilities JSON output
manifest generation with external backend
manifest generation without external backend
coverage and binary identity recording
```

## Why this matters

This phase is a bridge-quality improvement.  It does not claim additional performance improvement.  It ensures that the project has a stable contract before replacing the standalone bridge with a real vTriton/HivmOpsEditor backend.

The required production direction remains:

```text
MLIR / vTriton parser
  → HivmOpsEditor or PatternRewriter/RewriterBase operation mutation
  → target dialect verification
  → DES / trace / msprof validation
```

## Current Phase-2 status

Completed:

```text
Phase 2A: backend boundary
Phase 2B: legality precheck
Phase 2C: C++ bridge barrier rewrite
Phase 2D: C++ bridge CV boundary sync insertion
Phase 2E: GM round-trip precheck / deferred deletion
Phase 2F: structural validation summary
Phase 2G: adapter manifest and capability handshake
```

Remaining:

```text
Phase 2H: Phase-2 closure, README/CLI/report semantics cleanup, final Phase-2 status matrix
```

After Phase-2H, real double-buffer, full CV overlap, GM round-trip deletion, and real tiling lowering should move to Phase 3+.


---

## HIVM_REWRITE_PHASE2H_CLOSURE_REPORT.md

# V3.3.2 Phase-2H Closure Report

本阶段完成 Phase 2 收口，新增 `phase2_closure_report.json`，并补充 `PHASE2_CLOSURE_AND_PHASE3_PLAN.md`。

## 完成内容

1. 新增 `build_phase2_closure_report()`。
2. CLI 在开启 `--enable-structural-rewrite` 后自动输出 `phase2_closure_report.json`。
3. 报告中记录 Phase 2A-2H 状态矩阵。
4. 报告中记录 C++ backend mutation / precheck / deferred / out-of-scope 的边界。
5. 报告中给出 Phase 3A-3E 的任务、交付物和困难。

## Phase 2 当前结论

Phase 2 已完成 operation-level rewrite bridge 闭环：

```text
Python strategy search
  -> structural_edit_script.json
  -> C++/vTriton rewrite backend boundary
  -> optimized.structural.hivm.mlir
  -> validation / legality / manifest / closure reports
```

Phase 2 不再继续扩展 real double-buffer、full CV overlap 或 real tiling lowering，这些进入 Phase 3+。

## Phase 3 入口

下一阶段建议从 `Phase 3A: dependency graph and event liveness foundation` 开始。


---

## HIVM_REWRITE_PHASE3A_PROGRESS_REPORT.md

# HIVM Rewrite Phase-3A Progress Report

## 本阶段目标

Phase 3A 的目标不是继续扩大 IR rewrite 类型，而是建立后续危险结构改写所需的正确性基础：HIVM op inventory、保守 dependency graph 和 event liveness report。

Phase 2 已经完成了 C++ bridge 层面的两个真实 mutation：

1. `replace_barrier_all_with_directional_sync`
2. `insert_sync_before_first_vector_op`

但 Phase 3 开始，如果要继续做 GM round-trip 删除、Q-load hoist、real double-buffer、full CV overlap 或 real tiling lowering，就必须先能回答：哪些 op 依赖哪些 buffer，哪些 event set/wait 成对，哪些 op 语义未知，哪些 rewrite 不能证明安全。

## 新增模块

新增：

```text
strategy_search/phase3_analysis.py
```

新增输出：

```text
hivm_op_semantics_registry.json
hivm_ir_inventory.json
dependency_graph_report.json
event_liveness_report.json
phase3a_analysis_summary.json
```

## 当前实现内容

### 1. HIVM op semantics registry

内置轻量 HIVM op 语义表，包括常见：

```text
load / store / nd2nz / nz2nd / mmad / mmadL1 / fixpipe / vector / set_flag / wait_flag / barrier
```

每个 op 会标注 role、pipe、memory effect、读写 memory space。未知 op 默认作为 rewrite blocker，不能用于危险 rewrite。

### 2. HIVM op inventory

对输入/改写后的 HIVM IR 生成 op inventory，记录：

```text
op_id
line
op_name
role
pipe
known_semantics
region_depth
parent_loop
inputs / outputs
event info
barrier_all flag
```

当前实现是 conservative line scanner，后续应替换为 vTriton/HivmOpsEditor 或 MLIR Operation walk。

### 3. Conservative dependency graph v1

当前支持三类依赖边：

```text
memory_raw / memory_waw / memory_war
event_set_wait / event_redefinition / wait_without_visible_set
coarse_barrier_order
```

这个图不是完整 correctness proof，但已经可以作为 Phase 3B/3C 的证据基础。

### 4. Event liveness report

对每个 event id 记录 set/wait pair、live range、pipe pair 是否匹配、是否存在 unpaired wait、重复 set 或未关闭 set。

## 当前边界

Phase 3A 不做：

```text
GM round-trip deletion
event reuse
sync motion
real double-buffer
full CV overlap
real tiling lowering
```

这些仍然被锁定，需要 Phase 3B/3C 的 buffer liveness、GM alias 和 MemorySSA-like checker 后才能推进。

## 下一步

建议进入 Phase 3B：

```text
Buffer liveness + GM alias checker
```

需要新增：

```text
buffer_liveness_report.json
gm_alias_report.json
capacity_recheck_report.json
```

这一步会直接服务于 safe GM round-trip deletion 和 proof-based Q-load hoist。


---

## HIVM_REWRITE_PHASE3B_PROGRESS_REPORT.md

# HIVM Rewrite Phase-3B Progress Report

## 1. 本阶段定位

Phase-3B 的目标是补齐 **memory correctness evidence**，也就是在继续推进 GM 删除、Q-load hoist、real double-buffer、full CV overlap 之前，先回答三个基础问题：

1. 每个 buffer 在 IR 中什么时候被读、什么时候被写？
2. 局部 buffer 的保守峰值占用是否已经超过 UB/L1/L0C 等硬件边界？
3. GM load/store 是否可能构成可删除的 round-trip？如果有，是否已经具备删除证明？

本阶段仍然 **不新增危险 mutation**。它只生成证据报告，不解锁 GM 删除、Q-load hoist、double-buffer 或 CV overlap。

## 2. 新增模块

新增/扩展：

```text
strategy_search/phase3_analysis.py
```

新增 Phase-3B 输出：

```text
buffer_liveness_report.json
capacity_recheck_report.json
gm_alias_report.json
phase3b_analysis_summary.json
```

这些报告会在开启：

```bash
--enable-structural-rewrite
```

后自动生成。

## 3. buffer_liveness_report.json

该报告会收集：

```text
buffer var
address space: gm / ub / l1 / l0c / ...
static shape / dtype / size_bytes
declaration kind: alloc / boundary_or_operand / implicit_operand
first_use_line / last_use_line
read_count / write_count
loop_lines_touched
buffer_role
```

其中 `buffer_role` 会做保守分类：

```text
stream_buffer
softmax_or_score_buffer
accumulator
output
gm_input_or_boundary
gm_output_or_boundary
unknown_local_buffer
```

重要边界：accumulator、output、GM output/boundary buffer 默认是 rewrite blocker，不能被 hoist 或 double-buffer，除非后续有更强证明。

## 4. capacity_recheck_report.json

该报告会按 memory space 做保守容量检查：

```text
UB conservative_peak_bytes
L1 conservative_peak_bytes
L0C conservative_peak_bytes
```

当前策略是 **conservative sum of static local allocations**，也就是把所有静态局部 buffer 都当作可能同时存活。这会高估 peak bytes，但作为安全 gate 是合理的：如果保守上界都已经超限，就不能继续做 lifetime-extending rewrite。

默认容量来自 Ascend 910B 项目配置：

```text
UB: 256 KB
L1/CBUF: 1024 KB
L0A/L0B: 64 KB
L0C/CC: 256 KB
```

后续接入正式 vTriton/HivmOpsEditor 后，应由目标硬件 JSON 和真实 buffer lifetime 替代该保守估计。

## 5. gm_alias_report.json

该报告会收集 GM access：

```text
gm_var
access: read / write
op_id / line / op_name / role
parent_loop
```

并尝试发现保守的 GM round-trip candidate：

```text
store GM -> later load same GM
```

但当前仍然设置：

```json
"deletion_unlocked": false
```

原因是 Phase-3B 只能证明 textual same GM var，不能证明：

```text
same static offset/slice
no intervening MemoryDef/Use/Phi
no unknown GM side effect
not observable output/boundary behavior
```

所以 GM 删除仍然 deferred 到 Phase-3C。

## 6. Demo 结果

在 `fa_bad_inefficient.hivm.mlir` 上，Phase-3B demo 结果为：

```json
{
  "buffer_count": 17,
  "local_buffer_count": 13,
  "gm_buffer_count": 4,
  "capacity_recheck": {
    "passed_conservative_capacity_recheck": true,
    "peak_by_space": {
      "ub": {"conservative_peak_bytes": 98816, "utilization": 0.376953},
      "l1": {"conservative_peak_bytes": 32768, "utilization": 0.03125},
      "l0c": {"conservative_peak_bytes": 8192, "utilization": 0.03125}
    }
  },
  "gm_alias": {
    "gm_access_count": 4,
    "gm_roundtrip_candidate_count": 0,
    "deletion_unlocked": false
  }
}
```

解释：

1. 当前样例的保守 UB 峰值约 96.5 KB，低于 256 KB 默认限制。
2. L1 和 L0C 峰值也低于默认限制。
3. 当前优化后的 structural IR 中没有发现可疑 same-GM store→load round-trip，因此不会触发 GM 删除。
4. 即使未来发现 candidate，也必须等 Phase-3C 的 MemorySSA-like gate 才能删除。

## 7. 当前未解锁的 rewrite

Phase-3B 后仍然不允许：

```text
GM round-trip deletion
Q-load hoist with proof
real double-buffer ping-pong
real CV pipeline overlap
real tiling loop lowering
```

这些仍然依赖后续：

```text
Phase-3C: GM MemorySSA-like checker
Phase-3D: loop-invariant hoist proof
Phase-3E: tritonsim-hivm DES/trace validation
```

## 8. 工程意义

Phase-3A 解决的是“op 与依赖关系”；Phase-3B 解决的是“buffer 和 GM memory correctness 证据”。

现在项目已经具备：

```text
HIVM op inventory
  -> dependency graph
  -> event liveness
  -> buffer liveness
  -> capacity recheck
  -> GM alias precheck
```

这为后续真正删除 GM traffic、做 Q-load hoist、real double-buffer 和 full CV overlap 奠定了安全基础。


---

## HIVM_REWRITE_PHASE3C_PROGRESS_REPORT.md

# HIVM Rewrite Phase-3C Progress Report

## 目标

Phase-3C 的目标是补上 GM round-trip 删除前的 MemorySSA-like 合法性判断。它不直接扩大 rewrite 类型，而是回答：某个 `store GM -> load same GM` candidate 是否真的可以删除。

## 新增产物

- `gm_memory_ssa_report.json`：记录 GM MemoryDef / MemoryUse、unique reaching-def、unknown side-effect 和 observable boundary 阻断信息。
- `gm_roundtrip_deletion_decision.json`：对每个 GM round-trip candidate 给出 delete_permission。
- `rewrite_legality_gate_report.json`：统一汇总危险 rewrite 的 gate 状态。
- `phase3c_analysis_summary.json`：Phase-3C 总结。

## 当前原则

```text
cannot prove safe -> do not rewrite
```

即使 same textual GM var 成立，也不能直接删除。还需要 target parser / index analysis 证明 same static offset / slice，并确认中间无 unknown side effect，且该 GM 写入不是 observable boundary 行为。

## 当前解锁状态

- barrier/CV boundary sync 的本地 audit 可以继续保留。
- GM round-trip deletion 只有在所有 gate 通过时才允许；当前大多数真实输入仍会 deferred。
- Q-load hoist、real double-buffer、real CV overlap、real tiling 仍然 locked。

## Phase 3 子阶段规划

Phase 3 建议固定为 6 个子阶段：

1. Phase 3A：HIVM op inventory + dependency graph + event liveness。
2. Phase 3B：buffer liveness + GM alias + capacity recheck。
3. Phase 3C：GM MemorySSA-like checker + deletion decision gate。
4. Phase 3D：loop-invariant load hoist proof。
5. Phase 3E：tritonsim-hivm DES / trace validation wrapper。
6. Phase 3F：Phase-3 closure and Phase-4 handoff。

Phase 4 之后再推进 real double-buffer、full CV overlap 和 real tiling lowering。


---

## HIVM_REWRITE_PHASE3D_PROGRESS_REPORT.md

# HIVM Rewrite Phase-3D Progress Report

## 阶段定位

Phase-3D 的目标是建立 **loop-invariant load hoist proof gate**，尤其服务于 FA/Prefill 场景中常见的 Q-load hoist：

```text
for KV block:
    load Q -> q_ub
    nd2nz Q -> q_l1
    load K/V
    compute
```

如果 Q 的 GM 访问不依赖 KV loop 的 induction variable，并且 q_ub/q_l1 在 loop 内没有被覆盖，就可以成为未来 hoist 的候选：

```text
load Q -> q_ub
nd2nz Q -> q_l1
for KV block:
    load K/V
    compute
```

但 Phase-3D **不默认执行真实 hoist mutation**。它只输出候选、局部证明、缺失 gate 和后续 vTriton/HivmOpsEditor 需要确认的内容。

## 新增输出

开启 `--enable-structural-rewrite` 后新增：

```text
loop_invariant_load_hoist_report.json
q_load_hoist_decision.json
phase3d_analysis_summary.json
```

## 证明 gate

每个 hoist candidate 会检查：

```text
1. 是否在 loop 内；
2. 是否是 Q/stream-like GM -> local load；
3. load 文本是否不引用 visible loop induction variable；
4. destination buffer 在同一 loop 内是否存在其他 writer；
5. local event liveness 是否通过；
6. hoist 后 conservative capacity recheck 是否仍通过；
7. target parser 是否确认 region motion / dominance / exact lifetime。
```

其中第 7 项当前固定为 `false`，因为 standalone line scanner 不能证明 MLIR region motion 合法性。生产级 hoist 必须由 vTriton/HivmOpsEditor 或 MLIR Operation walk 确认。

## Demo 结果

使用 C++ bridge 模式运行 `sample_input/fa_bad_inefficient.hivm.mlir` 后，Phase-3D 找到 1 个 Q-load hoist candidate：

```json
{
  "candidate_count": 1,
  "local_proof_passed_count": 1,
  "hoist_allowed_count": 0,
  "hoist_unlocked": false
}
```

解释：

```text
局部证据显示：该 Q-load 看起来不依赖 KV loop induction variable，且 destination buffer 没有同 loop 覆盖，event/capacity gate 也通过。
但由于缺少 target parser 的 region-motion proof，所以 production mutation 仍然 deferred。
```

如果使用 Python fallback backend，Q-load 可能已经被 fallback 原型 hoist 到 loop 外，因此 Phase-3D 会看到 0 个剩余候选。这说明 Phase-3D 分析的是最终 `optimized.structural.hivm.mlir`，不是原始 IR。

## 当前边界

Phase-3D 仍然不解锁：

```text
real Q-load hoist production mutation
GM round-trip deletion
real double-buffer ping-pong
full CV overlap
real tiling loop lowering
```

Phase-3D 的贡献是：把 Q-load hoist 从“Python fallback 觉得可以移动”推进到“有可审计 gate 的候选决策”。

## 下一阶段

Phase-3E：tritonsim-hivm DES / trace validation wrapper。

目标是对 original / optimized IR 分别调用 vTriton 的 `tritonsim-hivm`，导出 DES / trace 或至少捕获分析结果，并生成对比报告。


---

## HIVM_REWRITE_PHASE3E_PROGRESS_REPORT.md

# HIVM Rewrite Phase-3E Progress Report

## 阶段定位

Phase-3E 的目标是建立 `tritonsim-hivm` / vTriton DES / Perfetto trace 的验证 wrapper。它不是新的 rewrite pass，也不解锁危险 mutation。它的作用是把 Phase 2/3 产生的 `optimized.structural.hivm.mlir` 放到外部建模/仿真框架中检查：能否解析、能否输出 DES graph、能否输出 trace，以及改写前后的结构差异是否可审计。

## 新增输出

开启 `--enable-structural-rewrite` 后新增：

- `vtriton_des_trace_validation_report.json`
- `phase3e_analysis_summary.json`
- `trace_comparison_report.html`

如果传入 `--run-vtriton-validation --tritonsim-hivm <binary>`，系统会尝试分别对 structural input IR 和 optimized structural IR 调用 `tritonsim-hivm`，并请求生成：

- `original_des_graph.json`
- `optimized_des_graph.json`
- `original_perfetto_trace.json`
- `optimized_perfetto_trace.json`

如果 binary 不存在或本地 vTriton build 不支持当前 flag，报告会保留 stdout/stderr、return code 和 pending reason。

## 当前能力

- 可以自动生成 Phase-3E validation wrapper 报告。
- 可以在没有 vTriton binary 的环境中稳定给出 pending 状态。
- 可以在有 binary 的环境中尝试生成 DES/trace artifact。
- 可以生成 HTML 对比报告，方便汇报时查看 original / optimized 的 validation 状态。
- 可以比较 original / optimized 的本地 op inventory 和 dependency graph 摘要。

## 当前边界

Phase-3E 不证明：

- 数值正确性；
- 目标编译器 verifier 通过；
- 真机 msprof 加速；
- GM round-trip deletion 可以执行；
- Q-load hoist 可以 production mutation；
- real double-buffer / full CV overlap / real tiling lowering 可以解锁。

## 下一步

Phase-3F 应该收口 Phase 3，生成最终 closure report，并判断哪些候选可以进入 Phase 4 的 mutation prototype。Phase 4 才适合考虑 GM 删除、Q-load hoist production、real double-buffer 或 CV overlap 等更危险改写。


---

## HIVM_REWRITE_PHASE3F_CLOSURE_REPORT.md

# HIVM Rewrite Phase-3F Closure Report

## 本阶段定位

Phase-3F 是 Phase 3 的收口阶段。它不新增新的 HIVM mutation，也不默认开启 GM 删除、Q-load hoist、real double-buffer、full CV overlap 或 tiling lowering。它的目标是把 Phase-3A 到 Phase-3E 产生的分析证据汇总成统一的 closure report，并给出 Phase 4 的候选方向、进入条件和 remaining blockers。

## 新增输出

开启 `--enable-structural-rewrite` 后会额外生成：

```text
phase3_closure_report.json
phase3f_analysis_summary.json
```

其中 `phase3_closure_report.json` 记录：

```text
1. Phase 3 evidence matrix
2. rewrite gate status
3. Phase 4 candidate status
4. remaining blockers
5. Phase 4 recommended plan
6. default mutation policy
```

`phase3f_analysis_summary.json` 是 compact summary，方便 CI 或报告读取。

## Phase 3 收口结论

Phase 3 已经完成的是 correctness foundation：

```text
Phase 3A: HIVM op inventory + dependency graph + event liveness
Phase 3B: buffer liveness + GM alias + capacity recheck
Phase 3C: GM MemorySSA-like checker + deletion decision gate
Phase 3D: loop-invariant load hoist proof gate
Phase 3E: tritonsim-hivm DES / trace validation wrapper
Phase 3F: closure + Phase-4 handoff
```

Phase 3 没有默认解锁危险 mutation。当前原则仍然是：

```text
cannot prove safe -> do not rewrite
```

## Phase 4 handoff

Phase 4 建议从 target parser / HivmOpsEditor integration 开始，而不是马上做完整 double-buffer 或 tiling lowering。

推荐顺序：

```text
Phase-4A: target parser / HivmOpsEditor integration hardening
Phase-4B: guarded Q-load hoist prototype
Phase-4C: limited GM round-trip deletion prototype
Phase-4D: CV stage graph and overlap prototype planning
Phase-4E: validation closure with DES/trace/msprof
```

## 仍然 locked 的能力

以下能力仍然 locked，除非后续通过 target parser、DES/trace、alias/liveness 和 msprof 验证：

```text
real GM round-trip deletion
real double-buffer ping-pong
full CV pipeline overlap
real tiling loop lowering
event reuse / sync motion
```

## 工程意义

Phase-3F 让项目从“分析报告很多”收束成“下一阶段能怎么推进”的清晰状态矩阵。它明确告诉使用者：哪些证据已经具备，哪些 rewrite 可以进入 Phase 4 prototype，哪些仍然不能动。


---

## HIVM_REWRITE_PHASE4A_PROGRESS_REPORT.md

# HIVM Rewrite Phase 4A Progress Report

## 当前阶段名称

**Phase 4A: HIVM Rewrite Bridge Hardening / Target Parser Readiness Audit**

这一阶段不再使用“fully vTriton-backed”描述当前版本。当前后端的准确名称是：

> **HIVM Rewrite Bridge**：一个 vTriton-compatible / HivmOpsEditor-oriented 的桥接后端。

它可以生成和执行部分结构改写，但还不是完整的 vTriton/HivmOpsEditor/MLIR Operation-level production backend。

## 本阶段目标

Phase 4A 的目标不是新增危险 rewrite，而是检查当前 bridge 是否具备进入正式 parser / DES / trace 验证链路的条件：

1. 外部 `hivm-strategy-rewrite` 是否存在；
2. 是否支持 `--print-capabilities` 能力握手；
3. 当前 requested edit 是否被 bridge 覆盖；
4. original / optimized IR 是否通过本地轻量 sanity check；
5. `tritonsim-hivm` 或 target parser 是否实际接通；
6. 是否允许进入后续 guarded Q-load hoist / GM deletion prototype。

## 新增交付物

运行 structural rewrite 后新增：

- `target_parser_validation_report.json`
- `phase4a_analysis_summary.json`

这两个文件明确说明当前是否已经接入 target parser。如果没有，它会保持危险 mutation locked，不会假装验证通过。

## 当前边界

Phase 4A 仍然不解锁：

- GM round-trip deletion
- Q-load production hoist
- real double-buffer ping-pong
- full CV pipeline overlap
- real tiling loop lowering

## 下一步

Phase 4B 需要在真实 vTriton / `tritonsim-hivm` 环境中跑通 original / optimized 的 DES graph 和 Perfetto trace 生成。只有 Phase 4B 成功后，才建议进入 guarded mutation prototype。


---

## HIVM_REWRITE_PHASE4B_PROGRESS_REPORT.md

# HIVM Rewrite Phase-4B Progress Report

## 目标

Phase-4B 的目标不是新增危险 IR 改写，而是把外部 DES / trace 验证从“有 wrapper”推进到“有明确执行门槛”。

也就是说，只有当 original 和 optimized 两份 HIVM IR 都能被配置的 `tritonsim-hivm` 接受、返回码为 0，并生成可解析的 DES graph 和 Perfetto trace JSON，系统才认为 DES/trace gate 通过。

## 新增交付物

- `phase4b_des_trace_execution_report.json`
- `phase4b_analysis_summary.json`
- `phase4b_validation_commands.sh`
- `tools/fake_tritonsim_hivm.py`：仅用于 CI/demo，不代表真实 vTriton 性能建模能力。

## 当前边界

Phase-4B 仍然不解锁：

- GM round-trip deletion
- Q-load production hoist
- real double-buffer
- full CVPipeline overlap
- real tiling lowering

原因是 DES/trace 通过只是必要条件，不是充分条件。后续仍需要 target parser、alias/liveness proof 和 msprof 验证。


---

## HIVM_REWRITE_PHASE4C_PROGRESS_REPORT.md

# HIVM Rewrite Phase-4C Progress Report

## Phase name

**Phase-4C: Guarded Q-load Hoist Prototype Gate**

## Goal

Phase-4C promotes Phase-3D loop-invariant Q-load hoist candidates into a guarded backend dry-run worklist.  It does **not** perform unsafe text-level region motion and does **not** enable production Q-load hoist by default.

The goal is to answer one practical engineering question:

> If a Q-load appears loop-invariant, do we have enough evidence to hand it to a future HivmOpsEditor / MLIR Operation-level backend for a dry-run?

## New outputs

When structural rewrite is enabled, the pipeline now emits:

- `phase4c_q_load_hoist_prototype_report.json`
- `phase4c_q_load_hoist_candidate_script.json`
- `phase4c_analysis_summary.json`

## Gate logic

A candidate enters the backend dry-run worklist only if the following gates pass:

1. Phase-3D local proof passed.
2. Phase-4A target parser / bridge gate is clean.
3. Phase-4B DES/trace execution gate passed.
4. Event liveness is locally valid.
5. Conservative buffer capacity recheck passed.

However, production mutation still requires:

- `target_region_motion_proof = true`

This is currently false because the project does not yet have a real HivmOpsEditor / MLIR Operation-level region-motion proof.  Therefore Phase-4C keeps production mutation locked.

## Demo result

Using the C++ HIVM Rewrite Bridge and the fake tritonsim fixture, the demo produced:

```json
{
  "candidate_count": 1,
  "backend_dry_run_ready_count": 1,
  "production_mutation_allowed_count": 0,
  "production_mutation_unlocked": false
}
```

Interpretation:

- One Q-load hoist candidate was found.
- The candidate is ready to be handed to a future backend dry-run.
- It is **not** actually applied yet.
- Production mutation remains blocked because target region-motion proof is missing.

## Why this is intentionally conservative

Moving a load across a loop boundary changes dominance, live range, buffer pressure, and synchronization assumptions.  Doing this with text rewriting is unsafe.  Phase-4C therefore emits a backend candidate script instead of modifying the IR directly.

## Still locked

The following remain locked:

- Production Q-load hoist mutation
- GM round-trip deletion
- Real double-buffer ping-pong
- Full CVPipeline overlap
- Real tiling loop lowering

## Next step

Phase-4D should implement a HivmOpsEditor / MLIR Operation-level dry-run for the candidate worklist, or first integrate a real target parser that can prove region motion and dominance.


---

## HIVM_REWRITE_PHASE4D_PROGRESS_REPORT.md

# HIVM Rewrite Phase-4D Progress Report

## 定位

Phase-4D 是 **official-docs-aligned Operation-level dry-run contract**。它不做新的生产级 IR mutation，也不做 Python 文本级 region motion。

Phase-4C 已经把 Q-load hoist 候选点放入 guarded backend dry-run worklist。Phase-4D 进一步把这个 worklist 转成未来 HivmOpsEditor / MLIR Operation-level backend 可以消费的 dry-run contract，并明确列出必须满足的官方工程约束。

## 为什么要这样做

Q-load hoist 不是简单插入一条同步指令，而是把 load 从 loop 内移动到 loop 外。这个动作会涉及：

- dominance / region ownership；
- buffer live range 延长；
- event liveness；
- MLIR verifier；
- DES/trace 再验证。

因此当前阶段只生成 dry-run 计划，不允许真实移动 op。

## 新增输出

```text
phase4d_operation_rewrite_dry_run_report.json
phase4d_hivmopseditor_dry_run_plan.json
phase4d_official_mlir_compliance_report.json
phase4d_analysis_summary.json
```

## 官方文档对齐原则

Phase-4D 按以下原则约束后续实现：

1. IR mutation 必须交给 rewriter/backend API，不能用 Python 文本替换做 region motion。
2. rewrite 必须有显式 legality / capability gate。
3. operation movement 必须在 Operation-level backend 中做 dominance / region-motion proof。
4. dry-run 输出之后必须重新跑 verifier 和 DES/trace。

## 当前结论

Phase-4D 可以生成 dry-run action 和 future-backend plan，但 production mutation 仍然锁定。

```text
production_mutation_unlocked = false
```

主要 blocker：

```text
operation_level_dominance_and_region_motion_backend_not_connected
```

## 下一步

进入 Phase-4E 时，建议不要立刻做真实 hoist，而是接真实 HivmOpsEditor / MLIR Operation-level backend，先完成：

1. 加载 HIVM module；
2. 将 candidate id 解析到 Operation handle；
3. 做 dominance / region-motion dry-run；
4. 输出 backend verifier report；
5. 再跑 DES/trace。


---

## HIVM_REWRITE_PHASE4E_CLOSURE_REPORT.md

# HIVM Rewrite Phase-4E Closure Report

## 结论

Phase 4E 是 Phase 4 的收口阶段。它不新增危险 IR mutation，而是把 Phase 4A–4D 的结果统一成一个 closure report：

- Phase 4A：HIVM Rewrite Bridge 能力握手与 target parser readiness audit；
- Phase 4B：DES / trace execution gate；
- Phase 4C：guarded Q-load hoist candidate worklist；
- Phase 4D：official-docs-aligned Operation-level dry-run contract；
- Phase 4E：Phase 4 closure + Phase 5 handoff。

当前仍然不允许默认开启：

- production Q-load hoist；
- GM round-trip deletion；
- real double-buffer；
- full CVPipeline overlap；
- real tiling loop lowering。

## 为什么仍然不解锁真实 mutation

Phase 4D 已经把 Q-load hoist candidate 变成了后端 dry-run contract，但还缺最后的正式后端证明：

1. 真实 HivmOpsEditor / MLIR Operation-level backend；
2. dominance / region-motion proof；
3. rewrite 后 MLIR verifier；
4. 真实 tritonsim-hivm DES / trace；
5. 后续 msprof 真机验证。

## 官方文档纪律

Phase 4E 延续 Phase 4D 的官方 MLIR rewrite 纪律：

- IR mutation 必须通过 rewriter/backend API 执行，不能用 Python 文本级 region motion；
- rewrite 必须有明确 legality gate；
- 跨 block/region 的 operation motion 必须在 Operation-level backend 中证明 dominance 和 region semantics。

## 新增交付物

- `phase4_closure_report.json`
- `phase4e_analysis_summary.json`
- `HIVM_REWRITE_PHASE4E_CLOSURE_REPORT.md`
- `PHASE4E_LEADERSHIP_BRIEF.md`

## Phase 5 建议路线

1. Phase-5A：接入真实 HivmOpsEditor / MLIR Operation-level backend；
2. Phase-5B：对 backend-mutated IR 跑 verifier + tritonsim-hivm；
3. Phase-5C：只在简单 pattern 上尝试 guarded Q-load hoist mutation；
4. Phase-5D：只在 exact same-address toy/simple pattern 上尝试 GM round-trip 删除；
5. Phase-5E：决定是否进入 msprof，再考虑 double-buffer / CV overlap。


---

## HIVM_REWRITE_PHASE5A_PROGRESS_REPORT.md

# HIVM Rewrite Phase 5A Progress Report

## 定位

Phase 5A 是从 **HIVM Rewrite Bridge 原型** 走向 **真实 HivmOpsEditor / MLIR Operation-level 后端** 的第一步。

这一步仍然不做生产级 mutation，不移动 loop 内 load，不删除 GM load/store，不做 double-buffer、CV overlap 或 tiling lowering。它做的是：

1. 明确未来正式 Operation-level 后端必须支持哪些能力；
2. 探测当前是否配置了真实后端、`hivm-crud` 或 `mlir-opt`；
3. 生成本地 conservative scanner 的 op inventory baseline；
4. 记录未来 backend inventory 和本地 baseline 应如何对齐；
5. 继续锁住所有高风险 mutation。

## 新增输出

开启 `--enable-structural-rewrite` 后新增：

```text
phase5a_operation_backend_readiness_report.json
phase5a_inventory_alignment_report.json
phase5a_analysis_summary.json
```

## 新增 CLI 参数

```bash
--hivm-operation-backend /path/to/future-operation-backend
--mlir-opt /path/to/mlir-opt
```

这两个参数目前只用于 readiness/capability probe。即使配置了，也不会自动开启 production mutation。

## 官方文档对齐原则

Phase 5A 把未来后端 contract 写成显式要求：

```text
--print-capabilities
--inventory
--roundtrip
--verify-only
--dry-run
```

原因是后续正式改写必须基于 MLIR Operation / Region / Block / Dominance / Verifier，而不能用 Python 文本剪切粘贴跨 region 移动。创建、替换、删除、移动 op 必须交给 rewriter/backend API 处理，并通过 explicit legality gate。

## 当前状态

在没有真实 HivmOpsEditor / MLIR Operation backend 的情况下，Phase 5A 会报告：

```text
backend_status = standalone_bridge_only_no_operation_backend 或 not_connected
production_mutation_allowed = false
```

这不是失败，而是诚实说明当前还没有进入真实 Operation-level backend mutation 阶段。

## 仍然 locked 的能力

```text
production Q-load hoist
GM round-trip deletion
real double-buffer ping-pong
full CVPipeline overlap
real tiling loop lowering
```

## 下一步

Phase 5B 应该接入真实 Operation backend 的 **inventory + no-op roundtrip + verifier**。只有无修改 roundtrip 稳定、verifier 通过、Operation inventory 和本地 baseline 可以解释性对齐后，才考虑把 Phase 4D 的 dry-run plan 交给真实 backend 执行 dry-run。


---

## HIVM_REWRITE_PHASE5B_PROGRESS_REPORT.md

# HIVM Rewrite Phase 5B Progress Report

## 定位

Phase 5B 是 **Operation backend no-op roundtrip / verifier gate**。本阶段仍然不做生产级 mutation，不移动 loop 内 load，不删除 GM 读写，也不做 double-buffer / CV overlap / tiling lowering。

本阶段的目标是先证明一件基础事情：未来接入的 HivmOpsEditor / MLIR Operation-level 后端，能否在“不做任何优化”的情况下稳定完成：

```text
read HIVM IR
  -> emit roundtrip HIVM IR
  -> verify roundtrip HIVM IR
```

如果一个后端连 no-op roundtrip 和 verify-only 都不能稳定通过，就不能让它执行 Q-load hoist 或 GM round-trip deletion。

## 官方文档约束

Phase 5B 继续遵循 MLIR 官方 rewrite 纪律：

1. Operation 是后续 inspection / transformation 的基本单位，不能把文本行当作安全 transformation unit。
2. Pattern rewrite 中的 IR mutation 应通过 PatternRewriter / backend API 进行，而不是绕过 rewriter 状态直接修改 IR。
3. Dialect Conversion 需要 explicit legality；pattern match 本身不能说明 rewrite 合法。
4. 跨位置移动 op 应是 Operation-level 行为，并需要 dominance / region / verifier 检查。

因此 Phase 5B 只做 no-op roundtrip 和 verify gate，不做任何真实 mutation。

## 新增输出

开启 structural rewrite 后会生成：

```text
phase5b_roundtrip_verifier_gate_report.json
phase5b_backend_execution_plan.json
phase5b_analysis_summary.json
```

其中：

- `phase5b_roundtrip_verifier_gate_report.json`：记录 original / optimized IR 的 inventory、roundtrip、verify-only 执行情况。
- `phase5b_backend_execution_plan.json`：记录未来真实 backend 需要执行的命令模板。
- `phase5b_analysis_summary.json`：给上层报告使用的简版总结。

## 新增工具

```text
tools/fake_hivm_operation_backend.py
```

这是 CI/demo fixture，只用于验证 Phase 5B 的接口和报告链路。它不是 MLIR parser，不是 HivmOpsEditor，也不是真实 verifier。

## 当前状态

如果没有配置真实 `--hivm-operation-backend`，Phase 5B 会输出 pending 状态，并保持 production mutation locked。

如果使用 fake backend fixture，本地 demo 能跑通 no-op roundtrip / verify gate，但这只证明工程链路通了，不代表真实 MLIR 后端已经接入。

## 当前仍然 locked

```text
production Q-load hoist
GM round-trip deletion
real double-buffer ping-pong
full CVPipeline overlap
real tiling loop lowering
```

## 下一步

Phase 5C 建议做 Operation-level dry-run execution：让真实 backend 或 contract fixture 读取 Phase 4D 的 dry-run plan，定位 Q-load candidate、目标 insertion point、region/dominance 约束，并输出 dry-run 报告。仍然不建议直接 production mutation。


---

## HIVM_REWRITE_PHASE5C_PROGRESS_REPORT.md

# HIVM Rewrite Phase 5C Progress Report

## Scope

Phase 5C adds an **Operation-level dry-run execution gate**. It asks the future
HivmOpsEditor / MLIR Operation backend to consume the Phase-4D dry-run plan,
locate candidate operations and report dominance / region-motion evidence.

This phase still performs **no production mutation**.

## New artifacts

- `phase5c_operation_level_dry_run_report.json`
- `phase5c_dominance_precheck_report.json`
- `phase5c_region_motion_precheck_report.json`
- `phase5c_analysis_summary.json`

## Official rewrite discipline

Phase 5C keeps the MLIR-aligned boundary:

- no Python text-level region motion;
- no real op movement;
- no GM deletion;
- no Q-load production hoist;
- no double-buffer / CV-overlap / tiling lowering.

A real mutation remains locked until a real Operation backend provides
per-action operation handles, dominance evidence, region-motion evidence,
verifier result, DES/trace validation and later msprof validation.

## Current expected result

With the CI/demo fake backend, the dry-run command can execute and locate a
candidate, but dominance and region-motion are intentionally not proven. This is
correct: the fake backend validates the interface, not compiler correctness.


---

## HIVM_REWRITE_PHASE5D_PROGRESS_REPORT.md

# HIVM Rewrite Phase-5D Progress Report

## Phase name

**Phase-5D: Guarded Operation-level Mutation Execution Gate**

## Why this phase exists

Phase 5C could ask a future Operation-level backend to locate a Q-load hoist candidate in dry-run mode, but it still did not define the actual mutation execution contract. Phase 5D closes that gap by defining the command, inputs, outputs, reports and pass/fail rules for a future backend that really performs a guarded Q-load hoist mutation.

This phase still follows the conservative rule:

> A fake backend, text-level backend, or standalone bridge must not be treated as a production MLIR/HivmOpsEditor mutation backend.

## New artifacts

When structural rewrite is enabled, Phase 5D emits:

```text
phase5d_guarded_mutation_execution_report.json
phase5d_mutation_safety_report.json
phase5d_analysis_summary.json
```

The future backend mutation command is represented as:

```bash
hivm-operation-backend \
  --mutate \
  --mutation-kind q_load_hoist \
  --input phase5d_optimized_input.hivm.mlir \
  --edit-script phase5d_q_load_hoist_mutation_input_plan.json \
  --output optimized.phase5d.q_load_hoist_candidate.hivm.mlir \
  --report phase5d_q_load_hoist_backend_mutation_report.json
```

## What this phase proves

Phase 5D proves the **mutation execution gate** and report contract are now wired into the project. It can call a backend if one is configured and will reject non-real or fake backends as non-production.

## What this phase does not prove

Phase 5D does not prove that Q-load hoist is already production-safe. The gate only passes if all conditions are met:

1. Phase 5B no-op roundtrip and verifier gate passed.
2. Phase 5C Operation-level dry-run gate passed.
3. Backend reports `is_real_mlir_backend = true`.
4. Backend reports mutation was actually performed.
5. Dominance proof passed.
6. Region-motion proof passed.
7. MLIR verifier passed after mutation.
8. DES/trace validation passed after mutation.

If any condition is missing, `production_mutation_allowed` remains `false`.

## Current status

With the included fake backend fixture, the command/report plumbing runs, but the fixture is explicitly rejected:

```text
production_mutation_allowed = false
mutation_performed = false
```

This is expected and correct. The fixture is not MLIR, not HivmOpsEditor, and cannot prove dominance, region motion, verifier success, or DES/trace validity.

## Next step

The next useful step is Phase 5E: either connect a real HivmOpsEditor/MLIR backend that can actually perform Q-load hoist under this contract, or close Phase 5 by documenting that real mutation remains blocked until such a backend exists.


---

## HIVM_REWRITE_PHASE5E_PROGRESS_REPORT.md

# HIVM Rewrite Phase-5E Progress Report

## Phase-5E: Limited GM Round-trip Deletion Gate

Phase-5E adds the first guarded gate for **GM round-trip deletion**.  It still does **not** delete GM traffic by text replacement.  The purpose is to prepare the execution contract for a future real MLIR/HivmOpsEditor Operation-level backend.

## What is new

New artifacts:

- `phase5e_limited_gm_roundtrip_deletion_report.json`
- `phase5e_gm_deletion_safety_report.json`
- `phase5e_analysis_summary.json`
- `phase5e_gm_roundtrip_deletion_input_plan.json`

New tests:

- `tests/test_phase5e_gm_deletion_gate.py`

The fake backend fixture was extended to understand:

```bash
--mutate --mutation-kind gm_roundtrip_deletion
```

The fake backend always refuses production deletion and marks itself as non-real, which is intentional.

## Safety policy

GM deletion is more dangerous than barrier/sync rewrite because it may remove externally visible memory effects.  Therefore Phase-5E only dispatches candidates to backend mutation when they have already passed Phase-3C deletion gates.

Required evidence before accepting deletion:

1. same GM base, static offset, slice and layout proof;
2. unique reaching GM definition/use proof;
3. no intervening unknown GM side effect;
4. not an output/boundary observable GM buffer;
5. real Operation-level backend, not fake scanner/text replacement;
6. MLIR verifier after deletion;
7. DES/trace validation after deletion.

If any of these are missing, deletion remains locked.

## Demo result

In the current `fa_bad_inefficient.hivm.mlir` demo, Phase-3C finds no executable GM deletion candidate, so Phase-5E correctly reports:

```json
{
  "candidate_count_total": 0,
  "executable_action_count": 0,
  "production_mutation_allowed": false,
  "deleted_pair_count": 0
}
```

This means the project did not fabricate GM deletion where no safe candidate exists.

## Current boundary

Phase-5E prepares the GM deletion gate, but it does not unlock:

- production GM round-trip deletion;
- Q-load hoist production mutation;
- real double-buffer ping-pong;
- full CVPipeline overlap;
- real tiling loop lowering.

## Next step

Phase-5F should close Phase 5 and state clearly what remains before any real production mutation:

- real MLIR/HivmOpsEditor Operation backend;
- verifier reports from real backend;
- DES/trace reports from real tritonsim-hivm;
- at least one restricted positive sample for Q-load hoist or GM deletion;
- later msprof validation.


---

## HIVM_REWRITE_PHASE5F_CLOSURE_REPORT.md

# HIVM Rewrite Phase 5F Closure Report

## 1. Phase 5F 定位

Phase 5F 是 Phase 5 的收口阶段。它不新增危险 IR mutation，不声称已经完成 production Q-load hoist、GM round-trip deletion、real double-buffer、full CV overlap 或 real tiling lowering。

Phase 5F 的目标是把 Phase 5A--5E 的结果合并成一份明确的闭环报告：

- 当前真正实现了什么；
- 哪些只是后端合同和门禁；
- 哪些 production mutation 仍然 locked；
- Phase 6 应该先做什么，而不是盲目进入更复杂优化。

## 2. Phase 5A--5E 回顾

| 阶段 | 已完成内容 | 是否真实 mutation |
|---|---|---|
| Phase 5A | Operation backend readiness / inventory alignment | 否 |
| Phase 5B | no-op roundtrip / verifier gate | 否 |
| Phase 5C | Operation-level dry-run execution gate | 否 |
| Phase 5D | Q-load hoist guarded mutation execution contract | 未解锁 production mutation |
| Phase 5E | limited GM round-trip deletion mutation contract | 未解锁 production mutation |
| Phase 5F | closure + Phase 6 handoff | 否 |

## 3. 当前真正实现的能力

当前项目已经具备：

1. 策略搜索与 cost model 排序；
2. annotation / hint 写回；
3. 小范围真实 HIVM op sequence 改写，主要包括 barrier/sync 类改写；
4. Q-load hoist 候选识别与后端 mutation 合同；
5. GM round-trip deletion 候选读取与后端 mutation 合同；
6. fake/non-MLIR 后端拒绝机制；
7. Phase 5 closure report 和 leadership summary。

## 4. 当前仍未实现的能力

当前仍不能声称已经实现：

- 完整 HivmOpsEditor / MLIR Operation-level backend；
- production Q-load hoist；
- production GM round-trip deletion；
- real double-buffer ping-pong；
- full CVPipeline overlap；
- real tiling loop lowering；
- 真实 tritonsim-hivm DES/trace 验证；
- msprof 真机性能收益证明。

## 5. 为什么 Phase 5F 仍然不解锁复杂 mutation

Phase 5 已经把后端调用接口和验收规则做好了，但当前环境下仍缺：

- 真实 Operation-level 后端；
- 真实 dominance / region-motion proof；
- 真实 MLIR verifier；
- 真实 DES/trace；
- 至少一个受限正例样本；
- msprof 真机验证。

因此，Phase 5F 继续遵守原则：没有真实后端证据，就不把复杂优化包装成 production mutation。

## 6. 新增交付物

Phase 5F 新增：

```text
phase5_closure_report.json
phase5f_analysis_summary.json
phase5f_leadership_summary.json
HIVM_REWRITE_PHASE5F_CLOSURE_REPORT.md
PHASE5F_LEADERSHIP_BRIEF.md
PHASE5_CLOSURE_AND_PHASE6_PLAN.md
```

## 7. 结论

Phase 5 完成的是“真实 Operation-level 后端接入前的合同与门禁阶段”。项目已经准备好接入真实 HivmOpsEditor / MLIR backend，但在真实后端接入前，复杂 production mutation 仍然保持 locked。


---

## HIVM_REWRITE_PHASE6A_PROGRESS_REPORT.md

# HIVM Rewrite Phase 6A Progress Report

## Scope

Phase 6A starts **Real Operation Backend Integration and Positive-case Validation**.  It does not perform production mutation.  Its job is to check whether the project has the real external ingredients needed to move beyond contracts and fake fixtures.

## What was added

New reports:

- `phase6a_real_backend_integration_report.json`
- `phase6a_backend_acceptance_matrix.json`
- `phase6a_required_inputs.json`
- `phase6a_analysis_summary.json`

New module:

- `strategy_search/phase6_analysis.py`

New CLI option:

- `--vtriton-source-root /path/to/vTriton`

## Current result

If no real backend is provided, Phase 6A reports:

```json
{
  "phase6a_status": "waiting_for_real_operation_backend_inputs",
  "accepted_for_phase6_positive_case": false,
  "production_mutation_allowed": false
}
```

This is expected.  Phase 6A is a strict gate: fake, mock, fixture, scanner-only, or standalone text bridges are not accepted as production Operation-level evidence.

## What we need from the user/team

To proceed beyond readiness gates, provide:

1. vTriton or internal HivmOpsEditor source tree.
2. Built HIVM Operation backend binary supporting capability handshake, inventory, roundtrip, verify-only, dry-run, and guarded mutate modes.
3. Built `tritonsim-hivm` binary.
4. One restricted positive HIVM fixture for Q-load hoist or GM round-trip deletion.
5. Dialect/version notes if parser compatibility is fragile.

## Boundary

Phase 6A still keeps these locked:

- production Q-load hoist
- production GM round-trip deletion
- real double-buffer
- full CVPipeline overlap
- real tiling lowering


---

## HIVM_REWRITE_PHASE6B_PROGRESS_REPORT.md

# HIVM Rewrite Phase-6B Progress Report

## Phase-6B name

**vTriton Positive Fixture Harness and Real-backend Execution Pack**

## What changed

Phase-6B moves beyond the Phase-6A input checklist.  It ingests concrete HIVM/NPUIR fixture files, performs conservative static triage, and generates a real-backend validation script that can be run once a real vTriton/HivmOpsEditor operation backend and `tritonsim-hivm` are available.

New outputs:

- `phase6b_positive_case_validation_report.json`
- `phase6b_fixture_acceptance_matrix.json`
- `phase6b_analysis_summary.json`
- `phase6b_real_backend_validation_commands.sh`

New sample fixtures:

- `sample_input/phase6_positive_fixtures/kernel.npuir.mlir`
- `sample_input/phase6_positive_fixtures/kernel_001.npuir.mlir`
- `sample_input/phase6_positive_fixtures/fa_best.hivm.mlir`
- `sample_input/phase6_positive_fixtures/restricted_q_load_in_loop_positive.hivm.mlir`
- `sample_input/phase6_positive_fixtures/restricted_gm_roundtrip_positive.hivm.mlir`

The two `restricted_*` files are intentionally tiny positive fixtures. They are not production kernels; they exist to force a real backend to prove or reject Q-load hoist and GM round-trip deletion under controlled patterns.

## Official vTriton alignment

The public vTriton README describes the repository as an MLIR-based Ascend NPU modeling tool and states that `tritonsim-hivm` directly analyzes `.npuir.mlir` and can export Perfetto trace.  Phase-6B follows that command shape by generating:

```bash
tritonsim-hivm \
  --npuir-file <fixture> \
  --scheduler des \
  --des-graph-file <fixture>_des_graph.json \
  --perfetto-trace-file <fixture>_trace.json
```

The public `tools/hivm-crud/hivm-crud.cpp` is a thin CLI wrapper around `HivmOpsEditor`. It states that upper-level C++ code should call `HivmOpsEditor` directly.  Phase-6B therefore still refuses to treat text scanners or fake backends as production mutation backends.

## Current demo result

With the included fixtures, Phase-6B reports:

- `fixture_count = 5`
- `candidate_fixture_count = 4`
- `real_backend_connected = false`
- `tritonsim_available = false`
- `production_mutation_allowed = false`

The fixture triage is working, but real execution is blocked until a real operation backend and real `tritonsim-hivm` are supplied.

## Current blockers

- `real_hivmopseditor_or_mlir_operation_backend_not_connected`
- `real_tritonsim_hivm_not_connected`
- `vtriton_source_root_missing_or_not_recognized`

## What this means

Phase-6B does not fake a production mutation.  It creates the concrete bridge between the user's HIVM samples and the real vTriton/HivmOpsEditor validation path.  Once the real backend and `tritonsim-hivm` are provided, the generated script can execute inventory, roundtrip, verify-only, DES/trace, and later guarded mutation checks on the actual fixtures.


---

## HIVM_REWRITE_PHASE6C_PROGRESS_REPORT.md

# HIVM Rewrite Phase 6C Progress Report

## 版本定位

Phase 6C 是项目中第一次把复杂优化候选从 dry-run / mutation contract 推进到 **真实文件级 IR 改写输出** 的阶段。

本阶段新增 `tools/restricted_hivm_true_rewriter.py`，它会在明确标记的受限正例 fixture 上真正生成改写后的 `.hivm.mlir` 文件。

重要边界：

- 这是 restricted true rewrite，不是 production MLIR/HivmOpsEditor backend。
- 它会真实改 IR 文件内容，但只允许 tiny positive fixtures。
- 复杂真实 kernel 仍然保持 locked。
- msprof / 真机验证仍然后置。

## 已实现的真实改写

### 1. Q-load hoist 受限正例

输入模式：

```mlir
scf.for %j = ... {
  hivm.hir.load ins(%Q_gm ...) outs(%q_ub ...)
  hivm.hir.nd2nz ins(%q_ub ...) outs(%q_l1 ...)
  ...
}
```

输出模式：

```mlir
hivm.hir.load ins(%Q_gm ...) outs(%q_ub ...)
hivm.hir.nd2nz ins(%q_ub ...) outs(%q_l1 ...)
scf.for %j = ... {
  ...
}
```

限制条件：

- input 必须带 restricted fixture marker；
- load / nd2nz 必须是 loop body 内前两个核心 op；
- load / nd2nz 不能使用 loop induction variable；
- loop 后续 body 不能再写 `%q_ub` 或 `%q_l1`；
- 只对最小正例执行，不对复杂真实 kernel 执行。

### 2. GM round-trip deletion 受限正例

输入模式：

```mlir
hivm.hir.load  ins(%A_gm ...) outs(%tmp_ub ...)
hivm.hir.store ins(%tmp_ub ...) outs(%A_gm ...)
hivm.hir.load  ins(%A_gm ...) outs(%tmp2_ub ...)
```

输出模式：

```mlir
hivm.hir.load  ins(%A_gm ...) outs(%tmp_ub ...)
// removed restricted redundant GM store round-trip: ...
// removed restricted redundant GM reload: ...
```

限制条件：

- input 必须带 restricted fixture marker；
- store 必须写回和前一条 load 相同的 GM base；
- store input 必须是前一条 load 的输出 buffer；
- reload 目标 buffer 后续不能再被使用；
- 不对 output / boundary / unknown side-effect pattern 执行。

## 新增输出

运行 structural rewrite 后会生成：

```text
phase6c_restricted_true_rewrite_report.json
phase6c_analysis_summary.json
phase6c_leadership_summary.json
optimized.phase6c.*.q_load_hoist.hivm.mlir
optimized.phase6c.*.gm_roundtrip_deletion.hivm.mlir
```

## Demo 结果

当前 demo 结果：

```json
{
  "phase": "Phase-6C",
  "status": "restricted_true_rewrite_positive_case_completed",
  "restricted_true_mutation_count": 2,
  "production_mutation_allowed": false,
  "blocker_count": 0
}
```

含义：

- 系统已经在两个受限正例上真实生成改写后的 HIVM IR；
- 但这些仍然不是 production compiler rewrite；
- 复杂真实 kernel 仍等待真正 HivmOpsEditor / MLIR Operation-level backend。

## 领导版一句话

Phase 6C 终于不是只做 dry-run 了：系统已经能在受限正例上真正输出改写后的 HIVM IR 文件，包括把 Q-load 搬出简单循环、删除局部冗余 GM store/reload。当前能力仍是受限原型，不是完整生产级编译器，但已经证明项目链路可以产生真实 IR 改写结果。


---

## HIVM_REWRITE_PHASE6D_PROGRESS_REPORT.md

# HIVM Rewrite Phase 6D Progress Report

## 目标

Phase 6D 的目标是把用户提供的 vTriton 源码真正纳入项目，而不是继续停留在假设接口。当前版本会扫描 vTriton source root，确认是否存在：

- `include/AscendModel/Transforms/HivmOpsEditor.h`
- `lib/AscendModel/Transforms/HivmOpsEditor.cpp`
- `tools/hivm-crud/hivm-crud.cpp`
- `tools/tritonsim-hivm/tritonsim-hivm.cpp`

并基于源码中实际观察到的 `HivmOpsEditor` API 生成一个可放入 vTriton tree 的 backend adapter skeleton。

## 新增内容

新增目录：

```text
vtriton_hivm_operation_backend/
  CMakeLists.txt
  README.md
  hivm_operation_backend.cpp
  vtriton_integration_patch.diff
```

新增安装脚本：

```text
scripts/phase6d_install_backend_adapter.sh
```

新增输出：

```text
phase6d_vtriton_source_integration_report.json
phase6d_generated_backend_files_manifest.json
phase6d_hivmopseditor_backend_adapter_plan.json
phase6d_analysis_summary.json
```

## 真实进展

这版已经不是凭空设计 backend contract，而是贴着 vTriton 源码中的 `HivmOpsEditor` 写 adapter skeleton。adapter 里直接 include：

```cpp
#include "AscendModel/Transforms/HivmOpsEditor.h"
```

并使用：

```text
HivmOpsEditor::loadFromFile
HivmOpsEditor::listOps
HivmOpsEditor::exportToFile
HivmOpsEditor::removeRedundantLoadStorePair
```

当前 adapter skeleton 支持的模式包括：

```text
--print-capabilities
--inventory
--roundtrip
--verify-only
--dry-run
--mutate --mutation-kind gm_roundtrip_deletion --max-gm-pairs N
```

`q_load_hoist` 仍然故意拒绝，因为源码里虽然有 CRUD API，但真正的 Q-load hoist 还需要 dominance / region-motion 算法，不能用文本移动冒充。

## 当前边界

Phase 6D 生成的是 source-aware adapter skeleton，还没有在本 sandbox 中完成 vTriton 编译。原因是 vTriton/MLIR/BishengIR 构建依赖需要用户本地或服务器环境。

因此：

- 可以说：已经生成贴合 vTriton 源码结构的 HivmOpsEditor backend adapter skeleton。
- 不可以说：已经编译通过并完成 production Q-load hoist。


---

## HIVM_REWRITE_PHASE6E_PROGRESS_REPORT.md

# HIVM Rewrite Phase 6E Progress Report

## 阶段名称

**Phase 6E：vTriton Local Build Integration Pack**

## 目标

Phase 6D 已经基于用户提供的 vTriton 源码生成了 `HivmOpsEditor` 后端骨架。Phase 6E 的目标是把这个骨架推进为可以在本地 vTriton 构建树中安装、编译、验收的工程包。

这一阶段仍然不声称已经完成复杂 production rewrite。它解决的是：如何把 `hivm-operation-backend` 放进真实 vTriton 构建环境，并让用户本地编译出真实 binary。

## 新增内容

新增脚本：

```text
scripts/phase6e_apply_vtriton_backend_patch.py
scripts/phase6e_build_hivm_operation_backend.sh
scripts/phase6e_smoke_test_backend.sh
```

新增输出：

```text
phase6e_vtriton_local_integration_report.json
phase6e_backend_build_plan.json
phase6e_analysis_summary.json
```

更新后端适配目录：

```text
vtriton_hivm_operation_backend/
  CMakeLists.txt
  hivm_operation_backend.cpp
  vtriton_integration_patch.diff
```

## 当前结果

在本环境中已经能识别用户提供的 vTriton 源码目录，并生成可执行安装/构建脚本。Demo 结果：

```json
{
  "status": "phase6e_integration_pack_ready_waiting_for_local_vtriton_build",
  "ready_to_run_local_install_script": true,
  "compiled_backend_accepted": false,
  "des_trace_ready": false,
  "production_mutation_allowed": false
}
```

这说明：

1. vTriton 源码已识别；
2. 后端 adapter 安装脚本已可运行；
3. vTriton build 集成包已准备好；
4. 但当前 sandbox 没有编译出真实 `hivm-operation-backend` binary；
5. 也没有真实 `tritonsim-hivm` binary；
6. 因此 production mutation 仍然锁定。

## 本地使用步骤

在用户本地/服务器环境中执行：

```bash
bash scripts/phase6e_build_hivm_operation_backend.sh /path/to/vTriton /path/to/vTriton/build
```

这个脚本会：

1. 将 `vtriton_hivm_operation_backend/` 拷贝到 `<vTriton>/tools/hivm-operation-backend/`；
2. 修改 `<vTriton>/tools/CMakeLists.txt`，增加 `add_subdirectory(hivm-operation-backend)`；
3. 调用 CMake 构建 `hivm-operation-backend` target；
4. 构建成功后运行 `--print-capabilities`。

构建完成后，运行 smoke test：

```bash
bash scripts/phase6e_smoke_test_backend.sh \
  /path/to/vTriton/build/bin/hivm-operation-backend \
  sample_input/phase6_positive_fixtures/restricted_gm_roundtrip_positive.hivm.mlir
```

## 仍然没有解锁的能力

```text
production Q-load hoist
production GM round-trip deletion on complex kernels
real double-buffer
full CVPipeline overlap
real tiling lowering
msprof validation
```

其中 GM round-trip deletion 是第一个可尝试的真实 mutation，但必须等本地真实 backend 编译成功，并通过 inventory / roundtrip / verify-only 后再执行。

## 结论

Phase 6E 把项目从“生成 HivmOpsEditor adapter 源码骨架”推进到“可安装、可编译、可 smoke-test 的 vTriton 本地集成包”。下一步的真实里程碑不是继续加报告，而是在用户本地 vTriton 环境中编译 `hivm-operation-backend`，并用受限 fixture 跑通 inventory / roundtrip / verify / guarded GM deletion。


---

## HIVM_REWRITE_PHASE6F_CLOSURE_REPORT.md

# HIVM Rewrite Phase 6F Closure Report

## 定位

Phase 6F 是 **compiled real backend acceptance + Phase 6 closure**。它不是继续增加 fake backend，也不是继续扩大 Python 文本级改写范围，而是把 Phase 6 的最后一道门禁补齐：

> 只有当用户提供的 `hivm-operation-backend` 真正编译成功，并声明自己是 MLIR/HivmOpsEditor-backed backend，同时在真实 fixture 上通过 inventory / roundtrip / verify smoke test，系统才把它接受为后续受限真实 mutation trial 的后端。

## 新增输出

- `phase6f_backend_acceptance_report.json`
- `phase6f_smoke_command_matrix.json`
- `phase6_closure_report.json`
- `phase6f_analysis_summary.json`

## 验收规则

Phase 6F 接受一个后端必须满足：

1. 提供真实 compiled binary；
2. `--print-capabilities` 返回 JSON；
3. 声明 `is_real_mlir_backend` 或等价字段；
4. 声明使用 `HivmOpsEditor` 或 MLIR Operation walk；
5. 支持 `--inventory`；
6. 支持 `--roundtrip`；
7. 支持 `--verify-only`；
8. 支持 `--dry-run`；
9. 支持受限 `gm_roundtrip_deletion` mutation；
10. 至少一个 fixture 的 inventory / roundtrip / verify smoke test 通过。

如果这些条件不满足，production mutation 仍然锁住。

## 当前边界

Phase 6F 不会解锁 broad production mutation。即使后端通过验收，也只是允许进入下一阶段的 **restricted mutation trial**，优先是受限 GM round-trip deletion。Q-load hoist 仍然需要真实 dominance / region-motion 算法，不能因为后端能编译就直接开启。

## 当前状态

如果未提供真实 backend binary，报告会显示：

```json
{
  "phase6f_status": "phase6f_waiting_for_compiled_real_backend_acceptance",
  "production_mutation_allowed": false
}
```

这说明 Phase 6 的源码、脚手架、集成包、受限正例、验收 gate 都已经准备好；剩下的关键动作是在真实 vTriton build 环境里编译并提供 `hivm-operation-backend` binary。


---

## IR_REWRITE_MODULE_MERGE_REPORT.md

# IR rewrite 模块合并报告

## 合并目标

本次基于 `strategy_search_demo_V3.3.1_prefill_a5_plan_calibrated_final` 新版本，将前序版本中的 IR rewrite 能力合并进来，保证新版本同时保留：

1. Prefill-A5 / msprof / plan-level calibration 相关 cost model 更新；
2. Step-1 全量 annotation rewrite；
3. Step-2 safe structural hint rewrite；
4. CVPipeline op-level safe hint rewrite；
5. Step-3 vTriton-inspired formal structural rewrite。

## 合并内容

### 1. strategy_search/rewrite.py

替换为前序 rewrite 完整版本，包含：

- `optimized.annotated.hivm.mlir` 生成；
- `optimized.safe_structural.hivm.mlir` 生成；
- `pass_pipeline_config.json` 生成；
- `strategy_edit_script.json` 生成；
- `rewrite_diff_report.json` 生成；
- `rewrite_capability_report.json` 生成；
- `cv_pipeline_rewrite_report.json` 生成；
- Step-3 structural rewrite 调用入口。

### 2. strategy_search/structural_rewrite.py

新增结构化 rewrite 后端模块，支持：

- 粗粒度 `hivm.hir.barrier {mode = "ALL"}` 替换为方向性 `set_flag/wait_flag`；
- 在 CV vector stage 前插入真实 `set_flag/wait_flag` 边界；
- 针对简单 FA pattern 执行 invariant Q load / nd2nz hoist；
- 生成 `structural_edit_script.json`；
- 生成 `structural_rewrite_report.json`；
- 可选调用外部 vTriton `hivm-crud` binary。

### 3. CLI 参数

在当前新版本 `strategy_search/core.py` 中补回 rewrite 参数：

```bash
--enable-ir-rewrite
--rewrite-mode {annotation,safe_structural,both}
--rewrite-safety {conservative,balanced,aggressive}
--enable-structural-rewrite
--structural-rewrite-safety {conservative,balanced,aggressive}
--vtriton-hivm-crud
--vtriton-crud-mode {read,add,delete,modify,roundtrip}
--vtriton-remove-gm-trips
```

其中 `--rewrite-safety balanced` 已重新可用。

### 4. 测试合并

新增/恢复测试：

- `tests/test_rewrite_step1_annotation.py`
- `tests/test_rewrite_step2_safe_structural.py`
- `tests/test_rewrite_cvpipeline_hint.py`
- `tests/test_structural_rewrite_step3.py`

当前完整测试结果：

```text
54 passed
```

## Demo 验证

使用命令：

```bash
python -m strategy_search.cli \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --enable-ir-rewrite \
  --rewrite-mode both \
  --rewrite-safety balanced \
  --enable-structural-rewrite \
  --structural-rewrite-safety balanced \
  --output-dir output_merge_rewrite_demo
```

成功生成：

- `optimized.annotated.hivm.mlir`
- `optimized.safe_structural.hivm.mlir`
- `optimized.structural.hivm.mlir`
- `pass_pipeline_config.json`
- `strategy_edit_script.json`
- `rewrite_capability_report.json`
- `cv_pipeline_rewrite_report.json`
- `structural_edit_script.json`
- `structural_rewrite_report.json`
- `rewrite_diff_report.json`

Demo 的 structural rewrite 结果：

```json
{
  "structural_rewrite_performed": true,
  "changes_summary": {
    "total_changes": 4,
    "change_counts": {
      "replace_barrier_all_with_directional_sync": 2,
      "insert_sync_before_first_vector_op": 1,
      "hoist_invariant_q_load_from_simple_loop": 1
    }
  }
}
```

## 当前能力边界

当前版本已经可以正式生成结构变化后的：

```text
optimized.structural.hivm.mlir
```

但仍然不是完整 compiler lowering。当前 Step-3 会真实改变 operation sequence，但只做显式 pattern 下的保守改写：

- 会替换部分 coarse barrier；
- 会插入 CV stage sync 边界；
- 会 hoist 简单 FA pattern 中 invariant Q load；
- 不生成新的 tiled loop nest；
- 不复制 buffer 成 ping-pong；
- 不做完整 cube/vector/store 跨 tile overlap schedule；
- 不做全局 dependency graph correctness proof。

后续如果要声称真实性能收益，需要接：

```text
optimized.structural.hivm.mlir -> tritonsim-hivm / DES / trace / compiler/runtime correctness validation
```


---

## LEADERSHIP_PROGRESS_REPORT.md

# HIVM IR Rewrite 当前进展汇报（领导版）

## 一句话结论

当前项目已经从“只会给策略打标签”推进到“可以把部分策略真正写成新的 HIVM IR 操作序列”。也就是说，系统现在不只是告诉后端“建议怎么改”，而是已经能在受控范围内生成一个被结构性修改过的 `optimized.structural.hivm.mlir`。

但当前还不是完整编译器。复杂优化，例如真实双缓冲、完整 CV 流水重排、真实 tiling loop lowering，还不能默认打开。

---

## 当前已经做到什么

### 1. 策略寻优已经能输出最优方案

系统可以根据硬件配置、profile 校准数据和 cost model，从四类参数中搜索策略：

```text
TilingPlan
MultiBufferPlan
CVPipelinePlan
SyncPlan
```

输出：

```text
selected_strategy.json
selected_plan.json
cost_breakdown.json
strategy_search_report.html
```

这部分回答的是：

> 哪组参数理论上更优？

---

### 2. 寻优结果已经能写回 HIVM IR

现在系统可以把最优策略写回 `.hivm.mlir`：

```text
optimized.annotated.hivm.mlir
optimized.safe_structural.hivm.mlir
optimized.structural.hivm.mlir
```

其中前两个主要是 attribute / hint；第三个 `optimized.structural.hivm.mlir` 已经包含部分真实 op sequence 改写。

这部分回答的是：

> 搜索出来的策略能不能落到 IR 文件里？

答案是：可以。

---

### 3. 已经实现第一版 C++ 结构改写桥

当前新增了一个 C++ bridge：

```text
hivm-strategy-rewrite
```

它可以读取：

```text
structural_edit_script.json
```

然后生成：

```text
optimized.structural.hivm.mlir
structural_rewrite_report.json
```

这说明项目已经从 Python prototype 往 C++ 后端迁移。

---

### 4. 当前 C++ bridge 已经能做两类真实改写

目前 C++ bridge 已经支持：

```text
1. 把粗粒度 barrier 替换成方向性 set/wait
2. 在 CV 边界前插入 set/wait
```

简单理解：

```text
原来：一个粗粒度“大家都等一下”的 barrier
现在：改成更明确的“哪个流水线等哪个流水线”的同步操作
```

这是真实改写 IR 操作，不是注释。

---

## 当前还不能做什么

当前还不能默认开启：

```text
1. 删除 GM load/store round-trip
2. 真实 Q-load hoist production mutation
3. 真实 double-buffer ping-pong
4. 完整 CV pipeline overlap
5. 真实 tiling loop lowering
```

原因不是没有价值，而是这些优化会直接影响程序正确性。没有更强的依赖分析、buffer 生命周期分析和 vTriton/真机验证前，贸然开启风险很大。

---

## Phase 2 完成了什么

Phase 2 的主要成果是：

> 搭好了“策略搜索结果驱动 C++ 后端改写 HIVM IR”的工程闭环。

当前链路是：

```text
策略搜索
  -> structural_edit_script.json
  -> C++ rewrite bridge
  -> optimized.structural.hivm.mlir
  -> rewrite / validation / manifest 报告
```

这说明项目已经不是单纯 cost model demo，而是有了 IR 改写后端雏形。

---

## Phase 3 完成了什么

Phase 3 的主要成果是：

> 建立了后续复杂改写需要的安全检查基础。

现在系统会分析：

```text
1. HIVM 里有哪些 op；
2. op 之间大概有什么依赖；
3. event set/wait 是否成对；
4. buffer 生命周期大概多长；
5. UB/L1 容量是否可能超限；
6. GM load/store 是否可能是冗余；
7. Q-load 是否具备 hoist 候选条件；
8. 是否已经接入外部 DES/trace 验证。
```

这部分不是为了马上多改几个 IR，而是为了避免后面改错。

---

## 当前项目的真实定位

当前项目可以定义为：

> HIVM 策略寻优 + 结构改写工程原型。

已经做到：

```text
能搜索策略；
能生成改写指令；
能通过 C++ bridge 做部分真实 IR 改写；
能生成合法性和验证报告；
能说明哪些改写可以做、哪些暂时不能做。
```

还没做到：

```text
完整生产级编译器 pass；
完整 目标 vTriton/HivmOpsEditor 接入；
完整 DES/trace 验证通过；
msprof 真机性能验证；
大规模自动 IR lowering。
```

---

## 下一步最重要的事

下一步应该优先做：

```text
Phase 4A: 接入真实 目标 parser / HivmOpsEditor parser
```

目的：

```text
把当前基于文本/轻量扫描的证据，升级成基于 MLIR Operation / HivmOpsEditor 的真实结构化证据。
```

只有这一步完成后，才适合继续做：

```text
GM round-trip 删除
Q-load hoist production mutation
real double-buffer
full CV overlap
real tiling lowering
```

---

## 领导可以怎么理解当前进展

可以理解为：

> 第一阶段，我们让系统“知道应该怎么优化”；
> 第二阶段，我们让系统“能把简单优化真的写进 HIVM IR”；
> 第三阶段，我们让系统“知道哪些复杂优化暂时不能乱做，并开始建立安全检查”。

当前最重要的进展不是某一个具体优化带来了多少性能提升，而是：

```text
项目已经从策略搜索 demo，升级成了有 IR 改写后端、有报告、有安全边界的工程原型。
```

后续要真正证明性能提升，还需要接 vTriton DES/trace 和 msprof 真机验证。


---

## MSPROF_CALIBRATION_README.md

# msprof 实机数据校准说明

本版本新增了 `--msprof-op-summary` 输入，用于把 Ascend msprof 导出的 `op_summary.csv` 接入 cost model 校准流程。

## 1. 校准目标

当前 cost model 估计的是端到端意义上的：

```text
total_cycles = load + compute + store + sync + scalar/control + penalty - overlap
```

因此，实机 target 不能使用：

```text
aic_total_cycles + aiv_total_cycles
```

因为 AIC/AIV total cycles 是资源侧累计计数，AIC 和 AIV 可能并行或交叠执行，直接相加会把墙钟时间放大。

本版本使用：

```text
measured_total_cycles = Task Duration(us) * cycles_per_us
```

当前 `configs/ascend_910b.json` 中 `clock.cycles_per_us = 1850`。对于本次上传的主 kernel：

```text
Task Duration(us) = 111891.595
measured_total_cycles = 111891.595 * 1850 = 206999450.75
```

## 2. 本次识别出的主 kernel

从 `profiles/raw/op_summary_20260623064651.csv` 中自动选择了 `Task Duration(us)` 最大、且匹配 `--msprof-op-name chunk_kda` 的行：

```text
chunk_kda_bwd_kernel_wy_dqkg_fused_opt_v2
```

主要实机信号：

```text
aiv_scalar_ratio = 0.844
aic_scalar_ratio = 0.071
aiv_vec_ratio    = 0.045
aic_mac_ratio    = 0.006
cube_utilization = 99.36%
```

这说明本 kernel 的墙钟瓶颈更接近 AIV scalar/control heavy，而不是单纯 cube compute heavy。

## 3. 新增的两层校准

### 3.1 component prior

使用 msprof 分项比例修正 kernel profile 中的 component correction：

```text
scalar_cycle_correction: 1.6171 -> 1.8018
sync_cycle_correction:   1.3933 -> 1.3963
overlap_confidence:      0.9009 -> 0.7385
cv_overlap_confidence:   0.9100 -> 0.7824
```

含义是：

- scalar/control 实机占比很高，因此提高 scalar 分项估计；
- sync/control 往往被 scalar 调度、事件、循环控制放大，因此小幅提高 sync correction；
- scalar/control heavy 时，理论 overlap 不一定能完全兑现，所以降低 overlap confidence。

### 3.2 absolute scale calibration

单样本下，component prior 只能修正分项方向，不能保证绝对 cycles 数值对齐。因此 `component_plus_scale` 会额外计算：

```text
global_cycle_scale = measured_total_cycles / current_ir_predicted_cycles_before_scale
```

本次结果为：

```text
current_ir_predicted_cycles_before_scale = 31549.5239
measured_total_cycles = 206999450.75
global_cycle_scale = 6561.0959
```

应用该尺度后：

```text
current_ir_estimated_predicted_cycles = 206999450.75
best_predicted_cycles = 140615231.52
```

注意：这个全局 scale 会乘到所有候选上，所以不会改变候选排序，只用于把当前单 kernel 的绝对量纲拉回实机尺度。

## 4. 运行命令

```bash
python auto_strategy_search.py \
  --kernel sample_input/chunk_kernel.npuir.mlir \
  --hardware-config configs/ascend_910b.json \
  --artifact-des-graph sample_product/prefill_des.json \
  --artifact-trace sample_product/prefill_trace.json \
  --cost-model-config configs/cost_model_conservative.json \
  --msprof-op-summary profiles/raw/op_summary_20260623064651.csv \
  --msprof-op-name chunk_kda \
  --msprof-calibration-mode component_plus_scale \
  --output-dir output_msprof_calibrated
```

## 5. 输出文件

新增或重点相关文件：

```text
output_msprof_calibrated/msprof_profile_summary.json
output_msprof_calibrated/msprof_cost_calibration_report.json
output_msprof_calibrated/kernel_cost_profile.json
output_msprof_calibrated/search_report.json
```

其中：

- `msprof_profile_summary.json`：记录选中的实机 kernel 行、measured target、AIC/AIV 分项比例；
- `msprof_cost_calibration_report.json`：记录 component prior 前后变化与 global scale；
- `kernel_cost_profile.json`：记录被 msprof component prior 修正后的 kernel profile；
- `search_report.json`：记录校准后的 current/best predicted cycles。

## 6. 当前校准的边界

这次只有一个主 kernel、一个策略、一次 profile，所以只能做：

```text
单样本 absolute calibration + component sanity check
```

它还不能训练候选排序，也不能证明 top candidate 在实机一定最快。

要进一步校准 ranking，需要补充同一个 kernel 在不同策略下的多组 msprof 数据，例如：

```text
double_buffer on/off
cv_pipeline_stage 1/2/3/4
sync_policy keep_existing / event / graph_sync_solver
不同 tile_m/tile_n/tile_k
不同 ub/l1/buffer multiplier
不同 block_dim
```

只有这样才能评估：

```text
Spearman rank correlation
Top-k recall
Best regret
```


---

## NAMING_AND_SCOPE_CLARIFICATION.md

# Naming and Scope Clarification：HIVM Bridge，不再称为 fully vTriton-backed

## 为什么要改名

此前文档中出现过 `vTriton-backed`、`vTriton adapter` 等表述，容易让人误解为当前项目已经完全接入 vTriton 的 `HivmOpsEditor` 或 MLIR Operation-level backend。

当前真实状态不是这样。

## 推荐新名称

从本版本开始，推荐使用：

```text
HIVM Rewrite Bridge
HIVM Bridge Adapter
HIVM Bridge Backend
```

不再把当前 standalone C++ bridge 称为：

```text
fully vTriton-backed backend
production vTriton backend
完整 HivmOpsEditor 后端
```

## 当前版本准确定位

当前版本是：

```text
Python strategy search
  -> structural_edit_script.json
  -> standalone HIVM Rewrite Bridge
  -> optimized.structural.hivm.mlir
  -> local legality / validation reports
  -> optional external tritonsim-hivm validation wrapper
```

它已经能做部分真实 op sequence rewrite，但仍然不是完整 compiler pass。

## 兼容关系

为了不破坏旧脚本和测试，当前仍保留：

```text
vtriton_adapter/
vtriton_adapter_manifest.json
```

同时新增推荐命名：

```text
hivm_bridge_adapter/
hivm_bridge_manifest.json
```

旧名称是兼容 alias，新名称是后续文档和汇报口径的主名称。

## 给领导的表述

可以说：

> 当前我们完成的是 HIVM Rewrite Bridge：它参考 vTriton 的工程方向，并预留后续接入 vTriton/HivmOpsEditor 的接口，但目前还不是完整 vTriton 后端。当前已经能完成部分真实 IR 结构改写，下一步 Phase 4A 会把它升级为目标 parser / HivmOpsEditor 级别的结构化改写后端。


---

## OFFICIAL_MLIR_REWRITE_GUIDANCE.md

# Official-Documentation-Aligned HIVM Rewrite Guidance

This project now treats the Python structural rewrite as a prototype/fallback,
not the final compiler engineering answer.

## 1. Pattern-based rewrite is the target model

MLIR's official pattern rewriting infrastructure is a general DAG-to-DAG
transformation framework. The production HIVM rewrite should therefore be built
around explicit pattern matching and operation-level mutation, not free-form
string edits.

Project rule:

```text
Match HIVM operation anchors → run legality checker → mutate with vTriton/HivmOpsEditor or MLIR PatternRewriter-style APIs → emit report.
```

## 2. Mutation must be coordinated by the rewrite driver

MLIR's `PatternRewriter` is a `RewriterBase` that coordinates pattern application
and tracks IR mutations. Production HIVM passes should not bypass that model.

Project rule:

```text
Python may generate structural_edit_script.json.
C++/vTriton backend should own actual Operation insertion/deletion/replacement/movement.
```

## 3. Legality must be explicit

MLIR dialect conversion formalizes the idea that a conversion target defines
legal/illegal operations and rewrite patterns transform illegal operations into
legal ones. We borrow the same engineering discipline even when not doing full
dialect conversion.

Project rule:

```text
Every edit has legality.required_gates.
Every applied/skipped edit has evidence in structural_rewrite_report.json.
```

## 4. Current implementation status

Implemented in this version:

```text
- structural_edit_schema.py
- structural_edit_script.json with legality fields
- structural_edit_schema.json output
- structural_edit_validation_report.json output
- vtriton_adapter/hivm_strategy_rewrite.cpp scaffold
```

Still prototype/fallback:

```text
- Python operation-sequence edits in structural_rewrite.py
```

Not yet implemented:

```text
- real vTriton/HivmOpsEditor binary integration
- full dependency graph legality proof
- full double-buffer lowering
- full CV overlap scheduling
- full tiling loop lowering
```


---

## PHASE2_CLOSURE_AND_PHASE3_PLAN.md

# HIVM IR Rewrite Phase 2 总结与 Phase 3 规划

## 1. Phase 2 的定位

Phase 2 的目标不是完整 compiler lowering，而是建立一个可审计、可扩展、可接入 vTriton/HivmOpsEditor 的 **operation-level structural rewrite bridge**：

```text
Python strategy search
  -> structural_edit_script.json
  -> C++/vTriton rewrite backend boundary
  -> optimized.structural.hivm.mlir
  -> validation / manifest / legality reports
```

这一路线遵循 MLIR 官方工程思想：真实 IR mutation 应由 pass/backend 通过 PatternRewriter/RewriterBase 或等价的 Operation-level API 管理；每个 rewrite 都应有明确 match anchor、legality contract、mutation record 和 validation output。

## 2. Phase 2 已完成子阶段

| 子阶段 | 状态 | 交付物 | 说明 |
|---|---|---|---|
| Phase 2A | 完成 | `structural_backend_execution_plan.json` | 拆出 structural rewrite backend 边界，支持 `auto/python/vtriton/dry_run`。 |
| Phase 2B | 完成 | `structural_legality_report.json` | 增加本地 legality precheck，记录 pass/deferred/fail。 |
| Phase 2C | 完成 | `hivm_strategy_rewrite.cpp` | C++ bridge 支持 `barrier_all -> directional set/wait`。 |
| Phase 2D | 完成 | C++ bridge update | C++ bridge 支持 `insert_sync_before_first_vector_op`。 |
| Phase 2E | 完成为 precheck | GM round-trip candidates | `remove_redundant_gm_roundtrip` 被纳入 edit request，但删除 deferred。 |
| Phase 2F | 完成 | `structural_validation_summary.json` | 自动比较 original / optimized op-count delta。 |
| Phase 2G | 完成 | `vtriton_adapter_manifest.json` | 增加 C++ backend capability handshake 和 coverage report。 |
| Phase 2H | 完成 | `phase2_closure_report.json` | 收口 Phase 2，给出 Phase 3 路线。 |

## 3. 当前真实 structural rewrite 能力

### C++ bridge 已支持真实 mutation

1. `replace_barrier_all_with_directional_sync`
   - 将显式 coarse barrier 替换为方向性 `set_flag/wait_flag`。
   - 属于真实 op sequence 改写。

2. `insert_sync_before_first_vector_op`
   - 在 cube/fixpipe 后的第一个 vector op 前插入 `set_flag/wait_flag`。
   - 属于真实 op insertion。

### 仅 precheck/deferred

1. `remove_redundant_gm_roundtrip`
   - 当前只发现 candidate，不做删除。
   - 删除必须等待 Phase 3 的 alias/dependency proof。

### 仍不属于 Phase 2 范围

1. real double-buffer ping-pong rewrite；
2. full CV pipeline overlap schedule；
3. real tiling loop lowering；
4. event reuse / sync motion；
5. target compiler-level local legality evidence / future target proof。

## 4. Phase 2 输出文件语义

| 文件 | 作用 |
|---|---|
| `structural_edit_script.json` | Python 寻优器生成的结构改写请求。 |
| `structural_edit_schema.json` | edit script schema。 |
| `structural_edit_validation_report.json` | schema 是否通过。 |
| `structural_legality_report.json` | 本地 anchor/precheck 结果。 |
| `structural_backend_execution_plan.json` | 后端选择与 fallback 原因。 |
| `vtriton_adapter_manifest.json` | 外部后端 capability、coverage、binary identity。 |
| `structural_rewrite_report.json` | 实际改写结果与 change list。 |
| `structural_validation_summary.json` | original/optimized op-count delta 审计。 |
| `phase2_closure_report.json` | Phase 2 总结与 Phase 3 交接报告。 |

## 5. Phase 2 为什么到这里收口

Phase 2 已经完成了工程闭环：

```text
strategy -> edit script -> C++ bridge -> structural IR -> validation / manifest / closure report
```

如果继续把 double-buffer、full CV overlap、tiling lowering 塞进 Phase 2，会跳过 dependency graph、event liveness、buffer live-range 和 alias proof，风险很大。因此 Phase 2 应在 operation-level bridge 边界收口，Phase 3 再做 legality foundation。

## 6. Phase 3 准备做什么

Phase 3 的主题是：**Dependency / Liveness / Legality Foundation**。

### Phase 3A：Dependency graph 与 event liveness

目标：构建 HIVM op 序列的 producer-consumer graph、pipe dependency、barrier/set/wait 和 event live range。

交付物：

```text
dependency_graph_report.json
event_liveness_report.json
sync_dependency_report.json
```

困难：

- 需要 dialect-aware parser 或 vTriton/HivmOpsEditor 接入；
- 文本顺序不能完整表达 SSA dataflow；
- event id 生命周期和跨 loop 依赖很容易误判。

### Phase 3B：Buffer liveness 与 alias checker

目标：证明 UB/L1/GM buffer 是否可以 hoist、reuse、remove 或 double-buffer。

交付物：

```text
buffer_liveness_report.json
gm_alias_report.json
hoist_legality_report.json
```

困难：

- same-GM-base 不等于 same semantic object；
- accumulator/output/persistent buffer 不能轻易复用；
- 动态 offset、subview、layout transform 会让 alias 判断复杂化。

### Phase 3C：Safe GM round-trip deletion decision gate

目标：把 Phase 2E 的 deferred candidate 变成可证明安全的删除。

交付物：

```text
gm_roundtrip_deletion_decision.json
gm_roundtrip_deletion_report.json
```

困难：

- 删除 load/store 可能改变 kernel observable memory behavior；
- 必须证明中间没有 consumer/writer；
- 必须证明 store result 不需要对外可见。

### Phase 3D：Loop-invariant load hoist with local proof gate

目标：对简单 KV loop 中的 Q/metadata load 进行合法 hoist。

交付物：

```text
optimized.hoisted.hivm.mlir
load_hoist_report.json
```

困难：

- 必须证明 candidate 不依赖 loop induction variable；
- 必须证明中间没有写 Q/q buffer；
- 必须处理嵌套 loop 和动态 index。

### Phase 3E：vTriton DES / trace validation integration

目标：自动跑 original/optimized 的 `tritonsim-hivm`，比较 DES graph 和 trace。

交付物：

```text
des_comparison_report.json
trace_comparison_report.html
vtriton_validation_report.json
```

困难：

- 不同 vTriton build 的命令行参数可能不同；
- DES/trace 输出格式可能变化；
- simulation 改善不一定等价于真实 msprof 改善。

## 7. Phase 3 最大风险

1. **没有 target parser 就不能做复杂 rewrite**：Phase 3 必须逐步迁移到 vTriton/HivmOpsEditor 或 MLIR Operation-level API。
2. **sync 改错会死锁或 silent wrong**：event reuse 和 sync motion 要放到更后面。
3. **data movement 删除必须有 alias/dependency proof**：GM round-trip 不能凭文本模式删除。
4. **buffer hoist/reuse 需要 live-range 和容量检查**：否则可能 UB/L1 overflow 或读写错位。
5. **cost model 和真实 profile 可能偏离**：Phase 3 之后必须接 DES/trace/msprof 反校准。

## 8. 下一步建议

Phase 3 第一件事不要直接删除 GM round-trip，也不要上 double-buffer。建议先做：

```text
Phase 3A: dependency graph + event liveness foundation
```

只有 dependency graph 和 liveness 做起来，后面的 GM 删除、hoist、double-buffer 和 CV overlap 才有安全基础。

## 审核修正说明

Phase 2 已完成的是 standalone C++ rewrite bridge 最小闭环，不是完整 HivmOpsEditor / MLIR pass。`replace_barrier_all_with_directional_sync` 和 `insert_sync_before_first_vector_op` 已经是 C++ bridge 真实 mutation；`remove_redundant_gm_roundtrip` 当前仍是 candidate/precheck/deferred，不做删除。


---

## PHASE3_CLOSURE_AND_PHASE4_PLAN.md

# Phase 3 Closure and Phase 4 Plan

## Phase 3 总结

Phase 3 的主题是 `Dependency / Liveness / Legality Foundation`。它不是为了继续增加 rewrite 类型，而是为了给后续正式结构优化建立证据链。

目前已经具备：

```text
op inventory
op semantics registry
dependency graph v1
event liveness report
buffer liveness report
capacity recheck report
gm alias report
gm MemorySSA-like report
GM round-trip deletion decision gate
loop-invariant load hoist proof gate
vTriton DES/trace validation wrapper
phase3 closure report
```

## 当前 rewrite gate 状态

可以继续用于审计和本地验证：

```text
barrier / local sync rewrite audit
CV boundary sync insertion audit
```

仍然不能默认开启：

```text
GM round-trip deletion
Q-load hoist production mutation
real double-buffer ping-pong
full CV pipeline overlap
real tiling loop lowering
```

## Phase 4 计划

### Phase-4A: target parser / HivmOpsEditor integration hardening

目标：把 Phase 3 的 text-scanner evidence 替换或增强为 目标 vTriton/HivmOpsEditor / MLIR Operation-level evidence。

困难：vTriton/MLIR 构建环境、dialect 版本、op API 可能不一致。

### Phase-4B: guarded Q-load hoist prototype

目标：只对通过 local proof 和 target parser region-motion proof 的 Q-load candidate 做真实 mutation。

困难：region motion 可能破坏 dominance、buffer lifetime、loop-carried dependency。

### Phase-4C: limited GM round-trip deletion prototype

目标：只删除同时通过 alias、MemorySSA、observable boundary 和 DES/trace 验证的 GM round-trip。

困难：GM alias 和 observable memory behavior 最容易误判。

### Phase-4D: CV stage graph and overlap prototype planning

目标：先建立 CV stage graph，再考虑 toy/simple pattern 的 overlap prototype。

困难：full CV overlap 会改变跨 tile 调度、stage buffer 和 event liveness，风险高。

### Phase-4E: validation closure

目标：对 Phase-4 prototype mutation 执行 DES/trace/msprof 验证，并反向校准 cost model。

困难：simulation 与真实硬件可能不一致，性能结论必须由 msprof 支撑。

## Phase 4 铁律

```text
不能证明安全，就不改。
不能通过 DES/trace，就不声称结构正确。
不能通过 msprof，就不声称真实性能提升。
```

## 审核修正说明

当前 Phase 3 的分析结果应被理解为 **local conservative evidence foundation**，不是完整 production correctness proof。下一步进入 Phase 4A 前，必须优先完成 target parser / HivmOpsEditor integration hardening。否则 GM 删除、Q-load hoist、real double-buffer、full CV overlap、real tiling lowering 都不能默认开启。


---

## PHASE4A_LEADERSHIP_BRIEF.md

# Phase 4A 给领导的简明汇报

当前项目已经完成了“能搜索策略、能生成改写指令、能做部分 IR 结构改写、能输出审计报告”的闭环。

Phase 4A 不是继续堆复杂优化，而是做工程加固：确认当前 HIVM Rewrite Bridge 是否能和后续正式 parser / vTriton / DES trace 链路接起来。

可以这样汇报：

> 目前我们已经把后端重新定位为 HIVM Rewrite Bridge，避免误解为已经完全基于 vTriton。这个 bridge 已经能做部分真实 IR 结构改写。Phase 4A 的工作是给它增加目标 parser 接入前的能力检查和 readiness 报告，明确哪些能力已经具备、哪些仍需要 vTriton/HivmOpsEditor 环境验证。这样后续做 Q-load hoist、GM 删除、double-buffer 等高风险优化时，不会盲目改 IR。

当前 Phase 4A 的输出是：

- `target_parser_validation_report.json`：说明 target parser / bridge 能力 / 外部验证是否接通；
- `phase4a_analysis_summary.json`：给出是否可以进入下一阶段的简短结论。

一句话总结：

> Phase 4A 是把“可运行的 IR 改写原型”往“可信的编译器改写工具”推进的第一步，重点是接入前检查和风险收口，而不是立刻上复杂优化。


---

## PHASE4B_LEADERSHIP_BRIEF.md

# Phase-4B 领导版进展说明

这一阶段我们没有继续扩大改写范围，而是把“改完以后怎么验证”这件事做得更严谨。

之前系统可以生成优化后的 HIVM IR，也预留了 vTriton / tritonsim-hivm 的验证接口。Phase-4B 进一步要求：原始 IR 和优化后的 IR 都必须能跑过外部 DES/trace 工具，并且产生调度图和 trace 文件，才算通过这一层验证。

当前完成的是验证闭环的工程化：

1. 生成标准验证报告；
2. 生成可直接执行的验证命令脚本；
3. 清楚区分“真实 vTriton 验证”和“本地 demo fixture”；
4. 如果没有真实工具或验证失败，报告会明确说明原因，不会假装通过。

这一步的价值是控制风险。后面如果要做 Q-load hoist、GM 删除、double-buffer 或 CV overlap，必须先过这一层验证，避免出现“IR 看起来优化了，但工具无法解析或调度图异常”的问题。


---

## PHASE4C_LEADERSHIP_BRIEF.md

# Phase-4C Leadership Brief

## 一句话总结

Phase-4C 没有贸然改程序执行逻辑，而是把“Q-load 能不能提前搬出循环”做成了一个受控原型 gate：系统能找到候选优化点，并生成给后续正式后端使用的候选脚本，但暂时不直接改 IR。

## 当前进展

前面几个阶段已经完成：

1. 能搜索策略；
2. 能把部分策略写回 HIVM IR；
3. 有 C++ HIVM Rewrite Bridge；
4. 能做局部依赖、buffer、event、GM 访问分析；
5. 能接 DES/trace 验证接口。

Phase-4C 在这个基础上推进到：

> 对 Q-load hoist 这种更复杂的结构优化，系统已经可以判断哪些候选值得交给正式后端尝试。

## 为什么不直接做 Q-load hoist？

因为 Q-load hoist 不是简单加一行注释，也不是简单插入 sync。它会把 loop 内的 load 移到 loop 外，可能影响：

- buffer 生命周期；
- UB/L1 内存占用；
- loop 内依赖关系；
- 同步关系；
- 程序语义正确性。

所以当前版本只生成候选和证据，不直接移动 op。

## Demo 结果怎么理解

当前 demo 结果是：

- 找到 1 个 Q-load hoist 候选；
- 这个候选可以进入后续 backend dry-run；
- 但还不能作为 production mutation 默认执行。

这说明项目已经从“能不能想到优化”推进到“能不能筛出可审计优化候选”。

## 当前边界

不能对外说已经完成：

- 生产级 Q-load hoist；
- GM 删除；
- double-buffer；
- CV 全流水重排；
- tiling loop lowering；
- msprof 真机性能提升证明。

## 下一步

下一步需要把这个候选脚本交给更正式的 Operation-level 后端，例如 HivmOpsEditor / MLIR parser，让后端证明这个 load 移动不会破坏程序语义。证明通过后，再做真实 IR mutation。


---

## PHASE4D_LEADERSHIP_BRIEF.md

# Phase-4D 领导版简报

## 一句话

Phase-4D 的工作是：**把“可能可以优化的 Q-load 提前搬移”变成正式后端可执行的 dry-run 计划，但暂时不真正改程序，避免语义风险。**

## 当前进展

前面 Phase-4C 已经找到了 Q-load hoist 的候选点。Phase-4D 做的是把这些候选点整理成更正式的后端计划：

```text
候选优化点
  -> dry-run action
  -> HivmOpsEditor / MLIR backend plan
  -> 官方约束检查
```

也就是说，现在不是简单说“这里可能能优化”，而是告诉后续 C++/MLIR 后端：

```text
该检查哪个 op；
需要证明哪些条件；
哪些条件没过就不能改；
改完必须重新验证什么。
```

## 为什么暂时不直接改 IR

因为 Q-load hoist 会把一条 load 从循环里面移动到循环外面。这个动作如果判断错，可能导致读错数据、同步错位或者 buffer 生命周期超限。

所以当前策略是：

```text
先 dry-run，后 mutation；
先证明安全，后追求性能。
```

## 当前结论

当前可以生成后端 dry-run 计划，但仍然不允许生产级 mutation。

原因是：还没有接入真正的 HivmOpsEditor / MLIR Operation-level 后端来证明 dominance 和 region-motion 正确性。

## 下一步

下一步要接正式后端，让工具真正加载 HIVM module，在 Operation 层面检查这个 load 是否能安全移动。只有这一步通过，再考虑真实 Q-load hoist。


---

## PHASE4E_LEADERSHIP_BRIEF.md

# Phase 4E 领导版汇报

## 当前进展

Phase 4 已经完成收口。当前项目已经不是单纯的参数搜索 demo，而是形成了一个较完整的 HIVM Rewrite Bridge 工程链路：

1. 能搜索策略；
2. 能生成结构改写指令；
3. 能通过 C++ bridge 做部分真实 IR 改写；
4. 能检查 bridge 能力；
5. 能生成 DES/trace 验证命令和报告；
6. 能把 Q-load hoist 这类复杂优化整理成后端 dry-run 计划；
7. 能明确告诉我们哪些优化仍然不能安全开启。

## 为什么这一步重要

Phase 4 的重点不是盲目做更多优化，而是把“能不能安全改”这件事工程化。现在系统不会因为发现一个优化机会就直接改 IR，而是会先判断：

- 当前 bridge 是否支持；
- 外部验证链路是否接通；
- 是否有足够的依赖和内存证据；
- 是否符合 MLIR 官方 rewrite 纪律；
- 是否需要真实后端证明。

这能降低把 IR 改错的风险。

## 当前还没做什么

还没有默认开启：

- GM round-trip 删除；
- Q-load 的生产级 hoist；
- real double-buffer；
- full CV overlap；
- real tiling loop lowering；
- msprof 真机性能验证。

这些不是没价值，而是风险更高，需要等真实 Operation-level 后端和验证闭环接好后再做。

## 下一步

下一阶段 Phase 5 建议优先做：

> 接入真实 HivmOpsEditor / MLIR Operation-level backend，让当前 dry-run plan 能真正进入正式后端验证。

一句话总结：

> Phase 4 已经把 HIVM Rewrite Bridge 从“能改一点 IR 的原型”推进到“有验证 gate、有官方 rewrite 纪律、有后端 dry-run 合同的工程框架”。下一步不是直接堆复杂优化，而是接真实 Operation-level 后端和 verifier。


---

## PHASE4_EXECUTION_PLAN.md

# Phase 4 Execution Plan：从 HIVM Bridge 升级到目标 parser 级改写与验证

## Phase 4 的一句话目标

Phase 4 的核心不是立刻上 full double-buffer 或 full tiling，而是把当前 HIVM Rewrite Bridge 从“可审计原型”升级到“更接近真实编译器后端的结构化改写链路”。

换句话说：

```text
Phase 3：我们知道哪些地方可能能改，并且有本地证据。
Phase 4：我们要让改写由目标 parser / HivmOpsEditor / DES/trace 来确认。
```

## Phase 4 子阶段安排

### Phase 4A：目标 parser / HivmOpsEditor 接入加固

目标：把当前 line-scanner 和 standalone C++ bridge 的证据，升级为 Operation-level 证据。

主要任务：

1. 保留 `HIVM Rewrite Bridge` 作为当前稳定入口。
2. 增加目标 parser capability check。
3. 尝试接入 vTriton/HivmOpsEditor 或等价 MLIR Operation walk。
4. 输出 `target_parser_validation_report.json`。
5. 明确哪些 op 可以被目标 parser 识别，哪些仍然 unknown。

主要困难：

- vTriton build 环境可能复杂；
- HIVM dialect 版本可能和样例 IR 不一致；
- Operation-level API 接口可能需要适配；
- parser 能读并不等于 rewrite 后语义正确。

解决办法：

- 先做 capability check，不一上来做复杂 rewrite；
- 先让 original / optimized IR 能 roundtrip；
- 遇到 parser 不支持的 op，直接标记 blocker；
- standalone bridge 继续作为 fallback，不中断现有流程。

### Phase 4B：外部 DES / trace 验证真正跑通

目标：让 original 和 optimized IR 都能进入 `tritonsim-hivm`，产出 DES graph / trace。

主要任务：

1. 配置 `--tritonsim-hivm`。
2. 对 original 和 optimized 分别生成 DES graph。
3. 对 original 和 optimized 分别生成 Perfetto trace。
4. 生成 `trace_comparison_report.html`。
5. 汇总 barrier/set/wait、GM load/store、Cube/Vector/MTE 时间线变化。

主要困难：

- 本地可能没有 vTriton 可执行文件；
- `tritonsim-hivm` 参数和当前 wrapper 假设可能不一致；
- IR 可能过不了 vTriton parser；
- DES/trace 有变化不等于真实硬件性能提升。

解决办法：

- wrapper 保持容错，失败时写 pending/failure reason；
- 根据实际 vTriton CLI 调整参数；
- 先使用最小样例验证 roundtrip；
- trace 只作为 simulation evidence，不包装成 msprof 结果。

### Phase 4C：guarded Q-load hoist prototype

目标：在目标 parser 和 Phase 3D proof gate 支持下，做受控 Q-load hoist 原型。

主要任务：

1. 只选择 local proof passed 的 candidate。
2. 目标 parser 确认 region motion / dominance。
3. capacity recheck 通过。
4. event liveness 通过。
5. 输出 `optimized.q_load_hoisted.hivm.mlir` 和 `q_load_hoist_rewrite_report.json`。

主要困难：

- 移动 load 会延长 buffer 生命周期；
- 可能破坏 loop-carried dependency；
- sync 位置可能也要跟着调整；
- 文本上 invariant 不代表 MLIR region 上一定合法。

解决办法：

- 只支持最简单 loop pattern；
- 不处理 nested / branch / unknown side-effect 情况；
- 任何 gate 不通过都 deferred；
- 改写后必须过 structural validation 和 DES/trace validation。

### Phase 4D：limited GM round-trip deletion prototype

目标：只在非常保守的模式下尝试真实删除 GM round-trip。

主要任务：

1. 使用 Phase 3C 的 GM MemorySSA-like decision gate。
2. 要求 same GM、same static offset、same slice。
3. 中间不能有 unknown GM side effect。
4. 不能是 observable output boundary。
5. 删除后生成 `gm_roundtrip_deletion_report.json`。

主要困难：

- GM alias 很难证明；
- store/load 可能跨 runtime boundary 有可见语义；
- offset 可能依赖 loop variable；
- subview/layout transform 会隐藏真实访问范围。

解决办法：

- 只删 exact same textual GM + static offset 的 toy pattern；
- output/persistent/boundary buffer 一律不删；
- unknown op 一律 blocker；
- 删除后必须跑 DES/trace，最终还要 msprof。

### Phase 4E：Phase 4 closure

目标：总结 Phase 4 哪些 prototype 真的可用，哪些仍然只能作为候选。

交付：

```text
phase4_closure_report.json
PHASE4_CLOSURE_AND_PHASE5_PLAN.md
```

Phase 4 结束时，应该能回答：

1. 当前 bridge 是否能被目标 parser 接管？
2. original / optimized 是否能生成 DES/trace？
3. Q-load hoist 是否至少在简单 pattern 上可行？
4. GM round-trip 是否至少在严格 pattern 上可删？
5. 哪些能力可以进入 Phase 5 msprof 验证？

## Phase 4 不做什么

Phase 4 暂时不做：

```text
real double-buffer ping-pong
full CVPipeline overlap
real tiling loop lowering
大规模自动 compiler lowering
```

这些放在后续阶段，因为它们需要更强的 parser、liveness、alias、trace 和 msprof 证据。

## 给领导的简化说法

> Phase 4 的重点不是继续堆优化，而是把现在的原型改写链路接到更正式的解析和验证工具上。我们先证明“改写后的 IR 能被工具读懂、能产生调度图和 trace、简单优化不会破坏结构”，再考虑更复杂的 double-buffer、CV overlap 和 tiling。这样路线更稳，不会为了看起来优化而冒语义错误风险。

## Phase-4D：Official-docs-aligned Operation-level dry-run contract

Phase-4D 不做真实 mutation。它把 Phase-4C 产生的 Q-load hoist candidate script 转成未来 HivmOpsEditor / MLIR Operation-level backend 可消费的 dry-run contract。

新增交付物：

```text
phase4d_operation_rewrite_dry_run_report.json
phase4d_hivmopseditor_dry_run_plan.json
phase4d_official_mlir_compliance_report.json
phase4d_analysis_summary.json
```

核心原则：

1. 不能用 Python 文本替换来移动跨 region 的 op。
2. 未来真实移动必须交给 HivmOpsEditor / MLIR Operation-level backend。
3. 必须先证明 dominance / region-motion / event-liveness / buffer-capacity / verifier / DES-trace 全部通过。
4. 当前 production mutation 继续 locked。

Phase-4D 的目标不是提升性能，而是把后续真实后端应该执行的检查项、动作和拒绝条件写清楚，避免后续实现偏离官方 MLIR rewrite 纪律。


---

## PHASE5A_LEADERSHIP_BRIEF.md

# Phase 5A 领导汇报简版

## 一句话

Phase 5A 不是继续堆复杂优化，而是开始把当前 HIVM Rewrite Bridge 升级到真正的 Operation-level 后端接入路径。

## 目前完成了什么

现在项目已经可以：

1. 搜索 HIVM 优化策略；
2. 把策略写回 HIVM IR；
3. 用 C++ Rewrite Bridge 做小范围真实 op sequence 改写；
4. 生成依赖、buffer、event、GM、DES/trace gate 等安全报告；
5. 找出 Q-load hoist 这类候选优化点，但暂不真正移动 IR。

## Phase 5A 做了什么

Phase 5A 增加了真实后端接入前的 readiness 检查：

1. 检查有没有配置真实 HivmOpsEditor / MLIR Operation-level backend；
2. 定义未来正式后端必须支持的能力：inventory、roundtrip、verify-only、dry-run；
3. 生成当前本地 op inventory baseline，方便后续和真实 backend 对比；
4. 明确当前所有高风险 mutation 仍然不能默认开启。

## 为什么这一步重要

因为后续 Q-load hoist、GM 删除、double-buffer、CV overlap、tiling 都会影响真实执行语义。如果没有真实 Operation-level parser、roundtrip 和 verifier，贸然修改可能导致 silent wrong，即程序能跑但结果错。

## 当前结论

当前已经完成“策略搜索 + 小范围 IR 结构改写 + 安全审计 + 后端接入合同”。

但还没有完成完整生产级编译器后端。下一步要让真实 Operation-level backend 能稳定读入 HIVM、输出 roundtrip、通过 verifier，再考虑受控 mutation。


---

## PHASE5B_LEADERSHIP_BRIEF.md

# Phase 5B 领导版简报

## 这一步做了什么

Phase 5B 不是继续堆复杂优化，而是在检查未来正式后端是否具备最基本的稳定性：

> 不做任何优化，只把 HIVM IR 读进去、原样输出、再验证一次。

这叫 no-op roundtrip / verifier gate。

## 为什么要做

因为后面如果要真正移动 load、删除 GM 读写、做 double-buffer 或 CV overlap，必须依赖一个稳定的 Operation-level 后端。如果后端连“不改内容的读写验证”都不稳定，就不能让它去做真实改写。

## 当前结果

当前项目已经新增了 Phase 5B 的报告链路和命令模板：

```text
phase5b_roundtrip_verifier_gate_report.json
phase5b_backend_execution_plan.json
phase5b_analysis_summary.json
```

如果没有真实后端，报告会明确写 pending，而不是假装通过。如果用本地 fake fixture，可以验证接口链路通了，但这不代表真实 vTriton / HivmOpsEditor 已经接入。

## 当前还不能做什么

仍然不能默认开启：

```text
Q-load 真正搬移
GM 读写删除
double-buffer
CV overlap
tiling loop rewrite
```

## 一句话总结

Phase 5B 完成的是“正式后端接入前的读写验证门禁”：先证明后端能稳定读写和验证 HIVM，再谈真正改写。


---

## PHASE5C_LEADERSHIP_BRIEF.md

# Phase 5C Leadership Brief

Phase 5C does not add a new risky optimization. It checks whether the future
formal backend can **find the exact operation that we may want to move** and can
report whether moving it would be legal.

In simple terms:

- earlier phases found a possible Q-load optimization;
- Phase 5C asks the backend to rehearse the move without changing the file;
- if the backend cannot prove dominance and region safety, the optimization stays locked.

This is a safety gate. It prevents us from turning a promising cost-model idea
into an unsafe IR rewrite.

Current status: dry-run interface is implemented; production mutation is still disabled.


---

## PHASE5D_LEADERSHIP_BRIEF.md

# Phase 5D Leadership Brief

## 一句话结论

Phase 5D 把“未来真正改 Q-load 的后端接口”打通了，但不会把测试后端或文本改写冒充成正式编译器改写。

## 目前进展

之前系统已经能找到一个可能优化点：把循环里的 Q-load 提前到循环外。但这类优化会改变执行顺序和 buffer 生命周期，不能用文本剪切粘贴硬做。

Phase 5D 现在做的是：

1. 明确未来正式后端应该如何接收这个优化请求；
2. 明确后端应该输出什么报告；
3. 明确哪些条件不过就不能认为优化成功；
4. 明确 fake backend / 非 MLIR 后端不能通过生产级门禁。

## 为什么这有价值

这一步不是“又写一个报告”，而是把真正 mutation 的接口和验收标准做出来。后续只要接入真实 MLIR/HivmOpsEditor 后端，就可以按这个合同执行：

```text
输入 HIVM IR + Q-load hoist mutation plan
        ↓
Operation-level backend 执行 mutation
        ↓
输出 optimized IR + dominance/region/verifier/DES 证据
        ↓
系统判断是否可以接受为真实改写结果
```

## 当前还没做到什么

当前还没有真实生产级 Q-load hoist，因为真实 HivmOpsEditor / MLIR Operation-level 后端尚未接入。

当前 fake backend 只能测试接口流程，不能证明程序语义正确。

## 对领导的通俗说法

现在不是“完全没改”，也不是“已经能随便改”。我们已经能小范围真实改 barrier/sync；对于 Q-load 这种更危险的优化，现在已经把正式施工合同、验收标准和拒绝机制建好了。下一步需要接真实后端，才能把候选优化变成真正的 IR mutation。


---

## PHASE5E_LEADERSHIP_BRIEF.md

# Phase-5E Leadership Brief

## 一句话结论

Phase-5E 做的是 **GM 读写删除的安全门禁**，不是直接删 GM。它让系统知道：如果未来要删除“写到 GM 又读回 GM”的冗余操作，必须先证明这个删除不会影响结果。

## 为什么要做这个

GM round-trip 删除看起来很简单：

```text
store GM
load GM
```

好像可以直接删掉。但实际很危险，因为这可能是输出、可能地址不同、也可能中间有别的操作依赖这段 GM 数据。删错了，程序可能还能跑，但结果错了。

## 当前实现了什么

现在项目已经能：

1. 读取 Phase-3C 的 GM 删除候选决策；
2. 只把通过安全门槛的候选交给后端；
3. 定义后端如何执行 GM 删除 mutation；
4. 要求后端提供 alias、memory effect、observable boundary、verifier、DES/trace 证据；
5. 拒绝 fake backend 或证据不足的结果。

## 当前 demo 结果

当前样例没有发现可以安全删除的 GM round-trip，所以系统没有删除任何 GM 操作。这是正确结果，不是失败。

## 当前还不能说什么

不能说已经完成真实 GM 删除，也不能说已经有真实性能提升。当前完成的是“删除前的安全审批机制”。

## 下一步

下一步 Phase-5F 收口 Phase 5，明确下一阶段需要接入真实 MLIR/HivmOpsEditor 后端，并准备至少一个受限正例样本来验证 Q-load hoist 或 GM 删除。


---

## PHASE5F_LEADERSHIP_BRIEF.md

# Phase 5F 领导版简报

## 一句话结论

Phase 5 已经把“未来真正改 HIVM IR 的后端接口和验收门槛”建好了，但还没有把 Q-load hoist、GM 删除、double-buffer、CV overlap、tiling 这些复杂优化作为正式能力打开。

## 目前已经做到什么

当前项目已经完成三件比较实在的事情：

1. **能选策略**：根据 cost model 和硬件配置，选择较优 HIVM 优化策略。
2. **能小范围真改 IR**：已经能真实改 barrier/sync 相关 op，不只是写注释或 attribute。
3. **能给复杂优化建门禁**：Q-load hoist 和 GM 删除已经有候选识别、后端调用合同和验收规则。

## 目前还没做到什么

还不能说已经完成：

- 完整 MLIR/HivmOpsEditor 后端；
- 真实 Q-load hoist；
- 真实 GM load/store 删除；
- double-buffer；
- CV overlap；
- tiling lowering；
- msprof 真机性能验证。

## 为什么不直接打开复杂优化

因为这些复杂优化会改变数据流、内存访问和循环结构。如果没有真实 Operation-level 后端、verifier、DES/trace 和 msprof，直接改可能造成 silent wrong，也就是程序能跑但结果错。

## Phase 6 建议

Phase 6 不建议直接做 double-buffer 或 full CV overlap。建议先做：

1. 接入真实 HivmOpsEditor / MLIR Operation backend；
2. 让真实后端完成 no-op roundtrip 和 verifier；
3. 找一个受限 Q-load hoist 正例；
4. 找一个受限 GM deletion 正例；
5. 准备后续 msprof 验证。

## 领导版表述

当前项目已经从“策略寻优 demo”推进到“能小范围真实改 HIVM，并为复杂改写准备后端合同和验收门禁”的工程原型。下一步关键不是继续堆复杂优化，而是接入真实 Operation-level 后端，用真实 verifier 和 trace 证明至少一个复杂改写正例。


---

## PHASE5_CLOSURE_AND_PHASE6_PLAN.md

# Phase 5 Closure and Phase 6 Plan

## Phase 5 Closure

Phase 5 completes the backend-contract stage for HIVM rewrite.

It provides:

- Operation backend readiness contract;
- no-op roundtrip / verifier gate;
- Operation-level dry-run execution gate;
- Q-load hoist guarded mutation contract;
- limited GM round-trip deletion guarded mutation contract;
- Phase 5 closure report and leadership summary.

It does **not** claim:

- production Q-load hoist;
- production GM deletion;
- real double-buffer;
- full CV overlap;
- real tiling lowering;
- msprof speedup.

## Recommended Phase 6

Recommended name:

```text
Phase 6: Real Operation Backend Integration and Positive-case Validation
```

### Phase 6A: Connect real HivmOpsEditor / MLIR Operation backend

Goal: replace fake backend/scanner evidence with real Operation inventory, no-op roundtrip and verifier evidence.

Deliverables:

```text
operation_inventory_backend.json
operation_inventory_diff.json
mlir_roundtrip_report.json
mlir_verifier_report.json
```

Exit criteria: original and optimized HIVM can be read, re-emitted and verified by the real backend.

### Phase 6B: Positive Q-load hoist sample

Goal: execute one restricted Q-load hoist with real dominance, region-motion, verifier and DES/trace evidence.

Deliverables:

```text
optimized.q_load_hoisted.hivm.mlir
q_load_hoist_mutation_report.json
q_load_hoist_verifier_report.json
q_load_hoist_trace_validation_report.json
```

Exit criteria: backend performs mutation and verifier + DES/trace pass.

### Phase 6C: Positive GM deletion sample

Goal: create or locate a deliberately simple same-base/same-offset GM round-trip fixture and validate deletion end to end.

Deliverables:

```text
optimized.gm_roundtrip_removed.hivm.mlir
gm_roundtrip_deletion_report.json
gm_roundtrip_verifier_report.json
gm_roundtrip_trace_validation_report.json
```

Exit criteria: only an allowed candidate is deleted, and verifier + DES/trace pass.

### Phase 6D: msprof readiness pack

Goal: prepare original/optimized artifacts and a reproducible hardware profiling protocol.

Deliverables:

```text
msprof_runbook.md
original_vs_optimized_artifact_manifest.json
msprof_readiness_report.json
```

Exit criteria: a real hardware profiling team can run original and optimized kernels under the same shape and runtime configuration.

## Explicitly not recommended yet

Do not start with:

- real double-buffer ping-pong;
- full CVPipeline overlap;
- real tiling loop lowering.

These should wait until at least one complex Operation-level mutation is validated by real backend + verifier + DES/trace.


---

## PHASE6A_LEADERSHIP_BRIEF.md

# Phase 6A Leadership Brief

Phase 6A moves the project from “contracts and safety gates” toward real backend integration.  The key point is simple:

> We are now ready to connect a real MLIR/HivmOpsEditor backend, but we should not claim complex production rewrite until that backend is actually provided and passes the acceptance checks.

Current system can already search strategies, write hints, and perform small sync/barrier op-sequence rewrites.  Phase 6A adds a strict checklist for the next milestone: real backend binary, source/build context, `tritonsim-hivm`, and a restricted positive HIVM sample.

If these are missing, the system reports exactly what is missing instead of pretending the optimization is complete.

## Required inputs for next real milestone

- vTriton/HivmOpsEditor source tree
- built Operation-level backend binary
- built `tritonsim-hivm`
- one simple positive HIVM sample
- dialect/version notes

## One-sentence update

Phase 6A completed the real-backend integration checklist; the next substantive step requires the actual vTriton/HivmOpsEditor backend and one positive HIVM fixture.


---

## PHASE6B_LEADERSHIP_BRIEF.md

# Phase-6B 领导版简报

## 当前进展

Phase-6B 已经把用户提供的 HIVM / NPUIR 样例接入项目，并生成了真实后端验证脚本。现在系统不再只是说“以后要接 vTriton”，而是已经能把具体样例整理成正例验证包。

## 这一步具体做了什么

1. 接收用户提供的 `kernel.npuir.mlir`、`kernel_001.npuir.mlir`、`fa_best.hivm.mlir` 等样例。
2. 对样例做静态扫描，判断是否包含 load、store、loop、sync、GM/UB/L1 等结构。
3. 新增两个受限正例 fixture，用于后续验证 Q-load hoist 和 GM round-trip deletion。
4. 生成 `phase6b_real_backend_validation_commands.sh`，未来真实 vTriton/HivmOpsEditor 后端接入后可以直接跑。
5. 继续拒绝 fake backend，避免把测试工具结果包装成真实编译器能力。

## 当前结果

当前样例中识别到 5 个 fixture，其中 4 个可以作为后续正例验证候选。系统仍然没有开启 production mutation，因为还缺真实 Operation-level 后端和真实 `tritonsim-hivm`。

## 领导版一句话

Phase-6B 已经把“真实样例 + vTriton 验证路径 + 后端执行脚本”接起来了；但真正改 Q-load 或删 GM 仍然等待真实 HivmOpsEditor/MLIR 后端和 `tritonsim-hivm` 可执行文件。


---

## PHASE6B_VTRITON_REAL_BACKEND_RUNBOOK.md

# Phase-6B vTriton Real Backend Runbook

This runbook records how to run the Phase-6B positive-case package against a real vTriton/HivmOpsEditor backend.

## Required external artifacts

- vTriton source tree
- built `tritonsim-hivm`, normally under `build/bin/tritonsim-hivm`
- real HIVM Operation backend that supports:
  - `--print-capabilities`
  - `--inventory`
  - `--roundtrip`
  - `--verify-only`
  - `--dry-run`
  - guarded `--mutate --mutation-kind q_load_hoist`
  - guarded `--mutate --mutation-kind gm_roundtrip_deletion`

## Officially aligned vTriton command shape

```bash
TRITONSIM_HIVM=/path/to/vTriton/build/bin/tritonsim-hivm
${TRITONSIM_HIVM} \
  --npuir-file sample_input/phase6_positive_fixtures/kernel_001.npuir.mlir \
  --scheduler des \
  --des-graph-file /tmp/kernel_001_des_graph.json \
  --perfetto-trace-file /tmp/kernel_001_trace.json
```

## Generated script

After running the main demo, use:

```bash
bash <output-dir>/phase6b_real_backend_validation_commands.sh
```

This script does not prove performance by itself. It only exercises the real parser/inventory/roundtrip/verifier/DES-trace path. Production mutation remains locked unless backend reports contain the required dominance, region-motion, verifier, and DES/trace evidence.


---

## PHASE6C_LEADERSHIP_BRIEF.md

# Phase 6C 领导版简报

## 当前突破

这一版开始做真正的 IR 文件改写，而不只是 dry-run 或报告。

系统现在能在明确标记的受限样例上生成改写后的 `.hivm.mlir` 文件：

1. 把循环内重复的 Q-load / nd2nz 搬到循环外；
2. 删除一个受限模式下的冗余 GM store / reload。

这说明项目已经从“只能检查候选”推进到“能产出真实改写文件”。

## 边界

这不是完整生产级编译器后端。当前只支持 tiny positive fixture，不会对真实复杂 kernel 默认执行这些危险改写。

原因是复杂 kernel 仍需要 HivmOpsEditor / MLIR Operation-level 后端证明 dominance、region motion、alias、verifier 等条件。

## 可以怎么汇报

当前项目已经具备三类能力：

1. 策略搜索；
2. 小范围真实 sync/barrier 改写；
3. 受限正例上的真实 Q-load hoist 和 GM round-trip 删除输出。

下一步应该把这个受限 rewriter 的规则迁移到真正 HivmOpsEditor / MLIR 后端，而不是扩大文本改写范围。


---

## PHASE6D_LEADERSHIP_BRIEF.md

# Phase 6D 领导版简报

这一步开始真正用上用户提供的 vTriton 源码了。

之前我们的后端接口还有一部分是按照预期设计的；现在已经扫描了 vTriton 源码，确认里面确实存在 `HivmOpsEditor` 和 `hivm-crud`，并基于这些真实 API 生成了一个新的 `hivm-operation-backend` 后端骨架。

这意味着项目从“我们假设未来后端应该长这样”，推进到“我们已经按 vTriton 现有源码结构写出了可接入的后端 adapter”。

目前这个 adapter 可以支持 inventory、roundtrip、verify-only、dry-run，以及受控 GM round-trip deletion 的接口。Q-load hoist 暂时仍然锁住，因为它需要更复杂的 dominance 和 region-motion 证明，不能靠简单移动文本实现。

下一步需要在真实 vTriton 编译环境里把这个 adapter 放进 `tools/hivm-operation-backend/` 并编译。如果编译通过，就可以开始真正用 HivmOpsEditor 对 HIVM IR 做 Operation-level 改写。


---

## PHASE6E_LEADERSHIP_BRIEF.md

# Phase 6E 领导版简报

## 一句话结论

Phase 6E 已经把真实 vTriton/HivmOpsEditor 后端的接入从“源码骨架”推进到“本地可安装、可编译、可验收的集成包”。

## 当前做成了什么

我们已经基于提供的 vTriton 源码，生成了一个 `hivm-operation-backend` 工具，并提供了安装和构建脚本。这个工具的目标是在 vTriton 中编译出来，之后用于读取 HIVM IR、输出 op inventory、做 roundtrip、做 verifier 检查，并尝试受控 GM round-trip 删除。

新增的关键脚本包括：

```text
phase6e_apply_vtriton_backend_patch.py
phase6e_build_hivm_operation_backend.sh
phase6e_smoke_test_backend.sh
```

## 当前还没完成什么

当前还没有在真实 vTriton 构建环境里编译出 `hivm-operation-backend` binary。因此还不能说复杂 production rewrite 已经完成。

现在状态是：

```text
后端源码和集成脚本：完成
真实后端 binary：待本地编译
真实 tritonsim-hivm：待本地构建/提供
复杂 production mutation：仍锁定
```

## 下一步需要什么

下一步需要在本地/服务器 vTriton 环境中执行构建脚本：

```bash
bash scripts/phase6e_build_hivm_operation_backend.sh /path/to/vTriton /path/to/vTriton/build
```

构建成功后，再跑：

```bash
hivm-operation-backend --print-capabilities
hivm-operation-backend --inventory ...
hivm-operation-backend --roundtrip ...
hivm-operation-backend --verify-only ...
```

如果这些通过，才进入第一个真实复杂 mutation 正例：受控 GM round-trip deletion。

## 给领导的说法

目前项目已经从“能在受限正例上真改 IR”进一步推进到“开始接入真实 vTriton/HivmOpsEditor 编译后端”。Phase 6E 已经准备好本地构建包，下一步关键动作是在 vTriton 环境中编译并运行 `hivm-operation-backend`。这一步通过后，项目才能从受限文本真改写升级到真正 HivmOpsEditor-backed rewrite。


---

## PHASE6F_LEADERSHIP_BRIEF.md

# Phase 6F 领导版简报

## 一句话结论

Phase 6F 已经把“真实后端是否可用”的验收标准做成了自动门禁。现在项目不会再把 fake backend 或文本工具包装成正式能力；只有真实编译出来的 HivmOpsEditor/MLIR 后端通过能力声明和 smoke test，才会进入下一步受限真实 mutation。

## 当前完成了什么

项目已经完成：

1. 受限正例上的真实 HIVM IR 改写；
2. 基于 vTriton 源码的 HivmOpsEditor backend adapter skeleton；
3. 放入 vTriton 编译的 build integration pack；
4. 编译后端的 smoke test 和验收报告；
5. Phase 6 收口报告。

## 当前还缺什么

还缺真实本地构建结果：

```text
hivm-operation-backend binary
```

也就是需要在本地/服务器 vTriton 环境里编译出这个后端，然后把 binary 或日志交给项目验收。

## 不能夸大的地方

当前不能说已经完成复杂真实 kernel 的 production rewrite。可以说：

> 已完成受限正例真实 rewrite，以及真实 vTriton/HivmOpsEditor 后端接入和验收机制。下一步是编译真实 backend，并跑受限 GM 删除正例。


---

## PREFILL_A5_BENCHMARK_README.md

# Prefill-A5 S0-S9 多阶段实测数据测试与校准说明

## 1. 数据定位

`profiles/prefill_a5/` 来自 `prefill_a5.zip`，不是普通文档，而是同一个 FlashAttention sparse prefill kernel 在 Ascend 910B3 上的 S0-S9 优化阶段记录。每个阶段都有一个实测 latency：

| Stage | latency | 主要变化 |
|---|---:|---|
| S0 | 5800 us | baseline |
| S1 | 5392 us | `BLOCK_V=512` |
| S2 | 4356 us | `BLOCK_SBS=256 + multibuffer=False` |
| S3 | 4337 us | `enable_mixed_cv=False` |
| S4 | 4294 us | `workspace_sv=bf16` |
| S5 | 4235 us | `enable_hivm_auto_cv_balance=True` |
| S6 | 4075 us | `tile_mix_cube_loop=4, tile_mix_vector_loop=1` |
| S7 | 3580 us | shared `kv_nope` SSA rewrite |
| S8 | 3589 us | hoist Q loads，实测略退化 |
| S9 | 3573 us | `enable_code_motion=True` |

因此它比单条 `op_summary.csv` 更适合做 **多策略 ranking sanity test** 和 **参数收益敏感度校准**。但是它没有每个阶段对应的 AIC/AIV/MTE/scalar/vector 分项 profile，所以不能替代 msprof component-level 校准。

## 2. 新增文件

```text
profiles/prefill_a5/extracted_stages/*.py
profiles/prefill_a5/prefill_a5_stage_labels.json
scripts/prefill_a5_stage_benchmark.py
tests/test_prefill_a5_stage_benchmark.py
output_prefill_a5_benchmark/prefill_a5_stage_benchmark_report.json
output_prefill_a5_benchmark/prefill_a5_stage_benchmark_report.md
output_prefill_a5_benchmark/prefill_a5_cost_calibration_priors.json
```

## 3. 运行方式

```bash
python scripts/prefill_a5_stage_benchmark.py \
  --stage-labels profiles/prefill_a5/prefill_a5_stage_labels.json \
  --kernel sample_input/chunk_kernel.npuir.mlir \
  --hardware-config configs/ascend_910b.json \
  --cost-model-config configs/cost_model_conservative.json \
  --artifact-des-graph sample_product/prefill_des.json \
  --artifact-trace sample_product/prefill_trace.json \
  --output-dir output_prefill_a5_benchmark
```

## 4. 测试结果

当前输出显示：

| Predictor | Spearman | Kendall | Top1 hit | Top3 recall | Best regret | MAPE |
|---|---:|---:|---:|---:|---:|---:|
| raw_project_anchor_scaled | 0.3713 | 0.2432 | False | 0.0000 | 0.1853 | 0.2409 |
| hybrid_calibrated | 0.9030 | 0.8222 | True | 1.0000 | 0.0000 | 0.0784 |
| stage_prior_calibrated | 1.0000 | 1.0000 | True | 1.0000 | 0.0000 | 0.0000 |

解释：

1. `raw_project_anchor_scaled` 只用 S0 做量纲 anchor，不用 S1-S9 的真实收益。这个结果说明当前 analytical cost model 对 S0-S9 的真实排序敏感度还不够，尤其无法表达 `BLOCK_V`、SSA rewrite、code motion 这类源码/IR 结构变化。
2. `hybrid_calibrated` 对当前 `StrategyConfig` 表达不充分的事件加入 stage gain prior，对部分可表达事件只用半权重修正。它能较好恢复 S0-S9 的真实排序。
3. `stage_prior_calibrated` 直接使用 S0-S9 的逐阶段实测 gain，是 fitted benchmark 上界，不能当成泛化能力证明。

## 5. 抽取出的 stage gain priors

| Event | Evidence | latency multiplier | speedup |
|---|---|---:|---:|
| `block_v_512_eliminate_v_loop` | S0->S1 | 0.9297 | 1.0757 |
| `block_sbs_256_multibuffer_false` | S1->S2 | 0.8079 | 1.2378 |
| `mixed_cv_disabled` | S2->S3 | 0.9956 | 1.0044 |
| `workspace_sv_bf16` | S3->S4 | 0.9901 | 1.0100 |
| `hivm_auto_cv_balance` | S4->S5 | 0.9863 | 1.0139 |
| `tile_mix_cube4_vec1` | S5->S6 | 0.9622 | 1.0393 |
| `shared_kv_nope_ssa_rewrite` | S6->S7 | 0.8785 | 1.1383 |
| `hoist_q_loads_rewrite` | S7->S8 | 1.0025 | 0.9975 |
| `compiler_code_motion` | S8->S9 | 0.9955 | 1.0045 |

这些 prior 已保存到：

```text
output_prefill_a5_benchmark/prefill_a5_cost_calibration_priors.json
```

## 6. 对 cost model 的校准含义

这组数据说明，当前 cost model 需要补强三类信息：

1. **loop/domain-crossing count**：`BLOCK_V=512` 和 `BLOCK_SBS=256` 的收益来自减少 V loop、SBS loop、C/V domain crossing 和 workspace round-trip。
2. **multibuffer pressure-aware modeling**：S2 说明大 tile 下 `multibuffer=True` 可能造成 CBUF overflow，所以 double-buffer 不是无脑收益。
3. **IR rewrite benefit modeling**：S7 的 shared `kv_nope` SSA rewrite 是大收益，说明减少 redundant `nd2nz`、barrier、workspace round-trip 的 IR rewrite 需要进入 cost model/rewrite plan。

## 7. 仍然缺什么

如果要进一步做 component-level 校准，还需要每个阶段分别对应的：

```text
S0/op_summary.csv
S1/op_summary.csv
...
S9/op_summary.csv
```

这样才能知道每个优化阶段到底减少的是 AIC MAC、AIV scalar、MTE2/MTE3、vector、sync 还是 barrier stall。

## Plan-only validation update

Because the current HIVM cost model only claims to model four strategy plans
(TilingPlan, MultiBufferPlan, CVPipelinePlan, SyncPlan), the Prefill-A5 S0-S9
history should not be evaluated as a single end-to-end prediction problem.
Some stages are outside the current model boundary:

- S3->S4: workspace_sv bf16, a dtype/workspace policy change.
- S6->S7: shared kv_nope SSA, an IR rewrite / SSA reuse change.
- S7->S8: hoist Q loads, an IR rewrite / code-motion change.
- S8->S9: compiler code motion.

There is also one boundary-gap event:

- S0->S1: BLOCK_V=512. This is conceptually a tiling/vector-block change,
  but the current StrategyConfig does not contain a BLOCK_V field, so S0 and
  S1 are intentionally not counted as a current-model failure.

Use the plan-only validation script:

```bash
python scripts/prefill_a5_plan_only_validation.py \
  --output-dir output_prefill_a5_plan_only_validation
```

The current validation result on the included benchmark is:

- Supported plan transitions: 4
- Direction hits: 2/4
- Direction hit rate: 50%
- Main correct transition: S1->S2, BLOCK_SBS=256 + multibuffer=False
- Main mismatches: S2->S3 mixed_cv=False and S5->S6 tile_mix_cube_loop=4 / tile_mix_vector_loop=1

This means the four-plan cost model has useful sensitivity, especially for
TilingPlan + MultiBufferPlan, but CVPipelinePlan terms still need calibration.
The result should be reported as plan-level partial validation, not as full
S0-S9 end-to-end model validation.

---

# Plan-only 校准更新

新增 `configs/cost_model_prefill_a5_plan_calibrated.json`，用于把 Prefill-A5 中四个 plan 可表达的 transition 接入 cost model 校准。该配置只校准 plan-level latency multiplier，不修改硬件组件效率，也不纳入 SSA reuse / hoist / compiler code motion 等 plan 外变化。

校准前：

```bash
python scripts/prefill_a5_plan_only_validation.py \
  --output-dir output_prefill_a5_plan_only_validation_uncalibrated
```

校准后：

```bash
python scripts/prefill_a5_plan_only_validation.py \
  --cost-model-config configs/cost_model_prefill_a5_plan_calibrated.json \
  --output-dir output_prefill_a5_plan_only_calibrated
```

结果摘要：

| Metric | Before | After |
|---|---:|---:|
| Direction hits | 2/4 | 4/4 |
| Direction hit rate | 50% | 100% |
| Mean absolute gain error | 0.0281 | 0.0126 |

详细说明见 `PREFILL_A5_PLAN_CALIBRATION_REPORT.md`。


---

## PREFILL_A5_PLAN_CALIBRATION_REPORT.md

# Prefill-A5 Plan-only Cost Model Calibration Report

## 1. 校准边界

本次校准只使用 `prefill_a5` 中当前四个 plan 可以表达的变化：

- `S1 -> S2`: `BLOCK_SBS=256 + multibuffer=False`，对应 `TilingPlan + MultiBufferPlan`；
- `S2 -> S3`: `enable_mixed_cv=False`，对应 `CVPipelinePlan`；
- `S4 -> S5`: `enable_hivm_auto_cv_balance=True`，对应 `CVPipelinePlan`；
- `S5 -> S6`: `tile_mix_cube_loop=4, tile_mix_vector_loop=1`，对应 `CVPipelinePlan`。

以下变化不纳入当前 cost model 的校准分数：

- `S0 -> S1`: `BLOCK_V=512`，概念上属于 tiling，但当前 `StrategyConfig` 没有 `BLOCK_V` 字段；
- `S3 -> S4`: `workspace_sv bf16`，属于 dtype/workspace policy；
- `S6 -> S7`: shared `kv_nope` SSA，属于 IR rewrite；
- `S7 -> S8`: hoist Q loads，属于 IR rewrite；
- `S8 -> S9`: compiler code motion，属于 compiler pass。

因此，这次校准验证的是 **四 plan 参数的 plan-level 预测能力**，不是完整 S0-S9 优化链路预测能力，也不是 AIC/AIV/MTE/scalar/vector 的 component-level 校准。

## 2. 发现的问题

校准前，plan-only validation 结果为：

| Metric | Before calibration |
|---|---:|
| Supported transitions | 4 |
| Direction hits | 2/4 |
| Direction hit rate | 50% |
| Mean absolute gain error | 0.0281 |

主要问题：

1. `S2 -> S3` 被误解释为关闭整个 CV pipeline。实际上 `enable_mixed_cv=False` 只是关闭 mixed C/V，并不等于 `cv_pipeline_stage=1`。
2. `S4 -> S5` 中 `auto_cv_balance=True` 的收益被模型夸大。真实收益只有约 `1.39%`。
3. `S5 -> S6` 的 `tile_mix=4:1` 被通用 tile-mix imbalance penalty 惩罚。实际在 Prefill-A5 中，`4:1` 是 reuse-friendly 的 cube-heavy/vector-light schedule，真实收益约 `3.93%`。

## 3. 实施的校准

### 3.1 修正 stage-to-strategy 映射

更新 `scripts/prefill_a5_stage_benchmark.py`：

- `enable_mixed_cv=False` 不再被映射为 `cv_pipeline_stage=1`；
- S2/S3/S4/S5/S6 均保持 stage-2 CV pipeline；
- `mixed_cv`、`auto_cv_balance`、`tile_mix` 被解释为 stage-2 内部策略变化；
- `tile_mix_cube_loop=4, tile_mix_vector_loop=1` 映射为 `P_PREFILL_LARGE_SBS_REUSE` 模板。

### 3.2 新增 plan-level calibration priors

新增配置：

```text
configs/cost_model_prefill_a5_plan_calibrated.json
```

其中包含：

```json
{
  "mixed_cv_disabled_latency_multiplier": 0.9956382001836548,
  "auto_cv_balance_latency_multiplier": 0.9862608290638108,
  "prefill_tile_mix_cube4_vec1_latency_multiplier": 0.9622195985832349
}
```

这些 multiplier 来自 Prefill-A5 的实测局部转移：

| Transition | Event | latency multiplier | speedup |
|---|---|---:|---:|
| S2 -> S3 | mixed_cv disabled | 0.9956 | 1.0044 |
| S4 -> S5 | auto_cv_balance | 0.9863 | 1.0139 |
| S5 -> S6 | tile_mix 4:1 | 0.9622 | 1.0393 |

### 3.3 修正 prefill large-SBS tile_mix 惩罚

更新 `strategy_search/core.py`：

- 普通 `tile_mix` 仍然受到 imbalance penalty；
- 但 `P_PREFILL_LARGE_SBS_REUSE` 不再使用普通 imbalance penalty；
- 该模板下的 `4:1` mix 被视为 Prefill-A5 证据支持的 reuse schedule。

### 3.4 保持硬件配置和 component-level correction 不变

这次没有把 Prefill-A5 写入硬件配置，也没有修改 GM/UB/L1/Cube/Vector 的硬件效率。原因是 Prefill-A5 缺少每个 stage 的 `op_summary.csv`，所以不能做 component-level 校准。

## 4. 校准结果

校准后，plan-only validation 结果为：

| Metric | Before | After |
|---|---:|---:|
| Supported transitions | 4 | 4 |
| Direction hits | 2/4 | 4/4 |
| Direction hit rate | 50% | 100% |
| Mean absolute gain error | 0.0281 | 0.0126 |
| Mean abs log gain error | 0.0255 | 0.0102 |

逐 transition 结果：

| Transition | Event | Real gain | Calibrated predicted gain | Direction hit |
|---|---|---:|---:|---|
| S1 -> S2 | `BLOCK_SBS=256 + multibuffer=False` | 1.2378 | 1.2842 | True |
| S2 -> S3 | `enable_mixed_cv=False` | 1.0044 | 1.0039 | True |
| S4 -> S5 | `enable_hivm_auto_cv_balance=True` | 1.0139 | 1.0151 | True |
| S5 -> S6 | `tile_mix_cube_loop=4, tile_mix_vector_loop=1` | 1.0393 | 1.0415 | True |

## 5. 如何复现

校准前验证：

```bash
python scripts/prefill_a5_plan_only_validation.py \
  --output-dir output_prefill_a5_plan_only_validation_uncalibrated
```

校准后验证：

```bash
python scripts/prefill_a5_plan_only_validation.py \
  --cost-model-config configs/cost_model_prefill_a5_plan_calibrated.json \
  --output-dir output_prefill_a5_plan_only_calibrated
```

完整测试：

```bash
pytest -q tests/test_prefill_a5_stage_benchmark.py \
          tests/test_prefill_a5_plan_only_validation.py \
          tests/test_cost_model_unit.py \
          tests/test_v33_kernel_profile.py
```

## 6. 结论

这次校准完成后，可以更稳地说：

> 在 Prefill-A5 的 plan-only 范围内，当前 cost model 已经能够正确捕捉四个可表达 plan transition 的收益方向，并且增量收益幅度更接近实测结果。

但仍然不能说：

> 当前 cost model 已经能够预测完整 S0-S9 优化链路。

因为 S7/S8/S9 的主要收益来自 SSA reuse、hoist 和 compiler code motion，这些不是当前四 plan 参数。


---

## README.md

# HIVM / AscendNPU-IR 四类 Plan 参数寻优 Demo

## 当前阶段：Phase-5D Guarded Mutation Gate

当前版本已经进入 Phase 5D：系统不再只是生成 dry-run 计划，而是定义了未来 Operation-level 后端执行 Q-load hoist mutation 的正式输入/输出合同。

新增输出：

```text
phase5d_guarded_mutation_execution_report.json
phase5d_mutation_safety_report.json
phase5d_analysis_summary.json
```

需要强调：Phase 5D 仍然不会把 fake backend、standalone bridge 或 Python 文本改写冒充成正式 compiler mutation。只有真实 MLIR/HivmOpsEditor 后端证明 dominance、region-motion、verifier 和 DES/trace 都通过，`production_mutation_allowed` 才可能为 true。


本项目是一个面向 **HIVM / AscendNPU-IR / NPUIR 风格 MLIR kernel** 的 strategy-level analytical search demo。它的目标不是替代真实 HIVM 编译器，也不是直接输出真机 msprof 性能，而是在没有完整 compiler pass、dry-run、DES 仿真闭环或 msprof 的情况下，对 HIVM 中最核心的四类优化机制进行参数建模、硬件边界检查、解析式 cost 评估、候选寻优和可解释报告生成。

当前 demo 把一个策略候选统一表示为：

```text
x = (T, M, P, Y)
```

其中：

| 符号 | Plan | 主要职责 | 是否进入寻优 | 是否进入 cost model / hardware gate |
|---|---|---|---|---|
| `T` | `TilingPlan` | tile 形状、block 并行度、loop 顺序、tail 策略、reduce 维切分 | 是 | 是 |
| `M` | `MultiBufferPlan` | double buffer、per-buffer multiplier、stage buffer、load/store overlap | 是 | 是 |
| `P` | `CVPipelinePlan` | Cube/Vector 软流水、pipeline stage、CV 模板、producer-consumer 距离 | 是 | 是 |
| `Y` | `SyncPlan` | keep existing / graph sync solver、event reuse、sync 粒度、sync motion | 是 | 是 |

一句话概括：

```text
输入 MLIR → 恢复 current IR 策略 → 生成四类 Plan 候选 → 硬件 gate → cost model 排序 → 输出报告 / 可选 rewrite bundle
```

---

## V3.3.2 Phase-5B：Operation backend no-op roundtrip / verifier gate

当前项目已经有 HIVM Rewrite Bridge，可以做少量真实 op sequence 改写。但复杂 mutation 仍然需要真实 Operation-level 后端。Phase-5B 新增的是后端接入前的稳定性门禁：

```text
original / optimized HIVM IR
  -> future Operation backend --roundtrip
  -> roundtrip HIVM IR
  -> future Operation backend --verify-only
  -> verifier report
```

新增输出：

```text
phase5b_roundtrip_verifier_gate_report.json
phase5b_backend_execution_plan.json
phase5b_analysis_summary.json
```

如果没有配置真实 `--hivm-operation-backend`，Phase-5B 会保持 pending 并明确列出 blocker。即使使用 `tools/fake_hivm_operation_backend.py` 跑通，也只说明 CLI/report 链路可用，不代表真实 MLIR/HivmOpsEditor 后端已经接入。

Phase-5B 不执行任何生产级 mutation；Q-load hoist、GM round-trip deletion、real double-buffer、full CV overlap 和 real tiling loop lowering 仍然 locked。


## V3.3.1：Structure-aware Cycle Correction Cost Model

V3.3.1 的核心定位是：**目标仍然是估计总 cycles**，但 MLIR 与编译产物不再作为额外打分项，而是用于修正各个分项 cycles 的基础估计误差。

更准确地说，本版本的 `predicted_cycles` 是：

```text
predicted_cycles =
    corrected_tile_cycles
  + corrected_sync_cycles
  + memory_capacity_penalty
  + shape_regularization_penalty
  + legality_risk_penalty
```

其中 `corrected_*_cycles` 仍然是 analytical estimate，不是真机 msprof cycles。在线寻优阶段不读取实机 profiling target，也不使用 DES makespan/global scale 做单样本校准。实机数据只应在离线阶段用于训练或校准 config 里的超参数。

### 0.1.1 为什么需要结构证据

基础 cost model 可以根据 tile shape、dtype bytes、带宽、吞吐和同步操作数量估计：

```text
T_load_base, T_store_base, T_cube_base, T_vector_base, T_sync_base, T_scalar_base
```

但这些基础项比较粗。例如同样的 `tile_m=64, tile_n=128, tile_k=64`，放在不同 kernel 里含义完全不同：

| kernel 结构 | 同样策略的真实含义 |
|---|---|
| cube-heavy | double buffer / CV pipeline 可能更有效 |
| memory-heavy | load/store exposed time 和 workspace traffic 更关键 |
| scalar/control-heavy | index/cast/control/schedule overhead 可能吃掉 pipeline 收益 |
| sync-heavy | event/barrier/wait 可能让 GraphSyncSolver 风险变高 |

所以 V3.3.1 使用 MLIR 与产物结构证据来修正分项 cycles，而不是直接给候选加一个抽象 score。

### 0.1.2 当前如何利用结构化信息

V3.3.1 会从 MLIR 和产物文件中抽取结构证据，包括：

- flat op counts：Cube、Vector、MTE/Layout、Sync、Scalar/Control/Address；
- loop-weighted op counts：内层循环中的 scalar/sync/memory/vector/compute 操作权重更高；
- memory space-path traffic：GM/UB/L1/L0 等空间路径上的静态 bytes 与 copy/layout 路径；
- buffer lifetime：局部 buffer 的 live span、byte-span pressure、per-buffer double-buffer benefit proxy；
- sync criticality proxy：内层同步、跨 pipe event pair、set/wait 配对缺失等；
- alignment/tail/mask proxy：shape 对齐、offset 对齐、mask/tail 操作密度；
- op sequence patterns：copy -> nd2nz -> cube、cube -> fixpipe -> vector、vector -> store 等流水机会；
- DES/trace JSON 中的 pipe mix、DMA path、sync/event name count 等结构信息。

结构证据先被归一化为：

```text
compute_ratio, memory_ratio, vector_ratio, scalar_ratio, sync_ratio
```

如果 DES 产物可用，当前采用保守融合：

```text
structure_ratios = 0.60 * MLIR_static_ratios + 0.40 * product_artifact_ratios
```

这样可以利用 lowering 后的产物结构信息，但避免 DES pipe fraction 单点过度主导模型。

### 0.1.3 结构证据如何进入分项 cycles

这些证据会被汇总到 `kernel_cost_profile.json`，生成一组 **cycle correction factors**：

| correction factor | 主要修正对象 | 证据来源 | 设计原则 |
|---|---|---|---|
| `memory_cycle_correction` | load/store cycles | memory ratio、DMA path、memory path bytes | memory 证据只修正搬运相关 cycles |
| `compute_cycle_correction` | cube compute cycles | cube op、compute ratio、CV opportunity | compute 证据不直接制造 reward，只修正 compute estimate |
| `vector_cycle_correction` | vector cycles | vector op、alignment/tail proxy | vector 与 alignment 影响 vector/fixpipe 估计 |
| `scalar_cycle_correction` | scalar/control cycles | scalar/control op、loop-weighted scalar | scalar 证据主要进入 scalar/control 项 |
| `sync_cycle_correction` | sync cycles | barrier、set/wait、sync criticality | sync 证据主要进入 sync 项 |
| `workspace_pressure_correction` | workspace exposed cycles | buffer lifetime、workspace pressure | 只修正额外 workspace traffic |
| `overlap_confidence` | load/store overlap ratio | scalar/sync/memory/CV opportunity | 只在窄范围内修正 overlap 可信度 |
| `cv_overlap_confidence` | cube-vector overlap ratio | compute/vector balance、sync/scalar density | 只在窄范围内修正 CV overlap 可信度 |

注意：旧字段名如 `scalar_control_multiplier`、`overlap_reward_scale` 仍作为兼容 alias 保留，但新语义是 cycle correction / overlap confidence，不再表示额外 ranking reward。

### 0.1.4 主公式

单 tile 的估计成本为：

```text
T_tile =
    max(T_load_exposed, T_compute_corrected, T_store_exposed)
  + T_scalar_corrected
  + T_workspace_exposed
  + T_schedule
  + T_warmup_drain
```

其中：

```text
T_load_corrected  = T_load_base  * memory_cycle_correction * memory_path_cycle_correction
T_store_corrected = T_store_base * memory_cycle_correction * memory_path_cycle_correction

T_cube_corrected   = T_cube_base   * compute_cycle_correction
T_vector_corrected = T_vector_base * vector_cycle_correction * alignment_cycle_correction
T_fix_corrected    = T_fix_base    * memory_cycle_correction * alignment_cycle_correction

T_compute_corrected =
    T_cube_corrected
  + T_vector_corrected
  - r_cv_strategy * cv_overlap_confidence * min(T_cube_corrected, T_vector_corrected)
  + T_fix_corrected

T_scalar_corrected = T_scalar_base * scalar_cycle_correction * small_tile_fragmentation_correction
T_sync_corrected   = T_sync_base   * sync_cycle_correction
```

overlap 只作用在 load/store 暴露部分和 cube-vector overlap：

```text
T_load_exposed  = T_load_corrected  * (1 - r_load_strategy  * overlap_confidence)
T_store_exposed = T_store_corrected * (1 - r_store_strategy * overlap_confidence)
```

总成本为：

```text
T_total =
    N_tiles / effective_parallelism * T_tile
  + T_sync_corrected
  + P_memory_capacity
  + P_shape
  + P_legality
```

这里 `P_legality` 专门表达 GraphSyncSolver / event reuse / CV pipeline legality 不确定性；它不再混入 sync cycles 的语义里。

### 0.1.5 和 V3.3 的区别

原 V3.3 的结构权重更像：

```text
结构证据 -> 多个 multiplier/reward/penalty -> total predicted cycles
```

同一个 scalar/sync-heavy 证据可能同时影响 scalar cost、sync cost、small tile penalty、overlap reward、CV reward、legality risk，容易出现 double counting。

V3.3.1 收敛为：

```text
结构证据 -> 对应分项 cycle correction -> 汇总 total predicted cycles
```

| 方面 | V3.3 | V3.3.1 |
|---|---|---|
| 总体语义 | structure-aware weighted cost | structure-aware corrected cycle estimate |
| 结构证据用途 | 可同时影响多个 cost/reward/penalty | 每类证据主要修正对应分项 cycles |
| scalar evidence | scalar、small tile、sync、overlap、CV reward 多路径影响 | 主要进入 scalar/control 和 fragmentation |
| sync evidence | sync multiplier、criticality multiplier、risk 可能叠加 | sync cycles 与 legality risk 分离 |
| overlap | 可能被 scalar/sync 较强打折 | 只做窄范围 confidence 修正 |
| DES artifact 权重 | 产物比例更强，容易主导 | MLIR 60% + artifact 40% 保守融合 |
| predicted_cycles 语义 | 更像 cycles-shaped ranking score | 更像 corrected component cycles sum |

更详细的公式、字段解释、样本解释和 V3.3 对比见 `cost_model_design_formula_explained.md` 或渲染后的 `cost_model_design_formula_explained_rendered.pdf`。

## 0.3 搜索质量审计说明（V3.2-stage2c）

在没有 profiling 数据时，当前版本新增 `--enable-search-quality-audit`，用于在紧凑候选空间上对 Beam Search 做两个基线对照：

- small-space exhaustive：小空间穷举，检查 Beam best 与紧凑空间全局最优之间的 gap；
- random baseline：固定随机种子和采样预算，检查 Beam Search 相对随机搜索是否更稳定。

审计结果写入 `search_audit.json` 的 `search_quality_audit` 字段，并在 Markdown/HTML 报告中摘要展示。该功能不证明真实硬件最优，只用于验证 Beam Search 在 bounded subspace 上的搜索质量。

## 0.2 搜索稳定性说明（V3.2-stage2b）

V3.2-stage2b 在 stage2a 的搜索空间包含性基础上，进一步加入 diversity-preserving Layer-1 Beam Search。Layer-1 frontier 现在不再只由 coarse cost Top-W 决定，而是由以下几部分合并得到：

```text
cost_topw + diversity representatives + pinned standard survivors + deterministic fallback
```

这样可以降低 expanded/full 搜索空间中由于候选更多导致 standard 好候选被粗筛挤掉的风险。每次运行会在 `search_audit.json` 和 HTML/Markdown 报告中记录 diversity 新增候选数、pinned standard survivors 数量、fallback 新增候选数和最终 Layer-1 kept 数量。

详细说明见 `STAGE2B_BEAM_SEARCH_STABILITY.md`。

## 0. 工程结构说明（Stage 3）

为了让代码仓从单文件 demo 逐步演进成可长期维护的项目，当前版本已经引入 `strategy_search/` 包结构，并保留原有 `auto_strategy_search.py` 作为兼容入口。

推荐入口仍然兼容旧命令：

```bash
python auto_strategy_search.py --kernel sample_input/fa_bad_inefficient.hivm.mlir --hardware-config configs/ascend_910b.json
```

也可以使用包形式入口：

```bash
python -m strategy_search.cli --kernel sample_input/fa_bad_inefficient.hivm.mlir --hardware-config configs/ascend_910b.json
```

当前模块边界如下：

| 模块 | 职责 | 说明 |
|---|---|---|
| `strategy_search.core` | 当前兼容核心实现 | 保留完整算法逻辑，保证行为不变 |
| `strategy_search.plans` | Plan / Feature 数据结构 | 导出 `StrategyConfig`, `KernelFeatures`, `TilingPlan` 等 |
| `strategy_search.parser` | IR 解析与证据抽取 | 导出 `parse_kernel_features`, `extract_mlir_evidence` 等 |
| `strategy_search.hardware` | 硬件容量、footprint、feasibility | 导出 `memory_cap_bytes`, `estimate_max_live`, `feasibility` 等 |
| `strategy_search.cost_model` | risk-aware analytical cost model | 导出 `estimate_cost`, `build_four_plan_bundle`, risk/penalty 相关函数 |
| `strategy_search.search` | 参数空间生成与搜索 | 导出 `auto_generate_search_space`, `build_layered_candidates` 等 |
| `strategy_search.report` | JSON/Markdown/HTML 报告输出 | 导出 `write_html_report`, `write_markdown_report` 等 |
| `strategy_search.rewrite` | annotation / sidecar rewrite bundle | 导出 `emit_strategy_rewrite_outputs` 等 |
| `strategy_search.cli` | 包形式 CLI 入口 | 支持 `python -m strategy_search.cli` |

注意：本阶段是**兼容优先的工程结构化**。为了避免一次性大拆造成行为漂移，核心实现暂时集中在 `strategy_search.core`，其他模块作为稳定 facade 暴露清晰 API。后续阶段可以继续把 `core` 中的实现逐步物理拆分到各模块中。


---

## 0.1 搜索空间稳定性说明（V3.2-stage2a）

当前版本新增了 **Stage2a 搜索空间稳定性机制**，目标是在不引入 profiling 数据、不改变 cost model 主公式的前提下，先解决 layered beam search 的候选空间稳定性问题。

核心改动包括：

| 机制 | 作用 | 输出位置 |
|---|---|---|
| `strategy_signature` | 为候选策略生成稳定签名，忽略易变的 `strategy_id`，用于 exact dedup 和回归测试 | `strategy_search.plans` |
| standard tile containment | `expanded/full` 搜索空间显式包含 `standard` tile 候选，避免更大空间反而丢掉代表点 | `effective_search_space.json` |
| standard Layer-1 pinning | 在 `expanded/full` 模式下，先计算 standard 模式的 Layer-1 survivor，并强制保留到 expanded Layer-1 frontier | `search_audit.json` |
| exact candidate dedup | 对完整四 Plan 策略按 `strategy_signature` 去重，避免完全重复候选进入排序 | `search_audit.json` |
| post-relax dedup | relax 后再次按 signature 去重，避免不同候选 relax 成同一个策略后重复进入 Top-K | `search_audit.json` |
| search audit | 记录搜索空间、Layer-1 pinning、候选去重和 relax 后去重信息 | `search_audit.json` / 报告摘要 |

这一步不是 Stage2b 的 diversity-preserving beam。Stage2a 的目标更基础：

```text
expanded/full 搜索空间不能因为候选更多而无意丢掉 standard 搜索空间的关键候选；
搜索过程中的 exact duplicate 要被识别和记录；
搜索审计信息要可追踪、可回归。
```

示例运行：

```bash
python -m strategy_search.cli \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --candidate-space expanded \
  --search-mode layered \
  --guided-mode off \
  --cost-risk-mode conservative \
  --cost-model-config configs/cost_model_conservative.json \
  --output-dir output_stage2a
```

关键审计文件：

```text
search_audit.json
```

其中会包含：

```json
{
  "stage": "V3.2-stage2a-search-space-stability",
  "standard_candidates_included": true,
  "layer1_stability_audit": {
    "policy": "cost_topw_plus_pinned_standard_layer1_survivors",
    "pinned_standard_after_topw": 11
  },
  "candidate_dedup_audit": {
    "dedup_key": "strategy_signature_without_strategy_id"
  },
  "post_relax_legal_dedup_audit": {
    "dedup_removed_after_relax": 588
  }
}
```

## 1. 项目定位与边界

### 1.1 当前已经实现

当前代码仓已经实现了以下能力：

| 能力 | 当前状态 | 说明 |
|---|---|---|
| MLIR 静态解析 | 已实现 | 解析 memref、memory scope、mmad、vector op、copy/fixpipe、sync op 等信息 |
| Current IR baseline 修正 | 已实现 | 不再使用人为构造 baseline，而是从输入 IR 恢复 `current_ir_estimated_strategy` |
| 四类 Plan 参数空间生成 | 已实现 | 自动生成 `TilingPlan / MultiBufferPlan / CVPipelinePlan / SyncPlan` 候选 |
| 硬件容量边界 gate | 已实现 | 检查 UB/L1/L0A/L0B/L0C/GM workspace 容量、tile 对齐、block_dim 边界 |
| Analytical cost model | 已实现 | 输出 `predicted_cycles` 和详细 `cost_breakdown` |
| 分层寻优 | 已实现 | 支持 `layered` 与 `exhaustive` 两种搜索模式 |
| 中文 HTML / Markdown 报告 | 已实现 | 适合汇报展示和工程审计 |
| 可选 strategy-to-HIVM rewrite bundle | 支持 | 输出 annotated IR、safe structural IR、pass config、edit script 等候选制品 |

### 1.2 当前不能过度承诺

当前 demo 不应该被描述为：

```text
完整生产级 HIVM compiler optimizer；
能够直接输出真实 optimized.hivm.mlir 并保证可编译运行；
能够给出真实 NPU cycles；
能够证明 GraphSyncSolver 的依赖正确性、死锁安全性和 event id 分配合法性。
```

更准确的定位是：

```text
这是一个 strategy-level optimizer / analytical search demo。
它能比较同一输入 kernel 下不同策略的相对优劣，解释四类 Plan 参数如何影响 cost 和硬件边界，
但 predicted_cycles 仍然是解析式估计，不是真机实测时间。
```

---

## 2. 整体运行流程

### 2.1 流程总览

```text
Step 1  输入 HIVM / NPUIR / MLIR kernel
        ↓
Step 2  解析 kernel 静态结构 KernelFeatures
        ↓
Step 3  恢复 current IR estimated strategy
        ↓
Step 4  根据 shape / memory / hardware 自动生成四类 Plan 参数空间
        ↓
Step 5  Layer-1：Tiling 粗筛，做容量、对齐、block_dim gate
        ↓
Step 6  Layer-2：组合 MultiBuffer / CVPipeline，重新估计 max-live 和 overlap
        ↓
Step 7  Layer-3：组合 SyncPlan，计算完整 predicted_cycles
        ↓
Step 8  选择 predicted_cycles 最低的合法候选
        ↓
Step 9  输出 JSON / Markdown / HTML 报告，以及可选 rewrite bundle
```

### 2.2 输入解析内容

输入文件可以是：

```text
.hivm.mlir
.npuir.mlir
.mlir
```

系统按文件内容解析，而不是只按后缀判断。主要抽取以下证据：

| 抽取信息 | 用途 |
|---|---|
| `memref<...>` shape / dtype / address space | 推断 problem shape、buffer 大小、存储层级、tile 证据 |
| `gm / ub / cbuf / cc / l0a / l0b / l0c` | 估计不同 memory scope 的 footprint 和 max-live |
| `hivm.hir.mmad / hivm.hir.mmadL1` | 识别 Cube 计算，推断 tile_m/tile_n/tile_k |
| `nd2nz / copy / load / store / fixpipe` | 识别搬运、layout transform 和 Cube 输出路径 |
| `vadd / vmul / vexp / vdiv / vreduce / softmax-like op` | 识别 Vector 计算和 CV pipeline 潜力 |
| `set_flag / wait_flag / pipe_barrier / sync_block_*` | 识别显式同步负担 |
| `multi_buffer = 2`、`ping/pong` | 判断输入 IR 是否已有 double buffer / staged buffer |
| `cube_loop / vector_loop` | 判断输入 IR 是否已有 CV pipeline 结构 |
| `hivm.sync = "graph_sync_solver"` | 判断输入 IR 是否已有 graph sync 方向的同步状态 |

### 2.3 Current IR baseline 的修正

旧版 demo 曾使用人为构造的 baseline，容易出现一个问题：即使把 optimized / target IR 作为输入，仍然可能显示虚高 speedup。

当前版本改为：

```text
current IR estimated strategy → best searched strategy
```

也就是说，系统会先根据输入 IR 当前已有结构恢复一个：

```text
current_ir_estimated_strategy
```

再计算：

```text
predicted_speedup_vs_current_ir_estimated
= current_ir_estimated_predicted_cycles / best_predicted_cycles
```

恢复规则包括：

| IR 可见特征 | current IR 策略恢复 |
|---|---|
| 输入 IR 中解析出的 tile shape | 作为 current tile |
| `multi_buffer = 2` 或 ping/pong buffer | `double_buffer=True` |
| `cube_loop / vector_loop` | `cv_pipeline_stage=2` |
| `hivm.sync="graph_sync_solver"` | 当前 IR 已有 graph sync 证据 |
| 显式 `set_flag/wait_flag/pipe_barrier` | 当前 IR 同步负担较重，cost 中保留同步开销 |
| 无显式 sync op | 当前 IR sync cost 较低 |

注意：`current_ir_estimated_predicted_cycles` 仍然是 analytical estimate，不是真机实测时间。

---

## 3. 四个参数 Plan 的设计

当前项目将策略空间显式拆成四类 Plan。这样做的好处是：每类参数的工程语义清楚，并且可以分别解释它们如何影响硬件容量、pipeline overlap、sync cost 和最终 predicted cycles。

---

### 3.1 TilingPlan

```text
TilingPlan = {
  tile_m,
  tile_n,
  tile_k,
  block_dim,
  loop_order,
  tail_strategy,
  reduce_tile_policy,
  layout_aware_tile
}
```

| 参数 | 取值来源/范围 | 工程含义 | 对 cost / gate 的影响 |
|---|---|---|---|
| `tile_m` | shape divisor、Cube alignment、常见 tile 值 | M 维 tile 大小 | 影响 L0A/L0C/UB 工作集、tile 数、Cube FLOPs |
| `tile_n` | shape divisor、Cube alignment、preferred tile_n | N 维 tile 大小 | 影响 L0B/L0C/UB 工作集、store bytes、tail penalty |
| `tile_k` | reduce 维、Cube K alignment、常见 tile 值 | K/reduce 维 tile 大小 | 影响 L0A/L0B/L1 输入工作集和 reduce loop |
| `block_dim` | 根据 tile 数和 core 数派生 | 并行 block 数 | 影响 effective parallelism；受 core 数和 tile 数限制 |
| `loop_order` | `outer_mnk / outer_mkn / outer_nmk` | 外层 tile loop 顺序 | 影响 locality 和 load 修正系数 |
| `tail_strategy` | `mask_or_pad / peel / pad` | shape 不整除 tile 时的尾块处理 | pad 增加搬运，peel 降低搬运但增加控制成本 |
| `reduce_tile_policy` | `full_k / half_k` | reduce 维是否拆小 | `half_k` 可降低单 tile 容量压力，但增加调度/循环成本 |
| `layout_aware_tile` | `true / false` | 是否偏好 layout/Cube-friendly tile | 影响 load/store 修正和 shape regularization |

TilingPlan 是四类 Plan 的基础，因为 tile 先决定单 tile 工作集、tile 数、L0/L1/UB 占用和并行粒度。后续 MultiBuffer 和 CVPipeline 是否可行，都依赖当前 tile 是否还有足够片上存储余量。

---

### 3.2 MultiBufferPlan

```text
MultiBufferPlan = {
  double_buffer,
  multibuffer_template,
  stage_buffer_policy,
  buffer_multipliers_json,
  ub_multiplier,
  l1_multiplier
}
```

| 参数 | 当前含义 | 对 cost / gate 的影响 |
|---|---|---|
| `double_buffer` | 是否启用高层 double buffer / ping-pong 策略 | 提高 load/store overlap，但增加 live buffer 压力 |
| `multibuffer_template` | `M0_no_multibuffer / M1_input_double_buffer / M4_cv_stage_aware_multibuffer` 等 | 影响 `load_overlap_ratio`、`store_overlap_ratio` 和轻量 template overhead |
| `stage_buffer_policy` | `none / ub_stage / l1_stage / l1_reuse / gm_workspace` 等 | 决定 stage buffer 主要压 UB、L1 还是 fallback 到 GM workspace |
| `buffer_multipliers_json` | 对代表性 local buffer 使用 `nbuf_b ∈ {1,2}` | 具体 buffer 级 ping-pong 额外副本进入 max-live 和 overlap bonus |
| `ub_multiplier / l1_multiplier` | 兼容字段 | 当前主要保留字段语义，实际搜索更依赖 per-buffer multiplier |

说明：per-buffer multiplier 没有完整枚举所有 buffer 的 `2^N` 组合，而是筛选代表性 local buffer 做受控候选生成，避免组合爆炸。

MultiBufferPlan 的核心 trade-off 是：

```text
更高 overlap  ↔  更高 UB/L1/L0 live buffer 压力
```

---

### 3.3 CVPipelinePlan

```text
CVPipelinePlan = {
  cv_pipeline_stage,
  cv_pipeline_template,
  enable_mixed_cv,
  tile_mix_cube_loop,
  tile_mix_vector_loop,
  auto_cv_balance,
  producer_consumer_distance
}
```

| 参数 | 当前含义 | 对 cost / gate 的影响 |
|---|---|---|
| `cv_pipeline_stage` | `1 / 2 / 4`，分别表示无 pipeline、stage-2 pipeline、更激进 pipeline | 提高 Cube/Vector overlap，但增加 stage buffer 压力和 warmup/drain |
| `cv_pipeline_template` | `P0_no_cv_pipeline / P1_stage2_basic / P2_stage2_balanced / P_PREFILL_LARGE_SBS_REUSE` 等 | 影响 `cv_overlap_ratio`、warmup/drain、template overhead |
| `enable_mixed_cv` | 是否允许 Cube-heavy / Vector-heavy 混合调度 | 影响 Cube/Vector overlap 建模 |
| `tile_mix_cube_loop` | Cube loop 在混合调度中的相对粒度 | 影响 CV mix balance penalty |
| `tile_mix_vector_loop` | Vector loop 在混合调度中的相对粒度 | 影响 CV mix balance penalty |
| `auto_cv_balance` | 是否根据 Cube/Vector 压力自动平衡 overlap | 影响 `cv_overlap_ratio` 的修正 |
| `producer_consumer_distance` | Cube 产出与 Vector 消费之间的 pipeline 距离 | 影响 overlap 折减和 producer-consumer 调度开销 |

CVPipelinePlan 的核心目标是让 Cube 和 Vector 不再完全串行，而是形成软流水：

```text
Cube compute 和 Vector compute 可重叠的部分，最多不超过 min(tau_cube, tau_vector)。
```

---

### 3.4 SyncPlan

```text
SyncPlan = {
  sync_policy,
  sync_template,
  barrier_level,
  event_reuse,
  sync_granularity,
  event_id_policy,
  sync_motion
}
```

| 参数 | 当前含义 | 对 cost / gate 的影响 |
|---|---|---|
| `sync_policy` | `keep_existing / graph_sync_solver` | 决定同步成本是否保留现有模式或进入 graph sync 抽象估计 |
| `sync_template` | `Y0_keep_existing / Y1_conservative_barrier / Y2_graph_sync_solver / Y3_event_reuse` | 影响 barrier/event 估计数量、stall factor、fixed overhead |
| `barrier_level` | 同步保守程度 | 影响 barrier penalty |
| `event_reuse` | 是否复用 event id | 降低 set/wait event 负担 |
| `sync_granularity` | `op / tile / stage` | 同步粒度越粗，理论次数越少，但真实正确性需要 compiler-side proof |
| `event_id_policy` | `keep / reuse / compact` 等抽象字段 | 影响 event stall 和同步开销 |
| `sync_motion` | `none / local_move` 等抽象字段 | 估计局部 sync motion 的收益 |

注意：当前 demo 只能估计 sync cost，不能证明 graph sync 的依赖正确性、死锁安全性或 event id 分配合法性。

---

## 4. 参数空间自动生成

参数空间不是手写一个固定模板，也不是完整枚举 HIVM 全部 pass，而是结合输入 MLIR、硬件配置和搜索密度自动生成。

支持三种候选密度：

| 参数 | 含义 |
|---|---|
| `--candidate-space standard` | 快速代表性搜索，适合 smoke test |
| `--candidate-space expanded` | 更密集的工程候选，推荐用于 demo 展示 |
| `--candidate-space full` | 更大的离散网格，可能较慢 |

支持两种搜索方式：

| 参数 | 含义 |
|---|---|
| `--search-mode layered` | 分层 / beam search，默认推荐 |
| `--search-mode exhaustive` | 对 demo 搜索空间做更展开的枚举，但不等价于真实 compiler oracle |

### 4.1 block_dim 的派生逻辑

`block_dim` 不是完全自由变量，而是由 tile 数量和硬件 core 数共同派生：

```text
block_dim <= available_cores
block_dim <= num_tiles
```

这样避免两类不合理候选：

| 不合理情况 | 原因 |
|---|---|
| `block_dim` 大于硬件可用 core 数 | 超出真实并行资源 |
| `block_dim` 远大于 tile 数 | 大量 block 没有实际工作，parallelism 估计虚高 |

程序会优先保留 full-core、half-core、quarter-core、tile-count boundary 等代表性点，而不是盲目枚举所有整数。

### 4.2 四类 Plan 不是独立打分

虽然参数空间被拆成四类 Plan，但最终 cost model 是统一的：

```text
x = (T, M, P, Y)
predicted_cycles = CostModel(x)
```

也就是说，四个 Plan 不是各自独立打分后加权投票，而是共同改变同一组中间变量：

```text
num_tiles
max_live
load/store bytes
Cube/Vector pipeline
sync cost
overlap ratio
effective parallelism
memory pressure penalty
shape regularization penalty
```

---

## 5. 硬件边界约束

硬件边界不是 cost model 的普通扣分项，而是候选进入排序之前必须通过的 legality gate。核心原则是：

```text
先保证候选 strategy 在真实片上存储层级中“放得下、对得齐、并行度不虚高”，
再允许 cost model 比较性能优劣。
```

### 5.1 硬件配置来源

硬件配置来自 JSON，例如：

```bash
configs/ascend_910b.json
```

程序从 `hardware_config.json` 的 `memory_spaces` 字段读取片上存储容量：

| Scope | 配置字段 | 当前含义 |
|---|---|---|
| `ub` | `memory_spaces.ub.size_kb` | Vector 计算、临时张量、mask、stage buffer 的主要容量边界 |
| `l1` / `cbuf` | `memory_spaces.l1.size_kb` | Cube 输入 staging、L1 reuse、部分 K/V staging 的容量边界 |
| `l0a` | `memory_spaces.l0a.size_kb` | Cube 左输入 tile 的容量边界 |
| `l0b` | `memory_spaces.l0b.size_kb` | Cube 右输入 tile 的容量边界，通常对 `tile_n × tile_k` 敏感 |
| `l0c` / `cc` | `memory_spaces.l0c.size_kb` | Cube accumulator / output tile 的容量边界 |
| `gm_ws` | `workspace_model` 或默认 workspace budget | GM workspace fallback / spill 的容量边界 |

主要代码入口：

```text
memory_cap_bytes(hw, space)
estimate_max_live(candidate, kernel_features, hw)
feasibility(candidate, max_live, hw)
```

### 5.2 max-live 估计公式

对一个候选策略：

```text
x = (T, M, P, Y)
```

每个 memory scope 的利用率为：

```text
util_S(x) = estimated_max_live_S(x) / capacity_S
```

其中：

```text
S ∈ {UB, L1, L0A, L0B, L0C, GM_WS}
```

max-live 估计采用：

```text
estimated_max_live_S(x)
= align_S( tile_working_set_S(T,M,P) + 0.08 × static_max_live_S(IR) )
```

含义如下：

| 项 | 说明 |
|---|---|
| `tile_working_set_S(T,M,P)` | 由 tile 大小、double buffer、CV stage、per-buffer multiplier、stage buffer policy 推导出的当前 tile 工作集 |
| `static_max_live_S(IR)` | 从输入 MLIR local buffer 中解析出的静态 max-live 近似 |
| `0.08 × static_max_live_S(IR)` | kernel 复杂度修正项，避免把静态 buffer 和合成 tile buffer 完全重复计算 |
| `align_S` | 按 scope 对齐：UB/L1 通常 32B，L0A/L0B/L0C 使用更粗的 512B 对齐近似 |

核心 working set 估计如下：

| Scope | 估计逻辑 | 主要受哪些 Plan 影响 |
|---|---|---|
| `l1` | `(tile_m×tile_k + tile_k×tile_n) × elem_bytes × double_buffer_multiplier × l1_multiplier` | `TilingPlan`、`MultiBufferPlan`、`reduce_tile_policy`、`stage_buffer_policy` |
| `l0a` | `tile_m × tile_k × elem_bytes` | `tile_m`、`tile_k` |
| `l0b` | `tile_k × tile_n × elem_bytes` | `tile_k`、`tile_n` |
| `l0c` | `tile_m × tile_n × accumulator_bytes` | `tile_m`、`tile_n` |
| `ub` | `tile_m × tile_n × vector/input/output staging`，再乘以 double buffer / stage / reuse 修正 | `tile_m`、`tile_n`、`double_buffer`、`cv_pipeline_stage`、`stage_buffer_policy` |
| `gm_ws` | CV handoff / spill fallback 对应的 off-chip workspace | `stage_buffer_policy=gm_workspace`、`cv_pipeline_stage`、`active_blocks` |

当前主路径近似：

```text
elem_bytes = 2          # bf16/fp16
accumulator_bytes = 4   # fp32 accumulator
```

### 5.3 硬约束 hard gate

候选必须满足：

```text
for S in {UB, L1, L0A, L0B, L0C, GM_WS}:
    estimated_max_live_S(x) <= capacity_S
```

或者等价地：

```text
max_S util_S(x) <= 1
```

若任意 scope 出现：

```text
util_S(x) > 1
```

该候选直接非法，不进入最终 ranking。

### 5.4 对齐与并行资源边界

当前 Ascend 910B 配置中常用 Cube/fractal 对齐为：

```text
tile_m % 16 == 0
tile_n % 16 == 0
tile_k % 16 == 0
```

同时检查基础搬运对齐：

```text
tile_n × elem_bytes 需要 32B 对齐
tile_k × elem_bytes 需要 32B 对齐
```

并行资源约束为：

```text
block_dim <= min(available_cores, num_tiles)
```

因此，当前硬件边界约束可以总结为：

| 约束类型 | 数学表达 | 作用 |
|---|---|---|
| 片上容量约束 | `estimated_max_live_S(x) <= capacity_S` | 防止 UB/L1/L0A/L0B/L0C/GM workspace overflow |
| Cube 对齐约束 | `tile_m,tile_n,tile_k` 满足 16 对齐 | 保证 tile 适合 Cube/fractal 计算 |
| 搬运对齐约束 | `tile_n×elem_bytes`、`tile_k×elem_bytes` 满足 32B 对齐近似 | 防止明显不合理的 DMA/ND2NZ 搬运 shape |
| 并行资源约束 | `block_dim <= min(available_cores, num_tiles)` | 防止 block 数超过 core 数或超过实际 tile 数 |
| GM workspace 约束 | `workspace_bytes(x) <= capacity_GM_WS` | 防止把 CV stage handoff / spill fallback 无限制放到 HBM |

### 5.5 软惩罚 soft penalty

如果候选没有超过容量，但某个 scope 利用率过高，则进入 memory pressure soft penalty，而不是直接拒绝：

```text
if util_S > threshold_S:
    penalty_S = alpha_S × ((util_S - threshold_S) / (1 - threshold_S))^2
else:
    penalty_S = 0
```

实际实现中还会做 per-scope cap：

```text
penalty_S = min(cap_S, penalty_S)
```

最终：

```text
memory_pressure_penalty = Σ_S penalty_S
```

区别如下：

| 情况 | 当前处理 |
|---|---|
| `util_S > 1` | hard reject，候选非法 |
| `threshold_S < util_S <= 1` | 候选合法，但加入 memory pressure soft penalty |
| `util_S <= threshold_S` | 候选合法，通常不加资源压力惩罚 |

### 5.6 relax 逻辑

如果候选超过硬件容量，demo 会尝试有限 relax，而不是马上全部丢弃。大致顺序是：

```text
level2 reuse → level1 → level0 → inplace
关闭 double buffer / 清空 per-buffer multiplier
降低 cv_pipeline_stage
缩小 tile_n
缩小 tile_k
缩小 tile_m
```

对应工程直觉是：

```text
先降低额外 buffer 和 pipeline 压力，再缩小 tile。
```

成功 relax 后的候选会记录到：

```text
relaxed_candidates.json
```

完全无法修复的候选会进入：

```text
rejected_candidates.json
```

---

## 6. Cost model 设计与公式展开

当前 cost model 的作用是对合法候选排序和解释优化方向。它不是精确性能模型，但会把输入 IR 的静态结构、四类 Plan 参数和硬件配置合成一个：

```text
predicted_cycles(x)
```

### 6.1 cost model 输入

| 输入 | 来源 | 作用 |
|---|---|---|
| `KernelFeatures` | 从 MLIR 解析 | 提供 shape、mmad 数、vector op 数、sync op 数、fixpipe/copy 证据 |
| `StrategyConfig` | 搜索空间生成 | 表示当前候选的四类 Plan 参数 |
| `hardware_config` | JSON 配置 | 提供 memory capacity、bandwidth、cube/vector throughput、core 数、校准参数 |
| `max_live` | `estimate_max_live` | 提供 UB/L1/L0A/L0B/L0C/GM workspace 利用率，用于 hard gate 和 soft penalty |
| optional DES / trace | `optional_profiles/*.json` | 作为 soft evidence 修正 pipeline fraction / sync scale，不作为真实 baseline |

### 6.2 总公式

当前主模型是：

```text
predicted_cycles(x)
= num_tiles(x) × steady_tile_time(x) / effective_parallelism(x)
  + sync_cost(x)
  + memory_pressure_penalty(x)
  + shape_regularization_penalty(x)
```

其中：

```text
x = (T, M, P, Y)
```

四类 Plan 共同影响同一个总公式，而不是分别独立评分。

---

### 6.3 Tile 数量

设整体问题规模为：

```text
M_total, N_total, K_total
```

当前候选 tile 为：

```text
tile_m, tile_n, tile_k
```

则 tile 数量为：

```text
num_tiles
= ceil(M_total / tile_m)
× ceil(N_total / tile_n)
× ceil(K_total / tile_k)
× outer_iterations
```

`M_total/N_total/K_total` 优先来自 MLIR 解析和 `search_space_demo.json` 中的 `problem_shape_hint`。

---

### 6.4 Load / Store 字节数与时间

基础搬运字节数：

```text
load_bytes
≈ (tile_m×tile_k + tile_k×tile_n + tile_m×tile_n) × elem_bytes

store_bytes
≈ tile_m×tile_n × elem_bytes
```

对应 cycles：

```text
tau_load
= load_bytes / bandwidth_mte2 + dma_startup

tau_store
= store_bytes / bandwidth_mte3 + dma_startup
```

其中：

```text
elem_bytes = 2
```

主要对应 bf16/fp16 主路径。

TilingPlan 和 DMA/layout 相关字段会对 load/store 做轻量修正：

| 参数 | 修正含义 |
|---|---|
| `reduce_tile_policy=half_k` | 单 tile 输入搬运略降，但 reduce loop 增多 |
| `layout_aware_tile=True` | 偏好 ND/NZ/Cube-friendly tile，load/store 略降 |
| `loop_order=outer_mkn` | 偏好 K locality，load 略降 |
| `tail_strategy=pad` | pad 会增加搬运 |
| `tail_strategy=peel` | peel 略减搬运但增加控制成本 |

---

### 6.5 Cube compute cost

Cube 计算按矩阵乘法 FLOPs 估计：

```text
flops_cube
= 2 × tile_m × tile_n × tile_k × max(1, num_mmad)
```

Cube 时间为：

```text
tau_cube
= flops_cube / cube_flops_per_cycle + cube_startup
```

其中：

```text
cube_flops_per_cycle
= cube_tflops_fp16 × 10^12 / frequency_hz
```

`cube_tflops_fp16` 和 `frequency_hz` 来自硬件配置。

---

### 6.6 Vector cost

Vector cost 按 vector op 数量和 tile 面积估计：

```text
vector_elements
= tile_m × tile_n × max(1, num_vector_ops)
```

基础时间为：

```text
tau_vector
= vector_elements / vector_width_elements + vector_startup
```

重型 vector op 会额外放大：

```text
heavy = 3×num_vexp + 2×num_vdiv + num_vreduce

tau_vector := tau_vector × (1 + 0.04 × heavy)
```

当前权重直觉：

| op 类型 | 当前处理 |
|---|---|
| `vexp` | 权重最高，约视为 simple op 的 4 倍影响 |
| `vdiv` | 中等偏重 |
| `vreduce` | 轻度额外开销 |
| `vadd/vmul/vsub` | simple op 基准 |

---

### 6.7 Fixpipe cost

Fixpipe 按 accumulator 输出搬运近似：

```text
tau_fix
= num_fixpipe × (tile_m × tile_n × accumulator_bytes)
  / bandwidth_mte3 × 0.20
```

其中：

```text
accumulator_bytes = 4
```

`0.20` 是当前解析式模型中的保守折算系数，用于表示 fixpipe 不完全等价于一次完整 store。

---

### 6.8 Cube/Vector pipeline 合成时间

如果没有 CV overlap，则：

```text
tau_cube_vector
= tau_cube + tau_vector + tau_fix
```

若启用 CV pipeline，则：

```text
tau_cube_vector
= tau_cube + tau_vector
  - cv_overlap × min(tau_cube, tau_vector)
  + tau_fix
```

含义是：Cube 和 Vector 可重叠部分最多不能超过两者中较短的一段。

`cv_overlap` 由 CVPipelinePlan 决定，并会受到以下因素影响：

| 参数 | 影响 |
|---|---|
| `cv_pipeline_stage` | stage 越深，理论 overlap 越高，但 warmup/drain 和容量压力也更高 |
| `cv_pipeline_template` | 不同模板给不同基础 overlap、调度开销和 warmup/drain |
| `enable_mixed_cv` | 允许 Cube-heavy / Vector-heavy 混合调度 |
| `auto_cv_balance` | 根据 Cube/Vector 压力轻度调节 overlap |
| `tile_mix_cube_loop / tile_mix_vector_loop` | 若 Cube/Vector 粒度不平衡，会进入 mix balance penalty |
| `producer_consumer_distance` | 距离过远会折减 overlap 并增加调度开销 |

---

### 6.9 Double buffer 后的暴露搬运时间

load/store overlap 后的暴露时间：

```text
load_exposed
= tau_load × (1 - load_overlap_ratio)

store_exposed
= tau_store × (1 - store_overlap_ratio)
```

`load_overlap_ratio` 和 `store_overlap_ratio` 主要由 MultiBufferPlan 决定：

| 参数 | 影响 |
|---|---|
| `double_buffer=True` | 提高 load/store overlap |
| `multibuffer_template=M1_input_double_buffer` | 增强输入双缓冲 overlap |
| `multibuffer_template=M4_cv_stage_aware_multibuffer` | 进一步考虑 CV stage aware overlap |
| `buffer_multipliers_json` | 对具体 local buffer 的 ping-pong 额外增加 overlap bonus |
| `stage_buffer_policy` | UB/L1/GM stage 不同，会影响 overlap 和 workspace cost |

如果启用了 double buffer 或 CV pipeline：

```text
steady_tile_time
= max(load_exposed, tau_cube_vector, store_exposed)
  + workspace_exposed
  + warmup_drain
  + template_schedule_overhead
```

如果没有启用 overlap：

```text
steady_tile_time
= tau_load + tau_cube_vector + tau_store
  + workspace_exposed
  + template_schedule_overhead
```

其中：

```text
warmup_drain
= (tau_load + tau_store + tau_cube_vector + workspace_exposed)
  × warmup_drain_factor
```

### 6.10 资源压力对 overlap 的折减

为了避免高资源利用率下 overlap 过度乐观，当前模型会根据 UB/L1/L0B/L0C 等 scope 的利用率降低 overlap：

```text
overlap_ratio := overlap_ratio × overlap_pressure_factor
```

也就是说，如果某个候选虽然没有 overflow，但 UB 或 L0B 已经非常紧张，那么它的 double buffer / CV pipeline overlap 不会被完全乐观兑现。

---

### 6.11 GM workspace fallback / spill cost

V2.8.7 之后，`gm_workspace` 被建模为更接近真实编译语义的 fallback / spill resource。它不是普通优化策略，也不是免费扩大 UB 的方式。

搜索优先级是：

```text
优先：UB stage buffer / L1 reuse
其次：调整 tile、降低 stage、降低 multibuffer 压力
最后：只有片上 stage-buffer 方案不可行时，才允许 GM workspace fallback
```

当候选满足：

```text
cv_pipeline_stage > 1
stage_buffer_policy = gm_workspace
```

会估算：

```text
handoff_bytes_per_stage
≈ tile_m × tile_n × elem_bytes × handoff_tensor_count
  + tile_m × tile_n × acc_bytes × partial_output_tensor_count × 0.25

workspace_bytes
= align32(handoff_bytes_per_stage × (stage - 1) × active_blocks)

workspace_traffic_per_tile
= handoff_bytes_per_stage × (stage - 1) × read_write_multiplier
```

并加入 hard gate：

```text
workspace_bytes <= capacity_GM_WS
workspace_bytes <= capacity_GM_WS × max_workspace_utilization
```

同时，如果片上方案可行，则拒绝 GM workspace fallback：

```text
if stage_buffer_policy == gm_workspace
   and require_onchip_infeasible == true
   and any(policy in {ub_stage, l1_reuse, none} is feasible):
       reject gm_workspace candidate
```

GM workspace read/write 会复用 MTE2/MTE3 通道，因此不是独立 lane，而是暴露 spill/fallback 代价：

```text
workspace_raw
= workspace_read_bytes / bandwidth_mte2
  + workspace_write_bytes / bandwidth_mte3
  + workspace_startup_cycles

workspace_exposed
= workspace_raw
  × (1 - workspace_overlap_ratio)
  × workspace_penalty_factor
```

所以 steady tile time 中是加法：

```text
steady_tile_time
= max(load_exposed, tau_cube_vector, store_exposed)
  + workspace_exposed
  + warmup_drain
  + template_schedule_overhead
```

---

### 6.12 模板类参数的 cost 映射：V3.0.1 重点

V3.0.1 修正了一个关键问题：template/hint 类参数如果只改变字段名、不改变 cost，就会导致 Top candidates 大量重复，看起来“在寻优”，但实际上参数没有真正影响模型。

当前原则是：

```text
只有当参数能改变 predicted cost、hardware gate 或最终 rewrite 行为时，才应作为有效寻优参数。
```

V3.0.1 将以下参数显式映射进 cost model：

| 参数 | 进入 cost model 的方式 |
|---|---|
| `multibuffer_template` | 影响 `load_overlap_ratio`、`store_overlap_ratio`，并增加轻量 per-tile schedule overhead |
| `cv_pipeline_template` | 影响 `cv_overlap_ratio`、`warmup_drain_factor` 和 CV 调度开销 |
| `tile_mix_cube_loop` / `tile_mix_vector_loop` | 影响 `tile_mix_balance_penalty` |
| `producer_consumer_distance` | 影响 CV overlap 折减和 `producer_consumer_distance_penalty` |
| `sync_template` | 影响 estimated barrier/event 数量、stall factor 和 fixed sync overhead |
| `event_id_policy` | 影响 event stall 和 event reuse 收益 |
| `sync_motion` | 影响同步移动收益估计 |

模板调度开销在总 tile time 中体现为：

```text
template_schedule_overhead
= mb_template_overhead
  + cv_template_overhead
  + tile_mix_penalty_cycles
  + producer_consumer_penalty_cycles
```

其中：

```text
mb_template_overhead
= (tau_load + tau_store) × mb_template_schedule_overhead_ratio

cv_template_overhead
= tau_cube_vector × cv_template_schedule_overhead_ratio

tile_mix_penalty_cycles
= tau_cube_vector × tile_mix_balance_penalty

producer_consumer_penalty_cycles
= tau_cube_vector × producer_consumer_distance_penalty
```

这样可以避免“模板字段不同但 predicted_cycles 完全相同”的大量重复候选。

---

### 6.13 Sync cost

同步成本来自输入 IR 中解析出的同步信号：

```text
raw_sync_ops
= num_pipe_barrier + num_set_flag + num_wait_flag + sync_block_ops
```

若候选使用 `sync_policy=keep_existing`，则基本保留原有同步负担。若使用 `graph_sync_solver`，则通过抽象 multiplier 估计 barrier/set/wait 减少效果。

当前公式为：

```text
sync_cost
= (num_barrier_estimated × barrier_unit_cost
   + (num_set_flag_estimated + num_wait_flag_estimated) × event_unit_cost)
  × stall_factor
  × sync_scale
  + template_fixed_overhead_cycles
```

其中：

```text
barrier_unit_cost = min(150, cycles_per_inner_iteration / 50)
event_unit_cost = 8
```

各参数影响如下：

| 参数 | 影响 |
|---|---|
| `sync_policy` | 决定保留原 sync 还是使用 graph sync 抽象估计 |
| `sync_template` | 改变 estimated barrier/event 数量、stall factor、fixed overhead |
| `barrier_level` | 控制 barrier 保守程度 |
| `event_reuse=True` | 降低 set/wait 负担 |
| `sync_granularity=op/tile/stage` | 粒度越粗，理论同步次数越少，但真实正确性需要 compiler-side proof |
| `event_id_policy=reuse/compact/keep` | 抽象估计 event id 复用收益 |
| `sync_motion=local_move` | 抽象估计局部同步移动收益 |
| optional DES sync evidence | 可作为 `sync_scale` 修正，不替代真实 GraphSyncSolver |

---

### 6.14 有效并行度

`block_dim` 不能直接当成有效并行度。当前模型会考虑 tile 数、core 数、waves 和 tail efficiency：

```text
active_blocks
= min(block_dim, available_cores, ceil(num_tiles))

waves
= ceil(num_tiles / active_blocks)

tail_efficiency
= num_tiles / (waves × active_blocks)

effective_parallelism
= active_blocks × tail_efficiency
```

这样可以避免：

```text
tile 数只有 8，但 block_dim 设置为 40，于是虚假获得 40 倍并行度。
```

---

### 6.15 Shape regularization penalty

为了避免 cost model 盲目偏好“刚好能塞进硬件的大 tile”，当前版本保留轻量 shape regularization，但已经取消原来的固定大额跳变惩罚。

当前 shape penalty 是连续、低权重、可封顶的 soft regularization：

```text
shape_regularization_penalty
= tail_penalty
  + irregular_tile_n_penalty
  + large_tile_n_penalty
```

尾块惩罚：

```text
tail_fraction
= min(tail, tile_n - tail) / tile_n

tail_penalty
= min(cap, alpha × tail_fraction^power)
```

不规则 tile_n 惩罚：

```text
distance_fraction
= abs(tile_n - nearest_preferred_tile_n)
  / max(64, tile_n, nearest_preferred_tile_n)

irregular_tile_n_penalty
= min(cap, alpha × distance_fraction^power)
```

过大 tile_n 惩罚：

```text
large_tile_n_penalty
= min(cap, alpha × ((tile_n - large_tile_n_soft_cap) / 64)^power)
```

这三项只应理解为轻量形状正则项，而不是 benchmark 含义的真实耗时。如果报告中 shape penalty 贡献过大，应优先审查 cost model calibration。

---

### 6.16 Cost breakdown 字段解释

`cost_breakdown.json` 中会保存以下关键字段：

| 字段 | 含义 |
|---|---|
| `per_tile_load_exposed` | overlap 后仍暴露的 load 时间 |
| `per_tile_store_exposed` | overlap 后仍暴露的 store 时间 |
| `per_tile_workspace_exposed` | GM workspace 读写后仍暴露的时间；未使用 workspace 时为 0 |
| `gm_workspace_bytes` | 该候选估计的 GM workspace live bytes |
| `gm_workspace_bytes_per_tile_total` | 每 tile workspace 读写总流量 |
| `per_tile_cube_vector_pipeline` | Cube/Vector/fixpipe 合成时间 |
| `template_schedule_overhead` | V3.0.1 中模板类参数引入的轻量调度开销 |
| `mb_template_overhead` | MultiBuffer 模板开销 |
| `cv_template_overhead` | CVPipeline 模板开销 |
| `tile_mix_penalty_cycles` | Cube/Vector tile mix 不平衡惩罚 |
| `producer_consumer_penalty_cycles` | producer-consumer 距离惩罚 |
| `parallelized_tile_cycles` | tile 时间除以有效并行度后的主体成本 |
| `sync_cost` | 同步成本 |
| `memory_pressure_penalty` | 资源压力惩罚 |
| `shape_regularization_penalty` | tile 形状正则惩罚 |
| `overlap_pressure_factor` | 高资源压力下 overlap 被压低的比例 |
| `tail_efficiency` | waves 尾部利用率 |

---

## 7. 寻优模式策略

### 7.1 优化目标

最终选择规则非常简单：

```text
best = argmin_x predicted_cycles(x)
subject to HardwareGate(x) = PASS
```

也就是说，guided mode 或诊断信息不会直接指定最优解；最终仍然由同一个 cost model 的 `predicted_cycles` 最小化决定。

---

### 7.2 Layered search

默认推荐：

```bash
--search-mode layered
```

它不是一次性对所有参数做笛卡尔积暴力枚举，而是拆成三层：

```text
Layer 1: Tiling 粗筛
Layer 2: MultiBuffer / CVPipeline allocation
Layer 3: SyncPlan refinement + 完整 cost 排序
```

对应代码入口：

```text
search_tiling_fusion(...)  # Layer 1
alloc_overlap(...)         # Layer 2
refine_inner(...)          # Layer 3
```

### 7.3 Layer 1：先找合法且有潜力的 tile

Layer 1 主要枚举：

```text
tile_m, tile_n, tile_k, block_dim,
loop_order, tail_strategy, reduce_tile_policy, layout_aware_tile
```

这一层只使用 single-buffer 近似做快速筛选：

```text
estimated_max_live_S(single_buffer) <= capacity_S
```

同时检查：

```text
Cube tile alignment
DMA basic alignment
block_dim <= min(available_cores, num_tiles)
```

粗 cost 近似为：

```text
coarse_cost
= num_tiles × (tau_load + max(tau_cube, tau_vector, tau_fix) + tau_store)
  + memory_pressure_penalty
  + shape_regularization_penalty
```

这一层的目标不是最终精确排序，而是排除明显不合法或明显低潜力的 tile。

### 7.4 Layer 2：在好 tile 上分配 overlap 机制

Layer 2 在 Layer 1 保留下来的 tile 上继续枚举：

```text
double_buffer
multibuffer_template
per-buffer multiplier
cv_pipeline_stage
cv_pipeline_template
stage_buffer_policy
load/store/CV overlap ratio
```

核心问题是：

```text
这个 tile 上，是否值得引入 double buffer？
是否有足够 UB/L1 余量支持 CV pipeline？
per-buffer multiplier 取 2 后是否会导致某个 scope overflow？
```

Layer 2 会重新估算：

```text
estimated_max_live_S(T, M, P)
= tile_working_set_S(T, M, P) + static_lifetime_correction_S(IR)
```

如果 double buffer、stage buffer 或 per-buffer multiplier 导致 overflow，该 allocation 会被拒绝或尝试 relax。

### 7.5 Layer 3：同步策略细化并完整排序

Layer 3 在已经通过容量检查的 `(T,M,P)` 上枚举 SyncPlan：

```text
sync_policy
sync_template
barrier_level
event_reuse
sync_granularity
event_id_policy
sync_motion
```

然后对完整候选：

```text
x = (T, M, P, Y)
```

计算完整：

```text
predicted_cycles(x)
```

最终选择 predicted_cycles 最低的合法候选。

### 7.6 为什么可以分层寻优

分层寻优成立的工程原因是四类 Plan 有明显依赖关系：

| 依赖关系 | 含义 |
|---|---|
| `TilingPlan` 决定基础工作集 | tile_m/tile_n/tile_k 先决定 L0A/L0B/L0C/UB/L1 基本占用 |
| `MultiBufferPlan` 依赖 tile | double buffer 和 per-buffer multiplier 的额外容量必须建立在某个 tile 的 working set 上 |
| `CVPipelinePlan` 依赖 tile 和 buffer 余量 | stage 越深，UB/L1 压力越大，所以必须知道 tile 和 buffer 后才能判断是否合法 |
| `SyncPlan` 对容量影响相对较小 | sync 主要影响 stall/cost，不主要改变 tile working set，因此适合放在最后细化 |

优点：

| 优点 | 说明 |
|---|---|
| 避免组合爆炸 | per-buffer multiplier 和 CV 模板如果全量笛卡尔积会快速膨胀 |
| 保留主要耦合关系 | Layer 2 会基于 Layer 1 的 tile 重新计算容量，不是简单独立打分 |
| 结果更可解释 | 报告能分别说明 tile、buffer/pipeline、sync 三层的作用 |

### 7.7 Exhaustive 与 guided mode

`--search-mode exhaustive` 用于小 kernel 或对照测试。它只是对 demo 搜索空间做更展开的枚举，不等价于完整 HIVM compiler oracle。

`--guided-mode` 可以作为诊断引导搜索空间的 soft bias。它可以帮助优先探索符合诊断方向的候选，但不能让非法候选通过，也不能压过 cost model。最终选择仍然是：

```text
min predicted_cycles among legal candidates
```

---

## 8. 输出文件与可视化展示

运行后会在 `--output-dir` 下生成：

| 文件 | 内容 | 怎么看 |
|---|---|---|
| `strategy_search_report.html` | 中文可视化报告 | 最适合汇报展示，直接浏览器打开 |
| `strategy_search_report.md` | 中文 Markdown 报告 | 适合粘贴到文档或代码评审 |
| `search_report.json` | 总报告 JSON | 包含 current IR、best strategy、top-k、search stats |
| `selected_strategy.json` | 最优候选策略 | 看 best candidate 和 current-IR reference |
| `selected_plan.json` | 最优候选四类 Plan sidecar | 看四个 Plan 的字段和 derived features |
| `top_candidates.json` | Top-K 候选列表 | 看排名靠前策略差异 |
| `top_plans.json` | Top-K 候选对应 plan sidecar | 比较不同 Plan 组合 |
| `hardware_boundary_audit.json` | 硬件边界检查结果 | 看容量、对齐、block_dim gate 是否通过 |
| `cost_breakdown.json` | cost breakdown | 看 predicted cycles 是由哪些项组成 |
| `buffer_life_report.json` | buffer lifetime / max-live 估计 | 看各 memory scope 的 max-live 和利用率 |
| `effective_search_space.json` | 实际生成的搜索空间 | 看参数空间是否真的展开 |
| `parameter_space_audit.json` | 参数空间审计 | 看四类 Plan 参数覆盖情况 |
| `rejected_candidates.json` | 被硬件 gate 拒绝的候选预览 | 看哪些候选因为 overflow / alignment 被拒绝 |
| `relaxed_candidates.json` | relax 后可行的候选预览 | 看系统如何修复原本不可行的候选 |

### 8.1 HTML 报告建议阅读顺序

汇报时建议按下面顺序看：

```text
1. 输入 kernel 与硬件配置
2. Search statistics：候选数量、合法数量、relax 数量
3. Current IR vs Best strategy：看 predicted speedup
4. Best strategy 四个 Plan 参数：看 T/M/P/Y 分别选了什么
5. Top-K candidates：看候选是否重复、排序是否合理
6. Cost breakdown：看收益来自 load/store overlap、CV overlap、sync 下降还是 penalty 变化
7. Hardware boundary：看 UB/L1/L0/GM workspace 是否都在容量内
8. Rejected / Relaxed candidates：看硬件 gate 是否真的生效
```

### 8.2 汇报口径

可以这样说：

```text
报告中的 predicted_cycles 是 analytical estimate。
它适合同一个 kernel 下比较不同 strategy 的相对优劣，
也适合解释四类 Plan 参数为什么影响 cost，
但不能直接当成真机 msprof cycles。
```

---

## 9. 运行示例

推荐使用 bad HIVM 输入演示，因为它更适合展示 demo 是否能识别缺陷并给出优化方向。

```bash
python auto_strategy_search.py \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --candidate-space expanded \
  --search-mode layered \
  --guided-mode off \
  --output-dir sample_outputs/bad_hivm_demo_run
```

本仓库已保存一次实际运行结果：

```text
sample_outputs/bad_hivm_demo_run/
```

可以重点查看：

```text
sample_outputs/bad_hivm_demo_run/strategy_search_report.html
sample_outputs/bad_hivm_demo_run/selected_strategy.json
sample_outputs/bad_hivm_demo_run/cost_breakdown.json
sample_outputs/bad_hivm_demo_run/hardware_boundary_audit.json
```

---

## 10. MLIR-derived Artifact Inputs (V3.3)

V3.3 支持读取 vTriton/HIVM analysis 从 `.npuir.mlir` 生成的结构化产物文件。推荐命名为：

```text
--artifact-des-graph <prefill_des.json>
--artifact-trace <prefill_trace.json>
```

这些文件是 **MLIR-derived artifacts**，不是实机 profiling 数据。V3.3 默认只使用其中的结构字段，不使用 DES makespan、真实 latency 或 global scale 校准。

| Artifact | 来源 | V3.3 使用方式 | 不使用的内容 |
|---|---|---|---|
| `prefill_des.json` | vTriton/HIVM analysis 对 MLIR 的 DES graph 导出 | pipe/op composition、dependency、sync/barrier/event、buffer read/write、memory path、loop multiplier、bytes/flops proxy | `max(end_cycle)` 作为 target、DES makespan/global scale |
| `prefill_trace.json` | DES schedule 的 Perfetto/Chrome trace 导出 | event-name counts、scalar/sync/memory/vector hints、sequence pattern evidence | 实机耗时、真实 kernel latency |

推荐命令：

```bash
python -m strategy_search.cli \
  --kernel sample_product/kernel_001.npuir.mlir \
  --hardware-config configs/ascend_910b.json \
  --artifact-des-graph sample_product/prefill_des.json \
  --artifact-trace sample_product/prefill_trace.json \
  --artifact-kernel-profile on \
  --des-calibration-mode off \
  --output-dir out_artifact_kernel_profile
```

兼容旧参数名，但不推荐在新文档中使用：

```text
--des-profile    -> --artifact-des-graph
--trace-profile  -> --artifact-trace
```

### 10.1 Artifact on/off 的含义

`--artifact-kernel-profile off`：使用原 analytical cost model，主要依赖 MLIR 静态解析、四类 Plan 参数和硬件约束。

`--artifact-kernel-profile on`：在 analytical cost model 上额外构建 `KernelCostProfile`，根据 MLIR + artifact 结构证据动态调整 compute、memory、vector、scalar、sync、overlap 和 risk 分项权重。

这不是：

```text
T_new = global_scale * T_old
```

而是：

```text
T_total =
    w_compute(kernel) * T_compute(plan)
  + w_memory(kernel)  * T_memory(plan)
  + w_vector(kernel)  * T_vector(plan)
  + w_scalar(kernel)  * T_scalar_control(plan)
  + w_sync(kernel)    * T_sync(plan)
  - S_overlap(plan, kernel)
  + P_hardware(plan, kernel)
  + P_risk(plan, kernel)
```

其中 `w_*` 来自 MLIR 和 artifact 的结构证据。

## 11. V3.0 Strategy-to-HIVM Rewrite Bridge

V3.0 增加了可选的 strategy-to-HIVM rewrite bridge。使用：

```bash
--enable-ir-rewrite
```

可以额外输出：

```text
optimized.annotated.hivm.mlir
optimized.safe_structural.hivm.mlir
pass_pipeline_config.json
strategy_edit_script.json
rewrite_diff_report.json
vtriton_candidate_bundle.json
```

含义如下：

| 文件 | 含义 |
|---|---|
| `optimized.annotated.hivm.mlir` | 在原 IR 上添加 strategy hints / attributes，供后续 pass 消费 |
| `optimized.safe_structural.hivm.mlir` | 只做保守结构化改写，例如 module sync hints 和安全 local attributes |
| `pass_pipeline_config.json` | 给 vTriton / compiler pass 的候选配置 |
| `strategy_edit_script.json` | 描述从 best strategy 到 IR edit 的结构化脚本 |
| `rewrite_diff_report.json` | 对比原 IR 与 rewrite artifact 的差异 |
| `vtriton_candidate_bundle.json` | 给 vTriton 集成使用的候选 bundle |

需要强调：

```text
annotated IR 和 safe structural IR 不是完整可执行优化 IR。
真正可编译、可运行、可 msprof 对比的 optimized HIVM，仍需要 vTriton / 真实 AscendNPU compiler passes 消费这些 hints 后生成并验证。
```

---

## 12. 测试

当前测试体系已经拆成三层：

| 层级 | 默认是否运行 | 目标 | 典型内容 |
|---|---:|---|---|
| `unit` | 是 | 秒级定位局部逻辑错误 | parser、Plan 参数敏感性、hardware gate、package facade |
| `smoke` | 是 | 验证主流程能跑通 | 小 sample kernel 的 CLI/direct run、报告文件生成、current-IR reference |
| `slow` | 否 | 验证搜索质量与扩展空间稳定性 | Beam vs compact exhaustive、random baseline、search quality audit schema |

推荐日常运行：

```bash
python -m pytest
```

由于 `pytest.ini` 默认配置了 `-m "not slow"`，日常测试会跳过耗时的搜索质量审计。

运行完整慢测试：

```bash
python -m pytest -m slow
```

运行全部测试，包括默认测试和 slow 测试：

```bash
python -m pytest -m "unit or smoke or regression or slow"
```

仍然兼容 unittest discover，但不建议作为日常入口，因为 unittest 不理解 pytest marker，可能会把 slow 测试一起跑掉：

```bash
python -m unittest discover -s tests -v
```

测试覆盖：

| 测试内容 | 说明 |
|---|---|
| sync parser | 同时识别 `hivm.set_flag`、`hivm.wait_flag`、`hivm.pipe_barrier` 和 `hivm.hir.*` 写法 |
| CLI end-to-end | 能从 sample bad HIVM 跑完整流程并生成 JSON/HTML/Markdown |
| current-IR reference | 输出 `current_ir_estimated_strategy` 与 `predicted_speedup_vs_current_ir_estimated` |
| Top-K 排序 | Top candidates 按 predicted cycles 排序 |
| TilingPlan 敏感性 | 改变 tile shape 后，`n_tiles` 和局部 memory footprint 必须变化 |
| MultiBufferPlan 敏感性 | 开启 double buffer 后，load/store exposed time 应下降，同时 live memory 应上升 |
| CVPipelinePlan 敏感性 | 开启 stage-2 pipeline 后，Cube/Vector overlap 项应变化，并显式产生估计合法性风险 |
| SyncPlan 敏感性 | `graph_sync_solver` / event reuse 应改变 sync cost，并显式产生未知合法性风险 |
| 硬件 gate 边界 | 刚好等于容量上限应通过，超过容量上限应被拒绝并给出 overflow 原因 |
| 搜索稳定性 | expanded 搜索空间包含 standard tiles，Layer-1 frontier 有 pinned standard survivors、diversity 和 fallback 审计 |
| 搜索质量审计 | slow 测试中比较 Beam、compact exhaustive 和 random baseline，防止 Beam 严重偏离小空间最优 |

---

## 13. 当前不足与下一步

### 13.1 当前不足

| 不足 | 说明 |
|---|---|
| Cost model 仍需实测校准 | 带宽、启动开销、overlap ratio、sync stall 等参数需要通过离线实机数据训练/校准 |
| 精确 buffer lifetime 未完整实现 | 当前是解析式 max-live 估计，不是真实 PlanMemory lifetime dump |
| GraphSyncSolver 不证明正确性 | 只估计 sync cost，不证明依赖图无死锁、event id 合法 |
| Bank conflict / stride legality 未完整覆盖 | 当前主要覆盖容量和基础对齐，没有完整地址级冲突分析 |
| IR rewrite 仍是 bridge 级别 | 当前输出 annotated / safe structural artifacts，不等于完整可编译 optimized HIVM |
| 跨 kernel predicted_cycles 不可直接比较 | 适合比较同一 kernel 下策略相对优劣，不适合作为跨 kernel 绝对性能指标 |

### 13.2 下一步最关键工作

优先级最高的是两个闭环：

```text
1. 离线接入真实 msprof / 实机数据，训练或校准 cost model 参数，并固化到 config；在线阶段仍只读取 MLIR + artifact。
2. 打通 best strategy → 合法 HIVM rewrite → 编译通过 → msprof 对比 的完整工程闭环。
```

更具体地说，需要补充：

| 方向 | 需要的数据/能力 |
|---|---|
| cost model 更真实 | 不同 tile/stage/buffer 策略的 msprof cycles、MTE/Cube/Vector pipe utilization、带宽和启动开销校准 |
| max-live 更真实 | compiler PlanMemory allocation / lifetime dump |
| sync 更真实 | GraphSyncSolver 输出的真实 dependency graph、event id 分配、barrier/set/wait 结果 |
| rewrite 更真实 | vTriton pass 消费 `pass_pipeline_config.json` / `strategy_edit_script.json` 后生成可编译 HIVM |
| 对比更真实 | 原始 IR 与 optimized IR 在同一硬件、同一输入 shape 下的 msprof 对比 |

---

## 14. 推荐汇报口径

可以这样向同事或领导介绍：

> 当前系统是一个面向 HIVM / AscendNPU-IR 的四类 Plan 参数寻优 demo。它从输入 MLIR 中抽取 kernel 静态结构，恢复 current IR 的策略状态，并在硬件容量约束下生成 TilingPlan、MultiBufferPlan、CVPipelinePlan 和 SyncPlan 的候选组合。系统使用 analytical cost model 对候选进行排序，输出相对于 current IR estimated cost 的 predicted speedup，并生成中文可解释报告。当前版本定位为 strategy-level optimizer，不执行完整 IR rewrite，也不声称输出真机实测性能。它的价值在于把 HIVM 优化策略拆成可审计、可解释、可迭代校准的参数空间和 cost model，为后续接入 vTriton pass、DES-after 和 msprof 闭环打基础。


## V3.2 第一阶段更新：Risk-aware Cost Model（无 profiling 数据阶段）

当前仓库尚未接入真实 `msprof` / profiling 数据，因此本阶段不再把 predicted speedup 作为真实硬件收益承诺，而是把系统定位为 **保守、稳定、可解释、未来可校准的策略候选生成器**。

### 1. Cost model 主入口

主搜索流程统一使用：

```python
estimate_cost(...)
```

当前主搜索统一使用 `estimate_cost(...)` 作为正式 cost model 入口；旧版 legacy cost model 已删除，避免两套公式并存造成维护混淆。

### 2. 新增 cost risk mode

CLI 新增参数：

```bash
--cost-risk-mode conservative   # 默认；无 profiling 数据时推荐
--cost-risk-mode balanced       # demo 展示折中模式
--cost-risk-mode aggressive     # 探索模式，保留较激进 overlap/sync 收益
```

三种模式的含义：

| 模式 | 含义 | 适用场景 |
|---|---|---|
| `conservative` | 对 `GraphSyncSolver` 的 `UNKNOWN` 合法性和 `CVPipeline` 的 `PASS_ESTIMATED` 合法性显式降权 | 没有 profiling / sidecar 数据时默认使用 |
| `balanced` | 保留大部分策略收益，但加入较轻风险惩罚 | 汇报 demo 或策略对比 |
| `aggressive` | 基本保留原本乐观收益估计 | 只用于探索潜在候选，不能作为真实性能承诺 |

也可以通过配置文件覆盖风险参数：

```bash
--cost-model-config configs/cost_model_conservative.json
--cost-model-config configs/cost_model_balanced.json
--cost-model-config configs/cost_model_aggressive.json
```

### 3. 新增 legality risk penalty

当候选策略依赖尚未验证的优化时，cost model 会额外输出并计入：

```json
"legality_risk_penalty": ...,
"sync_unknown_penalty": ...,
"event_reuse_penalty": ...,
"cv_estimated_penalty": ...
```

具体处理包括：

- `sync_legality = UNKNOWN` 且使用 `graph_sync_solver`：增加同步未知风险惩罚；
- `event_reuse = true` 且同步合法性未知：增加 event reuse 风险惩罚；
- `cv_pipeline_stage > 1` 且 CV 合法性只是 `PASS_ESTIMATED`：降低 CV overlap，并增加 CV 估计风险惩罚。

### 4. 新增 risk level 与收益归因

每个 candidate 的 cost 中新增：

```json
"risk_level": "LOW | MEDIUM | HIGH",
"risk_assessment": {
  "risk_score": ...,
  "risk_mode": ...,
  "risk_reasons": [...]
},
"improvement_attribution": {
  "positive_cost_components_cycles": {...},
  "optimistic_savings_proxies_per_tile": {...},
  "risk_adjustments_cycles": {...}
}
```

报告中会显示：

- 最优候选风险等级；
- 风险原因；
- 合法性风险惩罚；
- load/store/CV overlap 的收益代理项；
- Top candidates 的 risk level。


### 5. Cost model 超参数配置化

第一阶段已经把主 cost model 中最容易造成“魔数感”的参数移动到 `configs/cost_model_*.json`：

- `cost_model_risk_modes`：控制 conservative / balanced / aggressive 下的合法性风险惩罚；
- `cost_model_safety`：控制 memory pressure、shape regularization、overlap pressure 等安全系数；
- `cost_model_strategy_effects`：控制 MultiBuffer、CVPipeline、SyncPlan 对 overlap、stall、barrier/event 数量和 template overhead 的经验影响。

代码中仍保留同名默认值作为兜底，避免未传 `--cost-model-config` 时程序无法运行；正式实验和汇报建议始终显式传入：

```bash
--cost-model-config configs/cost_model_conservative.json
```

这一步并不等于已经完成 profiling 标定，只是把经验参数从源码魔数改为可审计、可替换、未来可校准的配置项。

### 6. 推荐运行命令

无 profiling 数据时推荐：

```bash
python auto_strategy_search.py \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --candidate-space expanded \
  --search-mode layered \
  --guided-mode off \
  --cost-risk-mode conservative \
  --cost-model-config configs/cost_model_conservative.json \
  --output-dir output_risk_aware_conservative
```

对比 balanced / aggressive：

```bash
python auto_strategy_search.py \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --candidate-space expanded \
  --search-mode layered \
  --guided-mode off \
  --cost-risk-mode balanced \
  --cost-model-config configs/cost_model_balanced.json \
  --output-dir output_risk_aware_balanced

python auto_strategy_search.py \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --candidate-space expanded \
  --search-mode layered \
  --guided-mode off \
  --cost-risk-mode aggressive \
  --cost-model-config configs/cost_model_aggressive.json \
  --output-dir output_risk_aware_aggressive
```

### 6. 解释边界

本阶段更新不会解决真实性能验证问题。它解决的是：

1. 没有 profiling 数据时，避免 cost model 过度乐观；
2. 明确区分 aggressive candidate 和 conservative candidate；
3. 把 GraphSyncSolver / CVPipeline 的未知合法性风险显式写入 cost 和报告；
4. 为未来 profiling 校准预留可配置参数接口。

因此，报告中的 predicted cycles 仍然是 analytical cost model 的排序信号，不是实测 cycles。


### 缺陷注入测试

当前仓库新增了 9 个 synthetic bad MLIR 样例，位于 `tests/defect_inputs/`。这些样例用于验证搜索器是否能识别小 tile、UB overflow、barrier-heavy、缺少 overlap、已有局部优化但整体仍差、以及多种瓶颈叠加等情况。详细结果见 `DEFECT_INJECTION_TEST_REPORT.md`。

常用命令：

```bash
python -m pytest -q tests/test_defect_injection_cases.py -m regression
```

需要重新实跑缺陷搜索时：

```bash
RUN_DEFECT_LIVE=1 python -m pytest -q -m slow tests/test_defect_injection_cases.py
```

## Appendix. Legacy/offline DES makespan calibration

V3.3 主路线不使用 DES makespan/global scale。历史版本中保留的 `--des-calibration-mode single_trace_prior` 只作为 legacy/offline experiment，不能作为默认在线 cost model 介绍口径。

如果确实需要离线实验，可先生成 artifact DES summary：

```bash
python scripts/build_artifact_des_summary.py \
  --artifact-des-graph profiles/raw/chunk_des.json \
  --mlir sample_input/chunk_kernel.npuir.mlir \
  --sample-id chunk_kernel_001 \
  --output profiles/summaries/chunk_kernel_001_summary.json
```

然后显式开启 legacy calibration：

```bash
python -m strategy_search.cli \
  --kernel sample_input/chunk_kernel.npuir.mlir \
  --hardware-config configs/ascend_910b.json \
  --artifact-des-summary profiles/summaries/chunk_kernel_001_summary.json \
  --des-calibration-mode single_trace_prior \
  --output-dir outputs/legacy_des_calibration
```

该模式会使用 DES makespan/global scale 对 analytical cycles 做单样本尺度对齐。它不是实机 profiling 校准，也不是 V3.3 默认推荐路径。V3.3 默认推荐始终使用：

```text
--artifact-kernel-profile on
--des-calibration-mode off
```


## msprof 实机数据校准入口

本版本支持读取 Ascend msprof 导出的 `op_summary.csv`，通过 `--msprof-op-summary` 对 cost model 做单 kernel 校准。校准逻辑详见 `MSPROF_CALIBRATION_README.md`。

核心原则：`aic_total_cycles` 和 `aiv_total_cycles` 是资源累计计数，不能直接相加作为总 cycles；当前 cost model 的实机 target 使用：

```text
measured_total_cycles = Task Duration(us) * clock.cycles_per_us
```

示例命令：

```bash
python auto_strategy_search.py \
  --kernel sample_input/chunk_kernel.npuir.mlir \
  --hardware-config configs/ascend_910b.json \
  --artifact-des-graph sample_product/prefill_des.json \
  --artifact-trace sample_product/prefill_trace.json \
  --cost-model-config configs/cost_model_conservative.json \
  --msprof-op-summary profiles/raw/op_summary_20260623064651.csv \
  --msprof-op-name chunk_kda \
  --msprof-calibration-mode component_plus_scale \
  --output-dir output_msprof_calibrated
```

三种模式：

- `off`：不使用 msprof；
- `component_prior`：只用 msprof 分项比例修正 scalar/sync/overlap 等 component correction；
- `component_plus_scale`：在 component prior 基础上，把 current-IR predicted cycles 对齐到实测 `Task Duration(us)` 对应的 cycles。

当前上传数据的主 kernel 校准结果：

```text
measured_total_cycles = 206999450.75
scalar_cycle_correction: 1.6171 -> 1.8018
overlap_confidence: 0.9009 -> 0.7385
global_cycle_scale = 6561.0959
current_ir_estimated_predicted_cycles = 206999450.75
best_predicted_cycles = 140615231.52
```

注意：单样本 global scale 只校准绝对量纲，不改变候选排序。真正训练排序需要同一 kernel 多个策略版本的 msprof 数据。

## Prefill-A5 S0-S9 多策略实测 benchmark

本版本新增 `profiles/prefill_a5/` 与 `scripts/prefill_a5_stage_benchmark.py`，用于尽可能利用 `prefill_a5.zip` 中同一个 sparse prefill kernel 的 S0-S9 多阶段实测 latency。它主要用于测试和校准 cost model 的策略排序敏感度，而不是替代 msprof component-level 校准。详细说明见 `PREFILL_A5_BENCHMARK_README.md`。

快速运行：

```bash
python scripts/prefill_a5_stage_benchmark.py --output-dir output_prefill_a5_benchmark
```


## Prefill-A5 plan-only 校准

本版本新增 `configs/cost_model_prefill_a5_plan_calibrated.json`，用于基于 `profiles/prefill_a5` 的 S0-S6 plan-level 实测转移校准当前四个 plan 的敏感度。该校准只覆盖 `TilingPlan`、`MultiBufferPlan`、`CVPipelinePlan` 中当前 `StrategyConfig` 可表达的参数，不把 shared SSA、hoist、compiler code motion 等 IR rewrite 收益算入当前 cost model。

复现命令：

```bash
python scripts/prefill_a5_plan_only_validation.py \
  --cost-model-config configs/cost_model_prefill_a5_plan_calibrated.json \
  --output-dir output_prefill_a5_plan_only_calibrated
```

校准后，在 Prefill-A5 plan-only validation 中 direction hit 从 `2/4` 提升到 `4/4`。详细报告见 `PREFILL_A5_PLAN_CALIBRATION_REPORT.md`。


## V3.3.2 Phase-2H：HIVM Structural Rewrite 第二阶段收口

当前版本将 Phase 2 定义为 operation-level rewrite bridge，而不是完整 compiler lowering。开启 `--enable-structural-rewrite` 后，会额外生成：

```text
phase2_closure_report.json
```

该报告总结 Phase 2A-2H 的完成状态、C++ bridge 真实支持的 mutation、precheck/deferred 的 rewrite 类型，以及 Phase 3 的进入条件。

Phase 2 已经完成：

```text
Python strategy search
  -> structural_edit_script.json
  -> C++/vTriton rewrite backend boundary
  -> optimized.structural.hivm.mlir
  -> validation / legality / manifest / closure reports
```

当前 C++ bridge 真实支持：

```text
replace_barrier_all_with_directional_sync
insert_sync_before_first_vector_op
```

`remove_redundant_gm_roundtrip` 当前只做 candidate/precheck，不做删除。real double-buffer、full CV overlap、real tiling lowering 进入 Phase 3+，需要 dependency graph、event liveness、buffer liveness 和 alias proof。

## Phase 3A: Dependency / Event Analysis Foundation

V3.3.2 Phase-3A starts the correctness-analysis layer for future HIVM structural rewrites. When `--enable-structural-rewrite` is enabled, the pipeline now also emits:

- `hivm_op_semantics_registry.json`: lightweight HIVM op semantics table used by the conservative analyzer.
- `hivm_ir_inventory.json`: op-level inventory with role, pipe, region depth, inputs/outputs, events, and unknown-op blockers.
- `dependency_graph_report.json`: conservative RAW/WAW/WAR, event set/wait, and coarse barrier dependency edges.
- `event_liveness_report.json`: event set/wait pairing and local live-range warnings.
- `phase3a_analysis_summary.json`: Phase-3A status and the remaining gates before dangerous rewrites.

Phase-3A does **not** authorize additional mutation. It is the evidence foundation before Phase-3B/3C tasks such as buffer liveness, GM alias/MemorySSA-like checking, safe GM round-trip deletion, and local-proof-gated Q-load hoist candidate.

---

## V3.3.2 Phase-3B：Buffer Liveness / GM Alias Foundation

Phase-3B 继续推进 Phase 3 的正确性基础设施。它不会新增危险 rewrite，而是新增 memory correctness evidence：

```text
buffer_liveness_report.json
capacity_recheck_report.json
gm_alias_report.json
phase3b_analysis_summary.json
```

其中：

- `buffer_liveness_report.json` 记录每个 buffer 的空间、大小、读写次数、首次/末次使用位置和保守角色分类；
- `capacity_recheck_report.json` 按 UB/L1/L0C 等空间重新估算保守峰值占用；
- `gm_alias_report.json` 记录 GM read/write 访问和 same-GM store→load round-trip candidate；
- `phase3b_analysis_summary.json` 汇总本阶段是否存在容量风险、GM candidate，以及后续 rewrite gate 是否解锁。

当前 Phase-3B 仍然不解锁：

```text
GM round-trip deletion
Q-load hoist with local proof gate
real double-buffer ping-pong
full CV pipeline overlap
real tiling loop lowering
```

这些必须等 Phase-3C/3D/3E 提供 MemorySSA-like GM proof、loop-invariant proof、DES/trace validation 后再推进。


## V3.3.2 Phase-3C：GM MemorySSA-like Legality Gate

Phase-3C 继续推进 Phase 3 的正确性基础设施，重点是把 Phase-3B 中“发现 GM round-trip candidate，但不能删除”的状态，推进成明确的删除决策 gate。

新增输出：

```text
gm_memory_ssa_report.json
gm_roundtrip_deletion_decision.json
rewrite_legality_gate_report.json
phase3c_analysis_summary.json
```

Phase-3C 的核心原则是：

```text
cannot prove safe -> do not rewrite
```

因此，即使发现 `store GM -> load same GM` 的候选，也必须同时通过：

1. same textual GM var gate；
2. same static offset/slice proof；
3. MemorySSA-like unique reaching-def gate；
4. no unknown GM side-effect gate；
5. non-observable boundary gate。

当前版本已经实现 MemorySSA-like reaching-definition 和统一 decision report，但如果缺少 target offset/slice 证明，或者 GM buffer 是 function boundary / observable buffer，则删除仍然 deferred。也就是说 Phase-3C 建立的是“能不能删”的判定机制，不是盲目删除 GM load/store。

Phase 3 计划收敛为 6 个子阶段：

```text
Phase 3A: HIVM op inventory + dependency graph + event liveness
Phase 3B: buffer liveness + GM alias + capacity recheck
Phase 3C: GM MemorySSA-like checker + deletion decision gate
Phase 3D: loop-invariant load hoist proof
Phase 3E: tritonsim-hivm DES / trace validation wrapper
Phase 3F: Phase-3 closure and Phase-4 handoff
```

real double-buffer、full CV overlap、real tiling loop lowering 不放在 Phase 3 内完成，它们依赖 Phase 3 的 dependency / liveness / legality / validation 结果，应进入 Phase 4+。

## Phase-3D: loop-invariant load hoist proof gate

Phase-3D adds proof reports for loop-invariant load hoist, focused on FA-style Q-load hoist candidates. It emits:

```text
loop_invariant_load_hoist_report.json
q_load_hoist_decision.json
phase3d_analysis_summary.json
```

The local gate checks whether a GM->local Q/stream load is inside a loop, does not visibly reference the loop induction variable, has no same-loop destination overwrite, passes event liveness and capacity checks. Production mutation is still deferred until 目标 vTriton/HivmOpsEditor or MLIR Operation walking proves region-motion legality.

## V3.3.2 Phase-3E：tritonsim-hivm DES / Trace Validation Wrapper

Phase-3E 继续推进 Phase 3 的正确性验证闭环。它不会新增危险 rewrite，也不会声称已经获得真实性能提升；它的目标是把 structural rewrite 后的 `optimized.structural.hivm.mlir` 接入外部 vTriton / `tritonsim-hivm` 验证链路。

开启 `--enable-structural-rewrite` 后，项目现在会额外生成：

- `vtriton_des_trace_validation_report.json`：记录 original / optimized IR 是否被 `tritonsim-hivm` 接受，是否生成 DES graph 和 Perfetto trace；
- `phase3e_analysis_summary.json`：Phase-3E 状态摘要；
- `trace_comparison_report.html`：轻量 HTML 对比报告，汇总 DES/trace artifact、local inventory delta 和 dependency delta。

如果同时传入：

```bash
--run-vtriton-validation --tritonsim-hivm /path/to/tritonsim-hivm
```

则 wrapper 会尝试对 structural input IR 和 optimized structural IR 分别运行：

```bash
tritonsim-hivm \
  --npuir-file <ir> \
  --des-graph-file <tag>_des_graph.json \
  --perfetto-trace-file <tag>_perfetto_trace.json
```

不同 vTriton build 的 flag 可能略有差异；如果本地 binary 不存在、命令失败，或没有生成 DES/trace artifact，报告会明确标记为 `pending_or_failed_external_des_trace_validation`。这不是失败吞掉，而是显式告诉使用者：当前还没有通过外部仿真验证，Phase-4 级别危险 mutation 仍然不能解锁。

Phase-3E 能证明的是：

- 如果外部 binary 可用并成功运行，original / optimized IR 至少可以进入 `tritonsim-hivm`；
- DES graph / Perfetto trace artifact 是否真实生成；
- 改写前后本地 op inventory 和 dependency graph 的轻量差异。

Phase-3E 不能证明的是：

- 数值正确性；
- 目标编译器完整 verifier 通过；
- msprof 真机性能提升；
- real double-buffer / full CV overlap / real tiling lowering 可以安全开启。

因此，Phase-3E 的定位是 **vTriton 外部验证接口与报告闭环**，不是最终性能结论。


## V3.3.2 Phase-3F: Phase 3 Closure and Phase 4 Handoff

Phase-3F closes the Phase 3 correctness-foundation work. When structural rewrite is enabled, the project now emits:

```text
phase3_closure_report.json
phase3f_analysis_summary.json
```

These reports consolidate op inventory, dependency graph, event liveness, buffer liveness, GM MemorySSA-like gates, load-hoist proof gates, and vTriton DES/trace wrapper status. Phase-3F does not enable new dangerous rewrites. It explicitly keeps GM deletion, production Q-load hoist, real double-buffer, full CV overlap, and real tiling lowering locked unless Phase 4 target-parser and validation gates pass.

Recommended next step is Phase-4A: target parser / HivmOpsEditor integration hardening.

---

## Audit correction note: current IR rewrite status

The current project state should be described carefully:

```text
Implemented:
- strategy search and cost-model ranking;
- strategy-to-IR annotation and safe hints;
- structural_edit_script.json;
- standalone C++ rewrite bridge;
- real op-sequence mutation for barrier replacement and CV boundary sync insertion;
- local evidence reports for dependency, event, buffer, GM alias, and load-hoist candidates.

Not yet production-grade:
- full 目标 vTriton/HivmOpsEditor Operation-level backend;
- true GM round-trip deletion;
- production Q-load hoist;
- real double-buffer ping-pong;
- full CV overlap;
- real tiling loop lowering;
- completed DES/trace/msprof validation.
```

`remove_redundant_gm_roundtrip` is currently a candidate/precheck/deferred edit, not a mutation. Phase-3 analysis reports are conservative local evidence, not a formal target-compiler correctness proof.

## Naming update: HIVM Rewrite Bridge

Starting from `3.3.2-phase3f-scope-clarified`, the recommended name for the current C++ structural rewrite component is:

```text
HIVM Rewrite Bridge / HIVM Bridge Adapter
```

The previous wording `vTriton-backed backend` is no longer used for the current implementation because it may overstate the integration level.  The current backend is a standalone, auditable C++ bridge that is compatible with future vTriton/HivmOpsEditor integration, but it is not a fully vTriton-backed production pass yet.

Backward-compatible files are kept:

```text
vtriton_adapter/
vtriton_adapter_manifest.json
```

Preferred new names are also emitted or documented:

```text
hivm_bridge_adapter/
hivm_bridge_manifest.json
```

See `NAMING_AND_SCOPE_CLARIFICATION.md` and `PHASE4_EXECUTION_PLAN.md` for the current scope and Phase 4 plan.


## Phase 4A: HIVM Rewrite Bridge Hardening

当前结构改写后端的推荐名称是 **HIVM Rewrite Bridge**。它是 vTriton-compatible / HivmOpsEditor-oriented 的桥接版，不是 fully vTriton-backed production backend。

开启 `--enable-structural-rewrite` 后，Phase 4A 会额外输出：

- `target_parser_validation_report.json`：检查 bridge 能力握手、requested edit 覆盖、本地 IR sanity、target parser / tritonsim 是否接通。
- `phase4a_analysis_summary.json`：给出是否可以进入后续 DES/trace 或 guarded mutation prototype 的简短结论。

Phase 4A 不会解锁 GM 删除、Q-load production hoist、real double-buffer、full CV overlap 或 real tiling lowering。


### Phase-4B: DES/trace execution gate

Phase-4B strengthens the external validation path. When `--run-vtriton-validation` and `--tritonsim-hivm` are provided, the project now emits:

- `phase4b_des_trace_execution_report.json`
- `phase4b_analysis_summary.json`
- `phase4b_validation_commands.sh`

This gate is stricter than the earlier wrapper: original and optimized HIVM IR must both be accepted by the configured `tritonsim-hivm`, return zero, and generate parseable DES graph and Perfetto trace JSON files. If this does not happen, high-risk rewrites such as GM deletion, production Q-load hoist, real double-buffer, full CV overlap, and real tiling remain locked.

For CI/demo environments without a real vTriton build, `tools/fake_tritonsim_hivm.py` can exercise the reporting path only. It must not be used as performance evidence.

### Phase-4C: guarded Q-load hoist prototype gate

Phase-4C promotes Phase-3D Q-load hoist candidates into a guarded backend dry-run worklist. It emits:

- `phase4c_q_load_hoist_prototype_report.json`
- `phase4c_q_load_hoist_candidate_script.json`
- `phase4c_analysis_summary.json`

This stage intentionally does **not** move load ops with text rewriting. A candidate may enter the backend dry-run worklist when local proof, target-parser/bridge readiness, DES/trace gate, event liveness, and capacity gates are clean. Production mutation remains locked until a HivmOpsEditor / MLIR Operation-level backend can prove safe region motion and dominance.



### Phase-4D: official-docs-aligned Operation-level dry-run contract

Phase-4D turns Phase-4C guarded Q-load hoist candidates into a future-backend dry-run contract. It does **not** move load operations with Python text rewriting and does **not** unlock production mutation.

New artifacts:

```text
phase4d_operation_rewrite_dry_run_report.json
phase4d_hivmopseditor_dry_run_plan.json
phase4d_official_mlir_compliance_report.json
phase4d_analysis_summary.json
```

The stage follows official MLIR rewrite discipline: mutation should be performed through a rewriter/backend API, legality must be explicit, and operation movement across regions requires Operation-level dominance/region-motion proof plus verifier and DES/trace validation.


## V3.3.2 Phase-4E：Phase 4 收口与 Phase 5 Handoff

Phase 4E 是 Phase 4 的收口阶段，不新增危险 IR mutation。它统一汇总 Phase 4A--4D 的结果：

- Phase 4A：HIVM Rewrite Bridge / target parser readiness audit；
- Phase 4B：DES / trace execution gate；
- Phase 4C：guarded Q-load hoist candidate worklist；
- Phase 4D：official-docs-aligned Operation-level dry-run contract；
- Phase 4E：`phase4_closure_report.json` 与 `phase4e_analysis_summary.json`。

当前仍然保持 locked：production Q-load hoist、GM round-trip deletion、real double-buffer、full CV overlap、real tiling loop lowering。下一阶段 Phase 5 的重点是接入真实 HivmOpsEditor / MLIR Operation-level backend，并运行 verifier、tritonsim-hivm DES/trace 和后续 msprof 验证。


### Phase 5C: Operation-level dry-run execution gate

Phase 5C asks a future HivmOpsEditor / MLIR Operation backend to consume the Phase-4D dry-run plan and locate candidate operations without mutating IR. It emits `phase5c_operation_level_dry_run_report.json`, `phase5c_dominance_precheck_report.json`, `phase5c_region_motion_precheck_report.json`, and `phase5c_analysis_summary.json`. Production mutation remains locked until a real Operation backend proves dominance, region motion, verifier, DES/trace and later msprof gates.



### Phase-5E：Limited GM Round-trip Deletion Gate

Phase-5E adds a strict gate for future GM round-trip deletion.  The project does **not** delete GM traffic by Python text replacement.  It only converts Phase-3C-approved GM deletion candidates into a future Operation-level backend mutation request and requires alias, memory-effect, observable-boundary, verifier and DES/trace evidence before any deletion can be accepted.

New outputs:

- `phase5e_limited_gm_roundtrip_deletion_report.json`
- `phase5e_gm_deletion_safety_report.json`
- `phase5e_analysis_summary.json`



## V3.3.2 Phase-5F：Phase 5 收口与 Phase 6 计划

- 新增 `phase5_closure_report.json`、`phase5f_analysis_summary.json`、`phase5f_leadership_summary.json`。
- 明确 Phase 5 完成的是 Operation-level backend 接入前的合同与门禁阶段，不声称 production Q-load hoist 或 GM deletion 已经实现。
- 新增 `HIVM_REWRITE_PHASE5F_CLOSURE_REPORT.md`、`PHASE5F_LEADERSHIP_BRIEF.md`、`PHASE5_CLOSURE_AND_PHASE6_PLAN.md`。
- Phase 6 建议聚焦真实 HivmOpsEditor / MLIR Operation backend 接入，以及受限 Q-load hoist / GM deletion 正例验证。


## V3.3.2 Phase-6A: Real Operation Backend Integration Readiness

Phase 6A starts the handoff from bridge contracts to a real MLIR/HivmOpsEditor Operation-level backend. It does **not** enable production complex mutation. Instead it emits:

- `phase6a_real_backend_integration_report.json`
- `phase6a_backend_acceptance_matrix.json`
- `phase6a_required_inputs.json`
- `phase6a_analysis_summary.json`

New optional input:

```bash
--vtriton-source-root /path/to/vTriton
```

To proceed beyond readiness gates, provide a real Operation backend binary via `--hivm-operation-backend`, a real `tritonsim-hivm`, vTriton/HivmOpsEditor source or build context, and one restricted positive HIVM fixture. Fake or fixture backends are intentionally rejected as production mutation evidence.


## Phase-6B: vTriton positive fixture harness

Phase-6B ingests concrete HIVM/NPUIR fixtures and prepares the real vTriton/HivmOpsEditor validation path. It does **not** claim production mutation without a real Operation-level backend.

New CLI option:

```bash
--phase6-positive-fixtures file1.mlir,file2.mlir
```

New outputs:

- `phase6b_positive_case_validation_report.json`
- `phase6b_fixture_acceptance_matrix.json`
- `phase6b_analysis_summary.json`
- `phase6b_real_backend_validation_commands.sh`

Included fixtures:

- `sample_input/phase6_positive_fixtures/kernel.npuir.mlir`
- `sample_input/phase6_positive_fixtures/kernel_001.npuir.mlir`
- `sample_input/phase6_positive_fixtures/fa_best.hivm.mlir`
- `sample_input/phase6_positive_fixtures/restricted_q_load_in_loop_positive.hivm.mlir`
- `sample_input/phase6_positive_fixtures/restricted_gm_roundtrip_positive.hivm.mlir`

The generated script follows the vTriton public command shape for HIVM analysis:

```bash
tritonsim-hivm --npuir-file <fixture> --scheduler des \
  --des-graph-file <fixture>_des_graph.json \
  --perfetto-trace-file <fixture>_trace.json
```

Production Q-load hoist and GM deletion remain locked until a real MLIR/HivmOpsEditor backend provides dominance, region-motion, verifier, and DES/trace evidence.


## Phase 6C：受限正例上的真正 IR 改写

从 Phase 6C 开始，项目不再只停留在 dry-run / mutation contract：新增 `tools/restricted_hivm_true_rewriter.py`，可在明确标记的 tiny positive fixtures 上真实生成改写后的 `.hivm.mlir` 文件。

当前支持两个受限真实改写：

1. `q_load_hoist`：把简单 `scf.for` 循环内的 `Q_gm -> q_ub -> q_l1` load/nd2nz pair 移到循环外；
2. `gm_roundtrip_deletion`：删除受限模式下的冗余 GM store/reload pair。

重要边界：

- 这是 restricted true rewrite，不是完整生产级 MLIR/HivmOpsEditor backend；
- 只对带 restricted marker 的正例 fixture 生效；
- 复杂真实 kernel 仍然不会默认执行 Q-load hoist、GM 删除、double-buffer、CV overlap 或 tiling lowering；
- 后续应该把这些受限规则迁移到真正的 HivmOpsEditor / MLIR Operation-level 后端。

运行 structural rewrite 后会生成：

```text
phase6c_restricted_true_rewrite_report.json
phase6c_analysis_summary.json
phase6c_leadership_summary.json
optimized.phase6c.*.hivm.mlir
```

## Phase 6E：vTriton 本地构建集成包

当前项目已经生成了面向真实 vTriton/HivmOpsEditor 的 `hivm-operation-backend` 适配器源码。Phase 6E 新增本地安装、构建和 smoke-test 脚本，用于把该后端放入用户本地 vTriton 构建树中。

关键脚本：

```bash
python scripts/phase6e_apply_vtriton_backend_patch.py \
  --vtriton-root /path/to/vTriton \
  --adapter-dir vtriton_hivm_operation_backend \
  --apply

bash scripts/phase6e_build_hivm_operation_backend.sh /path/to/vTriton /path/to/vTriton/build

bash scripts/phase6e_smoke_test_backend.sh \
  /path/to/vTriton/build/bin/hivm-operation-backend \
  sample_input/phase6_positive_fixtures/restricted_gm_roundtrip_positive.hivm.mlir
```

Phase 6E 会生成：

```text
phase6e_vtriton_local_integration_report.json
phase6e_backend_build_plan.json
phase6e_analysis_summary.json
```

注意：Phase 6E 仍不声称已经完成复杂 production rewrite。它完成的是真实后端的本地构建集成包。只有在用户本地 vTriton 环境中成功编译 `hivm-operation-backend`，并通过 `--inventory`、`--roundtrip`、`--verify-only` 后，才允许进入受控 GM round-trip deletion 正例。


## Phase 6F: compiled backend acceptance gate

Phase 6F closes the current Phase 6 line by adding a binary-facing acceptance gate for a real `hivm-operation-backend`.  It distinguishes three things:

1. restricted Python true-rewrite positive cases;
2. generated vTriton/HivmOpsEditor adapter source;
3. an actually compiled backend that proves real MLIR/HivmOpsEditor identity and passes inventory / roundtrip / verify smoke tests.

Generated outputs include:

- `phase6f_backend_acceptance_report.json`
- `phase6f_smoke_command_matrix.json`
- `phase6_closure_report.json`
- `phase6f_analysis_summary.json`

Broad production mutation remains locked until a compiled backend binary passes this gate.


---

## STAGE2A_SEARCH_STABILITY.md

# V3.2-stage2a 搜索空间稳定性更新

本阶段目标是在不依赖 profiling 数据、不重写 cost model 的情况下，先修复搜索空间稳定性与可审计性问题。

## 改动摘要

1. 新增稳定策略签名 `strategy_signature(cfg)`：忽略易变的 `strategy_id`，覆盖四类 Plan 的关键字段。
2. 新增 `layer1_signature(case)` 与 `tile_signature_from_dict(tile)`：用于 Layer-1 pinning 与 tile containment 检查。
3. `expanded/full` 自动搜索空间显式包含 `standard` tile 候选，避免更大候选空间丢掉代表点。
4. 在 `expanded/full` 模式下，先计算 standard 模式的 Layer-1 survivor，并把这些 survivor pin 到 expanded/full 的 Layer-1 frontier。
5. 对完整候选做 exact dedup，避免同一个四 Plan 策略被重复编号和重复进入排序。
6. relax 后再次按 signature 去重，避免多个候选 relax 成同一个策略后重复进入 Top-K。
7. 新增 `search_audit.json`，记录 Layer-1 pinning、候选去重、post-relax 去重等审计信息。
8. Markdown / HTML 报告中增加 Stage2a 搜索稳定性摘要。
9. 测试增加到 9 个，覆盖 strategy signature、standard tile containment、Layer-1 pinning 和 candidate dedup audit。

## 关键边界

Stage2a 不是 diversity-preserving beam，也不是全局最优保证。它解决的是更基础的问题：

```text
expanded/full 搜索空间不能因为候选更多而无意丢掉 standard 搜索空间的关键 Layer-1 frontier；
重复候选要被识别；
搜索过程要有可审计输出。
```

Stage2b 可继续在此基础上加入 diversity-preserving beam、fallback sampling 和 beam-width monotonicity regression。


---

## STAGE2B_BEAM_SEARCH_STABILITY.md

# V3.2-stage2b：Beam Search 稳定性改进

本阶段在 V3.2-stage2a 的基础上继续增强搜索稳定性。Stage2a 已经保证 expanded/full 搜索空间显式包含 standard tile 候选，并通过 stable strategy signature 做去重；Stage2b 进一步解决 Layer-1 Beam Search 过早剪枝的问题。

## 1. 目标

Stage2b 的目标不是修改 cost model，也不是追求更高 predicted speedup，而是让搜索过程更稳定、可解释、可回归：

- Layer-1 不再只保留 coarse cost Top-W；
- 保留 tile_m、tile_n、tile_k、block_dim 等关键维度的代表候选；
- 继续 pin standard Layer-1 survivors，避免 expanded/full 模式误杀 standard 中的好候选；
- 增加少量 deterministic fallback candidates；
- 在 search_audit.json 和报告中记录 beam frontier 的来源。

## 2. Layer-1 保留策略

新的 Layer-1 policy 为：

```text
cost_topw_plus_diversity_plus_pinned_standard_plus_fallback
```

具体由四部分组成：

1. `cost_topw`：按 coarse cost 保留原始 Top-W；
2. `diversity`：按 `tile_m/tile_n/tile_k/block_dim` 分组，每组保留若干代表候选；
3. `pinned_standard`：在 expanded/full 模式下，强制保留 standard 模式下的 Layer-1 survivors；
4. `fallback`：从剩余候选中按 coarse cost 额外保留少量候选，降低早期误剪枝风险。

## 3. 新增搜索参数

自动生成的 search space 中新增以下参数：

```json
{
  "layer1_diversity_beam_enabled": true,
  "layer1_diversity_group_fields": ["tile_m", "tile_n", "tile_k", "block_dim"],
  "layer1_diversity_per_group_keep": 1,
  "layer1_diversity_max_extra": 12,
  "layer1_fallback_keep": 4
}
```

这些参数可以通过 search-space override JSON 修改。

## 4. 审计字段

`search_audit.json` / report 中会包含：

- `diversity_added_after_topw`
- `diversity_group_fields`
- `diversity_per_group_keep`
- `diversity_max_extra`
- `pinned_standard_after_topw_and_diversity`
- `fallback_added_after_topw_diversity_and_pins`
- `final_kept`

## 5. 当前边界

Stage2b 仍然是启发式 Beam Search，不提供全局最优证明。它的价值是降低粗筛误杀风险，并通过审计和测试让搜索行为更稳定。

下一步可以继续增加：

- beam width monotonicity 回归测试；
- small-space exhaustive 对照；
- random search / simulated annealing 对照；
- top candidates near-duplicate 合并与解释。


---

## STAGE2C_SEARCH_QUALITY_AUDIT.md

# V3.2-stage2c 搜索质量审计

本版本在 stage2b 的 Beam Search 稳定性基础上，新增了 bounded search-quality audit。目标不是替代主搜索，而是给 Beam Search 增加可解释的对照基线。

## 新增能力

1. `--enable-search-quality-audit`：在正常 layered beam search 之外，额外构造一个紧凑候选空间。
2. 小空间穷举 baseline：在 compact subspace 上完整枚举，用于估计 Beam Search 与局部全局最优之间的 gap。
3. 随机搜索 baseline：固定随机种子和预算，从 compact exhaustive pool 中采样，用于证明 Beam Search 相对随机搜索的优势。
4. `search_audit.json` 新增 `search_quality_audit` 字段，包括 Beam best、small exhaustive best、random best、gap 和随机优势。

## 命令示例

```bash
python -m strategy_search.cli \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --candidate-space expanded \
  --search-mode layered \
  --guided-mode off \
  --cost-risk-mode conservative \
  --cost-model-config configs/cost_model_conservative.json \
  --enable-search-quality-audit \
  --search-quality-random-budget 64 \
  --search-quality-random-seed 7 \
  --output-dir output_stage2c
```

## 边界说明

该审计只在一个紧凑子空间上比较 Beam、exhaustive 和 random，不证明真实硬件全局最优，也不替代 profiling。它的价值是验证当前 Beam Search 在 bounded subspace 中是否表现合理。


---

## STEP2_SAFE_STRUCTURAL_REWRITE_REPORT.md

# Step 2：Safe Structural Hint Rewrite 实现报告

## 1. 本阶段目标

Step 2 的目标不是把寻优结果完整 lowering 成真实优化后的 HIVM，而是在 Step 1 全量 annotation rewrite 的基础上，进一步把部分低风险策略落到具体 IR anchor 上。

本阶段允许：

- 给已有 `memref.alloc` 添加 `multi_buffer` / `hivm.nbuf` hint；
- 替换已有 tile 属性 anchor，例如 `tile_m`、`hivm.tile_n`；
- 生成 `rewrite_capability_report.json`，明确说明哪些 rewrite 已做、哪些没有做、为什么 fallback；
- 对 GraphSyncSolver 只加 sync hint，不删除、不移动 barrier/event。

本阶段禁止：

- 不生成新的 loop nest；
- 不复制 buffer，不实现真实 ping-pong；
- 不移动 load/store/compute op；
- 不删除或移动 barrier/event；
- 不做 CV pipeline 的 op 重排。

因此 Step 2 的性质是：**安全结构 hint rewrite**，不是 full structural rewrite。

---

## 2. 修改的核心文件

### `strategy_search/rewrite.py`

新增或增强的核心能力：

1. **alloc-level multi-buffer hint rewrite**

   新增/重写：

   ```python
   _apply_safe_multibuffer_rewrite(ir_text, strategy, safety)
   ```

   作用：在满足安全条件时，对已有 UB/L1 `memref.alloc` 添加：

   ```mlir
   {multi_buffer = 2 : i64, hivm.nbuf = 2 : i64}
   ```

   示例：

   ```mlir
   %k_ub = memref.alloc() : memref<64x128xf16, #hivm.address_space<ub>>
   ```

   改写为：

   ```mlir
   %k_ub = memref.alloc() {multi_buffer = 2 : i64, hivm.nbuf = 2 : i64} : memref<64x128xf16, #hivm.address_space<ub>>
   ```

2. **已有 tile attr 替换**

   新增：

   ```python
   _apply_existing_tile_attr_rewrite(ir_text, strategy)
   ```

   只替换已有 tile 属性 anchor，例如：

   ```mlir
   tile_m = 8 : i64
   hivm.tile_n = 16 : i64
   ```

   替换为寻优结果：

   ```mlir
   tile_m = 32 : i64
   hivm.tile_n = 64 : i64
   ```

   如果原 IR 没有 tile anchor，则不生成新 loop，只在 capability report 中说明 fallback。

3. **Step-2 capability report**

   新增：

   ```python
   build_rewrite_capability_report(...)
   ```

   输出：

   ```text
   rewrite_capability_report.json
   ```

   记录：

   - 当前 Step 2 支持哪些 rewrite；
   - 找到了多少 alloc anchor；
   - 是否找到 tile attr anchor；
   - 实际给哪些 buffer 加了 hint；
   - 哪些 buffer 被跳过以及原因；
   - 为什么不做 loop rewrite / ping-pong rewrite / CV rewrite / sync rewrite。

4. **sync 处理改为只标注，不改写**

   `_safe_barrier_notes()` 现在不会删除 barrier，即使 `rewrite_safety=aggressive` 也不会删同步 op。

   它只会在 barrier 前加：

   ```mlir
   // [auto_strategy sync_hint] GraphSyncSolver candidate; Step-2 does not remove/move barriers without dependency legality proof
   hivm.hir.barrier {mode = "ALL"}
   ```

   这可以避免 safe structural 阶段误伤程序正确性。

---

## 3. 新增 rewrite safety 语义

### conservative

只使用明确的 per-buffer 信息：

```json
"buffer_multipliers_json": {"k_ub": 2, "v_l1": 2}
```

只有这些明确标为 `>=2` 的 UB/L1 buffer 才会添加 `multi_buffer/hivm.nbuf`。

### balanced

在 conservative 基础上，如果：

```text
double_buffer = true
```

并且 buffer 名字明显是输入流 buffer，例如：

```text
q_ub, k_ub, v_ub, q_l1, k_l1, v_l1
```

则允许通过名字启发式添加 `multi_buffer=2`。

这个模式适合 demo 展示，但 audit 中会标记原因为：

```text
balanced_stream_name_heuristic
```

### aggressive

允许对更广泛的 eligible UB/L1 buffer 添加 hint，但仍然不会删除 barrier、不会移动 op、不会复制 buffer。

---

## 4. 新增输出文件

使用：

```bash
python -m strategy_search.cli \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --enable-ir-rewrite \
  --rewrite-mode both \
  --rewrite-safety balanced \
  --output-dir output_step2_demo
```

会输出：

```text
optimized.annotated.hivm.mlir
optimized.safe_structural.hivm.mlir
pass_pipeline_config.json
strategy_edit_script.json
rewrite_diff_report.json
rewrite_capability_report.json
rewrite_audit.md
vtriton_candidate_bundle.json
vtriton_integration_report.json
```

其中 Step 2 新增重点是：

```text
optimized.safe_structural.hivm.mlir
rewrite_capability_report.json
```

---

## 5. 示例运行结果

对 `sample_input/fa_bad_inefficient.hivm.mlir` 使用 balanced 模式测试，结果为：

```json
{
  "buffer_hints_added": 6,
  "buffers_rewritten": [
    "q_ub",
    "k_ub",
    "v_ub",
    "q_l1",
    "k_l1",
    "v_l1"
  ],
  "tile_attrs_replaced": [],
  "sync_rewrites_performed": 0
}
```

说明：

- 对 `q/k/v` 的 UB/L1 输入流 buffer 添加了 `multi_buffer=2` 和 `hivm.nbuf=2`；
- 没有改 `acc_ub`、`o_ub`、`s_l0c` 等 accumulator/output/L0C buffer；
- 原样保留 barrier，只加 GraphSyncSolver candidate 注释；
- 该样例没有已有 tile attr anchor，所以没有做 tile attr 替换。

---

## 6. 测试情况

新增测试：

```text
tests/test_rewrite_step2_safe_structural.py
```

覆盖：

1. conservative 模式只对显式 `buffer_multipliers_json >= 2` 的 buffer 添加 hint；
2. accumulator/output buffer 不被误改；
3. 已有 `tile_m` / `hivm.tile_n` anchor 可被替换；
4. balanced 模式可对 `q/k/v` stream-like buffer 使用名字启发式；
5. barrier 不会被删除；
6. `rewrite_capability_report.json` 正确生成。

完整测试结果：

```text
45 passed
```

---

## 7. 当前边界

当前已经完成：

```text
Step 1: selected_strategy -> IR attributes + sidecar config
Step 2: selected_strategy -> safe local structural hints
```

当前还没有完成：

```text
真实 tiling loop rewrite
真实 ping-pong buffer duplication
真实 CV pipeline reorder
真实 GraphSyncSolver barrier/event rewrite
```

这几个属于后续 Step 3/4/5，需要依赖更完整的 IR pattern、producer-consumer dependency graph、event lifetime analysis 和 vTriton/编译器验证。


---

## TESTING.md

# 测试体系说明

本项目的测试目标不是证明真实 NPU 性能提升，而是保证 strategy-search demo 的工程行为稳定、可回归、可维护。

## 1. 测试分层

| 层级 | marker | 默认运行 | 目的 |
|---|---|---:|---|
| Unit | `unit` | 是 | 检查 parser、cost model 局部公式、hardware gate 和 package facade |
| Smoke | `smoke` | 是 | 跑小 sample kernel，验证主流程和报告输出不坏 |
| Regression | `regression` | 部分默认 / 部分 slow | 锁住 Stage2a/Stage2b/Stage2c 的搜索稳定性行为 |
| Slow | `slow` | 否 | Beam vs compact exhaustive / random baseline 等较重审计 |

`pytest.ini` 默认使用：

```bash
-m "not slow"
```

因此日常 CI 不会运行最重的 search-quality audit。

## 2. 推荐命令

日常开发：

```bash
python -m pytest
```

只跑快速单元测试：

```bash
python -m pytest -m "unit and not slow"
```

只跑 smoke：

```bash
python -m pytest -m "smoke and not slow"
```

跑慢速搜索质量审计：

```bash
python -m pytest -m slow
```

跑全部 pytest 测试：

```bash
python -m pytest -m "unit or smoke or regression or slow"
```

兼容旧的 unittest 入口：

```bash
python -m unittest discover -s tests -v
```

注意：unittest 不理解 pytest marker，因此会把 slow 测试也一起运行。

## 3. 新增的关键测试

### Plan 参数敏感性测试

新增 `tests/test_cost_model_unit.py`，专门检查四类 Plan 的主要参数是否真的进入 cost / gate：

| 测试 | 防止的问题 |
|---|---|
| TilingPlan 改变 tile count 和局部 memory | tile 参数只在字段里变化，但 cost 不变 |
| block_dim 改变 effective parallelism | block 并行度不影响 cost |
| MultiBufferPlan 降低 exposed load/store，同时提高 live memory | double buffer 只给收益、不占资源，或完全不影响模型 |
| CVPipelinePlan 改变 Cube/Vector overlap，并产生估计合法性风险 | CV stage 只出现在报告里，不影响模型 |
| SyncPlan 改变 sync cost，并产生 graph/event 风险 | graph_sync_solver/event reuse 收益没有进入 cost 或风险没体现 |
| hardware gate 边界测试 | 容量刚好等于上限和超过上限的行为不稳定 |

### 搜索稳定性测试

原有 `tests/test_strategy_search_smoke.py` 保留 Stage2a/Stage2b/Stage2c 的回归测试，并将较重的搜索质量审计标记为 `slow`。

## 4. 当前测试边界

这些测试仍然不能证明：

1. selected strategy 能被真实 compiler lowering；
2. graph sync solver 一定 deadlock-free；
3. predicted cycles 等于 msprof 实测 cycles；
4. optional DES/trace profile 一定来自同一个真实 kernel。

它们解决的是工程稳定性问题：防止参数失效、搜索退化、报告字段丢失、硬件 gate 失效。

## 缺陷注入测试（synthetic bad MLIR regression）

本仓库现在包含 9 个带明确缺陷的 synthetic MLIR 样例：

```text
tests/defect_inputs/
tests/defect_expected/defect_run_summary.json
tests/test_defect_injection_cases.py
DEFECT_INJECTION_TEST_REPORT.md
```

这些样例覆盖小 tile、UB overflow、barrier-heavy、缺少 double buffer/CV overlap、已有局部优化但整体仍差、以及多种瓶颈叠加等情况。

默认测试会验证缺陷文件、parser 恢复出的 current IR tile/sync 信息，以及已记录搜索结果是否朝正确方向优化：

```bash
python -m pytest -q tests/test_defect_injection_cases.py -m regression
```

当前结果：

```text
18 passed, 9 skipped
```

其中 9 个 skipped 是 opt-in live search 测试。需要重新实跑 9 个缺陷样例时：

```bash
RUN_DEFECT_LIVE=1 python -m pytest -q -m slow tests/test_defect_injection_cases.py
```

注意：缺陷注入测试证明的是 analytical cost model 下的方向合理性，不证明真实硬件加速。真实验证仍需要 optimized HIVM rewrite、编译运行和 msprof profiling 闭环。


---

## V3_0_INTEGRATION_NOTES.md

# V3.0 · vTriton Bridge and Strategy-to-HIVM Rewrite

V3.0 turns the strategy-search demo into a vTriton-bridge candidate generator.

## What vTriton provides

vTriton can provide structured evidence for the optimizer:

- `.npuir.mlir` / HIVM MLIR dumped from Triton DSL or supplied directly.
- DES graph JSON (`--des-graph-file`) with operation, pipe, duration, dependency and transfer evidence.
- Perfetto/Chrome trace JSON (`--perfetto-trace-file`) for timeline inspection.
- Bound reports and counterfactual reports from its `perfbound` / validation pipeline when available.
- A validation direction: edit → compile → verify → delta, when a working vTriton build and target environment are available.

## What this demo provides

The demo remains the strategy-search layer:

- Parse HIVM/NPUIR MLIR and optional vTriton DES/trace/bound/counterfactual artifacts.
- Generate and rank four-plan strategy candidates.
- Check UB/L1/L0A/L0B/L0C/GM workspace constraints.
- Emit a selected strategy and a vTriton candidate bundle.

## New V3.0 outputs

Enable with `--enable-ir-rewrite`.

```bash
python auto_strategy_search.py \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --candidate-space expanded \
  --search-mode layered \
  --guided-mode diagnosis \
  --des-profile original_repo_outputs/sample_hivm_des.json \
  --trace-profile optional_profiles/prefill_trace.json \
  --bound-report original_repo_outputs/sample_hivm_bound_report.json \
  --counterfactual original_repo_outputs/counterfactual_results.json \
  --enable-ir-rewrite \
  --rewrite-mode both \
  --rewrite-safety conservative \
  --output-dir output_v3
```

The new bridge outputs are:

- `optimized.annotated.hivm.mlir`: original IR plus `hivm.strategy.*` attributes and module sync hint.
- `optimized.safe_structural.hivm.mlir`: conservative structural IR with safe sync/barrier hints and explicit safe buffer hints when selected strategy has per-buffer multipliers.
- `pass_pipeline_config.json`: requested pass pipeline configuration for TileLoop / MarkMultiBuffer / CVPipelining / GraphSyncSolver / PlanMemory.
- `strategy_edit_script.json`: edit primitive script that can be consumed or translated by a vTriton edit/verify harness.
- `rewrite_diff_report.json`: machine-readable rewrite changes and limitations.
- `rewrite_audit.md`: human-readable audit.
- `vtriton_candidate_bundle.json`: manifest with before/after IR paths and suggested `tritonsim-hivm` rerun command.
- `vtriton_integration_report.json`: summary of consumed vTriton evidence and emitted bridge artifacts.

## Important boundary

V3.0 does not claim to produce final compiler-lowered optimized IR. It produces:

1. strategy hints embedded in HIVM/NPUIR;
2. conservative local structural edits;
3. pass configuration and edit script for vTriton / real compiler validation.

The final correctness/performance proof should come from vTriton or the real compiler stack by running reparse / DES-after / compile / output correctness / msprof delta.


---

## VTRITON_BACKED_STRUCTURAL_REWRITE_REPORT.md

# Step-3 vTriton-compatible Structural Rewrite 实现报告

## 目标

前两个阶段只完成了 strategy annotation / safe hint rewrite。Step-3 的目标是开始**正式修改 HIVM/NPUIR 的执行结构**，输出 `optimized.structural.hivm.mlir`。

## 借鉴 vTriton 的地方

vTriton 的 `tools/hivm-crud/hivm-crud.cpp` 使用 `HivmOpsEditor` 读取 MLIR module，然后执行 operation-level CRUD：

- 在 `vadd` 前插入 `set_flag + wait_flag`；
- 删除 `set_flag / wait_flag`；
- 替换 `vadd -> vsub`；
- roundtrip 模式中调用 `removeRedundantLoadStorePair(removeGMTrips)`。

本项目新增 `strategy_search/structural_rewrite.py`，按照类似 CRUD primitive 设计生成并执行 `structural_edit_script.json`。

## 新增命令参数

```bash
--enable-structural-rewrite
--structural-rewrite-safety balanced
--vtriton-hivm-crud /path/to/hivm-crud      # 可选
--vtriton-crud-mode roundtrip               # 可选
--vtriton-remove-gm-trips 1                 # 可选
```

如果没有本地 vTriton build，会使用内置 Python fallback。

## 当前真实 structural edits

当前第一版只做显式 anchor 下的有限结构改写：

1. `replace_barrier_all_with_directional_sync`
   - 把粗粒度 `hivm.hir.barrier {mode="ALL"}` / `pipe_barrier[<PIPE_ALL>]` 替换成方向性 `set_flag + wait_flag`。

2. `insert_sync_before_first_vector_op`
   - 对 CVPipelinePlan，找到 cube/fixpipe 后第一个 vector op，在其前插入 `PIPE_FIX -> PIPE_V` 的 `set_flag + wait_flag`。

3. `hoist_invariant_q_load_from_simple_loop`
   - 对简单 FlashAttention 样例，把 loop 内明显 invariant 的 `Q_gm -> q_ub -> q_l1` load/nd2nz hoist 到 loop 外。

4. `remove_adjacent_duplicate_sync_pairs`
   - aggressive 模式下删除相邻重复 sync 行。

## 输出文件

启用 Step-3 后新增：

```text
optimized.structural.hivm.mlir
structural_edit_script.json
structural_rewrite_report.json
```

## 重要边界

这一步已经不是单纯 attribute/hint，而是会改变 operation sequence。但它仍不是完整 compiler lowering：

- 不生成新 loop nest；
- 不复制 buffer 成 ping-pong；
- 不做完整 CV overlap schedule；
- 不做全局依赖图证明；
- 仍需要 vTriton / tritonsim-hivm / 真实 compiler 做 parse、DES/trace 和 correctness 验证。


---

## cost_model_design_formula_explained.md

# V3.3.1 Cost Model 设计说明：Structure-aware Cycle Correction

本文档把当前 cost model 从输入、结构证据、分项 cycles、overlap、sync、penalty 到最终 `predicted_cycles` 完整展开。核心目标只有一个：

```text
估计一个候选策略的 total predicted cycles，用于候选排序和可解释分析。
```

当前模型不是实机 msprof cycles，也不是 profiling-calibrated hardware model。它是一个 **structure-aware analytical cycle estimation model**：先用硬件参数和候选策略算出基础 cycles，再用 MLIR 与编译产物中的结构证据修正各分项 cycles 的系统误差，最后汇总为总 cycles 估计。

---

## 1. 一句话理解当前 cost model

当前版本不要理解成：

```text
score = load + compute + store + sync + 一堆额外加权惩罚
```

而应该理解成：

```text
predicted_cycles = sum(corrected component cycle estimates) + necessary constraint/risk penalties
```

更直白地说：

```text
第一步：先估计这个策略本来要搬多少数据、算多少 cube/vector、做多少 sync、产生多少 scalar/control 开销。
第二步：再看这个 kernel 的 MLIR/产物结构到底偏 memory、compute、vector、scalar 还是 sync。
第三步：用这些结构证据修正对应分项的 cycles，而不是到处额外加分扣分。
第四步：把修正后的分项 cycles 加起来，得到 total predicted cycles。
```

---

## 2. 候选策略变量

一个候选策略记作：

```text
x = (T, M, P, Y)
```

其中：

| 符号 | Plan | 主要控制什么 |
|---|---|---|
| `T` | `TilingPlan` | tile_m/tile_n/tile_k、block_dim、loop_order、tail_strategy、reduce_split |
| `M` | `MultiBufferPlan` | double buffer、per-buffer multiplier、stage buffer、load/store overlap |
| `P` | `CVPipelinePlan` | cube-vector pipeline、pipeline stage、producer-consumer distance、CV template |
| `Y` | `SyncPlan` | keep existing / graph sync solver、event reuse、sync granularity、sync motion |

cost model 的任务是：给每个 `x` 算一个 `predicted_cycles(x)`，然后搜索器选择 cycles 最低且通过硬件边界检查的候选。

---

## 3. 总公式

当前总成本为：

```text
T_total(x) =
    T_tiles(x)
  + T_sync(x)
  + P_capacity(x)
  + P_shape(x)
  + P_legality(x)
```

其中：

| 项 | 含义 | 是否是 cycles 语义 |
|---|---|---|
| `T_tiles` | 所有 tile 的主计算/搬运/标量控制成本，考虑并行度 | 是，analytical cycles |
| `T_sync` | sync/barrier/event 的估计成本 | 是，analytical cycles |
| `P_capacity` | UB/L1/L0/GM workspace 容量压力软惩罚 | 近似 cycles penalty |
| `P_shape` | shape/tile 不规整导致的软惩罚 | 近似 cycles penalty |
| `P_legality` | GraphSyncSolver / event reuse / CV pipeline 未验证合法性的风险惩罚 | risk penalty，不等价于真实执行 cycles |

`T_tiles` 定义为：

```text
T_tiles(x) = N_tiles / E_parallel * T_tile(x)
```

其中：

```text
N_tiles      = 当前 tile shape 下的 tile 数量
E_parallel   = effective_parallelism
T_tile       = 单 tile 的 corrected steady time
```

`E_parallel` 会考虑：

```text
active_blocks = min(block_dim, available_cores, ceil(N_tiles))
waves = ceil(N_tiles / active_blocks)
tail_efficiency = N_tiles / (waves * active_blocks)
E_parallel = active_blocks * clamp(tail_efficiency, 0.20, 1.00)
```

所以 block_dim 不是越大越好。如果 tile 数很少、tail wave 很碎，有效并行度会被 tail efficiency 拉低。

---

## 4. 单 tile 成本：为什么不是简单 load + compute + store？

如果没有 double buffer / CV pipeline，模型采用保守串行形式：

```text
T_tile =
    T_load_corrected
  + T_compute_corrected
  + T_store_corrected
  + T_workspace_exposed
  + T_scalar_corrected
  + T_schedule
```

如果开启了 double buffer 或 CV pipeline，load、compute、store 理论上可以部分重叠，所以模型采用 exposed-time 形式：

```text
T_tile =
    max(T_load_exposed, T_compute_corrected, T_store_exposed)
  + T_workspace_exposed
  + T_scalar_corrected
  + T_schedule
  + T_warmup_drain
```

这个设计的含义是：

```text
在稳定流水里，主导时间不是 load + compute + store 全部相加，
而是三个 pipeline 中暴露出来的最长路径，加上不能被隐藏的 scalar/control、workspace、schedule 和 warmup/drain。
```

---

## 5. Base cycles：先算一个没有结构修正的基础估计

模型先根据候选策略和硬件参数计算基础项：

```text
T_load_base
T_store_base
T_cube_base
T_vector_base
T_fix_base
T_sync_base
T_scalar_base
T_workspace_base
```

这些基础项来自：

| base 项 | 主要来自 |
|---|---|
| `T_load_base` | tile bytes、dtype bytes、GM/UB/L1/L0 读路径、MTE 带宽估计 |
| `T_store_base` | tile 输出 bytes、store/fixpipe path、MTE 写路径估计 |
| `T_cube_base` | tile_m/tile_n/tile_k、cube op proxy、cube 吞吐估计 |
| `T_vector_base` | vector op count proxy、vector tile workload、vector throughput |
| `T_fix_base` | fixpipe/layout conversion/format conversion 的估计 |
| `T_sync_base` | barrier、set_flag、wait_flag、sync_block 的数量与经验 latency |
| `T_scalar_base` | scalar/control/address/index/cast/loop 调度基础开销 |
| `T_workspace_base` | GM workspace spill/fallback/handoff traffic |

注意：这些不是实机测量值，而是 analytical estimate。正因为基础估计会有系统偏差，才需要结构证据修正。

---

## 6. 结构证据到底是什么？

当前模型使用三类输入证据：

```text
1. MLIR 静态结构证据
2. DES 产物结构证据
3. trace event name/count 结构证据
```

它们共同生成 `kernel_cost_profile.json`。

### 6.1 MLIR 静态结构证据

MLIR 侧主要抽取：

| 证据 | 例子 | 说明 |
|---|---|---|
| flat op counts | `mmadL1`, `copy`, `nd2nz`, `fixpipe`, vector op, scalar op | 判断 kernel 的原始结构组成 |
| scalar family counts | `arith_scalar`, `index_cast`, `pointer_cast`, `scf_for`, `scf_if` | 判断 scalar/control/address 开销 |
| sync counts | `pipe_barrier`, `set_flag`, `wait_flag`, `sync_block_set/wait` | 判断同步密度 |
| loop-weighted counts | 内层循环中的 compute/memory/vector/scalar/sync | 内层操作重复执行，权重更高 |
| memory path | GM/UB/L1/L0 之间的静态 path bytes | 判断 memory path 压力 |
| buffer lifetime | buffer live span、byte-span pressure | 判断 workspace/buffer pressure |
| alignment/tail | dim/offset misalignment、mask/tail ops | 判断 vector/fix/scalar fragmentation |
| sequence pattern | copy->nd2nz->cube、cube->fixpipe->vector | 判断 pipeline 机会 |

### 6.2 DES 产物结构证据

DES 侧主要使用：

| 证据 | 使用方式 |
|---|---|
| pipe fraction | 判断 lowering 后更像 compute/memory/vector/scalar/sync 哪类 kernel |
| DMA bytes by space path | 增强 memory evidence |
| sync/barrier ops | 增强 sync evidence |
| critical pipe | 作为报告解释字段 |

重要边界：

```text
当前版本不使用 DES makespan/global duration 做 target calibration。
```

也就是说，模型不会做：

```text
predicted_cycles *= DES_makespan / base_prediction
```

它只把 DES pipe mix 当作结构比例证据。例如 pipe_s 很高，说明 lowering 后 scalar/control 路径很重，于是主要修正 scalar/control cycles。

### 6.3 trace event name/count 结构证据

trace 侧只使用 event name 和 count 的结构提示，例如：

```text
index_cast/cmpi/addi/muli/load/apply -> scalar hint
barrier/set_flag/wait_flag/sync      -> sync hint
```

同样不读取实测 duration target。

---

## 7. 结构比例如何融合？

模型先从 MLIR 得到一组静态比例：

```text
static_ratios = normalize({compute_score, memory_score, vector_score, scalar_score, sync_score})
```

如果 DES 产物可用，再得到一组产物比例：

```text
product_ratios = normalize({compute_pipe, memory_pipe, vector_pipe, scalar_pipe, sync_pipe})
```

当前 V3.3.1 的融合方式为：

```text
structure_ratios = 0.60 * static_ratios + 0.40 * product_ratios
structure_ratios = normalize(structure_ratios)
```

为什么不是产物 65% 或 80%？因为 DES pipe fraction 不是实机 profiling。它能反映 lowering 后结构，但仍可能被某一个 pipe 字段支配。降低产物权重可以避免单样本产物过度主导 cost model。

在你上传的样本中，融合后 profile 类似：

```text
compute = 0.016
memory  = 0.116
vector  = 0.079
scalar  = 0.553
sync    = 0.236
```

因此该 kernel 被判为：

```text
kernel_type = scalar_control_heavy
dominant_component = scalar
```

这不是说真实 cycles 中 scalar 一定占 55.3%，而是说结构证据显示 scalar/control 是最强的修正方向。

---

## 8. 从结构比例到 cycle correction factors

V3.3.1 的核心改动是：结构证据不再到处扩散成一堆 reward/penalty，而是映射为分项 cycle correction factors。

当前主要 factors 为：

```text
m_mem       = memory_cycle_correction
m_mem_path  = memory_path_cycle_correction
m_cube      = compute_cycle_correction
m_vec       = vector_cycle_correction
m_align     = alignment_cycle_correction
m_scalar    = scalar_cycle_correction
m_frag      = small_tile_fragmentation_correction
m_sync      = sync_cycle_correction
m_ws        = workspace_pressure_correction
c_overlap   = overlap_confidence
c_cv         = cv_overlap_confidence
```

### 8.1 每个 factor 的语义

为了避免 PDF 表格过宽，下面逐项说明每个 factor 的含义：

- `memory_cycle_correction`：修正 load/store/fix 的 memory side。主要来自 `memory_ratio`、memory path bytes、buffer pressure。含义是搬运路径比基础估计更重或更轻。
- `memory_path_cycle_correction`：修正 load/store。主要来自 GM/UB/L1/L0 path bytes。含义是具体 memory path 的复杂度修正。
- `compute_cycle_correction`：修正 cube compute。主要来自 compute ratio 和 CV opportunity。它不是 cube reward，只是 cube cycles 的估计修正。
- `vector_cycle_correction`：修正 vector compute。主要来自 vector ratio、alignment/tail proxy。
- `alignment_cycle_correction`：修正 vector/fix/scalar fragmentation。主要来自 dim/offset misalignment 和 mask/tail ops。
- `scalar_cycle_correction`：修正 scalar/control cycles。主要来自 scalar ratio、loop-weighted scalar ratio、alignment proxy。
- `small_tile_fragmentation_correction`：修正小 tile 下的 scalar/control 碎片化成本。主要来自 tile fragmentation 和 loop scalar。
- `sync_cycle_correction`：修正 sync cost。主要来自 sync ratio 和 sync criticality。
- `workspace_pressure_correction`：修正 workspace exposed cycles。主要来自 buffer lifetime pressure。
- `overlap_confidence`：修正 load/store overlap 的可信度。主要来自 scalar/sync/memory/CV opportunity，但只做窄范围修正。
- `cv_overlap_confidence`：修正 cube-vector overlap 的可信度。主要来自 compute/vector balance、scalar/sync density，也只做窄范围修正。

### 8.2 设计边界

```text
memory evidence 主要进 memory cycles
scalar evidence 主要进 scalar/control cycles
sync evidence 主要进 sync cycles
alignment evidence 主要进 vector/fix/scalar fragmentation
overlap confidence 只做窄范围修正
legality risk 单独进入 P_legality
```

这个边界是为了避免 double counting。

---

## 9. Corrected component cycles 逐项展开

### 9.1 Load / Store

```text
T_load_corrected  = T_load_base  * m_mem * m_mem_path
T_store_corrected = T_store_base * m_mem * m_mem_path
```

解释：

```text
基础 load/store 根据 bytes / bandwidth 估计；
如果 MLIR/产物显示 memory path 更复杂、DMA path 更多、buffer pressure 更高，
则通过 m_mem 和 m_mem_path 修正搬运 cycles。
```

### 9.2 Cube / Vector / Fix

```text
T_cube_corrected   = T_cube_base   * m_cube
T_vector_corrected = T_vector_base * m_vec * m_align
T_fix_corrected    = T_fix_base    * m_mem * m_align
```

解释：

```text
cube 主要受 compute correction 修正；
vector 受 vector correction 和 alignment correction 修正；
fixpipe/layout conversion 同时带有 memory side 和 alignment side，因此使用 m_mem 与 m_align。
```

### 9.3 Cube-vector pipeline

```text
T_compute_corrected =
    T_cube_corrected
  + T_vector_corrected
  - r_cv * c_cv * min(T_cube_corrected, T_vector_corrected)
  + T_fix_corrected
```

其中：

```text
r_cv = CVPipelinePlan 给出的策略 overlap ratio
c_cv = 结构证据给出的 CV overlap confidence
```

解释：

```text
CV pipeline 的主要收益来自候选策略本身；
结构证据只判断这个收益是否可信，不能把 compute-heavy 直接变成额外 reward。
```

### 9.4 Scalar/control

```text
T_scalar_corrected = T_scalar_base * m_scalar * m_frag
```

解释：

```text
scalar/control 不是主 cube/vector pipeline 的一部分；
大量 index_cast、pointer_cast、scf_for/scf_if、get_block_idx、mask/tail、inner-loop scalar op 会形成不可忽视的调度/控制成本。
```

在你上传的样本里，scalar/control 证据很强，所以 `scalar_cycle_correction` 明显高于 1。这是合理的，因为该 kernel 的 MLIR 和产物都显示 scalar/control-heavy。

### 9.5 Workspace

```text
T_workspace_exposed = T_workspace_base * m_ws
```

解释：

```text
GM workspace / handoff / spill traffic 不是普通 load/store 的完全可隐藏部分；
它更像 fallback traffic，因此作为 exposed cost 叠加。
```

### 9.6 Sync

```text
T_sync = T_sync_base * m_sync
```

其中基础 sync 通常来自：

```text
T_sync_base =
    num_barrier * barrier_latency
  + num_set_flag * set_flag_latency
  + num_wait_flag * wait_flag_latency
  + sync_block_cost
```

解释：

```text
sync evidence 只修正同步操作本身的估计开销。
GraphSyncSolver 未验证是否合法，不应该混进 T_sync，而应该放到 P_legality。
```

---

## 10. Overlap 如何处理？

### 10.1 Load/store overlap

候选策略先给出基础 overlap：

```text
r_load_strategy
r_store_strategy
```

结构证据只给出 confidence：

```text
r_load  = r_load_strategy  * c_overlap
r_store = r_store_strategy * c_overlap
```

然后：

```text
T_load_exposed  = T_load_corrected  * (1 - r_load)
T_store_exposed = T_store_corrected * (1 - r_store)
```

### 10.2 为什么 overlap confidence 是窄范围？

因为 overlap 的主因应该是策略和硬件合法性，例如：

```text
double_buffer 是否开启
per-buffer multiplier 是否足够
stage buffer 是否放得下
producer-consumer distance 是否合理
UB/L1/L0 是否 overflow
```

结构证据只能说“这个 overlap 可信度更高或更低”，不能说“scalar-heavy 所有 overlap 全部大幅失效”。因此 V3.3.1 将 overlap confidence 限定在较窄范围，避免重复惩罚。

---

## 11. Penalty 的语义

### 11.1 Capacity penalty

```text
P_capacity = memory_pressure_penalty(scope_utilization, hw)
```

它表示：虽然没有触发硬件 gate 的 hard overflow，但 UB/L1/L0 等资源已经接近边界，可能导致更高风险或更差调度。

### 11.2 Shape penalty

```text
P_shape = shape_regularization_penalty(tile shape, kernel shape, hw)
```

它表示：tile shape 与 kernel shape/hardware granularity 不匹配，可能产生 tail、fragmentation 或不规则访问。

### 11.3 Legality risk penalty

```text
P_legality =
    P_graph_sync_unknown
  + P_event_reuse_unknown
  + P_cv_pipeline_estimated
```

它专门表达策略合法性/可落地性不确定性。例如：

```text
GraphSyncSolver status = UNKNOWN
CV pipeline legality = PASS_ESTIMATED
```

这类风险不能说是真实执行时间，因此单独放在 `P_legality`，不污染 `T_sync` 的 cycles 语义。

---

## 12. V3.3.1 如何利用结构化信息？

完整链路如下：

```text
MLIR + product artifacts
        |
        v
extract structural evidence
        |
        v
compute static_ratios and product_ratios
        |
        v
fuse ratios: 60% MLIR + 40% artifact
        |
        v
build kernel_cost_profile
        |
        v
map evidence to cycle correction factors
        |
        v
correct load/compute/store/scalar/sync/workspace cycles
        |
        v
apply strategy overlap and narrow confidence correction
        |
        v
sum corrected cycles + necessary penalties
        |
        v
predicted_cycles
```

也就是：结构化信息现在不是独立 score，而是进入每个分项 cycle estimate。

### 12.1 例子：一个 scalar-heavy kernel

如果 MLIR/产物显示：

```text
scalar_ratio 高
loop_weighted_scalar 高
pipe_s fraction 高
sync density 较高
```

V3.3.1 的行为是：

```text
scalar_cycle_correction 上升
small_tile_fragmentation_correction 上升
sync_cycle_correction 适度上升
overlap_confidence 轻微下降
```

但它不会再让同一个 scalar-heavy 证据同时大幅：

```text
提高 scalar cost
提高 sync cost
提高 small tile penalty
大幅压低 overlap reward
大幅压低 CV reward
提高 legality risk
```

这就是 V3.3.1 相比 V3.3 更干净的地方。

---

## 13. 和 V3.3 的区别

### 13.1 V3.3 的逻辑

V3.3 更像：

```text
结构证据 -> 多个 multiplier/reward/penalty -> total predicted cycles
```

当 kernel 被判为 scalar/sync-heavy 时，同一类证据可能同时影响：

```text
scalar_control_multiplier
small_tile_scalar_penalty_scale
loop_weighted_scalar_multiplier
sync_multiplier
sync_criticality_multiplier
overlap_reward_scale
cv_reward_scale
cube_reward_scale
legality_risk_penalty
```

问题是：这些路径之间存在语义重叠。比如 scalar-heavy 既提高 scalar_control_time，又降低 overlap，又降低 CV reward，还可能提高 sync/risk。最终 `predicted_cycles` 仍然叫 cycles，但内部更像“多重加权 ranking score”。

### 13.2 V3.3.1 的逻辑

V3.3.1 改成：

```text
结构证据 -> 对应分项 cycle correction -> total predicted cycles
```

核心变化：

| 方面 | V3.3 | V3.3.1 |
|---|---|---|
| 总体语义 | structure-aware weighted cost | structure-aware corrected cycle estimate |
| 结构证据用途 | 可同时影响多个 cost/reward/penalty | 每类证据主要修正对应分项 cycles |
| scalar evidence | scalar、small tile、sync、overlap、CV reward 多路径影响 | 主要进入 scalar/control 和 fragmentation |
| sync evidence | sync multiplier、criticality multiplier、risk 可能叠加 | sync cycles 与 legality risk 分离 |
| overlap | 可能被 scalar/sync 较强打折 | 只做窄范围 confidence 修正 |
| DES artifact 权重 | 产物比例更强，容易主导 | MLIR 60% + artifact 40% 保守融合 |
| predicted_cycles 语义 | 更像 cycles-shaped ranking score | 更像 corrected component cycles sum |
| double counting 风险 | 较高 | 明显降低 |

### 13.3 为什么 V3.3.1 更适合汇报？

因为可以清楚回答领导的几个问题：

- 问：你的目标到底是算 score 还是 cycles？
  答：目标是估计 total predicted cycles。
- 问：结构信息干什么用？
  答：修正 load/compute/store/scalar/sync/workspace 各分项 cycles 的基础估计误差。
- 问：有没有用实机数据硬拟合？
  答：没有。在线寻优不使用 msprof target，不使用 DES makespan/global scale。
- 问：为什么不是 load + compute + store + sync 直接加？
  答：因为有 pipeline overlap。主 tile 部分在流水模式下使用 `max(exposed load, compute, exposed store)`，然后再加 scalar/control、workspace、schedule 等不可隐藏项。
- 问：GraphSyncSolver 不确定怎么办？
  答：执行时间估计和合法性风险分开；未知合法性进入 `P_legality`，不污染 sync cycles。

---

## 14. 当前样本的解释方式

以 `kernel_001.npuir.mlir + prefill_des.json + prefill_trace.json` 为例，当前 profile 显示：

```text
dominant_component = scalar
kernel_type = scalar_control_heavy
```

融合后的结构比例大致为：

```text
compute: 0.016
memory : 0.116
vector : 0.079
scalar : 0.553
sync   : 0.236
```

对应 correction factors 大致为：

```text
memory_cycle_correction = 1.10
compute_cycle_correction = 1.06
vector_cycle_correction = 1.02
scalar_cycle_correction = 1.72
sync_cycle_correction = 1.36
overlap_confidence = 0.88
cv_overlap_confidence = 0.90
```

可以这样解释：

```text
这个 kernel 不是典型 cube-heavy kernel，而是 scalar/control 与 sync 结构比较重。
因此模型主要提高 scalar/control cycles 和 sync cycles 的估计；
memory/compute/vector 只做轻微修正；
overlap 与 CV pipeline 收益只被轻度降置信，而不是被结构证据大幅砍掉。
```

这比 V3.3 的解释更稳，因为不会出现“一个 scalar-heavy 判断到处乘”的问题。

---

## 15. 当前模型仍然不能证明什么？

当前模型可以用于：

```text
候选策略排序
缺陷 MLIR 的相对诊断
硬件边界检查
解释为什么某些策略被惩罚或被选中
在没有实机 profiling 时做 conservative analytical search
```

但不能直接证明：

```text
真实 msprof cycles 一定等于 predicted_cycles
真实 speedup 一定等于 predicted speedup
GraphSyncSolver 策略一定可 rewrite 且 deadlock-free
DES pipe fraction 与实机 pipe active/stall cycles 完全一致
```

如果要把它升级为更真实的 hardware performance model，需要：

```text
同一批 kernel 的 current IR 与候选策略 rewrite 后实机 msprof 数据
每个候选的编译产物 / DES 产物，而不是共享一个 kernel-level artifact profile
用实机数据离线拟合 correction factors 的 alpha/clamp/config
用 held-out kernel 验证 ranking accuracy 和 cycles prediction error
```

---

## 16. 推荐的口头表述

汇报时可以这样说：

我们当前的 cost model 目标仍然是估计总 cycles，但不是直接使用实机 profiling。

模型先根据 tile、buffer、pipeline、sync plan 和硬件配置，计算 load、compute、store、scalar/control、sync 等基础 cycles。

然后利用 MLIR 和编译产物中的结构证据生成 kernel-level cycle correction factors。这些结构证据包括 op count、loop-weighted scalar/sync、memory path、buffer lifetime、DES pipe mix 和 trace event name count。

这些 correction factors 只修正对应的分项 cycles。例如 memory 证据修正 load/store，scalar 证据修正 scalar/control，sync 证据修正 sync。

最后模型汇总 corrected component cycles，并额外加入容量、shape 和合法性风险惩罚，得到 predicted_cycles。

相比 V3.3，V3.3.1 最大变化是降低了结构证据的重复加权风险。结构信息不再同时作为多路 reward/penalty 扩散，而是回到分项 cycles 修正的语义上。

---

## 17. 文件和报告中应该怎么看

运行后重点看这些文件：

| 文件 | 看什么 |
|---|---|
| `kernel_cost_profile.json` | kernel 类型、结构比例、cycle correction factors |
| `cost_breakdown.json` | selected strategy 的分项 cycles、overlap saving、penalty |
| `selected_strategy.json` | 最终选择的候选参数 |
| `selected_plan.json` | 四类 plan 的具体取值与 legality 状态 |
| `top_candidates.json` | Top 候选的排序与差异 |
| `hardware_boundary_audit.json` | UB/L1/L0/GM workspace 是否接近或超过边界 |

最关键的是：不要只看 `predicted_cycles` 一个数字，要同时看：

```text
load_exposed
store_exposed
cube_vector_time
scalar_control_time
sync_cost
memory_pressure_penalty
shape_regularization_penalty
legality_risk_penalty
kernel_cost_profile_weights
```

这些分项能说明为什么候选被选中或被压下去。

---

## 18. 小结

V3.3.1 的 cost model 可以概括为：

```text
structure-aware corrected component cycle model
```

它的关键优点是：

```text
1. 目标仍然是 total predicted cycles；
2. 结构证据用于修正分项 cycles，而不是额外打分；
3. memory/scalar/sync/vector/compute 各有相对清晰的修正边界；
4. overlap 由策略主导，结构证据只做窄范围 confidence 修正；
5. legality risk 与 sync cycles 分离；
6. 相比 V3.3，double counting 风险更低，汇报语义更清楚。
```

一句话：

V3.3.1 不是把结构信息拿来“再加权一次总成本”。它的做法是：

```text
结构信息 -> 修正每个分项 cycles 的估计误差 -> 汇总为 predicted total cycles
```


---

## cost_model_design_formula_explained_pycharm_plain.md

# V3.3.1 Cost Model 设计说明：Structure-aware Cycle Correction

本文档说明当前版本的 cost model。核心原则是：**目标仍然是估计 total predicted cycles**。MLIR 与编译产物中的结构证据不是额外 score，也不是实机 profiling target，而是用于修正 load、compute、store、sync、scalar/control 等分项 cycles 的基础估计误差。

一句话概括：

```text
predicted_cycles = sum(corrected component cycle estimates) + necessary constraint/risk penalties
```

当前模型不声称输出真机 cycles。它是一个 structure-aware analytical cycle estimation model，适用于候选策略排序、缺陷识别、硬件边界审计和汇报解释。

---

## 1. 总公式

候选策略记为：

```text
x = (T, M, P, Y)
```

其中：

- `T` 是 TilingPlan；
- `M` 是 MultiBufferPlan；
- `P` 是 CVPipelinePlan；
- `Y` 是 SyncPlan。

总成本定义为：

```text
T_total(x) =
    T_tiles(x)
  + T_sync(x)
  + P_capacity(x)
  + P_shape(x)
  + P_legality(x)
```

其中：

```text
T_tiles(x) = N_tiles / E_parallel * T_tile(x)
```

`N_tiles` 是 tile 数，`E_parallel` 是考虑 block_dim、可用 core 数、wave tail efficiency 后的有效并行度。

---

## 2. 单 tile 成本

如果开启 double buffer 或 CV pipeline，单 tile 成本采用 pipeline exposed-time 形式：

```text
T_tile =
    max(T_load_exposed, T_compute_corrected, T_store_exposed)
  + T_workspace_exposed
  + T_scalar_corrected
  + T_schedule
  + T_warmup_drain
```

如果没有 double buffer / CV pipeline，则采用更保守的串行形式：

```text
T_tile =
    T_load_corrected
  + T_compute_corrected
  + T_store_corrected
  + T_workspace_exposed
  + T_scalar_corrected
  + T_schedule
```

这里的关键是：load、compute、store、sync、scalar/control 每一项仍然尽量保持 cycles 语义，而不是随意加权打分。

---

## 3. Base pipe cycles

首先基于策略参数和硬件参数计算基础估计：

```text
T_load_base
T_store_base
T_cube_base
T_vector_base
T_fix_base
T_sync_base
T_scalar_base
T_workspace_base
```

这些基础项来自 tile shape、dtype bytes、memory traffic、cube/vector op proxy、sync op count、硬件带宽/吞吐/latency 等 analytical 信息。它们不是实机测量值。

---

## 4. 结构证据

V3.3.1 从 MLIR 与编译产物中抽取结构证据：

| 证据类型 | 例子 | 用途 |
|---|---|---|
| flat op counts | `mmadL1`, `copy`, `fixpipe`, vector op, scalar op, barrier | 判断 compute/memory/vector/scalar/sync 结构比例 |
| loop-weighted counts | 内层循环中的 memory/scalar/sync 操作 | 修正 per-tile scalar/control 和 sync 估计 |
| memory path | GM/UB/L1/L0 space path bytes | 修正 load/store/workspace cycles |
| buffer lifetime | local buffer live span, byte-span pressure | 修正 workspace exposed cycles |
| sync criticality | inner-loop sync, cross-pipe set/wait, missing pair | 修正 sync cycles 和 legality risk |
| alignment/tail/mask | dim misalignment, offset misalignment, mask/tail ops | 修正 vector/fix/scalar fragmentation |
| sequence pattern | copy -> nd2nz -> cube, cube -> fixpipe -> vector | 判断 CV overlap 机会 |
| DES/trace product | pipe fraction, DMA path, event names | 作为 lowering 后结构证据，不作为 profiling target |

当 DES pipe fraction 可用时，当前版本采用保守融合：

```text
structure_ratios = 0.60 * MLIR_static_ratios + 0.40 * product_artifact_ratios
```

这样可以利用产物结构信息，但避免单个 DES pipe mix 过度主导 cost model。

---

## 5. Cycle correction factors

结构证据被映射为分项 cycle correction factors：

```text
m_mem       = memory_cycle_correction
m_mem_path  = memory_path_cycle_correction
m_cube      = compute_cycle_correction
m_vec       = vector_cycle_correction
m_align     = alignment_cycle_correction
m_scalar    = scalar_cycle_correction
m_frag      = small_tile_fragmentation_correction
m_sync      = sync_cycle_correction
m_ws        = workspace_pressure_correction
c_overlap   = overlap_confidence
c_cv         = cv_overlap_confidence
```

设计原则是：**每类结构证据只修正少数对应分项**。

| correction factor | 修正对象 | 不再做的事情 |
|---|---|---|
| `memory_cycle_correction` | load/store/fix memory side | 不修正 scalar/sync |
| `compute_cycle_correction` | cube compute | 不直接制造 cube reward |
| `vector_cycle_correction` | vector compute | 不直接影响 sync |
| `scalar_cycle_correction` | scalar/control cycles | 不强烈压低所有 overlap reward |
| `sync_cycle_correction` | sync cycles | 不混入 legality risk |
| `workspace_pressure_correction` | workspace exposed cycles | 不改变主 load/store overlap |
| `overlap_confidence` | load/store overlap 可信度 | 仅窄范围修正 |
| `cv_overlap_confidence` | cube-vector overlap 可信度 | 仅窄范围修正 |

---

## 6. Corrected component cycles

Memory 相关项：

```text
T_load_corrected  = T_load_base  * m_mem * m_mem_path
T_store_corrected = T_store_base * m_mem * m_mem_path
```

Compute 相关项：

```text
T_cube_corrected   = T_cube_base   * m_cube
T_vector_corrected = T_vector_base * m_vec * m_align
T_fix_corrected    = T_fix_base    * m_mem * m_align
```

Cube-vector pipeline 项：

```text
T_compute_corrected =
    T_cube_corrected
  + T_vector_corrected
  - r_cv * c_cv * min(T_cube_corrected, T_vector_corrected)
  + T_fix_corrected
```

其中 `r_cv` 主要来自候选策略的 CVPipelinePlan，`c_cv` 只是结构证据给出的窄范围 confidence。

Scalar/control 项：

```text
T_scalar_corrected = T_scalar_base * m_scalar * m_frag
```

Sync 项：

```text
T_sync = T_sync_base * m_sync
```

Workspace 项：

```text
T_workspace_exposed = T_workspace_base * m_ws
```

---

## 7. Overlap 处理

Double buffer / multi-buffer 的收益主要由候选策略决定：

```text
r_load_strategy
r_store_strategy
```

结构证据只修正这些 overlap 是否可信：

```text
r_load  = r_load_strategy  * c_overlap
r_store = r_store_strategy * c_overlap
```

暴露出来的 load/store 成本为：

```text
T_load_exposed  = T_load_corrected  * (1 - r_load)
T_store_exposed = T_store_corrected * (1 - r_store)
```

当前实现中 `c_overlap` 与 `c_cv` 被限制在较窄范围内，避免 scalar-heavy 或 sync-heavy 证据同时通过多个路径重复惩罚同一个候选。

---

## 8. Sync cost 与 legality risk 分离

同步操作本身的成本：

```text
T_sync = T_sync_base * sync_cycle_correction
```

GraphSyncSolver、event reuse、CV pipeline 等未完全验证的风险不再混入 sync cycles，而是单独进入：

```text
P_legality = P_sync_unknown + P_event_reuse + P_cv_estimated
```

这样可以保持两个语义清楚：

```text
T_sync      = 同步操作大约要花多少 cycles
P_legality  = 这个策略在真实 rewrite/编译中有多不确定
```

---

## 9. Penalty 项

当前保留三类主要 penalty。

### 9.1 Capacity penalty

```text
P_capacity = memory_pressure_penalty(scope_utilization, hardware_caps)
```

未 overflow 时，它是软惩罚；真正的 UB/L1/L0A/L0B/L0C/GM workspace overflow 由 feasibility gate 处理。

### 9.2 Shape regularization penalty

```text
P_shape = shape_regularization_penalty(tile_m, tile_n, tile_k, tail_strategy, alignment)
```

它用于惩罚过碎、过不规则、对齐差或 tail 处理代价高的 tile。

### 9.3 Legality risk penalty

```text
P_legality = sync_unknown_penalty + event_reuse_penalty + cv_estimated_penalty
```

它用于表达 demo 阶段无法证明 GraphSyncSolver deadlock-free、event reuse 合法性或 CV pipeline legality 的不确定性。

---

## 10. 与原 V3.3 的关键区别

原 V3.3 的 artifact kernel profile 已经能使用 MLIR 与产物结构证据，但权重传播偏宽，存在 double counting 风险。例如 scalar/sync-heavy 证据可能同时：

```text
提高 scalar cost
提高 sync cost
提高 small tile penalty
压低 overlap reward
压低 CV reward
提高 legality/sync criticality multiplier
```

V3.3.1 收敛为：

```text
结构证据 -> 对应分项 cycle correction -> 汇总 total predicted cycles
```

主要变化：

| 位置 | 原 V3.3 | V3.3.1 |
|---|---|---|
| DES/MLIR 融合 | MLIR 35% + product 65% | MLIR 60% + product 40% |
| scalar evidence | 影响 scalar/sync/overlap/CV/small tile | 主要影响 scalar/control 和 fragmentation |
| sync evidence | 影响 sync、overlap、CV、criticality multiplier | 主要影响 sync cycles，risk 单独进入 penalty |
| overlap | 可能被结构证据大幅压低 | 只做窄范围 confidence 修正 |
| cost 语义 | 更像 weighted analytical score | 更像 corrected total cycle estimate |

---

## 11. 当前输出字段说明

`cost_breakdown` 中关键字段包括：

| 字段 | 含义 |
|---|---|
| `tau_load`, `tau_store` | 修正后的 load/store per-tile cycles |
| `tau_cube`, `tau_vector`, `tau_fix` | 修正后的 cube/vector/fix per-tile cycles |
| `load_exposed`, `store_exposed` | overlap 后暴露出来的 load/store cycles |
| `cube_vector_time` | cube/vector/fix pipeline 后的 compute 侧 cycles |
| `scalar_control_time` | scalar/control/address/schedule 的 per-tile cycles |
| `workspace_exposed` | GM workspace fallback/spill 的暴露成本 |
| `sync_cost` | 修正后的同步成本 |
| `memory_pressure_penalty` | 容量压力软惩罚 |
| `shape_regularization_penalty` | shape/tail/alignment 软惩罚 |
| `legality_risk_penalty` | 未验证策略的风险惩罚 |
| `parallelized_tile_cycles` | 乘以 tile 数并除以有效并行度后的 tile 主体成本 |
| `predicted_cycles` | 总 estimated cycles |

---

## 12. 当前边界

当前 cost model 仍然有以下边界：

1. `predicted_cycles` 是 analytical estimate，不是真机实测 cycles。
2. `kernel_cost_profile` 使用 MLIR 与产物结构证据，但不使用 msprof target。
3. DES pipe fraction 只作为 product artifact ratio，不作为 makespan/global scale。
4. 所有 correction factor 仍需要未来通过多 kernel 实机 profiling 数据离线训练。
5. GraphSyncSolver 的 UNKNOWN legality 只能通过 penalty 表达，不能证明真实 rewrite 安全。

---

## 13. 最推荐的汇报表述

可以这样介绍当前版本：

```text
当前 cost model 的目标仍然是估计总 cycles。我们先基于 tile、buffer、pipeline、sync plan 和硬件参数计算 load、compute、store、sync、scalar/control 的基础 cycles，再用 MLIR 与编译产物中的结构证据对对应分项做 cycle correction，最后汇总得到 total predicted cycles。结构证据不是额外打分项，也不是实机 profiling 校准，而是用于修正 analytical model 的系统性偏差。
```

也可以更短地说：

```text
V3.3.1 是 structure-aware cycle estimation model，不是 profiling-calibrated hardware performance model。
```


---

## cost_model_hyperparameters_training_data.md

# V3.3.1 Cost Model 超参数与离线训练数据说明

本文档对应 **V3.3.1 Structure-aware Cycle Correction Cost Model**。

V3.3.1 的在线模型只读取：

```text
MLIR / NPUIR 文件
MLIR-derived artifact files: prefill_des.json, prefill_trace.json
hardware config
cost model config
```

它不在线读取实机 profiling，不使用 DES makespan/global scale 作为默认校准。实机数据的用途是未来**离线训练/校准参数**，训练后的参数固化到配置文件中。

---

## 1. V3.3.1 超参数分层

### 1.1 基础 analytical 参数

| 类别 | 例子 | 作用 | 未来训练需求 |
|---|---|---|---|
| 硬件吞吐 | MTE 带宽、Cube FLOPs、Vector 吞吐 | 计算 load/store/cube/vector 基础时间 | 需要用实机数据校准 |
| 启动开销 | DMA/Cube/Vector startup cycles | 小 tile / 短 op 的固定启动成本 | 需要校准 |
| overlap 参数 | load/store overlap、CV overlap | 估计 double buffer / pipeline 能隐藏多少时间 | 强烈需要校准 |
| 同步参数 | event cost、barrier cost、stall factor | 估计 set/wait/barrier/sync block 开销 | 强烈需要校准 |
| memory pressure | pressure threshold、alpha、cap | 防止候选贴近 UB/L1/L0 容量边界 | 可训练 |
| shape penalty | tail、mask、alignment、irregular shape | 惩罚不规整 tile | 可训练 |
| risk penalty | graph sync unknown、event reuse、CV estimated | 未验证收益的保守惩罚 | 可训练/策略化 |

### 1.2 V3.3.1 KernelCostProfile 参数

V3.3.1 的参数控制 MLIR/artifact 结构如何转成分项 cycle correction factors。

| 类别 | 参数例子 | 作用 |
|---|---|---|
| 结构分数权重 | compute_score_weight、memory_score_weight、scalar_score_weight、sync_score_weight | 把 MLIR/artifact 特征映射为 compute/memory/vector/scalar/sync ratios |
| loop-weighted 权重 | loop_weighted_scalar_multiplier、loop_weighted_sync_multiplier | 内层 loop op 的额外权重 |
| memory path 权重 | GM->UB、UB->GM、GM->L1、L1->L0、L0C->GM | 不同 memory path 的相对代价 |
| scalar/control 权重 | arith、index_cast、pointer_cast、apply、loop_control | scalar/control/address 开销 |
| sync criticality 权重 | inner_loop_sync、cross_pipe_event、barrier、unmatched_event | 同步关键性代理 |
| buffer pressure 权重 | live span、byte-span、multi-buffer slot、reuse distance proxy | buffer lifetime 与 per-buffer double buffer 风险 |
| artifact confidence | mlir_only_confidence、mlir_plus_artifact_confidence | 没有 artifact 时 correction factor 向 1.0 收缩 |
| cycle correction | memory_cycle_correction、compute_cycle_correction、vector_cycle_correction、scalar_cycle_correction、sync_cycle_correction | 修正对应分项 cycles 的基础估计误差 |
| overlap confidence | overlap_confidence、cv_overlap_confidence | 仅在窄范围内修正 overlap 可信度，避免重复惩罚 |

---

## 2. 在线输入与离线训练数据的区别

### 2.1 在线输入

在线寻优阶段：

```text
kernel.npuir.mlir
prefill_des.json / prefill_trace.json  # 可选 MLIR-derived artifact
configs/*.json
```

这些输入用于抽取结构特征，不包含实机 latency target。

### 2.2 离线训练数据

未来训练需要的数据格式应是：

```text
MLIR + artifacts + strategy metadata + real measured target
```

例如每条样本包含：

| 字段 | 含义 |
|---|---|
| `sample_id` | kernel/strategy 样本 ID |
| `mlir_file` | 输入 MLIR |
| `artifact_des_graph` | MLIR-derived DES graph artifact |
| `artifact_trace` | MLIR-derived trace artifact |
| `strategy` | tiling / multibuffer / cvpipeline / sync 参数 |
| `kernel_cost_profile` | 在线抽取的结构 profile |
| `cost_breakdown` | compute/memory/vector/scalar/sync/overlap/risk 分项 |
| `measured_latency` | 实机 msprof 或稳定 benchmark target |
| `device_info` | 硬件型号、频率、软件栈版本 |

训练目标不是让线上模型读取 measured latency，而是用 measured latency 学习参数。

---

## 3. 推荐训练目标

对寻优项目而言，最重要的不是绝对 cycles，而是候选排序。因此推荐同时看：

| 指标 | 作用 |
|---|---|
| MAPE / MAE | 绝对预测误差 |
| Spearman rank correlation | 候选排序是否更接近实机 |
| Top-k recall | 实机 best 是否落在模型 top-k |
| Best regret | 模型选中策略相对实机最优损失多少 |
| Kernel-family split | 泛化到不同 kernel 类型的能力 |

---

## 4. 防止过拟合的建议

V3.3.1 的结构增强会提高表达能力，也会带来规则型过拟合风险。推荐：

1. 所有 correction factor 设置上下限；
2. 使用连续平滑函数，不用硬阈值跳变；
3. MLIR-only 模式下降低 confidence，让 correction factor 向 1.0 收缩；
4. artifact evidence 只作为结构证据，不使用 makespan/global scale；
5. 离线训练时按 kernel 或 kernel family 切分 train/valid/test；
6. 做 feature ablation，确认 loop-weighted、memory path、sync criticality、buffer pressure 等特征各自有贡献。

---

## 5. 推荐配置输出

训练后的参数建议固化为：

```text
configs/cost_model_conservative.json
configs/cost_model_balanced.json
configs/cost_model_aggressive.json
configs/cost_model_v33_trained.json  # 未来可选
```

配置中应包含：

```json
{
  "cost_model_strategy_effects": {...},
  "cost_model_safety": {...},
  "cost_model_risk_modes": {...},
  "kernel_profile_weights": {
    "scalar_control": {...},
    "memory_path": {...},
    "sync_criticality": {...},
    "buffer_pressure": {...},
    "artifact_confidence": {...}
  }
}
```

当前 V3.3.1 已预留结构，但参数仍主要是 heuristic，需要未来实机数据离线训练。


---

## cost_model_hyperparameters_training_data_pycharm.md

# V3.3 Cost Model 超参数与离线训练数据说明

本文档对应 **V3.3 Artifact Kernel Profile Cost Model**。

V3.3 的在线模型只读取：

```text
MLIR / NPUIR 文件
MLIR-derived artifact files: prefill_des.json, prefill_trace.json
hardware config
cost model config
```

它不在线读取实机 profiling，不使用 DES makespan/global scale 作为默认校准。实机数据的用途是未来**离线训练/校准参数**，训练后的参数固化到配置文件中。

---

## 1. V3.3 超参数分层

### 1.1 基础 analytical 参数

| 类别 | 例子 | 作用 | 未来训练需求 |
|---|---|---|---|
| 硬件吞吐 | MTE 带宽、Cube FLOPs、Vector 吞吐 | 计算 load/store/cube/vector 基础时间 | 需要用实机数据校准 |
| 启动开销 | DMA/Cube/Vector startup cycles | 小 tile / 短 op 的固定启动成本 | 需要校准 |
| overlap 参数 | load/store overlap、CV overlap | 估计 double buffer / pipeline 能隐藏多少时间 | 强烈需要校准 |
| 同步参数 | event cost、barrier cost、stall factor | 估计 set/wait/barrier/sync block 开销 | 强烈需要校准 |
| memory pressure | pressure threshold、alpha、cap | 防止候选贴近 UB/L1/L0 容量边界 | 可训练 |
| shape penalty | tail、mask、alignment、irregular shape | 惩罚不规整 tile | 可训练 |
| risk penalty | graph sync unknown、event reuse、CV estimated | 未验证收益的保守惩罚 | 可训练/策略化 |

### 1.2 V3.3 KernelCostProfile 参数

V3.3 新增的参数控制 MLIR/artifact 结构如何转成动态 cost 权重。

| 类别 | 参数例子 | 作用 |
|---|---|---|
| 结构分数权重 | compute_score_weight、memory_score_weight、scalar_score_weight、sync_score_weight | 把 MLIR/artifact 特征映射为 compute/memory/vector/scalar/sync ratios |
| loop-weighted 权重 | loop_weighted_scalar_multiplier、loop_weighted_sync_multiplier | 内层 loop op 的额外权重 |
| memory path 权重 | GM->UB、UB->GM、GM->L1、L1->L0、L0C->GM | 不同 memory path 的相对代价 |
| scalar/control 权重 | arith、index_cast、pointer_cast、apply、loop_control | scalar/control/address 开销 |
| sync criticality 权重 | inner_loop_sync、cross_pipe_event、barrier、unmatched_event | 同步关键性代理 |
| buffer pressure 权重 | live span、byte-span、multi-buffer slot、reuse distance proxy | buffer lifetime 与 per-buffer double buffer 风险 |
| artifact confidence | mlir_only_confidence、mlir_plus_artifact_confidence | 没有 artifact 时动态权重向 1.0 收缩 |
| reward scale | cube_reward_scale、overlap_reward_scale、cv_reward_scale | 根据 kernel profile 降低或保留收益 |

---

## 2. 在线输入与离线训练数据的区别

### 2.1 在线输入

在线寻优阶段：

```text
kernel.npuir.mlir
prefill_des.json / prefill_trace.json  # 可选 MLIR-derived artifact
configs/*.json
```

这些输入用于抽取结构特征，不包含实机 latency target。

### 2.2 离线训练数据

未来训练需要的数据格式应是：

```text
MLIR + artifacts + strategy metadata + real measured target
```

例如每条样本包含：

| 字段 | 含义 |
|---|---|
| `sample_id` | kernel/strategy 样本 ID |
| `mlir_file` | 输入 MLIR |
| `artifact_des_graph` | MLIR-derived DES graph artifact |
| `artifact_trace` | MLIR-derived trace artifact |
| `strategy` | tiling / multibuffer / cvpipeline / sync 参数 |
| `kernel_cost_profile` | 在线抽取的结构 profile |
| `cost_breakdown` | compute/memory/vector/scalar/sync/overlap/risk 分项 |
| `measured_latency` | 实机 msprof 或稳定 benchmark target |
| `device_info` | 硬件型号、频率、软件栈版本 |

训练目标不是让线上模型读取 measured latency，而是用 measured latency 学习参数。

---

## 3. 推荐训练目标

对寻优项目而言，最重要的不是绝对 cycles，而是候选排序。因此推荐同时看：

| 指标 | 作用 |
|---|---|
| MAPE / MAE | 绝对预测误差 |
| Spearman rank correlation | 候选排序是否更接近实机 |
| Top-k recall | 实机 best 是否落在模型 top-k |
| Best regret | 模型选中策略相对实机最优损失多少 |
| Kernel-family split | 泛化到不同 kernel 类型的能力 |

---

## 4. 防止过拟合的建议

V3.3 的结构增强会提高表达能力，也会带来规则型过拟合风险。推荐：

1. 所有 multiplier 设置上下限；
2. 使用连续平滑函数，不用硬阈值跳变；
3. MLIR-only 模式下降低 confidence，让动态权重向 1.0 收缩；
4. artifact evidence 只作为结构证据，不使用 makespan/global scale；
5. 离线训练时按 kernel 或 kernel family 切分 train/valid/test；
6. 做 feature ablation，确认 loop-weighted、memory path、sync criticality、buffer pressure 等特征各自有贡献。

---

## 5. 推荐配置输出

训练后的参数建议固化为：

```text
configs/cost_model_conservative.json
configs/cost_model_balanced.json
configs/cost_model_aggressive.json
configs/cost_model_v33_trained.json  # 未来可选
```

配置中应包含：

```json
{
  "cost_model_strategy_effects": {...},
  "cost_model_safety": {...},
  "cost_model_risk_modes": {...},
  "kernel_profile_weights": {
    "scalar_control": {...},
    "memory_path": {...},
    "sync_criticality": {...},
    "buffer_pressure": {...},
    "artifact_confidence": {...}
  }
}
```

当前 V3.3 已预留结构，但参数仍主要是 heuristic，需要未来实机数据离线训练。


---

## optional_profiles_README.md

# MLIR-derived Artifact Inputs for V3.3

V3.3 uses **MLIR-derived compiler/modeling artifacts** as optional structural inputs. These files are generated from `.npuir.mlir` by vTriton/HIVM analysis tools. They are **not** real-device profiling data and are not treated as measured latency.

Preferred CLI names:

- `--artifact-des-graph <path.json>`: MLIR-derived DES graph artifact, usually named like `prefill_des.json`. It should contain an `operations` array with fields such as `name`, `pipe`, `duration`, `loop_multiplier`, `depends_on`, `is_sync`, `is_barrier`, `event_id`, `bytes`, `flops`, `read_buffers`, `write_buffers`, `src_space`, and `dst_space`.
- `--artifact-trace <path.json>`: MLIR-derived Perfetto/Chrome trace artifact, usually named like `prefill_trace.json`. It should contain `traceEvents` and is used for event-name and sequence evidence.

Deprecated aliases kept for backward compatibility:

- `--des-profile` -> `--artifact-des-graph`
- `--trace-profile` -> `--artifact-trace`

## Important boundary

The default V3.3 online path uses these artifacts only as **structural evidence**:

- pipe/op composition;
- dependency and cross-pipe sync evidence;
- memory space path and bytes proxies;
- buffer read/write and multi-buffer slot evidence;
- loop multiplier and operation sequence patterns;
- trace event-name counts.

It does **not** use:

- real msprof latency;
- measured kernel runtime;
- DES makespan as a target;
- global-scale calibration.

Use the V3.3 default:

```bash
python -m strategy_search.cli \
  --kernel sample_product/kernel_001.npuir.mlir \
  --hardware-config configs/ascend_910b.json \
  --artifact-des-graph sample_product/prefill_des.json \
  --artifact-trace sample_product/prefill_trace.json \
  --artifact-kernel-profile on \
  --des-calibration-mode off \
  --output-dir out_artifact_kernel_profile
```

The legacy `--des-calibration-mode single_trace_prior` path is retained only for offline experiments. It uses DES makespan/global-scale alignment and should not be presented as the V3.3 online cost model.
