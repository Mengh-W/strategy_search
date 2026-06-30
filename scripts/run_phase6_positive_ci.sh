#!/usr/bin/env bash
set -euo pipefail
# =============================================================================
# Phase-6 Positive-Case CI — run in a fresh shell before Linux handoff.
#
# Covers Phase-6A/6B real-backend readiness harness and Phase-6C restricted
# positive-case file-level rewrite tests.  Still no real vTriton/CANN required.
# =============================================================================
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

python -m pytest -q --cache-clear \
  tests/test_phase6a_real_backend_integration.py \
  tests/test_phase6b_positive_case_harness.py \
  tests/test_phase6c_restricted_true_rewrite.py
