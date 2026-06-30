#!/usr/bin/env bash
set -euo pipefail
# =============================================================================
# Pre-Linux CI checklist / optional runner.
#
# Default mode prints the recommended fresh-shell commands. Use --run to execute
# them sequentially in the current shell. Fresh-shell mode remains recommended on
# Windows/WSL if a chained pytest session hangs during interpreter cleanup.
# =============================================================================
COMMANDS=(
  "bash scripts/run_v531_fast_ci.sh"
  "bash scripts/run_multibuffer_ci.sh"
  "bash scripts/run_phase5b_roundtrip_ci.sh"
  "bash scripts/run_backend_fake_ci.sh"
  "bash scripts/run_phase6_positive_ci.sh"
)

if [[ "${1:-}" == "--run" ]]; then
  for cmd in "${COMMANDS[@]}"; do
    echo "[pre-linux-ci] $cmd" >&2
    eval "$cmd"
  done
  echo "[pre-linux-ci] all local pre-Linux gates passed" >&2
  exit 0
fi

cat <<'MSG'
Run these commands before Linux/vTriton handoff, preferably in fresh shells:

  bash scripts/run_v531_fast_ci.sh
  bash scripts/run_multibuffer_ci.sh
  bash scripts/run_phase5b_roundtrip_ci.sh
  bash scripts/run_backend_fake_ci.sh
  bash scripts/run_phase6_positive_ci.sh

Or run them sequentially in the current shell with:

  bash scripts/run_pre_linux_ci.sh --run

They require only Python/pytest and the files in this repository. They do not
require real BiShengIR, real MLIR verifier, CANN, Ascend hardware, or msprof.
MSG
