#!/usr/bin/env bash
set -euo pipefail
IR_PATH="${1:-sample_input/fa_best.hivm.mlir}"
SELECTED_PLAN="${2:-artifacts/latest_smoke_run/selected_plan.json}"
OUTPUT_DIR="${3:-artifacts/latest_sync_precision_contract}"
python tools/build_sync_precision_contract.py \
  --ir "$IR_PATH" \
  --selected-plan "$SELECTED_PLAN" \
  --output-dir "$OUTPUT_DIR"
echo "[OK] Sync precision contract generated at $OUTPUT_DIR"
