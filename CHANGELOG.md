
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
