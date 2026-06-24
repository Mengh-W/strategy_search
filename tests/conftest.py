# -*- coding: utf-8 -*-
"""Shared pytest helpers for the strategy-search test suite."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def repo_root() -> Path:
    return ROOT


def sample_kernel(name: str = "fa_bad_inefficient.hivm.mlir") -> Path:
    return ROOT / "sample_input" / name


def hardware_config(name: str = "ascend_910b.json") -> Path:
    return ROOT / "configs" / name


def cost_model_config(mode: str = "conservative") -> Path:
    return ROOT / "configs" / f"cost_model_{mode}.json"
