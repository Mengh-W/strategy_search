# -*- coding: utf-8 -*-
"""Hardware capacity, footprint, and feasibility utilities."""
from .core import (
    memory_cap_bytes,
    space_alignment,
    bandwidth_bytes_per_cycle,
    cube_flops_per_cycle,
    vector_elems_per_cycle,
    cube_tile,
    satisfies_align_tile,
    tile_buffers,
    workspace_model_config,
    estimate_workspace_bytes,
    workspace_transfer_time,
    estimate_max_live,
    gm_workspace_fallback_legality,
    feasibility,
    relax_candidate,
    feasible_with_relax,
)
