# V6.4 update: official backend final sanitize

V6.4 fixes the V6.3 official-document blockers found by manual audit: memref.subview now preserves GM/CBUF/UB address space, hivm.hir.load/store use GM→local and local→GM direction after subview lowering, Q/O tile subviews are relocated into tile-loop scope where possible, GM→CBUF copy in the sample path is lowered to local nd2nz staging, and a stricter v64 manual official audit is emitted. Linux backend parse/verify/compile remains required before claiming runnable performance.


## V6.1 - four-plan Linux handoff and real backend validation package

- 新增 `strategy_search/operation_rewrite/linux_handoff_v61.py`，在 V6.0 real operation materialization 后生成可复制到 Ascend Linux 的 `linux_handoff/` 目录。
- 新增 `scripts/run_v61_four_plan_linux_handoff.sh/.cmd`。
- `linux_handoff/` 包含 baseline/optimized HIVM、selected plan、backend command templates、acceptance gates、backend patch contract、Linux validation runner 和 msprof comparison collector。
- `four_plan_operation_rewrite_summary.json` 新增 `v61_linux_handoff_created`、`v61_linux_handoff_dir`、`v61_backend_patch_contract`、`recommended_next_step`。
- 明确边界：V6.1 不声称 Linux compile/run/msprof 已通过；它把项目推进到可在线下真实 backend 执行 parse/roundtrip/verify/compile/run/msprof 的落地 handoff 阶段。

# Changelog
## V6.0 - Four-Plan Real Operation Materialization

- Added `strategy_search/operation_rewrite/real_operation_materialization_v60.py`.
- Added a V6.0 materialization pass that moves V5.8/V5.9 semantic comments onto concrete HIVM operations as attributes or `annotation.mark` operations.
- TilingPlan: materializes tile-slice bindings, reduction accumulator bindings, tail strategy guard, reduce-tile guard, and layout-aware guard into op attributes/annotations.
- CVPipelinePlan: materializes stage role, prologue/steady/epilogue schedule, producer-consumer distance, tile index expression, pipeline template, stage count, and buffer-policy information into op attributes/annotations.
- SyncPlan: annotates regenerated dependency information on `wait_flag` / `set_flag` operations after Tiling/MultiBuffer/CVPipeline rewrite.
- MultiBufferPlan: adds `v60_multibuffer_use_def_coverage.json` for ping/pong slot coverage and conservative original-use risk reporting.
- Added `v60_semantic_marker_materialization_audit.json`; V6.0 passes when `semantic_marker_as_logic_count = 0` and required V6.0 materialization attributes exist.
- Added scripts: `scripts/run_v60_four_plan_real_operation_materialization.sh` and `.cmd`.
- Added tests in `tests/test_v60_real_operation_materialization.py`.
- Recommended Linux validation IR is now `optimized.four_plan_real_operation_materialized.hivm.mlir`.
- Boundary remains: V6.0 is stronger Linux-handoff materialization, not proof of Linux parser/verifier/backend compile/correctness/msprof success.

## V5.9 - Four-Plan Semantic Rewrite Syntax/Schedule Hardening

- Added `strategy_search/operation_rewrite/syntax_hardening_v59.py`.
- Fixed FA-like M/N/K constant materialization: `%cN` now maps to sequence length and `%cK` to head/reduction dimension for the sample pattern; `%cB` maps to selected `tile_n`.
- Added nested memref address-space closure repair before Linux handoff.
- Normalized bracket-style `wait_flag` / `set_flag` event operations back to attr-style HIVM operation form while preserving producer/consumer pipe metadata.
- Added `v59_textual_legality_audit.json` checking malformed memref closures, bracket-style event ops, and unlowered placeholders in code.
- Added `scripts/run_v59_four_plan_semantic_rewrite_hardening.sh`.
- Added `tests/test_v59_semantic_rewrite_hardening.py`.
- Recommended Linux validation IR is now `optimized.four_plan_operation_rewrite.v59_syntax_hardened.hivm.mlir`.
- Boundary remains: V5.9 is Linux-handoff hardening, not proof of Linux compile/run/msprof success.

## V5.4 - TilingPlan Operation Readiness

