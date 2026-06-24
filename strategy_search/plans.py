# -*- coding: utf-8 -*-
"""Core data structures and constants for the HIVM strategy search pipeline.

This module is intentionally dependency-light so parser/search/cost/report modules
can share the same public types without importing the whole CLI implementation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

DTYPE_BYTES = {
    "i1": 1, "i8": 1, "ui8": 1,
    "i16": 2, "f16": 2, "fp16": 2, "bf16": 2,
    "i32": 4, "f32": 4, "fp32": 4,
    "i64": 8, "f64": 8,
}

SPACE_ALIAS = {"cbuf": "l1", "cc": "l0c", "hbm": "gm"}
LOCAL_SPACES = {"ub", "l1", "l0a", "l0b", "l0c"}
RESOURCE_SCOPES = ["ub", "l1", "l0a", "l0b", "l0c", "gm_ws"]


# ---------------------------------------------------------------------------
# 数据结构定义
# ---------------------------------------------------------------------------
# StrategyConfig 是搜索器内部最核心的“候选策略”表示。
# 一个 StrategyConfig 就是一组完整的四 Plan 参数组合：
#   - TilingPlan：切分尺寸、block 并行度、循环顺序和尾块策略。
#   - MultiBufferPlan：双缓冲、逐 buffer 倍数和 stage buffer 策略。
#   - CVPipelinePlan：C/V 流水 stage、模板和混合 C/V 策略。
#   - SyncPlan：同步策略、同步模板、event 复用和同步粒度。
# cost model 和报告生成阶段都围绕 StrategyConfig 展开。
@dataclass(frozen=True)
class StrategyConfig:
    strategy_id: str
    fusion: str                  # 非核心维度：当前固定为 keep_existing
    tile_m: int                  # TilingPlan 搜索旋钮
    tile_n: int                  # TilingPlan 搜索旋钮
    tile_k: int                  # TilingPlan 搜索旋钮
    block_dim: int               # 根据 tile 数和 core 数派生，不作为无限制独立变量
    double_buffer: bool          # MultiBufferPlan 高层搜索旋钮
    cv_pipeline_stage: int       # CVPipelinePlan 高层搜索旋钮
    cv_split_ratio: str          # 当前固定为 1:1，预留给后续更细 CVPipelinePlan
    memory_reuse_level: str      # 当前固定/派生，不作为主要搜索维度
    sync_policy: str             # SyncPlan 高层搜索旋钮
    dma_policy: str              # 当前固定为 keep_existing，不搜索真实 DMA 改写
    # 下列字段是实际参与搜索和打分的 Plan 级旋钮，而不只是报告字段。
    loop_order: str = "outer_mnk"
    tail_strategy: str = "mask_or_pad"
    multibuffer_template: str = "auto"
    cv_pipeline_template: str = "auto"
    sync_template: str = "auto"
    enable_mixed_cv: bool = False
    tile_mix_cube_loop: int = 1
    tile_mix_vector_loop: int = 1
    auto_cv_balance: bool = True
    barrier_level: str = "medium"
    event_reuse: bool = False
    sync_granularity: str = "op"
    # 更接近 HIVM 的四类 Plan 扩展旋钮：reduce、layout、stage buffer、逐 buffer 倍数和同步移动。
    reduce_tile_policy: str = "full_k"
    layout_aware_tile: bool = True
    ub_multiplier: int = 1
    l1_multiplier: int = 1
    stage_buffer_policy: str = "none"
    buffer_multipliers_json: str = "{}"  # MultiBufferPlan：逐 buffer 的 nbuf_b∈{1,2}
    producer_consumer_distance: int = 1
    event_id_policy: str = "keep"
    sync_motion: str = "none"
    model_version: str = "V3.3-artifact-kernel-profile"


# BufferInfo 记录从 MLIR 中解析出的局部 buffer。
# gen/kill 是保守估计的首次使用和最后使用位置，用于估算静态最大存活容量。
@dataclass
class BufferInfo:
    name: str
    space: str
    size_bytes: int
    gen: int
    kill: int


# KernelFeatures 是 parse_kernel_features() 的输出，
# 它把原始 MLIR 文本压缩成后续搜索和 cost model 需要的结构化证据。
@dataclass
class KernelFeatures:
    op_counts: Dict[str, int]
    vector_op_counts: Dict[str, int]
    num_functions: int
    has_aic: bool
    has_aiv: bool
    num_pipe_barrier: int
    num_set_flag: int
    num_wait_flag: int
    num_sync_block_set: int
    num_sync_block_wait: int
    num_nd2nz: int
    num_mmad: int
    num_fixpipe: int
    num_load: int
    num_store: int
    base_local_footprint_bytes: Dict[str, int]
    static_max_live_bytes: Dict[str, int]
    buffers: List[BufferInfo]
    inferred_problem_shape: Dict[str, int]


@dataclass
class Layer1Case:
    fusion: str
    tile_m: int
    tile_n: int
    tile_k: int
    block_dim: int
    single_footprint: Dict[str, int]
    coarse_cost: float
    align_notes: List[str]
    loop_order: str = "outer_mnk"
    tail_strategy: str = "mask_or_pad"
    reduce_tile_policy: str = "full_k"
    layout_aware_tile: bool = True


@dataclass
class TilingPlan:
    source: str
    controllable_knobs: Dict[str, Any]
    derived_features: Dict[str, Any]
    legality: Dict[str, Any]


@dataclass
class MultiBufferPlan:
    source: str
    controllable_knobs: Dict[str, Any]
    derived_features: Dict[str, Any]
    legality: Dict[str, Any]


@dataclass
class CVPipelinePlan:
    source: str
    controllable_knobs: Dict[str, Any]
    derived_features: Dict[str, Any]
    legality: Dict[str, Any]


@dataclass
class SyncPlan:
    source: str
    controllable_knobs: Dict[str, Any]
    derived_features: Dict[str, Any]
    legality: Dict[str, Any]


@dataclass
class FourPlanBundle:
    model_version: str
    fixed_parameters: Dict[str, Any]
    tiling_plan: TilingPlan
    multibuffer_plan: MultiBufferPlan
    cv_pipeline_plan: CVPipelinePlan
    sync_plan: SyncPlan


@dataclass
class DesGraphProfile:
    source_files: List[str]
    num_operations: int
    pipe_duration: Dict[str, float]
    pipe_bytes: Dict[str, float]
    pipe_flops: Dict[str, float]
    sync_ops: int
    barrier_ops: int
    dependency_edges: int
    top_ops_by_duration: List[Dict[str, Any]]
    schema_fields: List[str]


@dataclass
class ArtifactProfile:
    source_files: List[str]
    source_meta: Dict[str, Any]
    mlir_evidence: Dict[str, Any]
    des_evidence: Dict[str, Any]
    trace_evidence: Dict[str, Any]
    schema_coverage: Dict[str, Any]



@dataclass
class DiagnosisHints:
    enabled: bool
    mode: str
    source_files: List[str]
    signals: List[Dict[str, Any]]
    variable_bias: Dict[str, float]
    value_bias: Dict[str, float]
    coverage: List[Dict[str, Any]]
    unknown_signals: List[Dict[str, Any]]
    des_profile: Optional[Dict[str, Any]] = None
    bound_reports: Optional[List[Dict[str, Any]]] = None
    counterfactual_reports: Optional[List[Dict[str, Any]]] = None
    multi_kernel_reports: Optional[List[Dict[str, Any]]] = None




def strategy_signature(cfg: StrategyConfig) -> Tuple[Any, ...]:
    """Return a stable strategy identity that ignores volatile candidate ids.

    The signature is used for candidate-space merge/dedup and regression tests.
    It intentionally includes all four Plan knobs that can affect legality or cost,
    but excludes ``strategy_id`` because ids are assigned after enumeration.
    """
    return (
        cfg.fusion,
        int(cfg.tile_m), int(cfg.tile_n), int(cfg.tile_k), int(cfg.block_dim),
        bool(cfg.double_buffer), int(cfg.cv_pipeline_stage), str(cfg.cv_split_ratio),
        str(cfg.memory_reuse_level), str(cfg.sync_policy), str(cfg.dma_policy),
        str(cfg.loop_order), str(cfg.tail_strategy), str(cfg.multibuffer_template),
        str(cfg.cv_pipeline_template), str(cfg.sync_template), bool(cfg.enable_mixed_cv),
        int(cfg.tile_mix_cube_loop), int(cfg.tile_mix_vector_loop), bool(cfg.auto_cv_balance),
        str(cfg.barrier_level), bool(cfg.event_reuse), str(cfg.sync_granularity),
        str(cfg.reduce_tile_policy), bool(cfg.layout_aware_tile),
        int(cfg.ub_multiplier), int(cfg.l1_multiplier), str(cfg.stage_buffer_policy),
        str(cfg.buffer_multipliers_json), int(cfg.producer_consumer_distance),
        str(cfg.event_id_policy), str(cfg.sync_motion),
    )


def layer1_signature(case: Layer1Case) -> Tuple[Any, ...]:
    """Stable identity for Layer-1 candidates before inner-plan expansion."""
    return (
        case.fusion, int(case.tile_m), int(case.tile_n), int(case.tile_k), int(case.block_dim),
        str(case.loop_order), str(case.tail_strategy), str(case.reduce_tile_policy), bool(case.layout_aware_tile),
    )


def tile_signature_from_dict(tile: Dict[str, Any]) -> Tuple[int, int, int]:
    """Stable identity for tile dictionaries in the auto-generated search space."""
    return (int(tile.get("m", 0)), int(tile.get("n", 0)), int(tile.get("k", 0)))
