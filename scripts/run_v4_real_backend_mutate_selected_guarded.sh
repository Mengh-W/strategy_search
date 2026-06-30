#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 4 ]]; then
  cat >&2 <<USAGE
Usage:
  HIVM_ALLOW_GUARDED_MUTATION=1 bash scripts/run_v4_real_backend_mutate_selected_guarded.sh \
    /path/to/hivm-operation-backend \
    input_ir.hivm.mlir \
    backend_dryrun_analysis_dir \
    output_dir

This script mutates at most ONE action using:
  backend_dryrun_analysis_dir/single_guarded_action_contract.json

It is intentionally guarded by the HIVM_ALLOW_GUARDED_MUTATION=1 environment
variable. Run it only after real backend dry-run analysis selected one action.
USAGE
  exit 2
fi

if [[ "${HIVM_ALLOW_GUARDED_MUTATION:-0}" != "1" ]]; then
  cat >&2 <<'WARNING'
[GUARD ACTIVE] Refusing mutation.
Set HIVM_ALLOW_GUARDED_MUTATION=1 only after reviewing:
  backend_dryrun_analysis.json
  guarded_mutation_selection.json
  single_guarded_action_contract.json
WARNING
  exit 10
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BACKEND="$1"
IR_PATH="$2"
ANALYSIS_DIR="$3"
OUT_DIR="$4"
SINGLE_CONTRACT="$ANALYSIS_DIR/single_guarded_action_contract.json"
SELECTION="$ANALYSIS_DIR/guarded_mutation_selection.json"

if [[ ! -e "$BACKEND" ]]; then echo "[ERROR] backend not found: $BACKEND" >&2; exit 3; fi
if [[ ! -f "$IR_PATH" ]]; then echo "[ERROR] IR not found: $IR_PATH" >&2; exit 4; fi
if [[ ! -f "$SINGLE_CONTRACT" ]]; then echo "[ERROR] single guarded action contract not found: $SINGLE_CONTRACT" >&2; exit 5; fi
if [[ ! -f "$SELECTION" ]]; then echo "[ERROR] selection report not found: $SELECTION" >&2; exit 6; fi

SELECTED_MUTATION_KIND=$(python - <<PY
import json
from pathlib import Path
obj=json.loads(Path('$SELECTION').read_text(encoding='utf-8'))
if not obj.get('selected'):
    raise SystemExit('selection report has selected=false')
print(obj.get('selected_mutation_kind') or 'guarded_single_action')
PY
)
mkdir -p "$OUT_DIR"

echo "[V4.0 guarded mutate] Mutating one selected action: $SELECTED_MUTATION_KIND"
python tools/execute_backend_contract.py \
  --backend "$BACKEND" \
  --ir "$IR_PATH" \
  --contract "$SINGLE_CONTRACT" \
  --output-dir "$OUT_DIR" \
  --mutation-kind "$SELECTED_MUTATION_KIND" \
  --run-mutate

echo "[V4.0 guarded mutate] Done. Check: $OUT_DIR/backend_contract_execution_summary.json"