- Added `strategy_search/tiling_operation_readiness.py` to upgrade TilingPlan from report/hint-only into Linux backend anchor/dry-run prevalidation.
- Added dry-run operation plan generation for `tile_m`, `tile_n`, `tile_k`, `loop_order`, `tail_strategy`, `reduce_tile_policy`, and `layout_aware_tile`.
- Integrated TilingPlan operation readiness into `strategy_search/rewrite_readiness.py`; TilingPlan can now report `READY_FOR_LINUX_BACKEND_ANCHOR_DRY_RUN` when loop/compute/load/store anchors are found.
- Added CLI/tooling: `tools/run_tiling_operation_readiness.py`, `scripts/run_v54_tiling_operation_readiness.sh`, and Windows `.cmd` wrapper.
- Added tests in `tests/test_v54_tiling_operation_readiness.py`.
- Boundary remains honest: production loop/index/slice/tailmask mutation is still disabled in Python and must be proven by MLIR/HivmOpsEditor backend.


## V5.3.1-backend-contract-ready-prelinux-lf-hygiene

- 新增 `docs/test_report/01_defect_hivm_cost_model_test_report_CN.md`，系统记录 14 个 defect HIVM 样例的缺陷定位、live optimizer 分批实跑命令、current IR legality、best strategy、predicted cycles 与优化方向判断。
- 对 14 个 defect 样例完成 live optimizer 分批回归：A-D、E-G、H-K、L/M/O 均通过。

- 新增 5 个扩展缺陷 HIVM/NPUIR 样例 J/K/L/M/O，并把 defect regression 从 9 个扩展到 14 个。
- 新增 `docs/core/06_extended_defect_cost_model_validation_CN.md`，记录新增样例的 cost model 识别方向与实跑结果。

- 按 Linux 交接前审核意见新增 `.gitattributes`，固定 `.py/.sh/.md/.json/.mlir` 为 LF，`.cmd/.bat` 为 CRLF。
- 将 `strategy_search/hivm_ops_editor.py`、`strategy_search/hivm_parser.py`、`strategy_search/hivm_backend.py` 从 CRLF 转为 LF。
- 同步将发布包内源代码、脚本、文档和 MLIR 样例统一为 LF，避免 Windows clone/zip 后在 Linux 上产生 shebang、diff 或 lint 问题。
- 修正 `scripts/run_v531_fast_ci.sh` 注释，使其与实际测试列表一致；MultiBuffer、Phase-3A 和 backend-contract acceptance 由 backend fake / phase6 positive CI 覆盖。
- 新增 `scripts/run_phase5b_roundtrip_ci.sh`，将 Phase-5B roundtrip/verifier gate 从 backend fake batch 中拆出，降低 Windows/WSL/Python 连续 pytest 清理挂住风险。
- 再次确认发布包无 `__pycache__`、`*.pyc`、`.pytest_cache` 和根目录临时调试脚本。

## V5.3.1-backend-contract-ready-prelinux

- Rewrote README and core docs to reflect the latest state: four-plan strategy search, portable/restricted rewrite, backend contract, fake backend CI, and Linux real-backend handoff.
- Added `scripts/run_backend_fake_ci.sh` for contract/fake-backend validation.
- Added `scripts/run_pre_linux_ci.sh` as the complete local gate before real Linux/vTriton/BiShengIR validation.
- Added `scripts/clean_release_package.sh` to remove Python caches and root-level temporary debug scripts before packaging.
- Added `docs/core/38_pre_linux_completion_and_handoff_CN.md` as the handoff checklist for Linux/vTriton/BiShengIR/CANN environments.
- Clarified that fake backend acceptance is not production rewrite proof.
- Clarified that production rewrite still requires real parser, verifier, HivmOpsEditor roundtrip, DES/trace, CANN compile/runtime, and msprof profile.


## V5.3.1-honest-e2e-docs

