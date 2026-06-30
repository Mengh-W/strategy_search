#!/usr/bin/env bash
set -euo pipefail
IR="${1:-sample_input/fa_best.hivm.mlir}"
PLAN="${2:-artifacts/latest_smoke_run/selected_plan.json}"
OUT="${3:-artifacts/v60_four_plan_real_operation_materialization}"
python tools/run_four_plan_operation_rewrite.py \
  --ir "$IR" \
  --selected-plan "$PLAN" \
  --output-dir "$OUT"
echo "[V6.0] recommended Linux validation IR: $OUT/optimized.four_plan_real_operation_materialized.hivm.mlir"
echo "[V6.0] marker/materialization audit: $OUT/v60_semantic_marker_materialization_audit.json"
