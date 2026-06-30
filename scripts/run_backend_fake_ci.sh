#!/usr/bin/env bash
set -euo pipefail
# =============================================================================
# Backend Fake CI — stable core, no real vTriton/BiShengIR/CANN required.
#
# Validates Python -> backend contract -> fake backend -> report plumbing.
# It does NOT prove production-level HIVM rewrite.
#
# Phase-5B roundtrip/verifier is intentionally split into
# scripts/run_phase5b_roundtrip_ci.sh and should be run in a separate fresh shell
# before Linux handoff.
# =============================================================================
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export PYTHONHASHSEED=0

python -m pytest -q --cache-clear \
  tests/test_backend_contract.py \
  tests/test_backend_contract_runner.py \
  tests/test_backend_dryrun_analyzer.py \
  tests/test_phase4b_des_trace_execution.py \
  tests/test_phase5c_operation_dry_run.py \
  tests/test_phase5d_guarded_mutation.py \
  tests/test_phase5e_gm_deletion_gate.py \
  tests/test_phase5f_closure.py \
  tests/test_phase6d_vtriton_adapter_skeleton.py \
  tests/test_phase6e_vtriton_integration_pack.py \
  tests/test_phase6f_backend_acceptance.py
