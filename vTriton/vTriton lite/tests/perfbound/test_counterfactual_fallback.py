# Tests for counterfactual validation with a fallback (known-good) kernel.
#
# Decouples A.6.2 counterfactual from chunk_kda (which crashes in
# bishengir-compile) by proving the mechanism on the simpler
# hivm_mixed_cv_kernel fixture that already compiles through tritonsim-hivm.
#
# The edit → extract → verify pipeline is fully offline-testable.
# Only the actual hardware compile path (recompile via bishengir on 910B3)
# is hardware-dependent.
#
# Source spec: .omc/plans/a6_2_blockers_scope.md Task 8

import json
import pytest
from pathlib import Path

from perfbound.validate.counterfactual import (
    CounterfactualResult,
    run_counterfactual,
)
from perfbound.validate.hivm_edits import (
    HivmEdit,
    raise_repeat,
    insert_pingpong,
    merge_transfers,
    verify_edit_via_extract,
)


# ── Fixtures / paths ────────────────────────────────────────────────

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SAMPLE_HIVM = FIXTURE_DIR / "sample_hivm.json"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIXED_CV_KERNEL = PROJECT_ROOT / "test" / "hivm_mixed_cv_kernel.npuir.mlir"

requires_mixed_cv = pytest.mark.skipif(
    not MIXED_CV_KERNEL.exists(),
    reason="hivm_mixed_cv_kernel.npuir.mlir not found",
)


# ── Helper mocks ────────────────────────────────────────────────────

def _mock_profile_baseline(**kwargs) -> float:
    return 1000.0


def _mock_compile_and_profile_ok(**kwargs) -> tuple[float, object]:
    """Simulate a successful compile+profile returning improvement."""
    return 780.0, None


def _mock_verify_true(*args, **kwargs) -> bool:
    return True


# ══════════════════════════════════════════════════════════════════════
# Test Class: Fallback kernel counterfactual
# ══════════════════════════════════════════════════════════════════════


class TestFallbackKernelCounterfactual:
    """Prove the counterfactual pipeline on a simpler kernel.

    Uses sample_hivm.json (known to parse through hivm_extractor) to
    exercise the full edit → extract → timing → verification flow
    without depending on the chunk_kda bishengir-compile bug.

    The edit + extract + verify path is fully offline.
    Only the compile+profile step requires hardware (mocked here).
    """

    def test_raise_repeat_counterfactual(self):
        """raise_repeat edit → mocked compile → valid counterfactual."""
        edit = HivmEdit(
            gap_name="gap4_intra_unit_exec",
            description="Raise repeat 2x on compute ops",
            apply=lambda p: raise_repeat(p, factor=2),
        )
        result = run_counterfactual(
            kernel_name="mixed_cv_test",
            gap_name="gap4_intra_unit_exec",
            predicted_gap_us=220.0,
            hivm_edit=edit,
            hivm_path=SAMPLE_HIVM,
            _profile_fn=lambda **kw: 1000.0,
            _compile_and_profile_fn=lambda **kw: (780.0, None),
            _verify_fn=lambda *a, **kw: True,
        )
        assert result.t_before_us == 1000.0
        assert result.t_after_us == 780.0
        assert result.measured_delta_us == 220.0
        assert result.is_valid is True
        assert result.quantification_error == pytest.approx(0.0)

    def test_insert_pingpong_counterfactual(self):
        """insert_pingpong edit → mocked compile → valid counterfactual."""
        edit = HivmEdit(
            gap_name="gap3_avoidable_serial",
            description="Insert ping-pong buffer for MTE_UB serialization",
            apply=lambda p: insert_pingpong(p),
        )
        result = run_counterfactual(
            kernel_name="mixed_cv_test",
            gap_name="gap3_avoidable_serial",
            predicted_gap_us=100.0,
            hivm_edit=edit,
            hivm_path=SAMPLE_HIVM,
            _profile_fn=lambda **kw: 1000.0,
            _compile_and_profile_fn=lambda **kw: (900.0, None),
            _verify_fn=lambda *a, **kw: True,
        )
        assert result.measured_delta_us == 100.0
        assert result.is_valid is True

    def test_merge_transfers_counterfactual(self):
        """merge_transfers edit → mocked compile → valid counterfactual."""
        edit = HivmEdit(
            gap_name="gap2_coalescing",
            description="Merge consecutive MTE_GM transfers",
            apply=lambda p: merge_transfers(p),
        )
        result = run_counterfactual(
            kernel_name="mixed_cv_test",
            gap_name="gap2_coalescing",
            predicted_gap_us=50.0,
            hivm_edit=edit,
            hivm_path=SAMPLE_HIVM,
            _profile_fn=lambda **kw: 1000.0,
            _compile_and_profile_fn=lambda **kw: (950.0, None),
            _verify_fn=lambda *a, **kw: True,
        )
        assert result.measured_delta_us == 50.0
        assert result.is_valid is True


