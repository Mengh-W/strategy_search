#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IR="${1:-$ROOT/sample_input/original_repo_samples/chunk_kda_kernel_clean.npuir.mlir}"
PLAN="${2:-$ROOT/artifacts/latest_smoke_run/selected_plan.json}"
OUT="${3:-$ROOT/artifacts/v410_cvpipeline_stage_planner}"
MAX_WINDOWS="${4:-50}"
MAX_ANNOTATIONS="${5:-20}"
MB_REPORT="${6:-}"
mkdir -p "$OUT"
ARGS=(--ir "$IR" --selected-plan "$PLAN" --output-dir "$OUT" --max-windows "$MAX_WINDOWS" --max-annotations "$MAX_ANNOTATIONS")
if [[ -n "$MB_REPORT" ]]; then
  ARGS+=(--multibuffer-stage-report "$MB_REPORT")
fi
python "$ROOT/tools/run_cvpipeline_stage_planner.py" "${ARGS[@]}"
