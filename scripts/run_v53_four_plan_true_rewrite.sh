#!/usr/bin/env bash
set -euo pipefail
IR=${1:-sample_input/original_repo_samples/chunk_kda_kernel_clean.npuir.mlir}
PLAN=${2:-artifacts/latest_smoke_run/selected_plan.json}
OUT=${3:-artifacts/v53_four_plan_true_rewrite}
MAX_MB_CAND=${4:-80}
MAX_MB_ACTIONS=${5:-3}
MAX_CV_WINDOWS=${6:-50}
MAX_CV_ACTIONS=${7:-2}
MAX_SYNC=${8:-999999}
python tools/run_four_plan_true_rewrite.py \
  --ir "$IR" \
  --selected-plan "$PLAN" \
  --output-dir "$OUT" \
  --max-multibuffer-candidates "$MAX_MB_CAND" \
  --max-multibuffer-actions "$MAX_MB_ACTIONS" \
  --max-cvpipeline-windows "$MAX_CV_WINDOWS" \
  --max-cvpipeline-actions "$MAX_CV_ACTIONS" \
  --max-sync-actions "$MAX_SYNC"
