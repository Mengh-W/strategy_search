from pathlib import Path
import json
from strategy_search.operation_rewrite.four_plan_operation_rewriter import run_four_plan_operation_rewrite


def test_v61_linux_handoff_created(tmp_path):
    summary = run_four_plan_operation_rewrite(
        "sample_input/fa_best.hivm.mlir",
        "artifacts/latest_smoke_run/selected_plan.json",
        tmp_path,
        max_multibuffer_actions=2,
        max_cvpipeline_actions=2,
    )
    assert summary["v61_linux_handoff_created"] is True
    handoff = Path(summary["v61_linux_handoff_dir"])
    assert (handoff / "inputs" / "baseline.hivm.mlir").exists()
    assert (handoff / "inputs" / "optimized.hivm.mlir").exists()
    assert (handoff / "inputs" / "selected_plan.json").exists()
    assert (handoff / "backend_commands.json").exists()
    assert (handoff / "run_linux_validation.py").exists()
    assert (handoff / "collect_msprof_compare.py").exists()
    contract = json.loads((handoff / "backend_patch_contract.json").read_text(encoding="utf-8"))
    assert "TilingPlan" in contract["must_validate"]
    assert "CVPipelinePlan" in contract["must_validate"]
    manifest = json.loads((tmp_path / "v61_linux_handoff_manifest.json").read_text(encoding="utf-8"))
    assert manifest["linux_backend_validation_required"] is True
    assert "Copy linux_handoff/" in manifest["next_action"]
