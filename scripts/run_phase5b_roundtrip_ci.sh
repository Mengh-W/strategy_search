#!/usr/bin/env bash
set -euo pipefail
# =============================================================================
# Phase-5B Roundtrip/Verifier CI — standalone pre-Linux gate.
#
# Runs the fake-backend no-op roundtrip/verify gate in a fresh shell. Keep this
# separate from backend_fake_ci because some Windows/WSL/Python combinations can
# hang during subprocess cleanup when Phase-5B and other fake-backend pytest
# batches are chained together.
# =============================================================================
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export PYTHONHASHSEED=0

python -m pytest -q --cache-clear tests/test_phase5b_roundtrip_verifier.py
