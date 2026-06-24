# V3.2-stage2c 搜索质量审计

本版本在 stage2b 的 Beam Search 稳定性基础上，新增了 bounded search-quality audit。目标不是替代主搜索，而是给 Beam Search 增加可解释的对照基线。

## 新增能力

1. `--enable-search-quality-audit`：在正常 layered beam search 之外，额外构造一个紧凑候选空间。
2. 小空间穷举 baseline：在 compact subspace 上完整枚举，用于估计 Beam Search 与局部全局最优之间的 gap。
3. 随机搜索 baseline：固定随机种子和预算，从 compact exhaustive pool 中采样，用于证明 Beam Search 相对随机搜索的优势。
4. `search_audit.json` 新增 `search_quality_audit` 字段，包括 Beam best、small exhaustive best、random best、gap 和随机优势。

## 命令示例

```bash
python -m strategy_search.cli \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --candidate-space expanded \
  --search-mode layered \
  --guided-mode off \
  --cost-risk-mode conservative \
  --cost-model-config configs/cost_model_conservative.json \
  --enable-search-quality-audit \
  --search-quality-random-budget 64 \
  --search-quality-random-seed 7 \
  --output-dir output_stage2c
```

## 边界说明

该审计只在一个紧凑子空间上比较 Beam、exhaustive 和 random，不证明真实硬件全局最优，也不替代 profiling。它的价值是验证当前 Beam Search 在 bounded subspace 中是否表现合理。