- 更新 README，明确当前项目定位为 four-plan strategy search + portable/restricted rewrite prototype，而非 production compiler rewrite pass。
- 更新 docs/00、docs/33、docs/34，统一 honest e2e 语义：`selected_plan_bound_to_same_input=true` 只代表 plan 绑定正确，不代表完整 e2e 通过。
- 新增 docs/calibration/35_v531_honest_e2e_and_docs_update_CN.md，说明本轮 wrapper 退出码、summary 字段、coverage 等级和官方 HIVM 同步语法口径。
- 将最新文档中的 `SEMANTIC_REWRITE / METADATA_REWRITE` 表述统一降级为 `RESTRICTED_STRUCTURAL_REWRITE / TRACE_METADATA_REWRITE`。
- 明确 `PRODUCTION_OPERATION_REWRITE` 只有在真实 parser/verifier/HivmOpsEditor/DES/compile/msprof 链路通过后才能 claim。

## V5.3.1-patch-official-syntax-and-bound-e2e

- 修复 `tests/test_des_profile_calibration.py` 中 optional profile 路径错误，改为读取 `artifacts/optional_profiles/prefill_des.json`。
- 新增 `pytest.ini`，注册 `unit/smoke/regression/slow` marker。
- 参考 AscendNPU-IR/HIVM 官方文档中的 bracket-style sync op 写法，将 portable rewrite 生成的事件标识从未定义 SSA 风格 `%hivm_*` 调整为 `EVENT_ID...` 风格属性：
  - SyncPlan: `EVENT_ID_AUTON`
  - CVPipelinePlan: `EVENT_ID_CVP_L2C_N` / `EVENT_ID_CVP_C2S_N`
- 修复 CVPipelinePlan portable rewrite 中 compute 前 wait edge 被重复插入的问题。
- 将参数覆盖等级从 `SEMANTIC_REWRITE / METADATA_REWRITE` 降级为更准确的 `RESTRICTED_STRUCTURAL_REWRITE / TRACE_METADATA_REWRITE`，保留 `PRODUCTION_OPERATION_REWRITE` 作为未来真实 HivmOpsEditor/MLIR verifier 通过后的等级。
- 新增强绑定端到端入口：
  - `tools/run_search_and_four_plan_rewrite.py`
  - `scripts/run_v531_bound_search_rewrite.sh`
  该入口先对当前输入 IR 运行寻优，再使用同一轮输出的 `selected_plan.json` 执行四 Plan rewrite，避免误用历史 selected_plan。
- 新增回归测试：`tests/test_v531_bound_search_rewrite.py`。

## V5.3.1-technical-reports-docs

- 新增两份总技术报告：
  - `docs/core/33_technical_report_optimization_CN.md`：寻优系统设计报告。
  - `docs/core/34_technical_report_rewrite_CN.md`：Rewrite 系统设计报告。
- 新增文档索引：
  - `docs/00_DOCUMENTATION_INDEX_CN.md`。
- 重写 `README.md`，将当前项目状态、运行命令、关键输出和真实验证边界整理为正式交付口径。
- 明确当前 V5.3.1 状态：四个参数 Plan 均已生成 portable/restricted rewritten HIVM artifact，进入真实 BiShengIR/vTriton/HivmOpsEditor 编译验证前置阶段，但不能 claim production rewrite。
- 本版本只整理文档和技术报告，不改变核心 rewrite 代码逻辑。

## V5.3-four-plan-true-rewrite-with-parameter-coverage

- 新增 `strategy_search/parameter_rewrite_coverage.py`：检查每个 controllable knob 是否有 rewrite consumer。
- 新增 `tools/run_four_plan_true_rewrite.py`：串联 Tiling -> MultiBuffer -> CVPipeline -> Sync -> Parameter metadata coverage。
- 新增最终输出 `optimized.four_plan_true_rewritten.hivm.mlir`。
- 新增 Windows / Linux 脚本 `run_v53_four_plan_true_rewrite`。
- 明确边界：所有 controllable knobs 可回写到 IR，但不是所有 knobs 都已完成 production operation-level semantic lowering。

## V5.2-tiling-restricted-metadata-true-rewrite

- 新增 TilingPlan restricted metadata true rewrite。
- 新增 `strategy_search/tiling_true_rewrite.py`。
- 新增 `tools/run_tiling_true_rewrite.py`。
- 新增 Windows/Linux 运行脚本。
- 新增 TilingPlan rewrite validation 与 diff 输出。
- 明确边界：仅 metadata-level true rewrite，不做 loop/index/memref-shape/tail-mask lowering。

## V5.1-cvpipeline-restricted-true-rewrite

