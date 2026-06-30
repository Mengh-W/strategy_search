#!/usr/bin/env bash
set -euo pipefail
IR="${1:-sample_input/original_repo_samples/chunk_kda_kernel_clean.npuir.mlir}"
PLAN="${2:-artifacts/latest_smoke_run/selected_plan.json}"
OUT="${3:-artifacts/v43_sync_rewrite_smoke}"
PYTHONPATH=. python tools/apply_sync_rewrite.py --ir "$IR" --selected-plan "$PLAN" --output-dir "$OUT" --max-actions 1
