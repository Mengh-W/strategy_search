#!/usr/bin/env bash
set -euo pipefail
# =============================================================================
# Dedicated MultiBuffer CI — restricted true-rewrite readiness/stage/action tests.
#
# This is separated from the fast smoke gate so users can run the lightweight
# default path quickly while still having an explicit MultiBuffer handoff gate.
# =============================================================================
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export PYTHONHASHSEED=0

python -m pytest -q --cache-clear \
  tests/test_v48_multibuffer_rewrite_readiness.py \
  tests/test_v49_multibuffer_stage_boundary.py \
  tests/test_v50_multibuffer_true_rewrite.py
