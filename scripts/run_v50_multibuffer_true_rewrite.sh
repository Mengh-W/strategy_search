#!/usr/bin/env bash
set -euo pipefail
IR_PATH="${1:-sample_input/original_repo_samples/chunk_kda_kernel_clean.npuir.mlir}"
SELECTED_PLAN="${2:-artifacts/latest_smoke_run/selected_plan.json}"
OUT_DIR="${3:-artifacts/v50_multibuffer_true_rewrite}"
MAX_CANDIDATES="${4:-80}"
MAX_ACTIONS="${5:-3}"
python tools/run_multibuffer_true_rewrite.py \
  --ir "$IR_PATH" \
  --selected-plan "$SELECTED_PLAN" \
  --output-dir "$OUT_DIR" \
  --max-candidates "$MAX_CANDIDATES" \
  --max-actions "$MAX_ACTIONS"
