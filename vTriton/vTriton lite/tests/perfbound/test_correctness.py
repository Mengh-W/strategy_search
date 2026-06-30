# Tests for correctness verification (A.6.2)
#
# verify_output must pass on matching arrays, fail on mismatch,
# handle edge cases gracefully (return False, not raise).

import numpy as np
import pytest

from perfbound.validate.correctness import verify_output


class TestVerifyOutput:
    """verify_output checks numerical equivalence via numpy.allclose."""

    def test_matching_arrays_pass(self):
        out = np.array([1.0, 2.0, 3.0])
        ref_fn = lambda: np.array([1.0, 2.0, 3.0])
        assert verify_output(out, ref_fn) is True

    def test_mismatching_arrays_fail(self):
        out = np.array([1.0, 2.0, 3.0])
        ref_fn = lambda: np.array([1.0, 2.0, 99.0])
        assert verify_output(out, ref_fn) is False

    def test_tolerance_honored(self):
        out = np.array([1.0, 2.0])
        ref_fn = lambda: np.array([1.001, 2.002])
        # Default rtol=1e-3: 0.002/2.0 = 0.001, so 2.002 should pass
        assert verify_output(out, ref_fn, rtol=1e-3, atol=1e-5) is True

        # Tighter tolerance should fail
        assert verify_output(out, ref_fn, rtol=1e-6, atol=1e-9) is False

    def test_shape_mismatch_returns_false(self):
        out = np.array([1.0, 2.0, 3.0])
        ref_fn = lambda: np.array([1.0, 2.0])
        assert verify_output(out, ref_fn) is False

    def test_reference_fn_error_returns_false(self):
        out = np.array([1.0, 2.0])
        ref_fn = lambda: (_ for _ in ()).throw(ValueError("boom"))
        assert verify_output(out, ref_fn) is False

    def test_reference_fn_returns_none(self):
        out = np.array([1.0, 2.0])
        ref_fn = lambda: None
        assert verify_output(out, ref_fn) is False

    def test_none_reference_fn_skips_check(self):
        """When reference_fn is None, verification passes (no check needed)."""
        out = np.array([1.0, 2.0])
        assert verify_output(out, None) is True

    def test_atol_tolerance(self):
        out = np.array([0.0, 0.0])
        ref_fn = lambda: np.array([1e-6, 1e-6])
        # atol=1e-5 should pass
        assert verify_output(out, ref_fn, rtol=1e-3, atol=1e-5) is True
        # atol=1e-9 should fail
        assert verify_output(out, ref_fn, rtol=1e-3, atol=1e-9) is False

    def test_2d_arrays(self):
        out = np.ones((3, 4))
        ref_fn = lambda: np.ones((3, 4))
        assert verify_output(out, ref_fn) is True

    def test_reference_fn_with_args(self):
        out = np.array([3.0, 5.0])
        def make_ref(a, b):
            return np.array([a, b])
        assert verify_output(out, make_ref, 3.0, 5.0) is True
        assert verify_output(out, make_ref, 1.0, 2.0) is False
