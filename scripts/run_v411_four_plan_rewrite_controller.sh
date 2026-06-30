#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IR="${1:-$ROOT/sample_input/original_repo_samples/chunk_kda_kernel_clean.npuir.mlir}"
PLAN="${2:-$ROOT/artifacts/latest_smoke_run/selected_plan.json}"
OUT="${3:-$ROOT/artifacts/v411_four_plan_rewrite_controller}"
MAX_SYNC="${4:-999999}"
MAX_MB="${5:-80}"
MAX_CV="${6:-50}"
MAX_ANN="${7:-20}"
python "$ROOT/tools/run_four_plan_rewrite_controller.py" \
  --ir "$IR" \
  --selected-plan "$PLAN" \
  --output-dir "$OUT" \
  --max-sync-actions "$MAX_SYNC" \
  --max-multibuffer-candidates "$MAX_MB" \
  --max-cvpipeline-windows "$MAX_CV" \
  --max-annotations "$MAX_ANN"
