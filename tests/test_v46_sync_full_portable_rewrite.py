# -*- coding: utf-8 -*-
import json
import subprocess
import sys
from pathlib import Path


def test_v46_full_rewrite_multiple_actions(tmp_path):
    root = Path(__file__).resolve().parents[1]
    ir = root / "sample_input" / "original_repo_samples" / "chunk_kda_kernel_clean.npuir.mlir"
    plan = root / "artifacts" / "latest_smoke_run" / "selected_plan.json"
    out = tmp_path / "v46"
    cmd = [sys.executable, str(root / "tools" / "run_sync_full_rewrite.py"), "--ir", str(ir), "--selected-plan", str(plan), "--output-dir", str(out), "--max-actions", "3"]
    subprocess.run(cmd, check=True)
    summary = json.loads((out / "sync_full_portable_rewrite_closure_summary.json").read_text())
    assert summary["portable_full_rewrite_closure_passed"] is True
    assert summary["rewritten_action_count"] == 3
    report = json.loads((out / "sync_full_portable_rewrite_report.json").read_text())
    assert report["rewritten_action_count"] == 3
    validation = json.loads((out / "sync_full_portable_rewrite_validation.json").read_text())
    assert validation["passed_portable_validation"] is True
    diff = json.loads((out / "sync_full_portable_rewrite_diff.json").read_text())
    assert diff["num_sync_related_diff_lines"] >= 3


def test_v46_full_rewrite_candidate_report(tmp_path):
    root = Path(__file__).resolve().parents[1]
    ir = root / "sample_input" / "original_repo_samples" / "chunk_kda_kernel_clean.npuir.mlir"
    plan = root / "artifacts" / "latest_smoke_run" / "selected_plan.json"
    out = tmp_path / "v46_candidates"
    subprocess.run([sys.executable, str(root / "tools" / "run_sync_full_rewrite.py"), "--ir", str(ir), "--selected-plan", str(plan), "--output-dir", str(out), "--max-actions", "1"], check=True)
    candidates = json.loads((out / "sync_full_rewrite_candidates.json").read_text())
    assert candidates["num_candidate_actions"] == 1
    assert candidates["candidate_actions"][0]["pipe"].startswith("PIPE_")
