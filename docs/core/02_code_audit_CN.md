# 02 代码仓审核报告

## 结论
代码功能已经从早期策略搜索 demo 推进到“策略搜索 + IR 写回 + 受限真改写 + vTriton 后端接入骨架”的阶段。工程方向是对的，但原始交付包最大的问题是：**根目录过度膨胀，文档阶段化堆叠，build/output/cache/历史报告混在一起，导致读者很难判断当前版本到底以哪个文件为准。**

## 本次实际检查结果
- 原始仓库大小约 306MB。
- 根目录 Markdown 文件 79 个。
- build/output 类目录约 33 个，其中 build_phase* 11 个、output* 22 个。
- 存在 `.pytest_cache`、`__pycache__`、`.pyc` 等不应进入正式交付包的缓存文件。
- `VERSION` 显示为 `V4.0-four-plan-backend-contract-execution`，但 README 开头仍在强调 Phase-5D / V3.3.1，存在明显版本叙述不一致。
- `python -m compileall -q strategy_search tools tests` 通过，说明 Python 源码层面没有基础语法错误。
- 选取 Phase6F / Phase6E / Phase6C / smoke / cost model 单测子集运行时，测试进度达到 `[100%]`；但在当前容器中 pytest 命令没有及时返回最终 summary，建议在本地环境进一步确认是否存在 pytest 插件/进程退出问题。
- 使用 `sample_input/fa_bad_inefficient.hivm.mlir` 做了一次 CLI smoke run，能够生成完整策略搜索与 rewrite 输出。最佳候选为 `candidate_01681`，`predicted_cycles=492.90`，模型估计相对 current IR speedup 为 `1.359x`。注意：这是模型估计，不是真机 msprof 结果。

## 代码结构优点
1. `strategy_search/` 已经按 parser、plans、cost_model、search、rewrite、phase analysis 分层，主干逻辑比早期单文件 demo 更可维护。
2. CLI 参数覆盖了 kernel、硬件配置、搜索空间、cost risk mode、artifact profile、rewrite、vTriton backend 等关键路径。
3. 测试覆盖了 cost model、DES/profile、defect injection、rewrite、phase3-6 gate、vTriton adapter skeleton 等多个层面。
4. 对危险 rewrite 采用 safety gate / dry-run / backend contract，而不是直接文本乱改真实 IR，这个方向正确。

## 主要问题
1. README 不是当前版本的单一事实来源。它混合了 Phase-5D、V3.3.1、V4.0/Phase-5B 等不同阶段叙述，容易误导读者。
2. 输出文件爆炸。一次 smoke run 会生成大量 phase2-phase6 JSON，适合调试，不适合正式交付；应该分为 `latest_smoke_run`、`debug_full_outputs`、`archive` 三类。
3. build 产物不应该进入源码包。`build_phase*` 目录、二进制、缓存都应该由本地构建生成，而不是随仓库提交。
4. 历史报告太多。阶段报告应该合并为一个 progress summary 和一个 archive combined 文档，而不是 70+ md 放根目录。
5. “optimized” 命名容易过度承诺。建议在文档里明确：optimized 是 model-selected / candidate optimized，不等于 verified-fast。
6. 当前仍缺真实 vTriton 编译验收日志、HivmOpsEditor API 对齐结果、DES/trace 对比和 msprof 闭环，因此不能宣称 production rewrite 完成。

## 本次清理原则
清理版保留源码、配置、测试、样例、后端 skeleton 和少量精选输出；删除/不纳入 build、cache、pyc、几十个历史 output 目录；将历史 md 合并进 `docs/archive/OLD_ROOT_REPORTS_COMBINED.md`。
