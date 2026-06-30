# -*- coding: utf-8 -*-
from pathlib import Path


def test_v42_backend_cpp_has_sync_action_parser_and_locator():
    text = Path("vtriton_hivm_operation_backend/hivm_operation_backend.cpp").read_text(encoding="utf-8")
    assert "parseEditScriptActionsBestEffort" in text
    assert "locateSyncActionJson" in text
    assert "event_id_or_contract_line_against_HivmOpsEditor_listOps" in text
    assert "hivm_operation_backend_dryrun_v3" in text
    assert "real_backend_sync_dryrun_per_action_locator_not_implemented_yet" not in text


def test_v42_backend_capabilities_declare_locator_not_mutation():
    text = Path("vtriton_hivm_operation_backend/hivm_operation_backend.cpp").read_text(encoding="utf-8")
    assert "sync_per_action_locator_dry_run" in text
    assert "sync_event_liveness_proof_available" in text
    assert "sync_deadlock_proof_available" in text
    assert "mutate_sync_event_insertion" in text
    assert "false" in text


def test_v42_scripts_and_doc_exist():
    assert Path("scripts/run_v42_sync_fake_backend_dryrun.cmd").exists()
    assert Path("scripts/run_v42_sync_real_backend_dryrun.cmd").exists()
    doc = Path("docs/archive/rewrite_history/19_v42_sync_real_backend_locator_CN.md")
    assert doc.exists()
    assert "Real-backend Locator" in doc.read_text(encoding="utf-8")
