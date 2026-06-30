#!/usr/bin/env bash
set -euo pipefail
IR="${1:-sample_input/original_repo_samples/chunk_kda_kernel_clean.npuir.mlir}"
SELECTED="${2:-artifacts/latest_smoke_run/selected_plan.json}"
OUT="${3:-artifacts/v45_sync_portable_rewrite}"
python tools/run_sync_rewrite_closure.py --ir "$IR" --selected-plan "$SELECTED" --output-dir "$OUT" --max-actions 1
