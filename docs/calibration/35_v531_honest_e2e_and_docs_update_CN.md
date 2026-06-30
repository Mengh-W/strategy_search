# V5.3.1：Honest E2E 与文档口径更新说明

版本：`V5.3.1-honest-e2e-docs`

本文件说明 V5.3.1 patch 后的关键工程修复和文档口径调整。重点是：项目可以生成四 Plan portable/restricted rewrite artifact，但不能把 search 成功、plan 绑定成功或 portable validation 当成 production rewrite 成功。

---

## 1. 为什么需要 honest e2e

早期 wrapper 存在一个风险：

```text
search 成功 + selected_plan 存在 + rewrite summary 能加载
```

就可能被记录为绑定成功，从而让读者误以为完整 e2e 通过。实际上，rewrite 子进程可能已经返回非 0，例如 SyncPlan audit 发现 blocked action，导致四 Plan rewrite 没有完整闭包。

因此 V5.3.1 将 summary 拆成多个明确字段：

| 字段 | 含义 |
|---|---|
| `search_returncode` | 寻优子进程返回码 |
| `rewrite_returncode` | 四 Plan rewrite 子进程返回码 |
| `selected_plan_bound_to_same_input` | rewrite 是否使用了本轮 search 生成的 selected_plan |
| `rewrite_summary_loaded` | 是否成功加载 rewrite summary |
| `rewrite_process_succeeded` | rewrite 子进程是否成功返回 0 |
| `all_portable_validations_passed` | 项目内 portable validation 是否通过 |
| `end_to_end_passed` | search、rewrite、summary、validation 是否整体通过 |
| `failure_reason` | 若失败，记录主要失败原因 |

---

## 2. 严格通过条件

现在只有同时满足以下条件，才会认为完整 e2e 通过：

```text
search_returncode == 0
rewrite_returncode == 0
rewrite_summary_loaded == true
all_portable_validations_passed == true
```

对应 summary：

```json
{
  "end_to_end_passed": true,
  "rewrite_process_succeeded": true,
  "all_portable_validations_passed": true
}
```

如果 rewrite 子进程失败，即使 selected_plan 确实绑定了当前输入，也必须返回失败：

```json
{
  "selected_plan_bound_to_same_input": true,
  "rewrite_process_succeeded": false,
  "end_to_end_passed": false,
  "failure_reason": "rewrite_process_failed"
}
```

---

## 3. 与官方 HIVM 文档对齐的同步语法修正

官方 HIVM dialect 中，`set_flag` / `wait_flag` / `pipe_barrier` 属于 bracket-style sync op。项目中不再使用未定义的 SSA 风格 event 占位符，例如：

```mlir
%hivm_sync_auto0
```

而改成更接近官方 op attribute 语义的 event id：

```mlir
hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_V>, EVENT_ID_CVP_L2C_0]
hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_V>, EVENT_ID_CVP_L2C_0]
```

这并不等于已经通过官方 verifier，只是避免生成明显像“未定义 SSA value”的文本。

---

## 4. Coverage 等级口径调整

为了避免过度 claim，当前 coverage 不再使用容易误解的：

```text
SEMANTIC_REWRITE
METADATA_REWRITE
```

改为：

```text
RESTRICTED_STRUCTURAL_REWRITE
TRACE_METADATA_REWRITE
PRODUCTION_OPERATION_REWRITE
```

含义如下：

| 等级 | 含义 | 当前状态 |
|---|---|---|
| `TRACE_METADATA_REWRITE` | 参数写入 metadata/annotation，支持 provenance、trace 和后续 lowering | 已支持 |
| `RESTRICTED_STRUCTURAL_REWRITE` | 参数驱动了 portable/text-level IR 结构变化 | 已部分支持 |
| `PRODUCTION_OPERATION_REWRITE` | 真实 MLIR/HivmOpsEditor operation mutation，并通过真实后端验证 | 尚未完成 |

---

## 5. 当前推荐验收方式

### 快速 CI

```bash
bash scripts/run_v531_fast_ci.sh
```

该脚本用于验证本轮关键修改，不代表全量慢速集成测试全部覆盖。

### 端到端入口

```bash
python tools/run_search_and_four_plan_rewrite.py \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --cost-model-config configs/cost_model_conservative.json \
  --cost-risk-mode conservative \
  --candidate-space standard \
  --output-dir artifacts/v531_bound_search_rewrite
```

验收时不要只看是否生成了 IR 文件，而要看：

```text
bound_search_rewrite_summary.json
```

尤其是：

```text
end_to_end_passed
rewrite_process_succeeded
all_portable_validations_passed
failure_reason
```

---

## 6. 对外汇报建议

可以说：

```text
我们已经实现了寻优与 rewrite 的强绑定入口，能够保证当前 selected_plan 来自当前输入 IR，并且 wrapper 会诚实暴露 rewrite/validation 失败，不再把失败包装成成功。
```

不能说：

```text
当前四 Plan 已经完成 production operation rewrite。
当前 rewritten HIVM 已经通过真实 parser/verifier/DES/msprof。
```

更准确的阶段定义：

```text
portable/restricted four-plan rewrite artifact generation, with honest e2e reporting; awaiting real backend validation.
```

