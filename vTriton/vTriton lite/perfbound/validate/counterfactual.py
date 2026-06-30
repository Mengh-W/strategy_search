# M6 — Counterfactual Validation
#
# Hand-edit HIVM (raise repeat, insert ping-pong), recompile via bishengir,
# verify correctness (output equivalence with reference), measure delta
# via msprof.
#
# Confirms a gap's quantified value matches measured improvement
# (validates attribution, separate from validating the bound).
#
# Source spec: .omc/specs/performance_bound_model.md §A.6

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .correctness import verify_output
from .hivm_edits import HivmEdit
from .msprof_parser import parse_kernel_time_us


@dataclass
class CounterfactualResult:
    """Result of a single counterfactual experiment."""
    kernel_name: str
    gap_name: str               # e.g. "gap3_avoidable_serial"

    # Predicted
    predicted_gap_us: float

    # Measured (before → after counterfactual edit)
    t_before_us: float
    t_after_us: float
    measured_delta_us: float

    # Validity
    output_verified: bool       # did edited kernel produce same output?

    notes: str = ""

    @property
    def quantification_error(self) -> float:
        """Relative error of predicted gap vs measured delta."""
        if self.measured_delta_us == 0:
            return float("inf")
        return abs(self.predicted_gap_us - self.measured_delta_us) / self.measured_delta_us

    @property
    def is_valid(self) -> bool:
        """A valid counterfactual: output verified + error < 20% (Exp 3 target)."""
        return self.output_verified and self.quantification_error < 0.20

    def __repr__(self) -> str:
        return (f"Counterfactual({self.kernel_name}/{self.gap_name}: "
                f"predicted={self.predicted_gap_us:.2f}, "
                f"measured={self.measured_delta_us:.2f}, "
                f"error={self.quantification_error:.3f}, "
                f"verified={self.output_verified})")


def run_counterfactual(
    kernel_name: str,
    gap_name: str,
    predicted_gap_us: float,
    hivm_edit: HivmEdit,
    hivm_path: Path | None = None,
    baseline_csv: Path | None = None,
    profiler_op_name: str | None = None,
    remote_host: str | None = None,
    remote_bench_script: str | None = None,
    reference_fn: Callable | None = None,
    reference_args: tuple = (),
    rtol: float = 1e-3,
    atol: float = 1e-5,
    *,
    # Injection points for testing (mock overrides)
    _profile_fn=None,
    _compile_and_profile_fn=None,
    _edit_fn=None,
    _verify_fn=None,
) -> CounterfactualResult:
    """Run a counterfactual experiment by editing HIVM and re-profiling.

    Orchestration:
    1. Parse baseline timing from baseline_csv (t_before_us)
    2. Apply HivmEdit to produce edited HIVM
    3. Compile + profile the edited HIVM (t_after_us)
    4. Verify output correctness if reference_fn is provided
    5. Compute measured_delta = t_before - t_after
    6. Return CounterfactualResult

    Infra failures (compile crash, profiler error) surface as a non-valid
    result with notes — never a spurious small delta.

    Args:
        kernel_name: Kernel to test.
        gap_name: Attribution gap being tested.
        predicted_gap_us: The gap value predicted by the model.
        hivm_edit: HivmEdit with apply() that produces edited HIVM.
        hivm_path: Path to the original HIVM DES-graph JSON that the edit is
            applied to (required for the production edit path; ignored when
            _edit_fn is injected).
        baseline_csv: Path to baseline msprof CSV for t_before.
        profiler_op_name: Op name filter for msprof parsing.
        remote_host: Remote 910B3 SSH host (None for local).
        remote_bench_script: Path to scripts/remote_bench.py.
        reference_fn: Callable returning reference output for correctness check.
        reference_args: Arguments to pass to reference_fn.
        rtol: Relative tolerance for correctness check.
        atol: Absolute tolerance for correctness check.
        _profile_fn: Override for baseline profiling (testing).
        _compile_and_profile_fn: Override for edit-then-profile (testing).
        _edit_fn: Override for HIVM editing (testing).
        _verify_fn: Override for output verification (testing).

    Returns:
        CounterfactualResult with pre/post timing and verification status.
    """
    # Resolve functions (use injection points for testing, defaults for production)
    profile_baseline = _profile_fn or _default_profile_baseline
    compile_and_profile = _compile_and_profile_fn or _default_compile_and_profile
    # Bind hivm_path into the default edit applier so the call site stays
    # single-arg (apply_edit(hivm_edit)) — compatible with injected
    # _edit_fn mocks of the form ``lambda edit: ...``.
    if _edit_fn is not None:
        apply_edit = _edit_fn
    else:
        apply_edit = lambda edit: _default_apply_edit(edit, hivm_path)
    do_verify = _verify_fn or verify_output

    # Step 1: Measure baseline timing
    try:
        t_before_us = profile_baseline(
            baseline_csv=baseline_csv,
            profiler_op_name=profiler_op_name,
            remote_host=remote_host,
            remote_bench_script=remote_bench_script,
            kernel_name=kernel_name,
        )
    except Exception as e:
        return CounterfactualResult(
            kernel_name=kernel_name,
            gap_name=gap_name,
            predicted_gap_us=predicted_gap_us,
            t_before_us=0.0,
            t_after_us=0.0,
            measured_delta_us=0.0,
            output_verified=False,
            notes=f"baseline profiling failed: {e}",
        )

    # Step 2: Apply HIVM edit
    try:
        edited_hivm_path = apply_edit(hivm_edit)
    except Exception as e:
        return CounterfactualResult(
            kernel_name=kernel_name,
            gap_name=gap_name,
            predicted_gap_us=predicted_gap_us,
            t_before_us=t_before_us,
            t_after_us=0.0,
            measured_delta_us=0.0,
            output_verified=False,
            notes=f"HIVM edit failed: {e}",
        )

    # Step 3: Compile + profile edited HIVM
    try:
        t_after_us, kernel_output = compile_and_profile(
            edited_hivm_path=edited_hivm_path,
            remote_host=remote_host,
            remote_bench_script=remote_bench_script,
            kernel_name=kernel_name,
            profiler_op_name=profiler_op_name,
        )
    except Exception as e:
        return CounterfactualResult(
            kernel_name=kernel_name,
            gap_name=gap_name,
            predicted_gap_us=predicted_gap_us,
            t_before_us=t_before_us,
            t_after_us=0.0,
            measured_delta_us=0.0,
            output_verified=False,
            notes=f"compile/profile failed: {e}",
        )

    # Step 4: Verify output correctness
    output_verified = do_verify(
        kernel_output,
        reference_fn,
        *reference_args,
        rtol=rtol,
        atol=atol,
    )

    if not output_verified:
        measured_delta = t_before_us - t_after_us
        return CounterfactualResult(
            kernel_name=kernel_name,
            gap_name=gap_name,
            predicted_gap_us=predicted_gap_us,
            t_before_us=t_before_us,
            t_after_us=t_after_us,
            measured_delta_us=measured_delta,
            output_verified=False,
            notes="output verification failed: edited kernel output differs from reference",
        )

    # Step 5: Compute delta
    measured_delta = t_before_us - t_after_us

    return CounterfactualResult(
        kernel_name=kernel_name,
        gap_name=gap_name,
        predicted_gap_us=predicted_gap_us,
        t_before_us=t_before_us,
        t_after_us=t_after_us,
        measured_delta_us=measured_delta,
        output_verified=True,
        notes="",
    )


