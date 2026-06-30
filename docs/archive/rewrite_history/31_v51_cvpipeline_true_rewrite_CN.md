# V5.1：CVPipelinePlan portable/restricted rewrite

## 目标

V4.10 的 CVPipelinePlan 只生成 staged rewrite plan，不改变 IR。V5.1 开始执行受限但真实的 CVPipelinePlan rewrite：

- 识别 `load/view -> compute -> store` pipeline window；
- 插入显式 `set_flag / wait_flag` 同步边；
- 在 IR 中写入 pipeline group begin/end；
- 如果输入已经经过 V5.0 MultiBufferPlan rewrite，则可绑定已有 ping/pong slot；
- 输出 `optimized.cvpipeline_rewritten.hivm.mlir`、rewrite report、validation 和 diff。

## 当前 rewrite 范围

V5.1 是保守的 additive rewrite，不移动原始 operation，不做 loop skew，不生成完整 prologue/steady/epilogue。它真正改变 IR 的部分是：

```mlir
// HIVM V5.1 CVPipelinePlan sync edge: load_to_compute
hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_V>, EVENT_ID_CVP_L2C_0]
// HIVM V5.1 CVPipelinePlan wait edge: load_to_compute
hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_V>, EVENT_ID_CVP_L2C_0]

// HIVM V5.1 CVPipelinePlan sync edge: compute_to_store
hivm.hir.set_flag[<PIPE_V>, <PIPE_MTE3>, EVENT_ID_CVP_C2S_0]
// HIVM V5.1 CVPipelinePlan wait edge: compute_to_store
hivm.hir.wait_flag[<PIPE_V>, <PIPE_MTE3>, EVENT_ID_CVP_C2S_0]
```

因此它不是单纯 annotation，而是会真实插入 HIVM sync op。

## 为什么不直接移动 operation？

CVPipeline 的完整 production rewrite 需要：

1. dominance / def-use / alias analysis；
2. loop prologue、steady-state、epilogue 改写；
3. MultiBuffer slot parity 绑定；
4. SyncPlan edge 证明；
5. MLIR verifier / DES / msprof 验证。

当前没有真实 BiShengIR/vTriton/HivmOpsEditor 环境，因此 V5.1 只执行 portable portable/restricted rewrite。

## 运行方式

Linux/WSL：

```bash
bash scripts/run_v51_cvpipeline_true_rewrite.sh
```

Windows CMD：

```cmd
scripts\run_v51_cvpipeline_true_rewrite.cmd
```

脚本会先运行 V5.0 MultiBufferPlan portable/restricted rewrite，再以其输出作为 CVPipelinePlan 输入。

## 输出文件

默认输出目录：

```text
artifacts/v51_cvpipeline_true_rewrite/
  01_multibuffer_true_rewrite/
  02_cvpipeline_true_rewrite/
  v51_cvpipeline_true_rewrite_closure_summary.json
```

核心文件：

```text
02_cvpipeline_true_rewrite/optimized.cvpipeline_rewritten.hivm.mlir
02_cvpipeline_true_rewrite/cvpipeline_true_rewrite_report.json
02_cvpipeline_true_rewrite/cvpipeline_true_rewrite_validation.json
02_cvpipeline_true_rewrite/cvpipeline_true_rewrite_diff.json
```

## 验收口径

可以说：

> CVPipelinePlan 已经进入 portable/restricted rewrite：系统会基于 pipeline window 真实插入 pipeline sync event，并输出改写后的 optimized HIVM MLIR。

不能说：

> CVPipelinePlan production rewrite 已经完成。

因为当前仍未完成 operation movement、loop skew、prologue/steady/epilogue materialization，以及真实 verifier/DES/msprof 验证。
