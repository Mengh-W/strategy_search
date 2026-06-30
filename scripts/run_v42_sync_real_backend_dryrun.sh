#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 /path/to/hivm-operation-backend [ir] [selected_plan] [output_dir]" >&2
  exit 2
fi
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
BACKEND="$1"
IR_PATH="${2:-sample_input/fa_best.hivm.mlir}"
SELECTED_PLAN="${3:-artifacts/latest_smoke_run/selected_plan.json}"
OUT_DIR="${4:-artifacts/v42_sync_real_backend_dryrun}"
python tools/execute_sync_precision_contract.py \
  --backend "$BACKEND" \
  --ir "$IR_PATH" \
  --selected-plan "$SELECTED_PLAN" \
  --output-dir "$OUT_DIR"
echo "V4.2 Sync real backend dry-run outputs: $OUT_DIR"
