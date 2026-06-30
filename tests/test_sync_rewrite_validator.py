# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from strategy_search.sync_contract_precision import build_sync_precision_contract_from_files
from strategy_search.sync_rewrite_executor import apply_restricted_sync_rewrite_from_files
from strategy_search.sync_rewrite_validator import validate_restricted_sync_rewrite_files, validate_restricted_sync_rewrite_texts


def test_validator_accepts_one_restricted_pipe_barrier_rewrite(tmp_path: Path):
    original = "module {\n  hivm.hir.pipe_barrier[<PIPE_MTE2>]\n}\n"
    rewritten = "module {\n  // HIVM V4.3 restricted SyncPlan rewrite: original hivm.hir.pipe_barrier[<PIPE_MTE2>]\n  hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_MTE2>, EVENT_ID_AUTO0]\n  hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_MTE2>, EVENT_ID_AUTO0]\n}\n"
    report = {"rewritten_action_count": 1, "mutation_performed": True}
    val = validate_restricted_sync_rewrite_texts(original, rewritten, report)
    assert val["passed_portable_validation"] is True
    assert val["checks"]["non_comment_pipe_barrier_decreased_by_expected"] is True
    assert val["checks"]["generated_events_paired"] is True


def test_full_portable_sync_rewrite_closure_on_chunk_sample(tmp_path: Path):
    repo = Path(__file__).resolve().parents[1]
    ir = repo / "sample_input" / "original_repo_samples" / "chunk_kda_kernel_clean.npuir.mlir"
    selected = repo / "artifacts" / "latest_smoke_run" / "selected_plan.json"
    out = tmp_path / "closure"
    cmd = [sys.executable, str(repo / "tools" / "run_sync_rewrite_closure.py"), "--ir", str(ir), "--selected-plan", str(selected), "--output-dir", str(out)]
    subprocess.run(cmd, cwd=repo, check=True)
    summary = json.loads((out / "sync_portable_rewrite_closure_summary.json").read_text(encoding="utf-8"))
    assert summary["mutation_performed"] is True
    assert summary["rewritten_action_count"] == 1
    assert summary["passed_portable_validation"] is True
    assert summary["production_rewrite_claim_allowed"] is False
    assert (out / "optimized.sync_portable_rewritten.hivm.mlir").exists()


def test_validation_file_api(tmp_path: Path):
    original_path = tmp_path / "a.mlir"
    rewritten_path = tmp_path / "b.mlir"
    report_path = tmp_path / "r.json"
    val_path = tmp_path / "v.json"
    original_path.write_text("module {\n  hivm.hir.pipe_barrier[<PIPE_MTE2>]\n}\n", encoding="utf-8")
    rewritten_path.write_text("module {\n  // HIVM V4.3 restricted SyncPlan rewrite: original hivm.hir.pipe_barrier[<PIPE_MTE2>]\n  hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_MTE2>, EVENT_ID_AUTO0]\n  hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_MTE2>, EVENT_ID_AUTO0]\n}\n", encoding="utf-8")
    report_path.write_text(json.dumps({"rewritten_action_count": 1, "mutation_performed": True}), encoding="utf-8")
    val = validate_restricted_sync_rewrite_files(original_path, rewritten_path, report_path, val_path)
    assert val["passed_portable_validation"] is True
    assert json.loads(val_path.read_text(encoding="utf-8"))["schema_version"] == "hivm_sync_rewrite_validator_v1"
