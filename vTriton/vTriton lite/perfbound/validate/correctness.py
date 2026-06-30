# M6 — Correctness Verification for Counterfactual Validation
#
# Compares edited kernel output against a reference output using numerical
# tolerance (numpy.allclose). A counterfactual whose edit corrupts output
# is invalid regardless of timing — this guards against "optimizations"
# that merely skip work.
#
# Source spec: .omc/plans/a6_2_counterfactual.md §2

from __future__ import annotations

from typing import Callable


def verify_output(
    kernel_output,
    reference_fn: Callable | None,
    *args,
    rtol: float = 1e-3,
    atol: float = 1e-5,
) -> bool:
    """Verify edited kernel output matches reference within tolerance.

    Uses numpy.allclose for numerical comparison. Returns False (not raises)
    on any error: shape mismatch, reference_fn failure, missing numpy, etc.

    Args:
        kernel_output: Array-like output from the edited kernel.
        reference_fn: Callable that returns the reference output when invoked
                      with *args. If None, verification is skipped (True).
        *args: Arguments passed to reference_fn.
        rtol: Relative tolerance (default: 1e-3).
        atol: Absolute tolerance (default: 1e-5).

    Returns:
        True if outputs match within tolerance, False otherwise.
    """
    if reference_fn is None:
        return True

    try:
        import numpy as np
    except ImportError:
        return False

    # Compute reference
    try:
        reference = reference_fn(*args)
    except Exception:
        return False

    if reference is None:
        return False

    try:
        arr_out = np.asarray(kernel_output)
        arr_ref = np.asarray(reference)
    except Exception:
        return False

    # Shape mismatch
    if arr_out.shape != arr_ref.shape:
        return False

    try:
        return bool(np.allclose(arr_out, arr_ref, rtol=rtol, atol=atol))
    except Exception:
        return False
