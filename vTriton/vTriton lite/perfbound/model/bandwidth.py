# M4 — Sustained Bandwidth Lookup (ported from tilesim arc_spec.py)
#
# Reimplements lookup_bw(src, dst, core_num) with linear interpolation
# over core_num.  Drops the L2-reuse / cache-hit logic (redundancy=1 default).
#
# Port source: tilesim core/config/arc_spec.py ArcConfig.lookup_bw()
#              tilesim core/backend/engineering_costmodel/core/aicore_costmodel.py
#
# Source spec: .omc/specs/performance_bound_model.md §4

from __future__ import annotations

from typing import Optional

from ..calibration.constants import MemHierarchy, MemLoc


def lookup_bw(
    memory: MemHierarchy,
    src: str,
    dst: str,
    core_num: int = -1,
    pkt_size: int = -1,
) -> float:
    """Look up sustained bandwidth in B/us for a memory transfer path.

    Thin wrapper around MemHierarchy.lookup_bw() that follows the
    tilesim ArcConfig.lookup_bw() API.

    Args:
        memory: Memory hierarchy with sustained bandwidth table.
        src: Source memory space (gm, l1, ub, l0a, l0b, l0c).
        dst: Destination memory space.
        core_num: Number of cores active (-1 = core-independent).
        pkt_size: Transfer size in bytes (-1 = size-independent).

    Returns:
        Sustained bandwidth in bytes per microsecond (single core).

    Raises:
        KeyError: If no bandwidth entry exists for the path.
    """
    return memory.lookup_bw(src, dst, core_num, pkt_size)[0]


def get_effective_bw(
    memory: MemHierarchy,
    src: str,
    dst: str,
    core_num: int = -1,
    pkt_size: int = -1,
    alignment_bytes: Optional[int] = None,
) -> float:
    """Get effective bandwidth accounting for alignment waste.

    Args:
        memory: Memory hierarchy.
        src, dst: Transfer path.
        core_num: Active core count.
        pkt_size: Transfer size in bytes.
        alignment_bytes: If set, waste from misalignment is
                         (alignment_bytes - 1) worst-case per transfer.

    Returns:
        Effective sustained bandwidth in B/us.
    """
    bw, _ = memory.lookup_bw(src, dst, core_num, pkt_size)

    if alignment_bytes and alignment_bytes > 1:
        # Conservative: assume worst-case (alignment_bytes-1) waste per transfer
        waste_factor = (pkt_size + alignment_bytes - 1) / pkt_size if pkt_size > 0 else 1.0
        bw /= waste_factor

    return bw
