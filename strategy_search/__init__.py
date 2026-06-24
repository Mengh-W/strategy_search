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

The extraction is staged: dataclasses/constants, report writers, and rewrite
emitters are now physically owned by their modules; parser/search/cost/hardware
facades still re-export core implementations until they are safely migrated.
"""
from .plans import StrategyConfig, KernelFeatures, TilingPlan, MultiBufferPlan, CVPipelinePlan, SyncPlan, FourPlanBundle
from .cost_model import estimate_cost
from .parser import parse_kernel_features
