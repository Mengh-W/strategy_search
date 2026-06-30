# M6 — Validation Harness (NOT part of the model)
#
# The only place compilation + execution happen.  Drives the
# remote-bench-910b3 skill for:
#   1. Soundness check:  T_bound ≤ T_measured  (binary, must hold 100%)
#   2. Tightness record: T_measured / T_bound   (median < 1.20 on optimized)
#   3. Counterfactual:   hand-edit HIVM, recompile, verify delta
#
# The model (M1–M5) never calls this module.
