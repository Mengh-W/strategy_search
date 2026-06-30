#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $# -lt 1 ]]; then
  echo "Usage: scripts/run_v44_real_sync_mutation.sh /path/to/hivm-operation-backend [ir] [selected_plan] [output_dir]" >&2
  exit 2
fi
if [[ "${HIVM_ALLOW_SYNC_MUTATION:-0}" != "1" ]]; then
  echo "Refusing to run mutation. Set HIVM_ALLOW_SYNC_MUTATION=1 explicitly." >&2
  exit 3
fi
BACKEND="$1"
IR_PATH="${2:-sample_input/original_repo_samples/chunk_kda_kernel_clean.npuir.mlir}"
SELECTED_PLAN="${3:-artifacts/latest_smoke_run/selected_plan.json}"
OUT_DIR="${4:-artifacts/v44_real_sync_mutation}"
CONTRACT_DIR="$OUT_DIR/sync_precision_contract"
mkdir -p "$CONTRACT_DIR"
python tools/build_sync_precision_contract.py --ir "$IR_PATH" --selected-plan "$SELECTED_PLAN" --output-dir "$CONTRACT_DIR"
"$BACKEND" --mutate --mutation-kind sync_event_insertion \
  --input "$IR_PATH" \
  --edit-script "$CONTRACT_DIR/sync_precision_contract.json" \
  --output "$OUT_DIR/optimized.sync_hivmopseditor.hivm.mlir" \
  --report "$OUT_DIR/sync_hivmopseditor_mutation_report.json"
echo "V4.4 real SyncPlan mutation prototype outputs: $OUT_DIR"
