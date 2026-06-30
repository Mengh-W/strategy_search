# Tests for validation harness (A.6.1)
#
# Validates validate_from_csv(), ValidationStatus tri-state, soundness rate
# computation excluding EXECUTION_ERROR rows.
#
# Source spec: .omc/plans/a6_validation_harness.md §7

import pytest
import tempfile
from pathlib import Path

from perfbound.validate.harness import (
    ValidationCase,
    ValidationResult,
    ValidationStatus,
    ValidationSuite,
    validate_from_csv,
)
from perfbound.combine.bound_combiner import BoundResult, BindingTier, Attribution
from perfbound.extract.op_classifier import Component


FIXTURE_DIR = Path(__file__).parent / "fixtures"
SAMPLE_CSV = FIXTURE_DIR / "op_summary_sample.csv"


def _make_bound_result(
    t_bound_us: float = 1000.0,
    binding_component: Component = Component.CUBE,
) -> BoundResult:
    return BoundResult(
        kernel_name="test_kernel",
        t_bound_us=t_bound_us,
        t_grid_floor_us=800.0,
        t_core_floor_us=900.0,
        t_serial_irreducible_us=100.0,
        binding_tier=BindingTier.COMPONENT,
        binding_component=binding_component,
        attribution=Attribution(),
    )


def test_validate_from_csv_pass():
    """T_measured > T_bound → PASS."""
    # Sample CSV has target_kernel with durations 1000/1050/5000 → median=1050
    br = _make_bound_result(t_bound_us=500.0)  # bound < measured
    case = ValidationCase(
        kernel_name="test_kernel",
        profiler_op_name="target_kernel",
        bound_result=br,
        csv_path=SAMPLE_CSV,
        n_warmup=0,
    )
    result = validate_from_csv(case)
    assert result.status == ValidationStatus.PASS
    assert result.t_measured_us == 1050.0
    assert result.tightness == pytest.approx(1050.0 / 500.0)


def test_validate_from_csv_violation():
    """T_measured < T_bound → BOUND_VIOLATION."""
    br = _make_bound_result(t_bound_us=2000.0)  # bound > measured (1050)
    case = ValidationCase(
        kernel_name="test_kernel",
        profiler_op_name="target_kernel",
        bound_result=br,
        csv_path=SAMPLE_CSV,
        n_warmup=0,
    )
    result = validate_from_csv(case)
    assert result.status == ValidationStatus.BOUND_VIOLATION
    assert result.t_measured_us == 1050.0


def test_validate_from_csv_missing_csv():
    """Missing path → EXECUTION_ERROR."""
    br = _make_bound_result()
    case = ValidationCase(
        kernel_name="test_kernel",
        profiler_op_name="target_kernel",
        bound_result=br,
        csv_path=Path("/nonexistent/path.csv"),
    )
    result = validate_from_csv(case)
    assert result.status == ValidationStatus.EXECUTION_ERROR
    assert "missing" in result.notes.lower() or "not found" in result.notes.lower()


def test_validate_from_csv_empty_csv():
    """Empty CSV → EXECUTION_ERROR."""
    csv_content = "Op Name,Task Type,Task Start Time(us),Task Duration(us)\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(csv_content)
        csv_path = Path(f.name)

    try:
        br = _make_bound_result()
        case = ValidationCase(
            kernel_name="test_kernel",
            profiler_op_name="target_kernel",
            bound_result=br,
            csv_path=csv_path,
        )
        result = validate_from_csv(case)
        assert result.status == ValidationStatus.EXECUTION_ERROR
    finally:
        csv_path.unlink()


def test_zero_bound_raises_in_validate():
    """ValidationCase.bound_result.t_bound_us=0 → EXECUTION_ERROR (not ZeroDivisionError)."""
    br = _make_bound_result(t_bound_us=0.0)
    case = ValidationCase(
        kernel_name="test_kernel",
        profiler_op_name="target_kernel",
        bound_result=br,
        csv_path=SAMPLE_CSV,
    )
    result = validate_from_csv(case)
    assert result.status == ValidationStatus.EXECUTION_ERROR
    assert "invalid bound" in result.notes.lower() or "<= 0" in result.notes


def test_soundness_rate_excludes_errors():
    """1 PASS + 1 EXECUTION_ERROR → rate=1.0 (denom=1)."""
    suite = ValidationSuite()
    suite.results.append(ValidationResult(
        kernel_name="pass_kernel",
        t_bound_us=1000.0,
        t_measured_us=1200.0,
        status=ValidationStatus.PASS,
        tightness=1.2,
    ))
    suite.results.append(ValidationResult(
        kernel_name="error_kernel",
        t_bound_us=1000.0,
        t_measured_us=0.0,
        status=ValidationStatus.EXECUTION_ERROR,
    ))
    # Only PASS counts in denominator
    assert suite.soundness_rate == 1.0


def test_soundness_rate_with_violation():
    """1 PASS + 1 VIOLATION → rate=0.5."""
    suite = ValidationSuite()
    suite.results.append(ValidationResult(
        kernel_name="pass_kernel",
        t_bound_us=1000.0,
        t_measured_us=1200.0,
        status=ValidationStatus.PASS,
        tightness=1.2,
    ))
    suite.results.append(ValidationResult(
        kernel_name="violation_kernel",
        t_bound_us=2000.0,
        t_measured_us=1500.0,
        status=ValidationStatus.BOUND_VIOLATION,
        tightness=0.75,
    ))
    assert suite.soundness_rate == 0.5
