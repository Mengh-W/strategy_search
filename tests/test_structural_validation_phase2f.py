import json
from pathlib import Path

from strategy_search.structural_rewrite import build_structural_validation_summary
from strategy_search.core import main


def test_phase2f_validation_summary_reflects_barrier_and_cv_sync_changes():
    original = """
module {
  func.func @k() {
    hivm.hir.mmad ins(%a) outs(%b)
    hivm.hir.barrier {mode = "ALL"}
    hivm.hir.vexp ins(%b) outs(%b)
    return
  }
}
""".lstrip()
    optimized = """
module {
  func.func @k() {
    hivm.hir.mmad ins(%a) outs(%b)
    hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_M>, <EVENT_ID0>]
    hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_M>, <EVENT_ID0>]
    hivm.hir.set_flag[<PIPE_FIX>, <PIPE_V>, <EVENT_ID1>]
    hivm.hir.wait_flag[<PIPE_FIX>, <PIPE_V>, <EVENT_ID1>]
    hivm.hir.vexp ins(%b) outs(%b)
    return
  }
}
""".lstrip()
    report = {
        "changes_summary": {
            "change_counts": {
                "replace_barrier_all_with_directional_sync": 1,
                "insert_sync_before_first_vector_op": 1,
            }
        },
        "changes": [],
    }
    summary = build_structural_validation_summary(original, optimized, report)
    assert summary["passed_local_validation"] is True
    assert summary["op_count_delta"]["barrier_all"] == -1
    assert summary["op_count_delta"]["set_flag"] == 2
    assert summary["op_count_delta"]["wait_flag"] == 2
    assert not summary["errors"]


def test_phase2f_cli_emits_structural_validation_summary(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    out = tmp_path / "out"
    argv = [
        "prog",
        "--kernel", str(root / "sample_input" / "fa_bad_inefficient.hivm.mlir"),
        "--hardware-config", str(root / "configs" / "ascend_910b.json"),
        "--enable-ir-rewrite",
        "--rewrite-mode", "both",
        "--rewrite-safety", "balanced",
        "--enable-structural-rewrite",
        "--structural-rewrite-safety", "balanced",
        "--structural-rewrite-backend", "python",
        "--output-dir", str(out),
    ]
    monkeypatch.setattr("sys.argv", argv)
    main()
    summary_path = out / "structural_validation_summary.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["schema_version"] == "hivm_structural_validation_summary_v1"
    assert "op_count_delta" in summary
    assert "claimed_change_counts" in summary
    assert summary["passed_local_validation"] is True
