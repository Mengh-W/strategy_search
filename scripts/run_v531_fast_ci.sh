#!/usr/bin/env bash
set -euo pipefail
# =============================================================================
# V5.3.1 Fast CI — deterministic subset, < 60 seconds, no real vTriton/CANN.
#
# Coverage:
#   - Bound search + rewrite wrapper
#   - DES profile calibration
#   - SyncPlan event rewrite / validator
#   - CVPipelinePlan restricted rewrite
#   - TilingPlan trace-metadata rewrite
#   - V5.3 parameter coverage
#   - Four-plan rewrite CLI
#
# Note:
#   Dedicated MultiBuffer restricted rewrite tests are intentionally split into
#   scripts/run_multibuffer_ci.sh. Backend-contract and Phase-6 positive tests are
#   split into scripts/run_backend_fake_ci.sh and scripts/run_phase6_positive_ci.sh.
#   Keeping them separate avoids long chained pytest sessions during Windows/WSL
#   pre-Linux handoff.
# =============================================================================
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

python -m pytest -q \
  tests/test_v531_bound_search_rewrite.py \
  tests/test_des_profile_calibration.py \
  tests/test_sync_rewrite_executor.py \
  tests/test_sync_rewrite_validator.py \
  tests/test_v51_cvpipeline_true_rewrite.py \
  tests/test_v52_tiling_true_rewrite.py \
  tests/test_v53_parameter_coverage.py \
  tests/test_v53_four_plan_true_rewrite_cli.py