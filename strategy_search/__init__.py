# -*- coding: utf-8 -*-
"""HIVM strategy search package.

Public APIs are grouped into lightweight facade modules:
- ``strategy_search.plans``: plan/config dataclasses.
- ``strategy_search.parser``: MLIR/HIVM feature extraction.
- ``strategy_search.hardware``: hardware capacity and footprint utilities.
- ``strategy_search.cost_model``: risk-aware analytical cost model.
- ``strategy_search.search``: candidate-space generation and beam search.
- ``strategy_search.report``: JSON/Markdown/HTML report writers.
- ``strategy_search.rewrite``: annotation/sidecar rewrite emitters.
- ``strategy_search.hivm_parser``: real MLIR/HIVM parser with round-trip fidelity.
- ``strategy_search.hivm_ops_editor``: HivmOpsEditor CRUD API (Python-native).
- ``strategy_search.hivm_backend``: unified backend bridge (auto-detect C++/Python).

The extraction is staged: dataclasses/constants, report writers, and rewrite
emitters are now physically owned by their modules; parser/search/cost/hardware
facades still re-export core implementations until they are safely migrated.
"""
from .plans import StrategyConfig, KernelFeatures, TilingPlan, MultiBufferPlan, CVPipelinePlan, SyncPlan, FourPlanBundle
from .cost_model import estimate_cost
from .parser import parse_kernel_features

# Phase-3A: Real MLIR/HIVM parser + HivmOpsEditor integration
# These are always available (pure Python, no C++ build dependency)
from .hivm_parser import (
    MLIRModule, MLIRFunction, MLIRRegion, MLIRBlock, MLIROperation,
    SSAValue, MLIRAttribute,
    parse_hivm_file, parse_hivm_text, serialize_module, write_module,
    MLIRParseError, MLIRParser, MLIRSerializer, MLIRTokenizer,
)
from .hivm_ops_editor import (
    HivmOpsEditor, HivmOpInfo,
    AddressSpace, PipeAttr, EventAttr,
    HIVM_DMA_OPS, HIVM_VECTOR_UNARY_OPS, HIVM_VECTOR_BINARY_OPS,
    HIVM_VECTOR_SPECIAL_OPS, HIVM_MACRO_OPS, HIVM_SYNC_OPS, HIVM_ALL_OPS,
    load_editor, create_editor_from_text,
)
from .hivm_backend import (
    HivmBackend, BackendKind, BackendCapabilities,
    get_backend, reset_backend, force_python_backend,
)
