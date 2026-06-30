"""
M3 — Semantic Extractor.

Provides two Gap 1 analysis paths:

1. **From HIVMExtract directly** (primary path): analyzes each HIVM op's
   name/pipe to determine what it *could* have run on, then compares against
   what HIVM *actually* assigned.  This works without TTIR semantic pass
   correlation because the HIVM op name encodes the original operation.

2. **From TTIR semantic records** (future path): when a dedicated semantic
   pass emits per-op metadata with stable IDs, analyze_gap1() will correlate
   those records against realized HIVM assignment.

The eligibility oracle compares what an op *could* run on (semantic eligibility)
against what HIVM *actually* assigned it to (realized unit_assignment).
Gap 1 is the diff between these two sets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional

from .op_classifier import Component
from .eligibility_oracle import compute_gap1, get_eligibility


# HIVM token → semantic category mapping.
# Op names are split on underscore/hyphen boundaries into tokens,
# then each token is checked against this ordered list.
# Order matters: multi-token compounds ("reduce_sum") are checked
# via _COMPOUND_CATEGORIES before single-token lookup.
_TOKEN_CATEGORIES: Dict[str, str] = {
    "matmul": "matmul",
    "mmad": "matmul",
    "reduce": "reduction",
    "cmp": "compare",
    "compare": "compare",
    "cast": "cast",
    "add": "elementwise",
    "sub": "elementwise",
    "mul": "elementwise",
    "div": "elementwise",
    "exp": "elementwise",
    "log": "elementwise",
    "sqrt": "elementwise",
    "rsqrt": "elementwise",
    "tanh": "elementwise",
    "sigmoid": "elementwise",
    "gelu": "elementwise",
    "relu": "elementwise",
}

# Multi-token compounds that map to a different category than their
# individual tokens (e.g., "reduce_sum" → reduction, not elementwise).
_COMPOUND_CATEGORIES: Dict[str, str] = {
    "reduce_sum": "reduction",
    "reduce_max": "reduction",
    "reduce_min": "reduction",
    "reduce_prod": "reduction",
}


# ── Data structures ───────────────────────────────────────────────────────


@dataclass
class SemanticOpRecord:
    """A TTIR/Linalg op with its semantic classification."""
    op_id: int
    op_name: str
    op_category: str        # "matmul", "elementwise", "reduction", "compare", "cast"
    precision: Optional[str]  # "fp16", "bf16", "fp32", "int8", "int32"
    elements: int = 0
    source_location: str = ""


@dataclass
class Gap1Report:
    """Result of Gap 1 analysis for one op."""
    op_id: int
    op_category: str
    precision: Optional[str]
    eligible_components: FrozenSet[Component]
    realized_component: Component
    is_gap1: bool


# ── Category mapping from TTIR/Linalg op names ───────────────────────────


_TTIR_OP_CATEGORIES: Dict[str, str] = {
    # matmul family
    "tt.dot": "matmul",
    "tt.matmul": "matmul",
    "linalg.matmul": "matmul",
    "linalg.batch_matmul": "matmul",
    "linalg.matvec": "matmul",

    # elementwise
    "tt.addptr": "elementwise",
    "arith.addf": "elementwise",
    "arith.addi": "elementwise",
    "arith.mulf": "elementwise",
    "arith.muli": "elementwise",
    "arith.divf": "elementwise",
    "arith.subf": "elementwise",
    "math.exp": "elementwise",
    "math.log": "elementwise",
    "math.sqrt": "elementwise",
    "math.rsqrt": "elementwise",
    "math.tanh": "elementwise",
    "math.fpowi": "elementwise",

    # reduction
    "tt.reduce": "reduction",

    # compare
    "arith.cmpf": "compare",
    "arith.cmpi": "compare",

    # cast
    "arith.extf": "cast",
    "arith.truncf": "cast",
    "arith.sitofp": "cast",
    "arith.fptosi": "cast",
}


def classify_ttir_op(op_name: str) -> str:
    """Map a TTIR/Linalg op name to its semantic category.

    Returns "unknown" for unmapped ops (conservative).
    """
    cat = _TTIR_OP_CATEGORIES.get(op_name)
    if cat:
        return cat
    for prefix, category in _TTIR_OP_CATEGORIES.items():
        if op_name.startswith(prefix):
            return category
    return "unknown"


def _classify_hivm_op(op_name: str) -> str:
    """Map an HIVM op name to its semantic category.

    Splits the op name on underscore/hyphen boundaries into tokens and
    checks multi-token compounds first (e.g., "reduce_sum"), then
    individual tokens.  This avoids substring collisions without regex
    (e.g., "mmadL1" won't match "mul" because tokens are ["mmadl1"]).

    Returns "unknown" for unmapped ops (conservative).
    """
    op_lower = op_name.lower()

    # Check compound matches first (e.g., "reduce_sum" as a unit)
    for compound, category in _COMPOUND_CATEGORIES.items():
        if compound in op_lower:
            return category

    # Split into tokens on common delimiters and check each
    tokens = op_lower.replace("-", "_").split("_")
    for token in tokens:
        cat = _TOKEN_CATEGORIES.get(token)
        if cat:
            return cat
    return "unknown"


def extract_semantic_records(ttir_info: Dict) -> List[SemanticOpRecord]:
    """Convert TTIR info dict (from mlir_parser.parse_ttir) to semantic records.

    NOTE: This path produces records with op_id=0 which do not correlate to
    HIVM op IDs.  Use analyze_gap1_from_extract() for the primary path that
    works directly on HIVMExtract.

    Args:
        ttir_info: Dict from parse_ttir() with structural TTIR info.

    Returns:
        List of SemanticOpRecord with inferred categories.
    """
    records = []
    if ttir_info.get("has_dot", False):
        records.append(SemanticOpRecord(
            op_id=0,
            op_name="tt.dot",
            op_category="matmul",
            precision="fp16",
            elements=0,
        ))
    return records


def analyze_gap1(
    semantic_records: List[SemanticOpRecord],
    realized_assignment: Dict[int, str],
) -> List[Gap1Report]:
    """Compare semantic eligibility against realized HIVM assignment.

    Args:
        semantic_records: Per-op semantic classification.
        realized_assignment: HIVMExtract.unit_assignment {op_id: component_name}.

    Returns:
        List of Gap1Report, one per op with semantic data.
    """
    reports = []
    for rec in semantic_records:
        realized_name = realized_assignment.get(rec.op_id)
        if realized_name is None:
            continue
        realized_comp = Component(realized_name)
        eligible = get_eligibility(rec.op_category, rec.precision)
        is_gap = compute_gap1(
            rec.op_id, rec.op_category, rec.precision, realized_comp,
        )
        reports.append(Gap1Report(
            op_id=rec.op_id,
            op_category=rec.op_category,
            precision=rec.precision,
            eligible_components=eligible,
            realized_component=realized_comp,
            is_gap1=is_gap,
        ))
    return reports


def analyze_gap1_from_extract(extract) -> List[Gap1Report]:
    """Primary Gap 1 analysis path: works directly on HIVMExtract.

    Derives semantic category from each HIVM op's name, then compares
    eligibility against the realized unit assignment.  This avoids the need
    for TTIR-to-HIVM ID correlation by inferring semantics from the HIVM
    op name itself.

    Args:
        extract: HIVMExtract with operations and unit_assignment populated.

    Returns:
        List of Gap1Report for ops where a semantic category could be inferred.
    """
    reports = []
    for op in extract.operations:
        category = _classify_hivm_op(op.op_name)
        if category == "unknown":
            continue  # cannot determine eligibility without a category

        precision = op.precision.value if op.precision else None
        eligible = get_eligibility(category, precision)
        realized_comp = op.component
        is_gap = compute_gap1(
            op.op_id, category, precision, realized_comp,
        )
        reports.append(Gap1Report(
            op_id=op.op_id,
            op_category=category,
            precision=precision,
            eligible_components=eligible,
            realized_component=realized_comp,
            is_gap1=is_gap,
        ))
    return reports
