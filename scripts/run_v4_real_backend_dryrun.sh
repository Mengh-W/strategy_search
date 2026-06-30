#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  cat >&2 <<USAGE
Usage:
  bash scripts/run_v4_real_backend_dryrun.sh /path/to/hivm-operation-backend [input_ir] [selected_plan] [output_root]

Example:
  bash scripts/run_v4_real_backend_dryrun.sh \
    /path/to/vTriton/build/bin/hivm-operation-backend \
    sample_input/fa_best.hivm.mlir \
    artifacts/latest_smoke_run/selected_plan.json \
    artifacts/v4_real_backend_dryrun

This script does NOT request mutation. It only runs:
  print-capabilities -> inventory -> roundtrip -> verify-only -> dry-run
USAGE
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BACKEND="$1"
IR_PATH="${2:-sample_input/fa_best.hivm.mlir}"
SELECTED_PLAN="${3:-artifacts/latest_smoke_run/selected_plan.json}"
OUT_ROOT="${4:-artifacts/v4_real_backend_dryrun}"
CONTRACT_DIR="$OUT_ROOT/backend_contract"
EXEC_DIR="$OUT_ROOT/backend_execution"
ANALYSIS_DIR="$OUT_ROOT/backend_dryrun_analysis"

if [[ ! -e "$BACKEND" ]]; then
  echo "[ERROR] backend not found: $BACKEND" >&2
  exit 3
fi
if [[ ! -f "$IR_PATH" ]]; then
  echo "[ERROR] input IR not found: $IR_PATH" >&2
  exit 4
fi
if [[ ! -f "$SELECTED_PLAN" ]]; then
  echo "[ERROR] selected_plan not found: $SELECTED_PLAN" >&2
  exit 5
fi

mkdir -p "$CONTRACT_DIR" "$EXEC_DIR" "$ANALYSIS_DIR"

echo "[V4.0 real dry-run] Build SyncPlan+MultiBufferPlan backend contract"
python tools/build_four_plan_backend_contract.py \
  --ir "$IR_PATH" \
  --selected-plan "$SELECTED_PLAN" \
  --output-dir "$CONTRACT_DIR"

echo "[V4.0 real dry-run] Execute contract against real backend: $BACKEND"
python tools/execute_backend_contract.py \
  --backend "$BACKEND" \
  --ir "$IR_PATH" \
  --contract "$CONTRACT_DIR/sync_multibuffer_backend_contract.json" \
  --output-dir "$EXEC_DIR"

echo "[V4.0 real dry-run] Analyze dry-run and guarded mutation eligibility"
python tools/analyze_backend_dryrun.py \
  --contract "$CONTRACT_DIR/sync_multibuffer_backend_contract.json" \
  --dry-run-report "$EXEC_DIR/backend_dry_run_contract.json" \
  --execution-summary "$EXEC_DIR/backend_contract_execution_summary.json" \
  --output-dir "$ANALYSIS_DIR"

echo "[V4.0 real dry-run] Done. Summary: $EXEC_DIR/backend_contract_execution_summary.json"
python - <<PY
import json
from pathlib import Path
p = Path('$EXEC_DIR/backend_contract_execution_summary.json')
obj = json.loads(p.read_text(encoding='utf-8'))
print(json.dumps({
  'summary': str(p),
  'decision': obj.get('decision'),
  'is_real_mlir_backend': obj.get('is_real_mlir_backend'),
  'all_required_commands_ok': obj.get('all_required_commands_ok'),
  'dry_run_action_count': obj.get('dry_run_action_count'),
  'dry_run_located_action_count': obj.get('dry_run_located_action_count'),
  'production_rewrite_claim_allowed': obj.get('production_rewrite_claim_allowed'),
  'dryrun_analysis': '$ANALYSIS_DIR/backend_dryrun_analysis_summary.json',
  'guarded_selection': '$ANALYSIS_DIR/guarded_mutation_selection.json',
}, ensure_ascii=False, indent=2))
PY
