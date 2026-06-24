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
