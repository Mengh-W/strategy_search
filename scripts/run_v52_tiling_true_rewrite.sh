#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IR="${1:-$ROOT/sample_input/original_repo_samples/chunk_kda_kernel_clean.npuir.mlir}"
PLAN="${2:-$ROOT/artifacts/latest_smoke_run/selected_plan.json}"
OUT="${3:-$ROOT/artifacts/v52_tiling_true_rewrite}"
python "$ROOT/tools/run_tiling_true_rewrite.py" --ir "$IR" --selected-plan "$PLAN" --output-dir "$OUT"
