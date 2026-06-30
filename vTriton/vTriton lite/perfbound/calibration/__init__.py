# M1 — Calibration Database
#
# Sustained-rate hardware constants for Ascend 910B3, measured via CCE
# micro-benchmarks.  Every constant carries provenance (value, ci, source,
# n_runs) — no datasheet peaks enter I_c.
#
# Key files:
#   constants.py    — dataclasses: CalibrationConstant, CoreConfig, CubeConfig, ...
#   calib_loader.py — load/validate versioned calib_910b3_vX.json
#   microbench/     — CCE micro-benchmark kernels (Cube, Vector, MTE, handoff)
