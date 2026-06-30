#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash scripts/run_e2e_initial_calibration.sh /path/to/e2e_split_qkv /path/to/e2e_chunk
#
# This script does not add these samples into CI/tests. It only reproduces the
# one-off weak calibration runs described in docs/calibration/36_e2e_initial_cost_model_calibration_CN.md.

SPLIT_ROOT=${1:?"missing e2e_split_qkv root"}
CHUNK_ROOT=${2:?"missing e2e_chunk root"}
OUT_ROOT=${OUT_ROOT:-artifacts/e2e_initial_calibration_reproduce}
CFG=${CFG:-configs/cost_model_e2e_initial_calibrated.json}
HW=${HW:-configs/ascend_910b.json}

mkdir -p "$OUT_ROOT"

run_case() {
  local name=$1
  local kernel=$2
  local op_summary=$3
  local mode=$4
  local out="$OUT_ROOT/${name}_${mode}"
  rm -rf "$out"
  python auto_strategy_search.py \
    --kernel "$kernel" \
    --hardware-config "$HW" \
    --cost-model-config "$CFG" \
    --cost-risk-mode conservative \
    --candidate-space standard \
    --artifact-kernel-profile on \
    --msprof-op-summary "$op_summary" \
    --msprof-calibration-mode "$mode" \
    --output-dir "$out"
}

run_case split_qkv "$SPLIT_ROOT/dump/kernel.npuir.mlir" "$SPLIT_ROOT/output/op_summary.csv" component_prior
run_case split_qkv "$SPLIT_ROOT/dump/kernel.npuir.mlir" "$SPLIT_ROOT/output/op_summary.csv" component_plus_scale
run_case chunk_kda "$CHUNK_ROOT/dump/kernel.npuir.mlir" "$CHUNK_ROOT/output/op_summary.csv" component_prior
run_case chunk_kda "$CHUNK_ROOT/dump/kernel.npuir.mlir" "$CHUNK_ROOT/output/op_summary.csv" component_plus_scale
