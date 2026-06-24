# -*- coding: utf-8 -*-
"""MLIR/HIVM text parsing and evidence extraction facade."""
from .core import (
    count_hivm_ops,
    extract_source_meta,
    extract_mlir_evidence,
    extract_des_evidence,
    extract_trace_evidence,
    build_artifact_profile,
    get_artifact,
    write_artifact_audits,
    parse_kernel_features,
    infer_current_ir_strategy,
    build_current_ir_estimate,
)
