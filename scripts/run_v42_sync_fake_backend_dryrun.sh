#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
IR_PATH="${1:-sample_input/fa_best.hivm.mlir}"
SELECTED_PLAN="${2:-artifacts/latest_smoke_run/selected_plan.json}"
OUT_DIR="${3:-artifacts/v42_sync_fake_backend_dryrun}"
python tools/execute_sync_precision_contract.py \
  --backend tools/fake_hivm_operation_backend.py \
  --ir "$IR_PATH" \
  --selected-plan "$SELECTED_PLAN" \
  --output-dir "$OUT_DIR"
echo "V4.2 Sync fake backend dry-run outputs: $OUT_DIR"
