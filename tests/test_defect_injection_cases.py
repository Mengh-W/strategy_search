#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Defect-injection regression tests for the nine synthetic HIVM/NPUIR cases.

The nine MLIR files in tests/defect_inputs/ are intentionally bad kernels.  The
checked behavior is demo-level and analytical: obvious low-quality directions
(small tiles, UB overflow, excessive barriers, missing overlap, mixed memory
pressure) should be reflected in parser/current-IR estimates, and the recorded
search result should move toward safer or lower-cost StrategyConfig choices.

The default tests are intentionally fast: they validate the defect files and the
recorded audit summary.  Set RUN_DEFECT_LIVE=1 to execute the live optimizer for
these cases; the live mode is useful before refreshing DEFECT_INJECTION_TEST_REPORT.md
but is kept opt-in because it is much heavier than unit/smoke tests.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import auto_strategy_search as search  # noqa: E402

SUMMARY_PATH = ROOT / "tests" / "defect_expected" / "defect_run_summary.json"
DEFECT_DIR = ROOT / "tests" / "defect_inputs"


def _load_summary() -> list[dict]:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


@pytest.mark.regression
@pytest.mark.parametrize("row", _load_summary(), ids=lambda r: r["case"])
def test_defect_input_file_exists_and_parser_matches_recorded_current_ir(row: dict) -> None:
    """The nine defect MLIR files are real test inputs and parser output matches the audit."""
    kernel = DEFECT_DIR / f"{row['case']}.mlir"
    assert kernel.exists(), kernel
    text = kernel.read_text(encoding="utf-8")
    assert "缺陷" in text or "defect" in text.lower()

    kf = search.parse_kernel_features(str(kernel))
    tm, tn, tk = [int(x) for x in row["cur_tile"].split("x")]
    shape = kf.inferred_problem_shape
    assert shape["extracted_tile_m"] == tm
    assert shape["extracted_tile_n"] == tn
    assert shape["extracted_tile_k"] == tk
    assert kf.num_pipe_barrier == row["cur_barrier"]
    assert kf.num_set_flag == row["cur_set"]
    assert kf.num_wait_flag == row["cur_wait"]


@pytest.mark.regression
@pytest.mark.parametrize("row", _load_summary(), ids=lambda r: r["case"])
def test_recorded_defect_search_result_moves_in_expected_direction(row: dict) -> None:
    """Recorded results should show the expected optimization direction for every defect case."""
    # Current IR legality expectation.
    if row["cur_feasible"]:
        assert row["cur_reason"] == "ok"
        assert row["speedup"] is not None
        assert row["speedup"] > 1.0
        assert row["best_cycles"] < row["cur_cycles"]
    else:
        assert "overflow" in row["cur_reason"].lower()
        assert row["speedup"] is None

    # Common best-strategy direction under the current analytical model.
    assert row["best_db"] is True
    assert row["best_cv"] == 2
    assert row["best_sync"] == "graph_sync_solver"
    assert row["best_event_reuse"] is True
    assert row["best_risk"] in {"MEDIUM", "HIGH"}
    assert row["legal"] > 0
    assert row["relaxed"] >= 0

    # Capacity-overflow cases should be pulled back to a smaller N tile.
    if not row["cur_feasible"]:
        cur_n = int(row["cur_tile"].split("x")[1])
        best_n = int(row["best_tile"].split("x")[1])
        assert best_n < cur_n


def _run_live_case(kernel: Path, out: Path) -> tuple[dict, dict]:
    cmd = [
        sys.executable,
        "auto_strategy_search.py",
        "--kernel",
        str(kernel),
        "--hardware-config",
        str(ROOT / "configs" / "ascend_910b.json"),
        "--cost-model-config",
        str(ROOT / "configs" / "cost_model_conservative.json"),
        "--cost-risk-mode",
        "conservative",
        "--output-dir",
        str(out),
    ]
    subprocess.run(cmd, cwd=ROOT, check=True, text=True, timeout=90)
    report = json.loads((out / "search_report.json").read_text(encoding="utf-8"))
    selected = json.loads((out / "selected_strategy.json").read_text(encoding="utf-8"))
    return report, selected


@pytest.mark.slow
@pytest.mark.regression
@pytest.mark.parametrize("row", _load_summary(), ids=lambda r: "live_" + r["case"])
def test_live_defect_case_optional(row: dict) -> None:
    """Opt-in live check: rerun the optimizer for one synthetic defect input."""
    if os.environ.get("RUN_DEFECT_LIVE") != "1":
        pytest.skip("set RUN_DEFECT_LIVE=1 to rerun live defect-injection searches")

    kernel = DEFECT_DIR / f"{row['case']}.mlir"
    with tempfile.TemporaryDirectory() as td:
        report, selected = _run_live_case(kernel, Path(td) / "out")

    cur = report["current_ir_estimated_strategy"]
    best = selected["strategy"]
    cur_m, cur_n, cur_k = [int(x) for x in row["cur_tile"].split("x")]
    assert (cur["strategy"]["tile_m"], cur["strategy"]["tile_n"], cur["strategy"]["tile_k"]) == (cur_m, cur_n, cur_k)
    assert cur["feasible"] is row["cur_feasible"]
    assert best["double_buffer"] is True
    assert best["cv_pipeline_stage"] == 2
    assert best["sync_policy"] == "graph_sync_solver"
