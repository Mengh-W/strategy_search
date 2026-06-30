#!/usr/bin/env bash
set -euo pipefail
IR=${1:-sample_input/fa_best.hivm.mlir}
PLAN=${2:-artifacts/latest_smoke_run/selected_plan.json}
OUT=${3:-artifacts/v59_four_plan_semantic_rewrite_hardening}
python tools/run_four_plan_operation_rewrite.py --ir "$IR" --selected-plan "$PLAN" --output-dir "$OUT"
echo "[V5.9] recommended Linux validation IR: $OUT/optimized.four_plan_operation_rewrite.v59_syntax_hardened.hivm.mlir"
