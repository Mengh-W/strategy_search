#!/usr/bin/env bash
set -euo pipefail
IR=${1:-sample_input/fa_best.hivm.mlir}
PLAN=${2:-artifacts/latest_smoke_run/selected_plan.json}
OUT=${3:-artifacts/v58_tiling_cvpipeline_semantic_rewrite}
python tools/run_four_plan_operation_rewrite.py --ir "$IR" --selected-plan "$PLAN" --output-dir "$OUT"
