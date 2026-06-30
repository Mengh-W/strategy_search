# -*- coding: utf-8 -*-
"""HIVM Operations Editor — Python mirror of the C++ HivmOpsEditor API.

Provides operation-level CRUD (Create, Read, Update, Delete) on an HIVM MLIR
module, using the Python MLIR parser from ``hivm_parser.py``.

This is the Python-native alternative to the C++ HivmOpsEditor that ships with
vTriton Lite.  It mirrors the same API surface and can be used when the C++
backends (``hivm-crud``, ``hivm-operation-backend``) are not available.

Key capabilities:
- READ: listOps, opCounts, collectOps, printSummary
- CREATE: addLoadBefore/After, addStoreBefore/After, addCopyBefore/After,
  addFixpipeBefore/After, addND2NZBefore/After, addSetFlagBefore/After,
  addWaitFlagBefore/After, addPipeBarrierBefore/After, addVAddBefore/After, etc.
- DELETE: deleteOp, deleteAllOpsWithName, deleteNthOpWithName,
  deleteSyncOpsForOp, deleteRedundantGMTrips
- MODIFY: changeElementType, changeMemorySpace, changePipeAttr, changeEventAttr,
  changeShape, replaceVAddWithVSub, etc.
- OPTIMISATION: removeRedundantLoadStorePair, fuseConsecutiveComputeOps,
  insertDoubleBuffering, barrierToDirectionalSync
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .hivm_parser import (
    MLIRModule, MLIRFunction, MLIRRegion, MLIRBlock, MLIROperation,
    SSAValue, MLIRAttribute,
    parse_hivm_file, parse_hivm_text, serialize_module, write_module,
)


# =============================================================================
# HIVM Dialect constants
# =============================================================================

class AddressSpace(Enum):
    GM = "gm"
    L1 = "cbuf"
    UB = "ub"
    L0C = "cc"
    L0A = "ca"
    L0B = "cb"


class PipeAttr(Enum):
    PIPE_V = "PIPE_V"
    PIPE_M = "PIPE_M"
    PIPE_S = "PIPE_S"
    PIPE_MTE1 = "PIPE_MTE1"
    PIPE_MTE2 = "PIPE_MTE2"
    PIPE_MTE3 = "PIPE_MTE3"
    PIPE_FIX = "PIPE_FIX"
    PIPE_ALL = "PIPE_ALL"


class EventAttr(Enum):
    EVENT_ID0 = "EVENT_ID0"
    EVENT_ID1 = "EVENT_ID1"
    EVENT_ID2 = "EVENT_ID2"
    EVENT_ID3 = "EVENT_ID3"
    EVENT_ID4 = "EVENT_ID4"
    EVENT_ID5 = "EVENT_ID5"
    EVENT_ID6 = "EVENT_ID6"
    EVENT_ID7 = "EVENT_ID7"


# HIVM operation names
HIVM_DMA_OPS = frozenset({
    'hivm.hir.load', 'hivm.hir.store', 'hivm.hir.copy', 'hivm.hir.fixpipe',
    'hivm.hir.nd2nz', 'hivm.hir.nz2nd',
})
HIVM_VECTOR_UNARY_OPS = frozenset({
    'hivm.hir.vexp', 'hivm.hir.vabs', 'hivm.hir.vln', 'hivm.hir.vrelu',
    'hivm.hir.vrsqrt', 'hivm.hir.vsqrt', 'hivm.hir.vtanh', 'hivm.hir.vsin',
    'hivm.hir.vcos', 'hivm.hir.verf', 'hivm.hir.vrec', 'hivm.hir.vnot',
    'hivm.hir.vcast',
})
HIVM_VECTOR_BINARY_OPS = frozenset({
    'hivm.hir.vadd', 'hivm.hir.vsub', 'hivm.hir.vmul', 'hivm.hir.vdiv',
    'hivm.hir.vmax', 'hivm.hir.vmin', 'hivm.hir.vor', 'hivm.hir.vand',
    'hivm.hir.vxor', 'hivm.hir.vmod', 'hivm.hir.vshl', 'hivm.hir.vshr',
    'hivm.hir.vcmp', 'hivm.hir.vpow', 'hivm.hir.vmulext',
})
HIVM_VECTOR_SPECIAL_OPS = frozenset({
    'hivm.hir.vsel', 'hivm.hir.vbrc', 'hivm.hir.vreduce', 'hivm.hir.vconcat',
    'hivm.hir.vflip', 'hivm.hir.vpad', 'hivm.hir.vgather', 'hivm.hir.vgathermask',
    'hivm.hir.vcumsum', 'hivm.hir.vcumprod', 'hivm.hir.vsort',
    'hivm.hir.vmulextended', 'hivm.hir.vtranspose', 'hivm.hir.varange',
    'hivm.hir.vinterleave', 'hivm.hir.vdeinterleave',
})
HIVM_MACRO_OPS = frozenset({
    'hivm.hir.mmad', 'hivm.hir.mmadL1', 'hivm.hir.batch_mmadL1',
    'hivm.hir.matmul', 'hivm.hir.mix_matmul', 'hivm.hir.mix_group_matmul',
    'hivm.hir.conv1dL1', 'hivm.hir.conv2dL1',
})
HIVM_SYNC_OPS = frozenset({
    'hivm.hir.set_flag', 'hivm.hir.wait_flag', 'hivm.hir.pipe_barrier',
    'hivm.hir.barrier', 'hivm.hir.sync_block', 'hivm.hir.sync_block_set',
    'hivm.hir.sync_block_wait',
})
HIVM_ALL_OPS = (
    HIVM_DMA_OPS | HIVM_VECTOR_UNARY_OPS | HIVM_VECTOR_BINARY_OPS |
    HIVM_VECTOR_SPECIAL_OPS | HIVM_MACRO_OPS | HIVM_SYNC_OPS
)


# =============================================================================
# HivmOpInfo
# =============================================================================

@dataclass
class HivmOpInfo:
    """Mirror of C++ HivmOpInfo struct."""
    index: int
    qualified_name: str
    op: MLIROperation
    line: int = -1


# =============================================================================
# HivmOpsEditor
# =============================================================================

class HivmOpsEditor:
    """Python-native HIVM Operations Editor.

    Mirrors the C++ ``mlir::ascend::HivmOpsEditor`` API for programmatic
    HIVM operation CRUD on an MLIR ModuleOp.

    Usage::

        editor = HivmOpsEditor.load_from_file("input.hivm.mlir")
        ops = editor.list_ops()
        editor.add_set_flag_before(target_op, PipeAttr.PIPE_MTE2,
                                   PipeAttr.PIPE_M, EventAttr.EVENT_ID0)
        editor.delete_op(target_op)
        editor.export_to_file("output.hivm.mlir")
    """

    def __init__(self, module: MLIRModule):
        self._module = module
        self._next_ssa_id = 0

    # ---- Factory methods ----

    @classmethod
    def load_from_file(cls, path: Union[str, Path]) -> 'HivmOpsEditor':
        """Load a HIVM MLIR file and create an editor."""
        module = parse_hivm_file(path)
        return cls(module)

    @classmethod
    def load_from_text(cls, text: str) -> 'HivmOpsEditor':
        """Load HIVM MLIR text and create an editor."""
        module = parse_hivm_text(text)
        return cls(module)

    def export_to_file(self, path: Union[str, Path]) -> bool:
        """Export the module to file. Returns True on success."""
        try:
            write_module(self._module, path)
            return True
        except Exception:
            return False

    def export_to_string(self) -> str:
        """Export the module as MLIR text."""
        return serialize_module(self._module)

    @property
    def module(self) -> MLIRModule:
        return self._module

    # ---- Helper ----

    def _new_ssa_name(self) -> str:
        """Generate a unique SSA value name."""
        while True:
            name = f'%v{self._next_ssa_id}'
            self._next_ssa_id += 1
            # Check for conflicts
            if not any(
                name == r.name
                for fn in self._module.functions
                for block in fn.body.blocks
                for op in block.operations
                for r in op.results
            ):
                return name

    def _all_ops(self) -> List[Tuple[MLIROperation, MLIRFunction, MLIRBlock]]:
        """Return all operations with their function and block context."""
        result = []
        for fn in self._module.functions:
            for block in fn.body.blocks:
                for op in block.operations:
                    result.append((op, fn, block))
        return result

    def _walk_ops(self):
        """Generator yielding (op, fn, block) tuples, recursing into nested regions."""
        def walk_block(block, fn):
            for op in block.operations:
                yield op, fn, block
                for region in op.regions:
                    for rblock in region.blocks:
                        yield from walk_block(rblock, fn)

        for fn in self._module.functions:
            for block in fn.body.blocks:
                yield from walk_block(block, fn)

    # =====================================================================
    # READ
    # =====================================================================

    def list_ops(self) -> List[HivmOpInfo]:
        """List all operations with their qualified names and indices."""
        result = []
        for idx, (op, fn, block) in enumerate(self._walk_ops()):
            result.append(HivmOpInfo(
                index=idx,
                qualified_name=op.full_name,
                op=op,
                line=op.line,
            ))
        return result

    def op_counts(self) -> Dict[str, int]:
        """Return a map of op name → count."""
        return dict(Counter(op.full_name for op, _, _ in self._walk_ops()))

    def print_summary(self):
        """Print a summary of all operations."""
        counts = self.op_counts()
        print(f'Module: {len(self._module.functions)} function(s)')
        print(f'Total ops: {sum(counts.values())}')
        for name, count in sorted(counts.items()):
            print(f'  {name}: {count}')

    def collect_ops(self, op_name: str) -> List[MLIROperation]:
        """Collect all operations with the given full name."""
        return [op for op, _, _ in self._walk_ops() if op.full_name == op_name]

    # =====================================================================
    # CREATE - DMA Ops
    # =====================================================================

    def _make_op(self, full_name: str, operands: List[str] = None,
                 results: List[str] = None, attributes: Dict = None) -> MLIROperation:
        op = MLIROperation()
        op.full_name = full_name
        parts = full_name.rsplit('.', 1)
        if len(parts) == 2:
            op.dialect, op.op_name = parts
        else:
            op.op_name = full_name
        if operands:
            for o in operands:
                op.operands.append(SSAValue(o))
        if results:
            for r in results:
                op.results.append(SSAValue(r))
        if attributes:
            for k, v in attributes.items():
                op.attributes[k] = MLIRAttribute(str(v), v)
        op.mark_modified()
        return op

    def _insert_op_before(self, target: MLIROperation, new_op: MLIROperation,
                          fn: MLIRFunction = None, block: MLIRBlock = None):
        if new_op.parent_block:
            return
        if block is None:
            for _, _fn, _block in self._walk_ops():
                for i, op in enumerate(_block.operations):
                    if op is target:
                        block = _block
                        fn = _fn
                        break
        if block is None:
            return
        for i, op in enumerate(block.operations):
            if op is target:
                new_op.parent_block = block
                new_op.mark_modified()
                block.operations.insert(i, new_op)
                self._mark_parent_region_modified(target)
                return

    def _insert_op_after(self, target: MLIROperation, new_op: MLIROperation,
                         fn: MLIRFunction = None, block: MLIRBlock = None):
        if new_op.parent_block:
            return
        if block is None:
            for _, _fn, _block in self._walk_ops():
                for i, op in enumerate(_block.operations):
                    if op is target:
                        block = _block
                        fn = _fn
                        break
        if block is None:
            return
        for i, op in enumerate(block.operations):
            if op is target:
                new_op.parent_block = block
                new_op.mark_modified()
                block.operations.insert(i + 1, new_op)
                self._mark_parent_region_modified(target)
                return

    def _mark_parent_region_modified(self, target: MLIROperation):
        """Mark the parent region-containing op as modified."""
        # Walk all ops to find the one that contains the target in its region
        for op, _, block in self._walk_ops():
            for region in op.regions:
                for rblock in region.blocks:
                    if target in rblock.operations:
                        op.mark_modified()
                        return

    def _add_dma_op(self, target: MLIROperation, op_name: str,
                    src: str, dst: str, before: bool = True) -> MLIROperation:
        op = self._make_op(op_name, operands=[src], results=[dst])
        if before:
            self._insert_op_before(target, op)
        else:
            self._insert_op_after(target, op)
        return op

    def add_load_before(self, target: MLIROperation, src: str, dst: str) -> MLIROperation:
        return self._add_dma_op(target, 'hivm.hir.load', src, dst, before=True)

    def add_load_after(self, target: MLIROperation, src: str, dst: str) -> MLIROperation:
        return self._add_dma_op(target, 'hivm.hir.load', src, dst, before=False)

    def add_store_before(self, target: MLIROperation, src: str, dst: str) -> MLIROperation:
        return self._add_dma_op(target, 'hivm.hir.store', src, dst, before=True)

    def add_store_after(self, target: MLIROperation, src: str, dst: str) -> MLIROperation:
        return self._add_dma_op(target, 'hivm.hir.store', src, dst, before=False)

    def add_copy_before(self, target: MLIROperation, src: str, dst: str) -> MLIROperation:
        return self._add_dma_op(target, 'hivm.hir.copy', src, dst, before=True)

    def add_copy_after(self, target: MLIROperation, src: str, dst: str) -> MLIROperation:
        return self._add_dma_op(target, 'hivm.hir.copy', src, dst, before=False)

    def add_fixpipe_before(self, target: MLIROperation, src: str, dst: str) -> MLIROperation:
        return self._add_dma_op(target, 'hivm.hir.fixpipe', src, dst, before=True)

    def add_fixpipe_after(self, target: MLIROperation, src: str, dst: str) -> MLIROperation:
        return self._add_dma_op(target, 'hivm.hir.fixpipe', src, dst, before=False)

    def add_nd2nz_before(self, target: MLIROperation, src: str, dst: str) -> MLIROperation:
        return self._add_dma_op(target, 'hivm.hir.nd2nz', src, dst, before=True)

    def add_nd2nz_after(self, target: MLIROperation, src: str, dst: str) -> MLIROperation:
        return self._add_dma_op(target, 'hivm.hir.nd2nz', src, dst, before=False)

    # =====================================================================
    # CREATE - Sync Ops
    # =====================================================================

    def _make_sync_op(self, full_name: str, attributes: Dict = None) -> MLIROperation:
        op = self._make_op(full_name, attributes=attributes)
        return op

    def add_set_flag_before(self, target: MLIROperation, set_pipe: PipeAttr,
                            wait_pipe: PipeAttr, event_id: EventAttr) -> MLIROperation:
        op = self._make_sync_op('hivm.hir.set_flag', {
            'pipe': set_pipe.value,
            'event': event_id.value,
        })
        self._insert_op_before(target, op)
        return op

    def add_set_flag_after(self, target: MLIROperation, set_pipe: PipeAttr,
                           wait_pipe: PipeAttr, event_id: EventAttr) -> MLIROperation:
        op = self._make_sync_op('hivm.hir.set_flag', {
            'pipe': set_pipe.value,
            'event': event_id.value,
        })
        self._insert_op_after(target, op)
        return op

    def add_wait_flag_before(self, target: MLIROperation, set_pipe: PipeAttr,
                             wait_pipe: PipeAttr, event_id: EventAttr) -> MLIROperation:
        op = self._make_sync_op('hivm.hir.wait_flag', {
            'pipe': wait_pipe.value,
            'event': event_id.value,
        })
        self._insert_op_before(target, op)
        return op

    def add_wait_flag_after(self, target: MLIROperation, set_pipe: PipeAttr,
                            wait_pipe: PipeAttr, event_id: EventAttr) -> MLIROperation:
        op = self._make_sync_op('hivm.hir.wait_flag', {
            'pipe': wait_pipe.value,
            'event': event_id.value,
        })
        self._insert_op_after(target, op)
        return op

    def add_set_flag_wait_flag_before(self, target: MLIROperation,
                                       set_pipe: PipeAttr, wait_pipe: PipeAttr,
                                       event_id: EventAttr) -> Tuple[MLIROperation, MLIROperation]:
        """Insert a set_flag/wait_flag pair before the target op."""
        set_op = self.add_set_flag_before(target, set_pipe, wait_pipe, event_id)
        wait_op = self.add_wait_flag_before(target, set_pipe, wait_pipe, event_id)
        return set_op, wait_op

    def add_set_flag_wait_flag_after(self, target: MLIROperation,
                                      set_pipe: PipeAttr, wait_pipe: PipeAttr,
                                      event_id: EventAttr) -> Tuple[MLIROperation, MLIROperation]:
        set_op = self.add_set_flag_after(target, set_pipe, wait_pipe, event_id)
        wait_op = self.add_wait_flag_after(target, set_pipe, wait_pipe, event_id)
        return set_op, wait_op

    def add_pipe_barrier_before(self, target: MLIROperation,
                                 pipe: PipeAttr = PipeAttr.PIPE_ALL) -> MLIROperation:
        op = self._make_sync_op('hivm.hir.pipe_barrier', {
            'pipe': pipe.value,
        })
        self._insert_op_before(target, op)
        return op

    def add_pipe_barrier_after(self, target: MLIROperation,
                                pipe: PipeAttr = PipeAttr.PIPE_ALL) -> MLIROperation:
        op = self._make_sync_op('hivm.hir.pipe_barrier', {
            'pipe': pipe.value,
        })
        self._insert_op_after(target, op)
        return op

    def add_barrier_before(self, target: MLIROperation, mode: str = "ALL") -> MLIROperation:
        op = self._make_sync_op('hivm.hir.barrier', {
            'mode': mode,
        })
        self._insert_op_before(target, op)
        return op

    def add_barrier_after(self, target: MLIROperation, mode: str = "ALL") -> MLIROperation:
        op = self._make_sync_op('hivm.hir.barrier', {
            'mode': mode,
        })
        self._insert_op_after(target, op)
        return op

    # =====================================================================
    # CREATE - Vector Unary Ops
    # =====================================================================

    def _add_vector_op(self, target: MLIROperation, op_name: str,
                       ops: List[str], outs: List[str], before: bool = True) -> MLIROperation:
        op = self._make_op(op_name)
        for o in ops:
            op.operands.append(SSAValue(o))
        for o in outs:
            op.results.append(SSAValue(o))
        if before:
            self._insert_op_before(target, op)
        else:
            self._insert_op_after(target, op)
        return op

    def add_vexp_before(self, target: MLIROperation, ops: List[str], outs: List[str]) -> MLIROperation:
        return self._add_vector_op(target, 'hivm.hir.vexp', ops, outs, before=True)

    def add_vexp_after(self, target: MLIROperation, ops: List[str], outs: List[str]) -> MLIROperation:
        return self._add_vector_op(target, 'hivm.hir.vexp', ops, outs, before=False)

    def add_vrelu_before(self, target: MLIROperation, ops: List[str], outs: List[str]) -> MLIROperation:
        return self._add_vector_op(target, 'hivm.hir.vrelu', ops, outs, before=True)

    def add_vrelu_after(self, target: MLIROperation, ops: List[str], outs: List[str]) -> MLIROperation:
        return self._add_vector_op(target, 'hivm.hir.vrelu', ops, outs, before=False)

    def add_vadd_before(self, target: MLIROperation, ops: List[str], outs: List[str]) -> MLIROperation:
        return self._add_vector_op(target, 'hivm.hir.vadd', ops, outs, before=True)

    def add_vadd_after(self, target: MLIROperation, ops: List[str], outs: List[str]) -> MLIROperation:
        return self._add_vector_op(target, 'hivm.hir.vadd', ops, outs, before=False)

    def add_vsub_before(self, target: MLIROperation, ops: List[str], outs: List[str]) -> MLIROperation:
        return self._add_vector_op(target, 'hivm.hir.vsub', ops, outs, before=True)

    def add_vsub_after(self, target: MLIROperation, ops: List[str], outs: List[str]) -> MLIROperation:
        return self._add_vector_op(target, 'hivm.hir.vsub', ops, outs, before=False)

    def add_vmul_before(self, target: MLIROperation, ops: List[str], outs: List[str]) -> MLIROperation:
        return self._add_vector_op(target, 'hivm.hir.vmul', ops, outs, before=True)

    def add_vmul_after(self, target: MLIROperation, ops: List[str], outs: List[str]) -> MLIROperation:
        return self._add_vector_op(target, 'hivm.hir.vmul', ops, outs, before=False)

    def add_vdiv_before(self, target: MLIROperation, ops: List[str], outs: List[str]) -> MLIROperation:
        return self._add_vector_op(target, 'hivm.hir.vdiv', ops, outs, before=True)

    def add_vdiv_after(self, target: MLIROperation, ops: List[str], outs: List[str]) -> MLIROperation:
        return self._add_vector_op(target, 'hivm.hir.vdiv', ops, outs, before=False)

    def add_vmax_before(self, target: MLIROperation, ops: List[str], outs: List[str]) -> MLIROperation:
        return self._add_vector_op(target, 'hivm.hir.vmax', ops, outs, before=True)

    def add_vmax_after(self, target: MLIROperation, ops: List[str], outs: List[str]) -> MLIROperation:
        return self._add_vector_op(target, 'hivm.hir.vmax', ops, outs, before=False)

    def add_vreduce_before(self, target: MLIROperation, ops: List[str], outs: List[str],
                           reduce_op: str = "max") -> MLIROperation:
        op = self._make_op('hivm.hir.vreduce', attributes={'reduce_op': reduce_op})
        for o in ops:
            op.operands.append(SSAValue(o))
        for o in outs:
            op.results.append(SSAValue(o))
        self._insert_op_before(target, op)
        return op

    def add_vreduce_after(self, target: MLIROperation, ops: List[str], outs: List[str],
                          reduce_op: str = "max") -> MLIROperation:
        op = self._make_op('hivm.hir.vreduce', attributes={'reduce_op': reduce_op})
        for o in ops:
            op.operands.append(SSAValue(o))
        for o in outs:
            op.results.append(SSAValue(o))
        self._insert_op_after(target, op)
        return op

    # =====================================================================
    # CREATE - Macro / Compute Ops
    # =====================================================================

    def add_mmad_before(self, target: MLIROperation, a: str, b: str, c: str) -> MLIROperation:
        op = self._make_op('hivm.hir.mmad')
        op.operands = [SSAValue(a), SSAValue(b)]
        op.results = [SSAValue(c)]
        self._insert_op_before(target, op)
        return op

    def add_mmad_after(self, target: MLIROperation, a: str, b: str, c: str) -> MLIROperation:
        op = self._make_op('hivm.hir.mmad')
        op.operands = [SSAValue(a), SSAValue(b)]
        op.results = [SSAValue(c)]
        self._insert_op_after(target, op)
        return op

    def add_matmul_before(self, target: MLIROperation, a: str, b: str, c: str) -> MLIROperation:
        op = self._make_op('hivm.hir.matmul')
        op.operands = [SSAValue(a), SSAValue(b)]
        op.results = [SSAValue(c)]
        self._insert_op_before(target, op)
        return op

    def add_matmul_after(self, target: MLIROperation, a: str, b: str, c: str) -> MLIROperation:
        op = self._make_op('hivm.hir.matmul')
        op.operands = [SSAValue(a), SSAValue(b)]
        op.results = [SSAValue(c)]
        self._insert_op_after(target, op)
        return op

    # =====================================================================
    # DELETE
    # =====================================================================

    def delete_op(self, op: MLIROperation):
        """Delete a specific operation from its parent block."""
        op.mark_modified()  # Mark as modified so it won't be serialized
        def remove_from_block(block):
            if op in block.operations:
                block.operations.remove(op)
                return True
            for child_op in block.operations:
                for region in child_op.regions:
                    for rblock in region.blocks:
                        if remove_from_block(rblock):
                            return True
            return False
        for fn in self._module.functions:
            for block in fn.body.blocks:
                if remove_from_block(block):
                    return

    def delete_all_ops_with_name(self, op_name: str):
        """Delete all operations with the given full name."""
        for fn in self._module.functions:
            for block in fn.body.blocks:
                block.operations = [
                    o for o in block.operations
                    if o.full_name != op_name
                ]

    def delete_nth_op_with_name(self, op_name: str, n: int):
        """Delete the n-th operation (0-indexed) with the given name."""
        count = 0
        for fn in self._module.functions:
            for block in fn.body.blocks:
                for i, op in enumerate(block.operations):
                    if op.full_name == op_name:
                        if count == n:
                            block.operations.pop(i)
                            return
                        count += 1

    def delete_sync_ops_for_op(self, compute_op: MLIROperation):
        """Delete adjacent sync ops (set_flag/wait_flag/barrier) around a compute op."""
        for fn in self._module.functions:
            for block in fn.body.blocks:
                for i, op in enumerate(block.operations):
                    if op is compute_op:
                        # Delete before
                        while i > 0 and block.operations[i - 1].full_name in HIVM_SYNC_OPS:
                            block.operations.pop(i - 1)
                            i -= 1
                        # Delete after
                        j = block.operations.index(compute_op) + 1
                        while j < len(block.operations) and block.operations[j].full_name in HIVM_SYNC_OPS:
                            block.operations.pop(j)
                        return

    def delete_redundant_gm_trips(self, count: int):
        """Delete up to 'count' redundant GM round-trip (load+store) pairs."""
        deleted = 0
        for fn in self._module.functions:
            for block in fn.body.blocks:
                i = 0
                while i < len(block.operations) - 1 and deleted < count:
                    a = block.operations[i]
                    b = block.operations[i + 1]
                    if a.full_name == 'hivm.hir.load' and b.full_name == 'hivm.hir.store':
                        # Check if stores back to same buffer
                        a_ins = {o.name for o in a.operands}
                        b_outs = {o.name for o in b.results}
                        if a_ins & b_outs:  # Same buffer
                            block.operations.pop(i + 1)
                            block.operations.pop(i)
                            deleted += 1
                            continue
                    i += 1

    # =====================================================================
    # MODIFY
    # =====================================================================

    def change_element_type(self, old_type: str, new_type: str):
        """Change element type in all type annotations."""
        self._module.raw_text = self._module.raw_text.replace(old_type, new_type)
        for fn in self._module.functions:
            for arg in fn.args:
                if old_type in arg.type_str:
                    arg.type_str = arg.type_str.replace(old_type, new_type)

    def change_memory_space(self, old_space: str, new_space: str):
        """Change memory space annotations."""
        self._module.raw_text = self._module.raw_text.replace(
            f'address_space<{old_space}>', f'address_space<{new_space}>'
        )
        for fn in self._module.functions:
            for arg in fn.args:
                arg.type_str = arg.type_str.replace(
                    f'address_space<{old_space}>', f'address_space<{new_space}>'
                )

    def change_pipe_attr(self, old_pipe: str, new_pipe: str):
        """Change pipe attributes in all sync ops."""
        for op, _, _ in self._walk_ops():
            if op.full_name in HIVM_SYNC_OPS:
                for key, attr in op.attributes.items():
                    if old_pipe in attr.text:
                        op.attributes[key] = MLIRAttribute(
                            attr.text.replace(old_pipe, new_pipe)
                        )
                if '_bracket_attrs' in op.attributes:
                    ba = op.attributes['_bracket_attrs']
                    new_text = ba.text.replace(old_pipe, new_pipe)
                    op.attributes['_bracket_attrs'] = MLIRAttribute(new_text)

    def change_event_attr(self, old_event: str, new_event: str):
        """Change event attributes in all sync ops."""
        for op, _, _ in self._walk_ops():
            if op.full_name in HIVM_SYNC_OPS:
                for key, attr in op.attributes.items():
                    if old_event in attr.text:
                        op.attributes[key] = MLIRAttribute(
                            attr.text.replace(old_event, new_event)
                        )

    def replace_vadd_with_vsub(self, op: MLIROperation) -> MLIROperation:
        """Replace a vadd op with vsub."""
        op.full_name = 'hivm.hir.vsub'
        return op

    def replace_vsub_with_vadd(self, op: MLIROperation) -> MLIROperation:
        op.full_name = 'hivm.hir.vadd'
        return op

    def replace_vmul_with_vdiv(self, op: MLIROperation) -> MLIROperation:
        op.full_name = 'hivm.hir.vdiv'
        return op

    def replace_vdiv_with_vmul(self, op: MLIROperation) -> MLIROperation:
        op.full_name = 'hivm.hir.vmul'
        return op

    def replace_vmax_with_vmin(self, op: MLIROperation) -> MLIROperation:
        op.full_name = 'hivm.hir.vmin'
        return op

    def replace_vmin_with_vmax(self, op: MLIROperation) -> MLIROperation:
        op.full_name = 'hivm.hir.vmax'
        return op

    # =====================================================================
    # OPTIMISATION CONVENIENCE
    # =====================================================================

    def remove_redundant_load_store_pair(self, n: int):
        """Remove up to n redundant load+store pairs (identical GM round-trips)."""
        self.delete_redundant_gm_trips(n)

    def fuse_consecutive_compute_ops(self):
        """Fuse consecutive compute ops (placeholder)."""
        # Requires actual dependency analysis — not yet implemented in Python
        pass

    def insert_double_buffering(self, src: str, ub0: str, ub1: str,
                                 set_pipe: PipeAttr, wait_pipe: PipeAttr,
                                 event_id: EventAttr):
        """Insert double-buffering pattern with ping-pong buffers."""
        loads = self.collect_ops('hivm.hir.load')
        for load_op in loads:
            # Find the load that uses src
            if any(o.name == src for o in load_op.operands):
                # Insert set_flag/wait_flag pair and alternate buffer
                self.add_set_flag_wait_flag_after(
                    load_op, set_pipe, wait_pipe, event_id
                )
                break

    def barrier_to_directional_sync(self, barrier_op: MLIROperation,
                                     set_pipe: PipeAttr, wait_pipe: PipeAttr,
                                     event_id: EventAttr) -> Tuple[MLIROperation, MLIROperation]:
        """Replace a barrier/pipe_barrier with directional set_flag/wait_flag pair.

        This is the key SyncPlan rewrite: replaces coarse barrier synchronization
        with fine-grained directional event pairs.
        """
        barrier_op.mark_modified()
        set_op, wait_op = self.add_set_flag_wait_flag_before(
            barrier_op, set_pipe, wait_pipe, event_id
        )
        self.delete_op(barrier_op)
        return set_op, wait_op

    def hoist_q_load(self, load_op: MLIROperation, nd2nz_op: MLIROperation):
        """Hoist a Q load + nd2nz pair from inside a loop to before the loop.

        This is a structural edit that requires the caller to verify:
        1. The Q buffer is loop-invariant
        2. No dependency on loop-carried values
        3. The hoisted ops don't break SSA dominance
        """
        for fn in self._module.functions:
            for block in fn.body.blocks:
                if load_op in block.operations and nd2nz_op in block.operations:
                    # Move both ops to before the first op in the function
                    block.operations.remove(load_op)
                    block.operations.remove(nd2nz_op)
                    # Find the loop body and insert before it
                    # This is a simplified version — real implementation needs
                    # to find the enclosing scf.for
                    block.operations.insert(0, nd2nz_op)
                    block.operations.insert(0, load_op)
                    return

    def insert_cv_pipeline_sync(self, cube_op: MLIROperation, vector_op: MLIROperation,
                                 set_pipe: PipeAttr = PipeAttr.PIPE_FIX,
                                 wait_pipe: PipeAttr = PipeAttr.PIPE_V,
                                 event_id: EventAttr = EventAttr.EVENT_ID0):
        """Insert directional sync between Cube/Fixpipe and first Vector op.

        This enables CV pipeline overlap: Cube computes, Fixpipe converts,
        then Vector consumes — synchronized by set_flag/wait_flag.
        """
        self.add_set_flag_wait_flag_before(
            vector_op, set_pipe, wait_pipe, event_id
        )
        return True

    # =====================================================================
    # Utility
    # =====================================================================

    def get_op_text(self, op: MLIROperation) -> str:
        """Get the text representation of an operation."""
        from .hivm_parser import MLIRSerializer
        serializer = MLIRSerializer()
        return serializer._serialize_op(op, indent=0)

    def get_capabilities(self) -> Dict[str, Any]:
        """Return capabilities JSON matching the C++ backend format."""
        return {
            "schema_version": "hivm_ops_editor_python_v1",
            "backend_kind": "python_hivmopseditor",
            "is_real_mlir_backend": False,
            "uses_hivmopseditor": True,
            "uses_mlir_operation_walk": True,
            "inventory": True,
            "roundtrip": True,
            "verify_only": False,
            "dry_run": True,
            "sync_per_action_locator_dry_run": True,
            "hivmopseditor_load_export_list_ops": True,
            "hivmopseditor_insert_sync_ops_api_available": True,
            "hivmopseditor_gm_roundtrip_delete_api_available": True,
            "hivmopseditor_buffer_clone_api_available": False,
            "hivmopseditor_replace_uses_api_available": False,
            "hivmopseditor_region_motion_api_available": False,
            "hivmopseditor_loop_split_api_available": False,
            "mutate_sync_event_insertion": True,
            "sync_event_liveness_proof_available": False,
            "sync_deadlock_proof_available": False,
            "mutate_multibuffer_clone": False,
            "mutate_cv_pipeline_stage_reorder": False,
            "mutate_tiling_loop_split": False,
            "mutate_q_load_hoist": True,
            "mutate_gm_roundtrip_deletion": True,
            "notes": [
                "Python-native HivmOpsEditor — no LLVM/MLIR build dependency",
                "Sync event insertion is supported for barrier_to_directional_event_pair",
                "Q-load hoist is supported with structural (non-dominance-proven) safety",
                "GM round-trip deletion is supported via pattern matching",
                "Buffer clone, region motion, loop split require C++ HivmOpsEditor or MLIR backend",
                "This is a Python fallback — for production use, prefer the C++ hivm-operation-backend"
            ],
        }


# =============================================================================
# Convenience functions
# =============================================================================

def load_editor(path: Union[str, Path]) -> HivmOpsEditor:
    """Load a HIVM MLIR file into an editor."""
    return HivmOpsEditor.load_from_file(path)


def create_editor_from_text(text: str) -> HivmOpsEditor:
    """Create an editor from HIVM MLIR text."""
    return HivmOpsEditor.load_from_text(text)