#!/usr/bin/env bash
set -euo pipefail
IR_PATH="${1:-sample_input/fa_best.hivm.mlir}"
PLAN_PATH="${2:-artifacts/latest_smoke_run/selected_plan.json}"
OUT_DIR="${3:-artifacts/v54_tiling_operation_readiness}"
python tools/run_tiling_operation_readiness.py --ir "$IR_PATH" --selected-plan "$PLAN_PATH" --output-dir "$OUT_DIR"
