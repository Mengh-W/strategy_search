# 01 项目通俗版说明：这个代码仓现在到底在干什么

## 一句话
这个项目现在做的事情可以理解为：**给 HIVM/NPUIR kernel 找一组更可能跑得快的编译策略，然后把这组策略尽量写回到 HIVM IR 里；但真正复杂的 IR 改写还必须等 vTriton/HivmOpsEditor 后端编译验收通过。**

## 它不是在做什么
它不是一个已经生产可用的 HIVM compiler pass，也不是已经能保证真机提速的优化器。当前的 predicted cycles 还是模型估计，不等于 msprof 真机时间。

## 它已经能做什么
1. 读取 `.hivm.mlir` / `.npuir.mlir` 样例，抽取一些 shape、buffer、sync、op 结构信息。
2. 围绕四类 Plan 搜索候选策略：TilingPlan、MultiBufferPlan、CVPipelinePlan、SyncPlan。
3. 用硬件边界 gate 过滤明显不合法的方案，例如 UB/L1/L0 容量爆掉、tile 太碎、同步风险太高。
4. 用 cost model 对候选策略估计总 cycles，并排序输出最优候选。
5. 把策略写回 IR：
   - annotation rewrite：写 attribute，风险低；
   - safe structural hint rewrite：写 multi-buffer / CV pipeline hint，风险中低；
   - small structural rewrite：对 barrier/sync 类做小范围 op sequence 改写；
   - restricted positive rewrite：在受限正例上做 Q-load hoist 和 GM round-trip deletion。
6. 生成 vTriton/HivmOpsEditor 后端 skeleton 和本地编译/验收脚本。

## 最容易误解的点
当前项目里很多文件叫 optimized，但这不代表已经真机验证提速。更准确地说，它们是“按照当前模型和安全规则生成的候选优化 IR”。其中 annotation/hint 改写可信度较高，复杂结构改写仍然要靠真实 backend、verifier、DES/trace 和 msprof 闭环确认。

## 当前最关键的下一步
不要再继续堆 phase 报告了。下一步应该在真实 vTriton 环境中编译 `hivm-operation-backend`，然后依次跑：

```bash
hivm-operation-backend --print-capabilities
hivm-operation-backend --inventory
hivm-operation-backend --roundtrip
hivm-operation-backend --verify-only
hivm-operation-backend --dry-run
hivm-operation-backend --mutate --mutation-kind gm_roundtrip_deletion
```

只有这些通过，后面谈真实复杂 kernel 的 GM 删除、Q-load hoist、double-buffer、CV overlap、tiling lowering 才比较稳。
