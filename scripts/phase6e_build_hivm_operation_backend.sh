#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 /path/to/vTriton [build-dir]" >&2
  exit 2
fi
VTRITON_ROOT="$1"
BUILD_DIR="${2:-${VTRITON_ROOT}/build}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

python "${SCRIPT_DIR}/phase6e_apply_vtriton_backend_patch.py" \
  --vtriton-root "${VTRITON_ROOT}" \
  --adapter-dir "${PROJECT_ROOT}/vtriton_hivm_operation_backend" \
  --report "${PROJECT_ROOT}/phase6e_vtriton_backend_patch_report.json" \
  --apply

if [[ ! -d "${BUILD_DIR}" ]]; then
  echo "Build dir ${BUILD_DIR} does not exist. Re-run your vTriton CMake configure first." >&2
  echo "Example: cmake -S ${VTRITON_ROOT} -B ${BUILD_DIR} <your existing vTriton MLIR/BishengIR options>" >&2
  exit 3
fi

cmake --build "${BUILD_DIR}" --target hivm-operation-backend -j"$(nproc)"

BIN="${BUILD_DIR}/bin/hivm-operation-backend"
if [[ ! -x "${BIN}" ]]; then
  BIN="$(find "${BUILD_DIR}" -type f -name hivm-operation-backend -perm -111 | head -n 1 || true)"
fi
if [[ -z "${BIN}" ]]; then
  echo "Build finished but hivm-operation-backend binary was not found." >&2
  exit 4
fi
"${BIN}" --print-capabilities
