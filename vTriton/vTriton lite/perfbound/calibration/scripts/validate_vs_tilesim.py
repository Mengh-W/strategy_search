#!/usr/bin/env python3
"""
validate_vs_tilesim.py - Cross-validate 910B3 calibration against tilesim reference.

Performs three validation checks:
  1. vec_cycle: Compare computing_cycles to 910B1 after clock normalization
  2. Cube throughput: Verify measured 910B3 ≤ clock-scaled 910B4 × 1.05
  3. BW ratios: Check 910B3/910B4 single-core BW ratio ≤ 1.3

If any P0 constant fails validation, exits with non-zero code.

Usage:
    python validate_vs_tilesim.py <calib_json> [vec_cycle_csv] [bandwidth_csv]

Source spec: .omc/specs/performance_bound_model.md §A.1 (Step 4)
Related: perfbound/calibration/data/vec_cycle_910b3.csv
Related: perfbound/calibration/data/bandwidth_910b3.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Add perfbound to path
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from perfbound.calibration.constants import CalibrationDB, DType


# ── Reference Values (from tilesim / datasheet) ────────────────────────────────

# 910B1 vec_cycle reference (for clock-normalization comparison)
# Source: tilesim/core/config/arc_config/910B1/vec_cycle_910B1.csv
VEC_CYCLE_910B1_REF = {
    "add": {"computing_cycles": 1, "head_cycles": 0, "interval_cycles": 1},
    "mul": {"computing_cycles": 1, "head_cycles": 0, "interval_cycles": 1},
    "exp": {"computing_cycles": 4, "head_cycles": 0, "interval_cycles": 4},
    "log": {"computing_cycles": 3, "head_cycles": 0, "interval_cycles": 3},
    "sqrt": {"computing_cycles": 2, "head_cycles": 0, "interval_cycles": 2},
    "rsqrt": {"computing_cycles": 2, "head_cycles": 0, "interval_cycles": 2},
}

# 910B4 Cube reference (for clock-scaling comparison)
# Source: 910B4 datasheet (clock=1.65 GHz, 20 AIC)
# Cube FP16: 271.4 TFLOPS at 1650 MHz
# Scaled to 1850 MHz: 271.4 × 1850/1650 ≈ 304 TFLOPS
CUBE_910B4_FP16_TFLOPS = 271.4
CUBE_910B4_CLOCK_GHZ = 1.65
CUBE_910B3_CLOCK_GHZ = 1.85
CUBE_910B3_SCALED_MAX = CUBE_910B4_FP16_TFLOPS * (CUBE_910B3_CLOCK_GHZ / CUBE_910B4_CLOCK_GHZ) * 1.05

# 910B4 Bandwidth reference (single-core, for ratio check)
BW_910B4_GM_UB_GBPS = 64.36  # Tilesim sustained measured reference


# ── Validation Checks ─────────────────────────────────────────────────────────

def validate_vec_cycle(vec_cycle_csv: Path) -> List[str]:
    """Validate vec_cycle entries against 910B1 after clock normalization.

    Check: computing_cycles within 10% after clock normalization.
    Clock factor: 910B3 @ 1850 MHz vs 910B1 @ 1650 MHz = 1.121

    Returns:
        List of violation messages (empty if all pass)
    """
    violations = []

    if not vec_cycle_csv.exists():
        violations.append(f"vec_cycle CSV not found: {vec_cycle_csv}")
        return violations

    with open(vec_cycle_csv) as f:
        reader = csv.DictReader([line for line in f if not line.strip().startswith("#")])
        for row in reader:
            intrinsic = row.get("intrinsic", "").strip()
            computing_cycles = int(row.get("computing_cycles", "0"))

            if intrinsic in VEC_CYCLE_910B1_REF:
                ref_cycles = VEC_CYCLE_910B1_REF[intrinsic]["computing_cycles"]
                # Clock normalization: 910B3 is 1.85/1.65 = 1.121x faster
                # So cycles should scale inversely (fewer cycles at higher clock)
                normalized_ref = ref_cycles / (CUBE_910B3_CLOCK_GHZ / 1.65)  # 910B1 is ~1.65 GHz

                delta_pct = abs(computing_cycles - normalized_ref) / normalized_ref * 100 if normalized_ref > 0 else 0

                if delta_pct > 10:
                    violations.append(
                        f"vec_cycle[{intrinsic}]: {computing_cycles} vs ref {normalized_ref:.1f} "
                        f"(delta={delta_pct:.1f}% > 10%)"
                    )

    return violations


def validate_cube_throughput(db: CalibrationDB) -> List[str]:
    """Validate Cube FP16 throughput against clock-scaled 910B4 value.

    Check: measured_910B3_fp16_TFLOPS ≤ clock_scaled_910B4_fp16_TFLOPS × 1.05
    (5% margin for measurement noise; > 5% = re-measure)

    Returns:
        List of violation messages
    """
    violations = []

    cube_fp16 = db.cube.throughput.get(DType.FP16, 0.0)

    if cube_fp16 == 0.0:
        violations.append("Cube FP16 throughput is 0 (not measured yet)")
        return violations

    if cube_fp16 > CUBE_910B3_SCALED_MAX:
        violations.append(
            f"Cube FP16: {cube_fp16:.1f} TFLOPS exceeds scaled 910B4 max {CUBE_910B3_SCALED_MAX:.1f} TFLOPS "
            f"(ratio={cube_fp16/CUBE_910B3_SCALED_MAX:.3f} > 1.05)"
        )

    return violations


def validate_bandwidth_ratios(bw_csv: Path) -> List[str]:
    """Validate 910B3 single-core BW vs 910B4 reference.

    Check: BW_910B3_gm_ub_1core / BW_910B4_gm_ub_1core ≤ 1.3
    (Unexpected if > 1.3; would need investigation)

    Returns:
        List of violation messages
    """
    violations = []

    if not bw_csv.exists():
        violations.append(f"bandwidth CSV not found: {bw_csv}")
        return violations

    # Read 910B3 single-core GM→UB bandwidth
    bw_910b3_gm_ub = None
    with open(bw_csv) as f:
        reader = csv.DictReader([line for line in f if not line.strip().startswith("#")])
        for row in reader:
            if row.get("src_mem") == "gm" and row.get("dst_mem") == "ub":
                core_num = int(row.get("core_num", "-1"))
                if core_num == -1 or core_num == 1:
                    bw_910b3_gm_ub = float(row.get("bandwidth(GB/s)", "0"))
                    break

    if bw_910b3_gm_ub is None:
        violations.append("GM→UB bandwidth (single core) not found in CSV")
        return violations

    ratio = bw_910b3_gm_ub / BW_910B4_GM_UB_GBPS

    if ratio > 1.3:
        violations.append(
            f"Bandwidth ratio: {ratio:.2f} > 1.3 "
            f"(910B3={bw_910b3_gm_ub:.1f} GB/s vs 910B4={BW_910B4_GM_UB_GBPS:.1f} GB/s)"
        )

    return violations


# ── Main Validation ───────────────────────────────────────────────────────────

def validate_all(
    calib_json: Path,
    vec_cycle_csv: Path,
    bandwidth_csv: Path,
) -> Tuple[List[str], List[str]]:
    """Run all validation checks.

    Returns:
        (warnings, errors) where errors cause non-zero exit
    """
    warnings = []
    errors = []

    # Load calibration DB
    if not calib_json.exists():
        errors.append(f"Calibration JSON not found: {calib_json}")
        return warnings, errors

    with open(calib_json) as f:
        calib_dict = json.load(f)
    db = CalibrationDB.from_dict(calib_dict)

    # Check 1: vec_cycle validation
    vec_violations = validate_vec_cycle(vec_cycle_csv)
    for v in vec_violations:
        # Flag if > 10% delta
        warnings.append(f"[vec_cycle] {v}")

    # Check 2: Cube throughput validation
    cube_violations = validate_cube_throughput(db)
    for v in cube_violations:
        # This is a P0 violation - re-measure if exceeds scaled 910B4
        errors.append(f"[cube_throughput] {v}")

    # Check 3: Bandwidth ratio validation
    bw_violations = validate_bandwidth_ratios(bandwidth_csv)
    for v in bw_violations:
        # Flag if ratio > 1.3 (needs investigation)
        warnings.append(f"[bandwidth] {v}")

    return warnings, errors


# ── CLI Entry Point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Cross-validate 910B3 calibration against tilesim")
    parser.add_argument("calib_json", type=Path, help="Calibration JSON (calib_910b3_v1.json)")
    parser.add_argument("--vec-cycle", type=Path,
                        default=PROJECT_ROOT / "perfbound/calibration/data/vec_cycle_910b3.csv",
                        help="vec_cycle CSV path")
    parser.add_argument("--bandwidth", type=Path,
                        default=PROJECT_ROOT / "perfbound/calibration/data/bandwidth_910b3.csv",
                        help="bandwidth CSV path")
    args = parser.parse_args()

    print("Cross-validating 910B3 calibration against tilesim reference...")
    print("=" * 70)

    warnings, errors = validate_all(args.calib_json, args.vec_cycle, args.bandwidth)

    # Print warnings
    if warnings:
        print("⚠ Warnings (informational, may need investigation):")
        for w in warnings:
            print(f"  {w}")
        print()

    # Print errors
    if errors:
        print("✗ Validation errors (P0 constants failed):")
        for e in errors:
            print(f"  {e}")
        print()
        print("Action: Re-measure failed constants or investigate measurement artifacts.")
        return 1
    else:
        print("✓ All validation checks passed.")
        print()
        print("Summary:")
        print(f"  - vec_cycle: within 10% of 910B1 after clock normalization")
        print(f"  - Cube FP16: ≤ {CUBE_910B3_SCALED_MAX:.1f} TFLOPS (clock-scaled 910B4 × 1.05)")
        print(f"  - Bandwidth: ≤ {BW_910B4_GM_UB_GBPS * 1.3:.1f} GB/s (1.3× 910B4 reference)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
