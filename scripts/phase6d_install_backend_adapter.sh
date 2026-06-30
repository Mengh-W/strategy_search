#!/usr/bin/env bash
set -euo pipefail

# Copy the generated Phase-6D HIVM Operation backend adapter into a vTriton tree.
# Usage:
#   ./scripts/phase6d_install_backend_adapter.sh /path/to/vTriton

VTRITON_ROOT="${1:-}"
if [[ -z "${VTRITON_ROOT}" || ! -d "${VTRITON_ROOT}" ]]; then
  echo "usage: $0 /path/to/vTriton" >&2
  exit 2
fi

SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)/vtriton_hivm_operation_backend"
DST_DIR="${VTRITON_ROOT}/tools/hivm-operation-backend"
mkdir -p "${DST_DIR}"
cp -R "${SRC_DIR}/"* "${DST_DIR}/"

echo "Installed adapter to ${DST_DIR}"
echo "Next: add add_subdirectory(hivm-operation-backend) to ${VTRITON_ROOT}/tools/CMakeLists.txt if not already present, then rebuild vTriton."
