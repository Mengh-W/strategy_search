# -*- coding: utf-8 -*-
import json
import sys

from strategy_search.structural_rewrite import build_phase2_closure_report


def test_phase2h_closure_report_contains_phase3_plan():
    report = build_phase2_closure_report(
        edit_script={"edits": [{"type": "replace_barrier_all_with_directional_sync", "enabled": True}]},
        backend_plan={"selected_backend": "vtriton_strategy_rewriter"},
        adapter_manifest={"external_backend_coverage": {"coverage_by_edit_type": {"replace_barrier_all_with_directional_sync": True}}},
        legality_report={"summary": {"local_precheck_passed": 1}},
        rewrite_report={"changes_summary": {"change_counts": {"replace_barrier_all_with_directional_sync": 1}}},
        validation_summary={"passed_local_validation": True, "warnings": []},
    )
    assert report["schema_version"] == "hivm_phase2_closure_report_v1"
    assert report["phase2_status"] == "closed"
    assert any(x["subphase"] == "Phase 2H" for x in report["subphase_matrix"])
    assert report["recommended_next_entrypoint"].startswith("Phase 3A")
    assert report["phase3_plan"]


def test_phase2h_cli_emits_closure_report(tmp_path, monkeypatch):
    from strategy_search import core

    out = tmp_path / "out"
    argv = [
        "prog",
        "--kernel", "sample_input/fa_bad_inefficient.hivm.mlir",
        "--hardware-config", "configs/ascend_910b.json",
        "--enable-ir-rewrite",
        "--rewrite-mode", "both",
        "--rewrite-safety", "balanced",
        "--enable-structural-rewrite",
        "--structural-rewrite-backend", "python",
        "--structural-rewrite-safety", "balanced",
        "--output-dir", str(out),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    core.main()
    path = out / "phase2_closure_report.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["phase2_status"] == "closed"
    assert "phase3_key_difficulties" in data
