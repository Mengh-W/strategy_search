#!/usr/bin/env bash
set -euo pipefail

# 用法：在项目根目录运行。该脚本只复核合并 config，不要求把样本纳入测试集。
# 需要用户自行提供 e2e_split_qkv / e2e_chunk 的解压目录。

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

CONFIG="configs/cost_model_e2e_prefill_merged.json"
OUT_ROOT="artifacts/merged_calibration_rerun"
mkdir -p "$OUT_ROOT"

python scripts/prefill_a5_plan_only_validation.py \
  --cost-model-config "$CONFIG" \
  --output-dir "$OUT_ROOT/prefill_a5_plan_only"

echo "Prefill-A5 validation done."
echo "For E2E split_qkv/chunk_kda, run auto_strategy_search.py with --cost-model-config $CONFIG and --msprof-calibration-mode component_prior."