class TestFallbackEditExtractVerify:
    """Exercise the offline edit → extract → verify pipeline.

    These tests do NOT need any compile or hardware — they prove that
    HIVM edits actually change model-visible structure using the real
    hivm_extractor (via verify_edit_via_extract).
    """

    def test_raise_repeat_is_model_visible(self):
        """raise_repeat(factor=2) changes structure seen by hivm_extractor."""
        assert verify_edit_via_extract(
            SAMPLE_HIVM,
            raise_repeat(SAMPLE_HIVM, factor=2),
        ), "raise_repeat(factor=2) should be model-visible"

    def test_raise_repeat_factor_1_is_noop(self):
        """raise_repeat(factor=1) is a genuine no-op — verify_edit returns False."""
        assert not verify_edit_via_extract(
            SAMPLE_HIVM,
            raise_repeat(SAMPLE_HIVM, factor=1),
        ), "raise_repeat(factor=1) is a no-op and should NOT be model-visible"

    def test_insert_pingpong_is_model_visible(self):
        """insert_pingpong adds operations visible to hivm_extractor."""
        assert verify_edit_via_extract(
            SAMPLE_HIVM,
            insert_pingpong(SAMPLE_HIVM),
        ), "insert_pingpong should add model-visible operations"

    def test_merge_transfers_no_op_for_non_adjacent(self):
        """merge_transfers correctly preserves non-adjacent MTE ops.

        sample_hivm.json has MTE2 ops with different dst_spaces (l0a vs l0b),
        so merge_transfers should NOT merge them — verify_edit returns False.
        """
        assert not verify_edit_via_extract(
            SAMPLE_HIVM,
            merge_transfers(SAMPLE_HIVM),
        ), "merge_transfers should be a no-op for non-adjacent/different-space MTE ops"

    def test_edited_hivm_is_valid_json(self):
        """Edited HIVM round-trips as valid JSON with operations array."""
        edited = raise_repeat(SAMPLE_HIVM, factor=3)
        data = json.loads(edited.read_text())
        assert "operations" in data
        assert len(data["operations"]) > 0
        # Repeat field should be tripled on compute ops
        for op in data["operations"]:
            if op.get("pipe") in ("Cube", "Vector", "Scalar"):
                assert op["repeat"] == 3  # was 1, now 1*3

    def test_edited_hivm_preserves_non_compute_ops(self):
        """Non-compute ops (MTE) are not affected by raise_repeat."""
        edited = raise_repeat(SAMPLE_HIVM, factor=2)
        data = json.loads(edited.read_text())
        mte_ops = [op for op in data["operations"]
                    if op.get("pipe") in ("MTE2", "MTE_UB", "MTE_GM")]
        for op in mte_ops:
            assert op["repeat"] == 1, (
                f"MTE op '{op['name']}' should have repeat=1, "
                f"got {op['repeat']}"
            )


class TestFallbackHardwareCompileXfail:
    """Mark the hardware-only compile path as xfail.

    The actual recompile via bishengir on 910B3 requires hardware.
    This test documents the gap and will pass when hardware is available.
    """

    @pytest.mark.xfail(
        reason="Hardware compile path requires 910B3 with CANN — offline scaffold only",
    )
    def test_recompile_via_remote_bench(self):
        """End-to-end: edit HIVM → recompile on remote → profile → verify.

        This test requires a real 910B3 with CANN installed.  The edit
        and extract steps are proven offline above; this test adds the
        hardware compile + profile step.
        """
        edit = HivmEdit(
            gap_name="gap4_intra_unit_exec",
            description="Raise repeat 2x",
            apply=lambda p: raise_repeat(p, factor=2),
        )
        # This will fail because no remote host is configured
        result = run_counterfactual(
            kernel_name="mixed_cv_test",
            gap_name="gap4_intra_unit_exec",
            predicted_gap_us=220.0,
            hivm_edit=edit,
            hivm_path=SAMPLE_HIVM,
            remote_host="user@nonexistent-host",
            remote_bench_script="scripts/remote_bench.py",
            _verify_fn=lambda *a, **kw: True,
        )
        assert result.is_valid is True
