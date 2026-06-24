# V3.3.1 Cost Model 超参数与离线训练数据说明

本文档对应 **V3.3.1 Structure-aware Cycle Correction Cost Model**。

V3.3.1 的在线模型只读取：

```text
MLIR / NPUIR 文件
MLIR-derived artifact files: prefill_des.json, prefill_trace.json
hardware config
cost model config
```

它不在线读取实机 profiling，不使用 DES makespan/global scale 作为默认校准。实机数据的用途是未来**离线训练/校准参数**，训练后的参数固化到配置文件中。

---

## 1. V3.3.1 超参数分层

### 1.1 基础 analytical 参数

| 类别 | 例子 | 作用 | 未来训练需求 |
|---|---|---|---|
| 硬件吞吐 | MTE 带宽、Cube FLOPs、Vector 吞吐 | 计算 load/store/cube/vector 基础时间 | 需要用实机数据校准 |
| 启动开销 | DMA/Cube/Vector startup cycles | 小 tile / 短 op 的固定启动成本 | 需要校准 |
| overlap 参数 | load/store overlap、CV overlap | 估计 double buffer / pipeline 能隐藏多少时间 | 强烈需要校准 |
| 同步参数 | event cost、barrier cost、stall factor | 估计 set/wait/barrier/sync block 开销 | 强烈需要校准 |
| memory pressure | pressure threshold、alpha、cap | 防止候选贴近 UB/L1/L0 容量边界 | 可训练 |
| shape penalty | tail、mask、alignment、irregular shape | 惩罚不规整 tile | 可训练 |
| risk penalty | graph sync unknown、event reuse、CV estimated | 未验证收益的保守惩罚 | 可训练/策略化 |

### 1.2 V3.3.1 KernelCostProfile 参数

V3.3.1 的参数控制 MLIR/artifact 结构如何转成分项 cycle correction factors。

| 类别 | 参数例子 | 作用 |
|---|---|---|
| 结构分数权重 | compute_score_weight、memory_score_weight、scalar_score_weight、sync_score_weight | 把 MLIR/artifact 特征映射为 compute/memory/vector/scalar/sync ratios |
| loop-weighted 权重 | loop_weighted_scalar_multiplier、loop_weighted_sync_multiplier | 内层 loop op 的额外权重 |
| memory path 权重 | GM->UB、UB->GM、GM->L1、L1->L0、L0C->GM | 不同 memory path 的相对代价 |
| scalar/control 权重 | arith、index_cast、pointer_cast、apply、loop_control | scalar/control/address 开销 |
| sync criticality 权重 | inner_loop_sync、cross_pipe_event、barrier、unmatched_event | 同步关键性代理 |
| buffer pressure 权重 | live span、byte-span、multi-buffer slot、reuse distance proxy | buffer lifetime 与 per-buffer double buffer 风险 |
| artifact confidence | mlir_only_confidence、mlir_plus_artifact_confidence | 没有 artifact 时 correction factor 向 1.0 收缩 |
| cycle correction | memory_cycle_correction、compute_cycle_correction、vector_cycle_correction、scalar_cycle_correction、sync_cycle_correction | 修正对应分项 cycles 的基础估计误差 |
| overlap confidence | overlap_confidence、cv_overlap_confidence | 仅在窄范围内修正 overlap 可信度，避免重复惩罚 |

---

## 2. 在线输入与离线训练数据的区别

### 2.1 在线输入

在线寻优阶段：

```text
kernel.npuir.mlir
prefill_des.json / prefill_trace.json  # 可选 MLIR-derived artifact
configs/*.json
```

这些输入用于抽取结构特征，不包含实机 latency target。

### 2.2 离线训练数据

未来训练需要的数据格式应是：

```text
MLIR + artifacts + strategy metadata + real measured target
```

例如每条样本包含：

| 字段 | 含义 |
|---|---|
| `sample_id` | kernel/strategy 样本 ID |
| `mlir_file` | 输入 MLIR |
| `artifact_des_graph` | MLIR-derived DES graph artifact |
| `artifact_trace` | MLIR-derived trace artifact |
| `strategy` | tiling / multibuffer / cvpipeline / sync 参数 |
| `kernel_cost_profile` | 在线抽取的结构 profile |
| `cost_breakdown` | compute/memory/vector/scalar/sync/overlap/risk 分项 |
| `measured_latency` | 实机 msprof 或稳定 benchmark target |
| `device_info` | 硬件型号、频率、软件栈版本 |

训练目标不是让线上模型读取 measured latency，而是用 measured latency 学习参数。

---

## 3. 推荐训练目标

对寻优项目而言，最重要的不是绝对 cycles，而是候选排序。因此推荐同时看：

| 指标 | 作用 |
|---|---|
| MAPE / MAE | 绝对预测误差 |
| Spearman rank correlation | 候选排序是否更接近实机 |
| Top-k recall | 实机 best 是否落在模型 top-k |
| Best regret | 模型选中策略相对实机最优损失多少 |
| Kernel-family split | 泛化到不同 kernel 类型的能力 |

---

## 4. 防止过拟合的建议

V3.3.1 的结构增强会提高表达能力，也会带来规则型过拟合风险。推荐：

1. 所有 correction factor 设置上下限；
2. 使用连续平滑函数，不用硬阈值跳变；
3. MLIR-only 模式下降低 confidence，让 correction factor 向 1.0 收缩；
4. artifact evidence 只作为结构证据，不使用 makespan/global scale；
5. 离线训练时按 kernel 或 kernel family 切分 train/valid/test；
6. 做 feature ablation，确认 loop-weighted、memory path、sync criticality、buffer pressure 等特征各自有贡献。

---

## 5. 推荐配置输出

训练后的参数建议固化为：

```text
configs/cost_model_conservative.json
configs/cost_model_balanced.json
configs/cost_model_aggressive.json
configs/cost_model_v33_trained.json  # 未来可选
```

配置中应包含：

```json
{
  "cost_model_strategy_effects": {...},
  "cost_model_safety": {...},
  "cost_model_risk_modes": {...},
  "kernel_profile_weights": {
    "scalar_control": {...},
    "memory_path": {...},
    "sync_criticality": {...},
    "buffer_pressure": {...},
    "artifact_confidence": {...}
  }
}
```

当前 V3.3.1 已预留结构，但参数仍主要是 heuristic，需要未来实机数据离线训练。