# ── Default implementations (production path) ──────────────────────────

def _default_profile_baseline(
    baseline_csv: Path | None,
    profiler_op_name: str | None,
    remote_host: str | None,
    remote_bench_script: str | None,
    kernel_name: str,
) -> float:
    """Parse baseline timing from CSV (or run remote profile)."""
    if baseline_csv is not None and Path(baseline_csv).exists():
        timing = parse_kernel_time_us(
            baseline_csv, op_name_filter=profiler_op_name
        )
        return timing.t_us

    # Remote path: call remote_bench.py to profile on 910B3
    if remote_host and remote_bench_script:
        import subprocess
        import tempfile
        from ..validate.msprof_parser import parse_kernel_time_us as _parse

        tmp_csv = Path(tempfile.mktemp(suffix=".csv"))
        # Import run_remote_bench dynamically to avoid circular imports
        import importlib
        rb = importlib.import_module("scripts.remote_bench")
        csv_path, _ = rb.run_remote_bench(
            remote_host=remote_host,
            kernel_name=kernel_name,
            output_csv=tmp_csv,
        )
        timing = _parse(csv_path, op_name_filter=profiler_op_name)
        return timing.t_us

    raise ValueError(
        "No baseline timing source: provide baseline_csv or "
        "(remote_host + remote_bench_script)"
    )


def _default_compile_and_profile(
    edited_hivm_path: Path,
    remote_host: str | None,
    remote_bench_script: str | None,
    kernel_name: str,
    profiler_op_name: str | None,
) -> tuple[float, object]:
    """Compile edited HIVM and profile the result.

    Returns (t_after_us, kernel_output).
    kernel_output is np.ndarray if output .npy was fetched, else None.
    """
    if remote_host and remote_bench_script:
        import tempfile
        from ..validate.msprof_parser import parse_kernel_time_us as _parse

        tmp_csv = Path(tempfile.mktemp(suffix=".csv"))
        tmp_npy = Path(tempfile.mktemp(suffix=".npy"))

        import importlib
        rb = importlib.import_module("scripts.remote_bench")
        csv_path, npy_path = rb.run_remote_bench(
            remote_host=remote_host,
            kernel_name=kernel_name,
            hivm_in=Path(edited_hivm_path),
            output_csv=tmp_csv,
            output_npy=tmp_npy,
        )
        timing = _parse(csv_path, op_name_filter=profiler_op_name)

        # Load kernel output if available
        kernel_output = None
        if npy_path and npy_path.exists():
            try:
                import numpy as np
                kernel_output = np.load(npy_path)
            except ImportError:
                pass

        return timing.t_us, kernel_output

    raise ValueError(
        "No compilation target: provide remote_host + remote_bench_script, "
        "or use injection points for testing."
    )


def _default_apply_edit(hivm_edit: HivmEdit, hivm_path: Path | None) -> Path:
    """Apply ``hivm_edit.apply`` to the original HIVM and return the edited path.

    ``HivmEdit.apply`` is ``Callable[[Path], Path]`` — it takes the original
    HIVM DES-graph path and returns a new temp path with the edit applied
    (the edit functions in ``hivm_edits`` are typically bound via
    ``partial``/lambda so only the input path remains free). The original
    HIVM path therefore MUST be supplied; there is no meaningful default.
    """
    if hivm_path is None:
        raise ValueError(
            "hivm_path is required to apply a HIVM edit in the production path "
            "(pass hivm_path=... to run_counterfactual, or inject _edit_fn)."
        )
    return hivm_edit.apply(Path(hivm_path))
