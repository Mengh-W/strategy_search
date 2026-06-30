# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from strategy_search.backend_contract_runner import execute_backend_contract


def test_backend_contract_runner_with_fake_backend(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    # Build a minimal contract with action anchors.  This validates the execution
    # harness without requiring a real vTriton/HivmOpsEditor binary.
    contract = {
        "schema_version": "test_contract",
        "actions": [
            {
                "action_id": "sync_001_test",
                "plan": "SyncPlan",
                "mutation_kind": "validate_existing_set_wait_events",
                "load_line": 1,
            }
        ],
    }
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = execute_backend_contract(
        repo_root / "tools" / "fake_hivm_operation_backend.py",
        repo_root / "sample_input" / "fa_best.hivm.mlir",
        contract_path,
        tmp_path / "backend_out",
        run_mutate=False,
        mutation_kind="contract_smoke",
    )

    assert summary["all_required_commands_ok"] is True
    assert summary["is_real_mlir_backend"] is False
    assert summary["production_rewrite_claim_allowed"] is False
    assert (tmp_path / "backend_out" / "backend_capabilities.json").exists()
    assert (tmp_path / "backend_out" / "backend_inventory.json").exists()
    assert (tmp_path / "backend_out" / "backend_dry_run_contract.json").exists()
    dry = json.loads((tmp_path / "backend_out" / "backend_dry_run_contract.json").read_text(encoding="utf-8"))
    assert dry["action_count"] == 1
    assert dry["production_mutation"] is False
