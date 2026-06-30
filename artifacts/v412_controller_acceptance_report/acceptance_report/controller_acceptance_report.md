# HIVM Four-Plan Rewrite Acceptance Report

版本：`V4.12-controller-acceptance-report`

## 1. 总体结论

- Controller decision: `PORTABLE_SYNC_REWRITE_PLUS_MULTI_PLAN_SCAFFOLD_READY`
- Acceptance decision: `ACCEPTED_AS_PORTABLE_CONTROLLER_DEMO_NOT_PRODUCTION`
- Acceptance checks: `5/5`
- Production rewrite claim allowed: `False`

> 当前验收口径：可以验收为 portable/controller demo；不能宣称 production-level HivmOpsEditor rewrite 已完成。

## 2. Claim boundary

Only SyncPlan has audited portable/text-level semantic rewrite. MultiBuffer/CVPipeline/Tiling are scaffold/readiness/planner stages until real HivmOpsEditor verifier is available.

## 3. Stage summary

| Stage | Status | Semantic mutation | Production claim | Key counts |
|---|---:|---:|---:|---|
| SyncPlan | `PASSED` | ✅ | ❌ | rewritten_action_count=74 |
| MultiBufferPlan readiness | `UNKNOWN` | ❌ | ❌ | selected_candidate_count=80 |
| MultiBufferPlan stage-boundary | `UNKNOWN` | ❌ | ❌ | stage_mutation_plan_action_count=20 |
| CVPipelinePlan staged planner | `UNKNOWN` | ❌ | ❌ | pipeline_window_count=50, cvpipeline_rewrite_plan_action_count=50 |
| TilingPlan feasibility | `REVIEW_REQUIRED` | ❌ | ❌ | loop_anchor_count=10 |

## 4. Acceptance checks

| Check | Result | Evidence |
|---|---:|---|
| SyncPlan audited portable rewrite closure | ✅ | rewritten_action_count=74<br>audit_decision=PORTABLE_REWRITE_AUDITED_NOT_PRODUCTION<br>diff_lines=321 |
| MultiBufferPlan rewrite readiness scaffold | ✅ | ready_for_pingpong=20<br>stage_plan_actions=20 |
| CVPipelinePlan staged rewrite planner scaffold | ✅ | pipeline_windows=50<br>ready_windows=36 |
| TilingPlan feasibility scan | ✅ | readiness=READY_FOR_TILING_PLAN_SCAFFOLD<br>loop_anchors=10<br>compute_anchors=156 |
| Production rewrite claim remains blocked until real verifier | ✅ | Only SyncPlan has audited portable/text-level semantic rewrite. MultiBuffer/CVPipeline/Tiling are scaffold/readiness/planner stages until real HivmOpsEditor verifier is available. |

## 5. HivmOpsEditor migration queue

| Priority | Plan | Action count | Status | Required operation-level API |
|---:|---|---:|---|---|
| 1 | SyncPlan | 74 | `portable_rewrite_available_waiting_for_real_verifier` | addSetFlagWaitFlagBefore, deleteOp, exportToFile, verify |
| 2 | MultiBufferPlan | 20 | `planned_not_mutated_requires_dominance_alias_capacity_proof` | clone/create buffer slot, rewrite producer uses, rewrite consumer uses, insert/reuse sync edge, verify |
| 3 | CVPipelinePlan | 50 | `planner_available_no_semantic_op_motion_yet` | split stage, move/clone ops across prologue/steady/epilogue, compose multibuffer slots, insert sync edges, verify |
| 4 | TilingPlan | None | `feasibility_only_high_risk` | split/rewrite loops, rewrite indices, tail mask/pad, verify |

## 6. 推荐执行顺序

- 1. Apply/prove SyncPlan event rewrite first because it provides explicit synchronization edges.
- 2. Use MultiBufferPlan readiness and stage-boundary evidence to select ping-pong candidates.
- 3. Use CVPipelinePlan windows only after buffer slots and sync edges are known.
- 4. Treat TilingPlan as high-risk until operation-level loop/index rewrite is available.

## 7. 后续验收门槛

1. 编译真实 vTriton/BiShengIR 环境，确认 `hivm-crud` 或 `hivm-operation-backend` 可运行。
2. 用 HivmOpsEditor 执行 SyncPlan mutation，并通过 MLIR verifier。
3. 对 before/after HIVM 跑 DES/trace，对比同步结构和执行图。
4. 上真机用 msprof 对比性能和正确性。
5. MultiBuffer/CVPipeline/Tiling 只能在 operation-level verifier 可用后进入 semantic mutation。