- 新增 CVPipelinePlan restricted true rewrite：从 staged planner 推进到真实改写 IR。
- 新增 `strategy_search/cvpipeline_true_rewrite.py` 与 `tools/run_cvpipeline_true_rewrite.py`。
- 新增 `scripts/run_v51_cvpipeline_true_rewrite.cmd/.sh`，默认先跑 V5.0 MultiBuffer true rewrite，再跑 V5.1 CVPipeline true rewrite。
- 输出 `optimized.cvpipeline_rewritten.hivm.mlir`、`cvpipeline_true_rewrite_report.json`、`cvpipeline_true_rewrite_validation.json`、`cvpipeline_true_rewrite_diff.json`。
- 当前 rewrite 会真实插入 load->compute 与 compute->store 的 set_flag/wait_flag，同步边可见；仍不做 operation movement / loop skew / prologue-steady-epilogue 生成。
- production-level 正确性仍需真实 HivmOpsEditor/MLIR verifier/DES/msprof 验证。

## V5.0-multibuffer-restricted-true-rewrite

- Added `strategy_search/multibuffer_true_rewrite.py` for restricted additive MultiBufferPlan true rewrite.
- Added `tools/run_multibuffer_true_rewrite.py` and Windows/Linux scripts.
- MultiBufferPlan now emits `optimized.multibuffer_rewritten.hivm.mlir` with ping/pong slot definitions and producer/consumer use replacement.
- Added portable validation for slot definitions, replacement map, fallback preservation, and rewrite markers.
- Added unified diff report `multibuffer_true_rewrite_diff.json`.
- Added tests and documentation for V5.0.

## V5.3.1-honest-e2e-docs

- 更新 README，明确当前项目定位为 four-plan strategy search + portable/restricted rewrite prototype，而非 production compiler rewrite pass。
- 更新 docs/00、docs/33、docs/34，统一 honest e2e 语义：`selected_plan_bound_to_same_input=true` 只代表 plan 绑定正确，不代表完整 e2e 通过。
- 新增 docs/calibration/35_v531_honest_e2e_and_docs_update_CN.md，说明本轮 wrapper 退出码、summary 字段、coverage 等级和官方 HIVM 同步语法口径。
- 将最新文档中的 `SEMANTIC_REWRITE / METADATA_REWRITE` 表述统一降级为 `RESTRICTED_STRUCTURAL_REWRITE / TRACE_METADATA_REWRITE`。
- 明确 `PRODUCTION_OPERATION_REWRITE` 只有在真实 parser/verifier/HivmOpsEditor/DES/compile/msprof 链路通过后才能 claim。
## V5.5 - Four-Plan Production Candidate Rewrite

- 新增 `tools/run_four_plan_production_candidate_rewrite.py`，将 TilingPlan、MultiBufferPlan、CVPipelinePlan、SyncPlan 串联成一个统一 production-candidate rewrite pipeline。
- 新增 `strategy_search/tiling_operation_true_rewrite_v55.py`，TilingPlan 不再只写 metadata，而是对 local memref shape / operation type signature 做可见 mutation candidate。
- 新增 `strategy_search/sync_event_true_rewrite_v55.py`，当 barrier rewrite candidate 不存在时，对已有 `set_flag/wait_flag` 做 visible operation normalization，保证 SyncPlan 在四 Plan pipeline 中产生 mutation。
- 新增 `scripts/run_v55_four_plan_production_candidate_rewrite.sh/.cmd` 和文档 `docs/backend/12_four_plan_production_candidate_rewrite_CN.md`。
- 样例输出显示四个 Plan 均执行了 mutation，生成 `optimized.four_plan_production_candidate.hivm.mlir`；但仍明确标记 Linux backend parse/verify/compile/msprof 未执行，不能直接声称生产级性能提升。

## V5.6 - four-plan operation-level rewrite MVP

