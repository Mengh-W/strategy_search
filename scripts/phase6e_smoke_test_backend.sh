#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 /path/to/hivm-operation-backend fixture.hivm.mlir [out-dir]" >&2
  exit 2
fi
BACKEND="$1"
FIXTURE="$2"
OUT_DIR="${3:-phase6e_smoke_out}"
mkdir -p "${OUT_DIR}"

"${BACKEND}" --print-capabilities | tee "${OUT_DIR}/capabilities.json"
"${BACKEND}" --inventory --input "${FIXTURE}" --report "${OUT_DIR}/inventory.json"
"${BACKEND}" --roundtrip --input "${FIXTURE}" --output "${OUT_DIR}/roundtrip.mlir" --report "${OUT_DIR}/roundtrip_report.json"
"${BACKEND}" --verify-only --input "${OUT_DIR}/roundtrip.mlir" --report "${OUT_DIR}/verify_report.json"
"${BACKEND}" --mutate --mutation-kind gm_roundtrip_deletion --max-gm-pairs 1 --input "${FIXTURE}" --output "${OUT_DIR}/gm_removed.mlir" --report "${OUT_DIR}/gm_mutation_report.json" || true

echo "Smoke test artifacts written to ${OUT_DIR}" >&2
