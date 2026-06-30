#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
IR="${1:-sample_input/original_repo_samples/chunk_kda_kernel_clean.npuir.mlir}"
PLAN="${2:-artifacts/latest_smoke_run/selected_plan.json}"
OUT="${3:-artifacts/v47_sync_rewrite_safety_audit}"
MAX_ACTIONS="${4:-999999}"
python tools/run_sync_full_rewrite.py --ir "$IR" --selected-plan "$PLAN" --output-dir "$OUT" --max-actions "$MAX_ACTIONS"
