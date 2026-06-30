# -*- coding: utf-8 -*-
from pathlib import Path


def test_v44_backend_declares_guarded_sync_mutation_prototype():
    text = Path("vtriton_hivm_operation_backend/hivm_operation_backend.cpp").read_text(encoding="utf-8")
    assert "hivm_operation_backend_capabilities_v4_4" in text
    assert "mutate_sync_event_insertion" in text
    assert "completed_guarded_sync_mutation_prototype" in text
    assert "mutateSingleSyncBarrierAction" in text
    assert "editor.addSetFlagWaitFlagBefore" in text
    assert "editor.deleteOp(target)" in text


def test_v44_sync_mutation_is_single_action_guarded():
    text = Path("vtriton_hivm_operation_backend/hivm_operation_backend.cpp").read_text(encoding="utf-8")
    assert "blocked_requires_exactly_one_sync_action" in text
    assert "barrier_to_directional_event_pair" in text
    assert "blocked_target_not_found_or_ambiguous" in text
    assert "production_rewrite_claim_allowed" in text


def test_v44_windows_and_shell_scripts_exist():
    assert Path("scripts/run_v44_real_sync_mutation.cmd").exists()
    assert Path("scripts/run_v44_real_sync_mutation.sh").exists()
    cmd = Path("scripts/run_v44_real_sync_mutation.cmd").read_text(encoding="utf-8")
    sh = Path("scripts/run_v44_real_sync_mutation.sh").read_text(encoding="utf-8")
    assert "HIVM_ALLOW_SYNC_MUTATION" in cmd
    assert "HIVM_ALLOW_SYNC_MUTATION" in sh
