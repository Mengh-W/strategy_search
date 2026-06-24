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
