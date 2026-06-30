# V5.9 四 Plan 语义 rewrite 的 syntax / schedule hardening

## 1. 本版本目标

V5.8 已经把 TilingPlan 和 CVPipelinePlan 从 scaffold / marker 推进到语义绑定层：

- TilingPlan：M/N/K axis binding、tile-slice binding、reduction binding；
- CVPipelinePlan：stage graph、prologue / steady / epilogue schedule binding。

V5.9 不再继续堆新的 marker，而是修正进入 Linux backend 前最容易阻断 parser / verifier 的文本级问题：

```text
四 Plan semantic operation rewrite
→ precompile hardening
→ V5.9 syntax hardening
→ 输出推荐 Linux 验证 IR
```

## 2. 新增能力

### 2.1 FA-like M/N/K 常量推断修正

V5.9 将 FA 样例里的轴语义统一为：

```text
Q_gm: M x D_head
K_gm: N_seq x D_head
V_gm: N_seq x D_head
O_gm: M x D_out
```

因此：

```text
%cM = M = Q_gm dim0
%cN = N_seq = K_gm dim0
%cK = D_head = K_gm dim1 / Q_gm dim1
%cB = tile_n
%cE = N_seq
```

在默认 `fa_best.hivm.mlir` 上，V5.9 会物化：

```text
%cM = 64
%cN = 1024
%cK = 128
%cB = 64
%cE = 1024
```

### 2.2 nested memref closure repair

前序 MVP textual rewrite 中，部分 `memref<..., #hivm.address_space<...>>` 在多 operand 类型列表中可能被正则处理成少一个 `>` 的形式。

V5.9 新增：

```text
strategy_search/operation_rewrite/syntax_hardening_v59.py
```

用于修复：

```text
#hivm.address_space<ub>
→ #hivm.address_space<ub>>
```

只修复明显的外层 `memref` 闭合问题，不修改 operation 语义。

### 2.3 event operation normalization

V5.5/V5.8 中为了表达 producer-consumer pipe，曾生成 bracket-style event op，例如：

```text
hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_V>, EVENT_ID_CVP_L2C_0]
```

V5.9 将其恢复为更接近原始 HIVM 样例的 attr-style operation：

```text
hivm.hir.wait_flag {pipe="V", event="EVENT_ID_CVP_L2C_0", producer_pipe="MTE2", consumer_pipe="V", hivm.v59_event_normalized=true}
```

这样做的目的不是声明官方语法已经确定，而是减少 Linux parser 入口前的明显文本风险。

### 2.4 V5.9 textual legality audit

新增输出：

```text
v59_textual_legality_audit.json
```

检查：

```text
malformed nested memref address_space
bracket-style event op
unlowered code placeholder
```

默认样例结果应为：

```json
{
  "passed_v59_textual_legality_audit": true,
  "malformed_memref_line_count": 0,
  "bracket_event_line_count": 0,
  "unlowered_code_placeholder_line_count": 0
}
```

## 3. 推荐 Linux 验证文件

V5.9 后，优先交给 Linux backend 的文件是：

```text
artifacts/v59_four_plan_semantic_rewrite_hardening/
  optimized.four_plan_operation_rewrite.v59_syntax_hardened.hivm.mlir
```

而不是 V5.7 的 `precompile_hardened` 文件。

## 4. 运行命令

```bash
bash scripts/run_v59_four_plan_semantic_rewrite_hardening.sh \
  sample_input/fa_best.hivm.mlir \
  artifacts/latest_smoke_run/selected_plan.json \
  artifacts/v59_four_plan_semantic_rewrite_hardening
```

## 5. 边界

V5.9 仍然不能 claim：

```text
Linux 已编译通过
真机已运行通过
msprof 已证明 speedup
```

V5.9 能 claim 的是：

```text
四 Plan semantic operation rewrite 已生成；
TilingPlan / CVPipelinePlan 的语义绑定继续保留；
进入 Linux backend 前的若干明显文本级 blocker 已被清除；
推荐验证文件已更新为 v59_syntax_hardened 版本。
```
