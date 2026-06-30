#!/usr/bin/env bash
# Compatibility wrapper for the maintained CANN 9 remote benchmark runner.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

host="${REMOTE_HOST:-910B3}"
output_dir="${1:-${REPO_ROOT}/perfbound/calibration/bench_output}"

exec python3 "${SCRIPT_DIR}/cce_remote_bench.py" \
  --host "${host}" \
  --output-dir "${output_dir}" \
  "${@:2}"
