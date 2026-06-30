#!/usr/bin/env bash
set -euo pipefail
# Remove local caches and temporary debug files before packaging.
find . -type d -name "__pycache__" -prune -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
rm -rf .pytest_cache
rm -f _debug_parse.py _test_editor_integration.py _test_full.py _test_real_parser.py _test_roundtrip.py _test_structural_rewrite_integration.py
rm -rf artifacts/prelinux_ci_logs
find . -type d -name ".omc" -prune -exec rm -rf {} +
