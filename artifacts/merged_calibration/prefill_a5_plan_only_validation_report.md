# Prefill-A5 Plan-only Cost Model Validation Report

## 1. 验证边界

本报告只验证当前 cost model 承诺建模的四个 plan：TilingPlan、MultiBufferPlan、CVPipelinePlan、SyncPlan。S6->S7 的 shared SSA、S7->S8 的 hoist、S8->S9 的 compiler code motion，以及 S3->S4 的 dtype/workspace policy 不计入当前 cost model 的性能验证。

## 2. 核心结果

- Supported plan transitions: `4`
- Direction hits: `4/4`
- Direction hit rate: `100.00%`
- Mean absolute gain error: `0.0126`
- Verdict: **good: current four-plan cost model captures most plan-level directions on this benchmark**

## 3. Plan-only transition validation

| Transition | Event | Plans | Real gain | Model predicted gain | Direction hit | Interpretation |
|---|---|---|---:|---:|---|---|
| S1->S2 | BLOCK_SBS=256 + multibuffer=False | TilingPlan, MultiBufferPlan | 1.2378 | 1.2842 | True | Direction and rough gain magnitude are acceptable for this weak benchmark. |
| S2->S3 | enable_mixed_cv=False | CVPipelinePlan | 1.0044 | 1.0039 | True | Direction and rough gain magnitude are acceptable for this weak benchmark. |
| S4->S5 | enable_hivm_auto_cv_balance=True | CVPipelinePlan | 1.0139 | 1.0151 | True | Direction and rough gain magnitude are acceptable for this weak benchmark. |
| S5->S6 | tile_mix_cube_loop=4, tile_mix_vector_loop=1 | CVPipelinePlan | 1.0393 | 1.0415 | True | Direction and rough gain magnitude are acceptable for this weak benchmark. |

## 4. 不计入当前 cost model 验证的变化

| Transition | Event | Classification |
|---|---|---|
| S0->S1 | BLOCK_V=512 | conceptually TilingPlan, but not represented in current StrategyConfig |
| S3->S4 | workspace_sv bf16 | dtype / workspace policy, not one of the current four plan knobs |
| S6->S7 | shared kv_nope SSA | IR rewrite / SSA reuse, not in current four-plan cost model |
| S7->S8 | hoist Q loads | IR rewrite / code motion, not in current four-plan cost model |
| S8->S9 | enable_code_motion=True | compiler pass / code motion, not in current four-plan cost model |

## 5. 校准建议

| Transition | Event | Current predicted gain | Real gain | Suggested multiplier | Note |
|---|---|---:|---:|---:|---|
| S1->S2 | BLOCK_SBS=256 + multibuffer=False | 1.2842 | 1.2378 | 0.9639 | no urgent calibration needed |
| S2->S3 | enable_mixed_cv=False | 1.0039 | 1.0044 | 1.0005 | no urgent calibration needed |
| S4->S5 | enable_hivm_auto_cv_balance=True | 1.0151 | 1.0139 | 0.9988 | no urgent calibration needed |
| S5->S6 | tile_mix_cube_loop=4, tile_mix_vector_loop=1 | 1.0415 | 1.0393 | 0.9978 | no urgent calibration needed |

## 6. 结论

这次验证说明：当前四 plan cost model 已经能对部分 plan 参数变化产生有效响应，尤其是 BLOCK_SBS/multibuffer 组合；但它还不能稳定预测所有 plan-level 增量，特别是 mixed_cv=False 和 tile_mix=4:1 两个 CVPipelinePlan 相关转移方向判断错误。因此，prefill_a5 可以证明当前 cost model 有可校准的策略敏感度，但还不能证明它已经具备可靠的 plan-level ranking 能力。下一步应该把 mixed_cv 与 tile_mix 的经验项改成 workload/profile dependent，而不是固定奖励或固定惩罚。
