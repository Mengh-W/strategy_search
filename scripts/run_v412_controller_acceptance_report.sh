#!/usr/bin/env bash
set -euo pipefail
IR_PATH="${1:-sample_input/original_repo_samples/chunk_kda_kernel_clean.npuir.mlir}"
PLAN_PATH="${2:-artifacts/latest_smoke_run/selected_plan.json}"
OUT_DIR="${3:-artifacts/v412_controller_acceptance_report}"
MAX_SYNC="${4:-999999}"
MAX_MB="${5:-80}"
MAX_CV="${6:-50}"
MAX_ANN="${7:-20}"
python tools/run_controller_acceptance_report.py \
  --ir "$IR_PATH" \
  --selected-plan "$PLAN_PATH" \
  --output-dir "$OUT_DIR" \
  --max-sync-actions "$MAX_SYNC" \
  --max-multibuffer-candidates "$MAX_MB" \
  --max-cvpipeline-windows "$MAX_CV" \
  --max-annotations "$MAX_ANN"
