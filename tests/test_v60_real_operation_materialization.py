# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v60_real_operation_materialization_outputs(tmp_path: Path):
    out = tmp_path / "v60"
    cmd = [
        sys.executable,
        str(ROOT / "tools" / "run_four_plan_operation_rewrite.py"),
        "--ir", str(ROOT / "sample_input" / "fa_best.hivm.mlir"),
        "--selected-plan", str(ROOT / "artifacts" / "latest_smoke_run" / "selected_plan.json"),
        "--output-dir", str(out),
    ]
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=True)
    summary = json.loads(proc.stdout)
    assert summary["four_plan_operation_rewrite_performed"] is True
    assert summary["v60_real_operation_materialization_performed"] is True
    assert summary["v60_marker_materialization_audit_passed"] is True
    assert summary["v60_semantic_marker_as_logic_count"] == 0
    ir_path = Path(summary["v60_real_operation_materialized_ir"])
    assert ir_path.exists()
    text = ir_path.read_text(encoding="utf-8")
    assert "hivm.v60_tiling_materialized=true" in text
    assert "hivm.v60_reduction_materialized=true" in text
    assert "hivm.v60_cvpipeline_materialized=true" in text
    assert "hivm.v60_sync_dependency_regenerated=true" in text
    assert "HIVM V5.8 tile-slice binding" not in text
    assert "HIVM V5.8 CVPipeline stage binding" not in text
    audit = json.loads((out / "v60_semantic_marker_materialization_audit.json").read_text(encoding="utf-8"))
    assert audit["passed_v60_marker_materialization_audit"] is True
    mb = json.loads((out / "v60_multibuffer_use_def_coverage.json").read_text(encoding="utf-8"))
    assert mb["all_materialized_buffers_have_ping_pong"] is True
