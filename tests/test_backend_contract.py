# -*- coding: utf-8 -*-
import json
from pathlib import Path

from strategy_search.backend_contract import build_backend_contract, build_backend_contract_reports
from strategy_search.hivm_official_rewrite_plan import build_hivm_inventory
from strategy_search.rewrite_readiness import build_rewrite_readiness_bundle

ROOT = Path(__file__).resolve().parents[1]


def _inputs():
    ir = (ROOT / "sample_input" / "fa_best.hivm.mlir").read_text(encoding="utf-8")
    selected = json.loads((ROOT / "artifacts" / "latest_smoke_run" / "selected_plan.json").read_text(encoding="utf-8"))
    inventory = build_hivm_inventory(ir, "fa_best.hivm.mlir")
    readiness = build_rewrite_readiness_bundle(selected, inventory)
    return selected, inventory, readiness


def test_backend_contract_contains_action_work_orders():
    selected, inventory, readiness = _inputs()
    contract = build_backend_contract(selected, inventory, readiness)
    assert contract["schema_version"] == "hivm_four_plan_backend_contract_v1"
    assert contract["backend_cli_contract"]["required_modes"]
    assert contract["actions"]
    plans = {a["plan"] for a in contract["actions"]}
    assert {"SyncPlan", "MultiBufferPlan", "CVPipelinePlan", "TilingPlan"}.issubset(plans)
    for action in contract["actions"]:
        assert action["action_id"]
        assert action["mutation_kind"]
        assert action["backend_requirements"]
        assert action["acceptance"]


def test_first_backend_milestone_is_sync_and_multibuffer_only():
    selected, inventory, readiness = _inputs()
    contract = build_backend_contract(selected, inventory, readiness)
    ids = set(contract["first_backend_milestone"]["actions"])
    assert ids
    action_by_id = {a["action_id"]: a for a in contract["actions"]}
    assert all(action_by_id[i]["plan"] in {"SyncPlan", "MultiBufferPlan"} for i in ids)
    assert any(action_by_id[i]["plan"] == "MultiBufferPlan" for i in ids)


def test_build_backend_contract_reports_writes_expected_files(tmp_path):
    paths = build_backend_contract_reports(
        ROOT / "sample_input" / "fa_best.hivm.mlir",
        ROOT / "artifacts" / "latest_smoke_run" / "selected_plan.json",
        tmp_path,
    )
    assert set(paths) == {"inventory", "rewrite_plan", "readiness", "contract", "sync_multibuffer_contract"}
    contract = json.loads(paths["contract"].read_text(encoding="utf-8"))
    subset = json.loads(paths["sync_multibuffer_contract"].read_text(encoding="utf-8"))
    assert len(subset["actions"]) <= len(contract["actions"])
    assert all(a["plan"] in {"SyncPlan", "MultiBufferPlan"} for a in subset["actions"])