- 新增 `strategy_search/operation_rewrite/four_plan_operation_rewriter.py`，将四个参数 Plan 统一推进到 operation-level MVP rewrite。
- 新增 `tools/run_four_plan_operation_rewrite.py`、`scripts/run_v56_four_plan_operation_rewrite.sh/.cmd`。
- TilingPlan 不再只做 metadata/type-shape candidate：新增 M/N/K outer tile loop scaffold、`loop_order` materialization、tail/reduction/layout guard request，并继续执行 local memref operation/type shape rewrite。
- MultiBufferPlan 继续执行 ping/pong alloc clone 与 producer/consumer use-def 替换。
- CVPipelinePlan 继续执行 pipeline group、load→compute、compute→store sync edge 插入与 slot binding。
- SyncPlan 继续执行 set_flag/wait_flag event operation normalization。
- 新增 `operation_parameter_coverage.json`，记录每个寻优参数对应的 operation action。
- 新增 `docs/backend/13_four_plan_operation_level_rewrite_MVP_CN.md` 与测试 `tests/test_v56_four_plan_operation_rewrite.py`。
- 明确边界：V5.6 生成 operation-level optimized HIVM candidate，但仍需要 Linux MLIR/HIVM parse、verifier、backend compile、correctness 与 msprof 后才能声称真实性能提升。

## V5.7 - four-plan operation rewrite precompile hardening

- 新增 `strategy_search/operation_rewrite/linux_precompile_audit.py`，在四 Plan operation rewrite 后执行本地 Linux precompile blocker 检查。
- 新增 `optimized.four_plan_operation_rewrite.precompile_hardened.hivm.mlir`，对 `%cM/%cN/%cK/%c32` 等 tile/index 常量做保守物化，便于 Linux backend 前置验证。
- 新增 `v57_linux_precompile_audit.json`，检查 duplicate SSA、undefined symbol、memref type mismatch、operand type harmonization、brace balance、四 Plan rewrite marker 是否齐全。
- `four_plan_operation_rewrite_summary.json` 新增 `linux_precompile_audit_passed`、`linux_precompile_blocker_count`、`precompile_hardened_ir` 等字段。
- 新增 `scripts/run_v57_four_plan_operation_rewrite_precompile_audit.sh/.cmd`、`docs/backend/14_v57_four_plan_operation_rewrite_precompile_audit_CN.md` 和 `tests/test_v57_linux_precompile_audit.py`。
- 明确边界：V5.7 仍不声称 Linux 可编译；它把四 Plan operation rewrite 从“有 action”推进到“有本地 precompile blocker gate”。


## V5.8 - Tiling/CVPipeline semantic rewrite hardening

- Added `tiling_semantic_full_rewrite_v58.py` for M/N/K axis binding, per-operation tile-slice binding, tail strategy semantic binding, and reduction accumulator semantic binding.
- Added `cvpipeline_semantic_schedule_v58.py` for stage graph analysis and prologue/steady/epilogue schedule binding.
- Integrated V5.8 reports into `run_four_plan_operation_rewrite.py`.
- Added `scripts/run_v58_tiling_cvpipeline_semantic_rewrite.sh/.cmd`.
- Added V5.8 tests covering tiling axis/slice binding and CVPipeline stage schedule binding.
- Scope boundary remains explicit: Linux backend compile/correctness/msprof validation is required before performance claims.

## V6.2 - four-plan official-backend lowering hardening

- Added `strategy_search/operation_rewrite/official_backend_lowering_v62.py`.
- Lowers `annotation.mark` operations into nearby `memref.alloc` attributes when possible and strips loop/constant marker annotations for official backend handoff.
- Normalizes Python-list-like generated attributes such as `hivm.tile_offsets="['%m_outer', ...]"` into compact backend-oriented strings such as `hivm.tile_offsets="m_outer,k_outer"`.
- Materializes `D_tile` and `propagate_from_input` placeholders in generated HIVM candidates.
- Adds strict MultiBuffer residual-use rewrite for HIVM operation lines after ping/pong buffers exist.
- Adds `v62_official_backend_handoff_audit.json` with hard blockers and warnings, and updates Linux handoff to use `optimized.four_plan_official_backend_lowered.hivm.mlir` as the recommended optimized input.
- Adds `tests/test_v62_official_backend_lowering.py`.

## V6.3-four-plan-official-backend-subview-lowering
- Adds official-style memref.subview lowering for mismatched hivm.hir.load/store operands.
- Strips generated private v5/v6/tile/pipeline debug attrs from Linux handoff IR.
- Adds v63 official-compare audit and backend contract.
