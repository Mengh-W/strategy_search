#!/usr/bin/env bash
set -euo pipefail
IR=${1:-sample_input/fa_bad_inefficient.hivm.mlir}
OUT=${2:-artifacts/v531_bound_search_rewrite}
HW=${3:-configs/ascend_910b.json}
COST=${4:-configs/cost_model_conservative.json}
MODE=${5:-conservative}
SPACE=${6:-standard}
python tools/run_search_and_four_plan_rewrite.py \
  --kernel "$IR" \
  --hardware-config "$HW" \
  --cost-model-config "$COST" \
  --cost-risk-mode "$MODE" \
  --candidate-space "$SPACE" \
  --output-dir "$OUT"
