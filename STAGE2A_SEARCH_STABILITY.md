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
