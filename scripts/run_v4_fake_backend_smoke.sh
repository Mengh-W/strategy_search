#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

IR_PATH="${1:-sample_input/fa_best.hivm.mlir}"
SELECTED_PLAN="${2:-artifacts/latest_smoke_run/selected_plan.json}"
OUT_ROOT="${3:-artifacts/v4_fake_backend_smoke}"
CONTRACT_DIR="$OUT_ROOT/backend_contract"
EXEC_DIR="$OUT_ROOT/backend_execution"
ANALYSIS_DIR="$OUT_ROOT/backend_dryrun_analysis"

mkdir -p "$CONTRACT_DIR" "$EXEC_DIR" "$ANALYSIS_DIR"

echo "[V4.0 fake smoke] Build backend contract"
python tools/build_four_plan_backend_contract.py \
  --ir "$IR_PATH" \
  --selected-plan "$SELECTED_PLAN" \
  --output-dir "$CONTRACT_DIR"

echo "[V4.0 fake smoke] Execute contract with bundled fake backend"
python tools/execute_backend_contract.py \
  --backend tools/fake_hivm_operation_backend.py \
  --ir "$IR_PATH" \
  --contract "$CONTRACT_DIR/sync_multibuffer_backend_contract.json" \
  --output-dir "$EXEC_DIR"

echo "[V4.0 fake smoke] Analyze dry-run and guarded mutation eligibility"
python tools/analyze_backend_dryrun.py \
  --contract "$CONTRACT_DIR/sync_multibuffer_backend_contract.json" \
  --dry-run-report "$EXEC_DIR/backend_dry_run_contract.json" \
  --execution-summary "$EXEC_DIR/backend_contract_execution_summary.json" \
  --output-dir "$ANALYSIS_DIR"

echo "[V4.0 fake smoke] Done. Summary: $EXEC_DIR/backend_contract_execution_summary.json"
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
  'production_rewrite_claim_allowed': obj.get('production_rewrite_claim_allowed'),
  'dryrun_analysis': '$ANALYSIS_DIR/backend_dryrun_analysis_summary.json',
}, ensure_ascii=False, indent=2))
PY
