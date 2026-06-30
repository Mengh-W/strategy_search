# -*- coding: utf-8 -*-
"""HIVM Backend Bridge — unified interface to HIVM backends.

Provides a single, unified interface for HIVM MLIR parsing and editing that
auto-detects the available backend and falls back gracefully:

Backend priority:
1. C++ ``hivm-operation-backend`` (real MLIR, requires vTriton build)
2. C++ ``hivm-strategy-rewrite`` (text-level bridge, always available)
3. Python ``HivmOpsEditor`` (built-in, no external deps)

The bridge is designed to be used by the strategy_search pipeline as a
drop-in replacement for the text-level regex approach in structural_rewrite.py.

Usage::

    from strategy_search.hivm_backend import HivmBackend

    backend = HivmBackend.detect()
    editor = backend.load("input.hivm.mlir")
    ops = editor.list_ops()
    editor.barrier_to_directional_sync(barrier_op, ...)
    editor.export_to_file("output.hivm.mlir")
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .hivm_parser import (
    MLIRModule, MLIRFunction, MLIRRegion, MLIRBlock, MLIROperation,
    SSAValue, parse_hivm_file, parse_hivm_text, serialize_module, write_module,
)
from .hivm_ops_editor import (
    HivmOpsEditor, HivmOpInfo,
    AddressSpace, PipeAttr, EventAttr,
    HIVM_DMA_OPS, HIVM_SYNC_OPS, HIVM_ALL_OPS,
    load_editor, create_editor_from_text,
)


# =============================================================================
# Backend kind
# =============================================================================

class BackendKind(Enum):
    PYTHON = "python_hivmopseditor"
    CPP_BRIDGE = "hivm_strategy_rewrite_bridge"
    CPP_MLIR = "hivm_operation_backend"
    NONE = "none"


@dataclass
class BackendCapabilities:
    kind: BackendKind
    version: str = ""
    is_real_mlir: bool = False
    can_inventory: bool = False
    can_roundtrip: bool = False
    can_mutate_sync: bool = False
    can_mutate_gm_delete: bool = False
    can_mutate_q_load_hoist: bool = False
    can_mutate_buffer_clone: bool = False
    can_mutate_cv_reorder: bool = False
    can_mutate_tiling_split: bool = False
    binary_path: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# HivmBackend
# =============================================================================

class HivmBackend:
    """Unified HIVM backend bridge.

    Auto-detects the best available backend and provides a consistent API
    for loading, editing, and saving HIVM MLIR files.
    """

    # Known binary paths to search
    _KNOWN_BINARIES = [
        # C++ MLIR backend (highest priority)
        "hivm-operation-backend",
        # C++ text bridge
        "hivm-strategy-rewrite",
        # vTriton build output
        "build/bin/hivm-operation-backend",
        "build/bin/hivm-strategy-rewrite",
        "build/tools/hivm-crud/hivm-crud",
        # vTriton lite build
        "vTriton/vTriton lite/build/bin/hivm-operation-backend",
        "vTriton/vTriton lite/build/bin/hivm-strategy-rewrite",
    ]

    def __init__(self, capabilities: BackendCapabilities, editor_class=None):
        self._capabilities = capabilities
        self._editor_class = editor_class or HivmOpsEditor

    @classmethod
    def detect(cls, search_paths: List[str] = None) -> 'HivmBackend':
        """Auto-detect the best available backend.

        Returns a HivmBackend configured for the best available backend.
        """
        paths = search_paths or cls._KNOWN_BINARIES

        # Try to find C++ MLIR backend
        for name in paths:
            binary = cls._find_binary(name)
            if binary:
                caps = cls._probe_cpp_backend(binary)
                if caps and caps.is_real_mlir:
                    return cls(caps)

        # Try to find C++ text bridge
        for name in paths:
            binary = cls._find_binary(name)
            if binary:
                caps = cls._probe_cpp_backend(binary)
                if caps:
                    return cls(caps)

        # Fall back to Python
        return cls.python_backend()

    @classmethod
    def python_backend(cls) -> 'HivmBackend':
        """Create a Python-native backend."""
        caps = BackendCapabilities(
            kind=BackendKind.PYTHON,
            version="hivm_ops_editor_python_v1",
            is_real_mlir=False,
            can_inventory=True,
            can_roundtrip=True,
            can_mutate_sync=True,
            can_mutate_gm_delete=True,
            can_mutate_q_load_hoist=True,
            can_mutate_buffer_clone=False,
            can_mutate_cv_reorder=False,
            can_mutate_tiling_split=False,
        )
        return cls(caps, editor_class=HivmOpsEditor)

    @classmethod
    def _find_binary(cls, name: str) -> Optional[str]:
        """Find a binary by name in PATH or relative to project root."""
        # Check PATH
        if shutil.which(name):
            return shutil.which(name)

        # Check relative to project root
        project_root = Path(__file__).resolve().parent.parent
        candidate = project_root / name
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)

        # Check with .exe on Windows
        if os.name == 'nt':
            candidate = project_root / (name + '.exe')
            if candidate.exists():
                return str(candidate)

        return None

    @classmethod
    def _probe_cpp_backend(cls, binary: str) -> Optional[BackendCapabilities]:
        """Probe a C++ binary for its capabilities."""
        try:
            result = subprocess.run(
                [binary, '--print-capabilities'],
                capture_output=True, text=True, timeout=10,
                cwd=str(Path(__file__).resolve().parent.parent),
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return BackendCapabilities(
                    kind=BackendKind.CPP_MLIR if data.get('is_real_mlir_backend') else BackendKind.CPP_BRIDGE,
                    version=data.get('schema_version', ''),
                    is_real_mlir=data.get('is_real_mlir_backend', False),
                    can_inventory=data.get('inventory', False),
                    can_roundtrip=data.get('roundtrip', False),
                    can_mutate_sync=data.get('mutate_sync_event_insertion', False),
                    can_mutate_gm_delete=data.get('mutate_gm_roundtrip_deletion', False),
                    can_mutate_q_load_hoist=data.get('mutate_q_load_hoist', False),
                    can_mutate_buffer_clone=data.get('mutate_multibuffer_clone', False),
                    can_mutate_cv_reorder=data.get('mutate_cv_pipeline_stage_reorder', False),
                    can_mutate_tiling_split=data.get('mutate_tiling_loop_split', False),
                    binary_path=binary,
                    raw=data,
                )
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            pass
        return None

    @property
    def capabilities(self) -> BackendCapabilities:
        return self._capabilities

    @property
    def kind(self) -> BackendKind:
        return self._capabilities.kind

    def load(self, path: Union[str, Path]) -> HivmOpsEditor:
        """Load a HIVM MLIR file into an editor."""
        return self._editor_class.load_from_file(path)

    def load_text(self, text: str) -> HivmOpsEditor:
        """Load HIVM MLIR text into an editor."""
        return self._editor_class.load_from_text(text)

    def parse(self, path: Union[str, Path]) -> MLIRModule:
        """Parse a HIVM MLIR file into an IR tree."""
        return parse_hivm_file(path)

    def parse_text(self, text: str) -> MLIRModule:
        """Parse HIVM MLIR text into an IR tree."""
        return parse_hivm_text(text)

    def serialize(self, module: MLIRModule) -> str:
        """Serialize a module to MLIR text."""
        return serialize_module(module)

    def write(self, module: MLIRModule, path: Union[str, Path]):
        """Write a module to file."""
        write_module(module, path)

    def apply_structural_edit(self, input_path: Path, edit_script: Dict,
                              output_path: Path, report_path: Path = None) -> Dict:
        """Apply a structural edit script using the best available backend.

        If the C++ backend is available, delegates to it. Otherwise, uses
        the Python HivmOpsEditor.

        Returns a report dict.
        """
        if self._capabilities.kind == BackendKind.CPP_MLIR:
            return self._apply_via_cpp_mlir(input_path, edit_script, output_path, report_path)
        elif self._capabilities.kind == BackendKind.CPP_BRIDGE:
            return self._apply_via_cpp_bridge(input_path, edit_script, output_path, report_path)
        else:
            return self._apply_via_python(input_path, edit_script, output_path, report_path)

    def _apply_via_cpp_mlir(self, input_path: Path, edit_script: Dict,
                            output_path: Path, report_path: Path = None) -> Dict:
        """Apply edits via the C++ MLIR backend."""
        binary = self._capabilities.binary_path
        if not binary:
            return {"status": "failed", "error": "C++ binary not found"}

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(edit_script, f)
            edit_path = f.name

        try:
            cmd = [
                binary,
                '--input', str(input_path),
                '--output', str(output_path),
                '--edit-script', edit_path,
                '--mutate',
                '--mutation-kind', edit_script.get('mutation_kind', 'sync_event_insertion'),
            ]
            if report_path:
                cmd.extend(['--report', str(report_path)])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if report_path:
                with open(report_path, 'r') as f:
                    return json.load(f)
            return {"status": "completed" if result.returncode == 0 else "failed",
                    "stderr": result.stderr}
        finally:
            os.unlink(edit_path)

    def _apply_via_cpp_bridge(self, input_path: Path, edit_script: Dict,
                               output_path: Path, report_path: Path = None) -> Dict:
        """Apply edits via the C++ text bridge."""
        binary = self._capabilities.binary_path
        if not binary:
            return {"status": "failed", "error": "C++ bridge binary not found"}

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(edit_script, f)
            edit_path = f.name

        try:
            cmd = [
                binary,
                '--input', str(input_path),
                '--edit-script', edit_path,
                '--output', str(output_path),
            ]
            if report_path:
                cmd.extend(['--report', str(report_path)])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if report_path and os.path.exists(report_path):
                with open(report_path, 'r') as f:
                    return json.load(f)
            return {"status": "completed" if result.returncode == 0 else "failed",
                    "stderr": result.stderr}
        finally:
            os.unlink(edit_path)

    def _apply_via_python(self, input_path: Path, edit_script: Dict,
                           output_path: Path, report_path: Path = None) -> Dict:
        """Apply edits using the Python HivmOpsEditor."""
        editor = self.load(input_path)
        report = {
            "schema_version": "hivm_backend_python_v1",
            "status": "completed_python_rewrite",
            "backend_kind": "python_hivmopseditor",
            "is_real_mlir_backend": False,
            "input": str(input_path),
            "output": str(output_path),
            "actions": [],
            "op_count_before": len(editor.list_ops()),
        }

        actions = edit_script.get('actions', [])
        for action in actions:
            action_report = self._execute_python_action(editor, action)
            report['actions'].append(action_report)

        report['op_count_after'] = len(editor.list_ops())
        editor.export_to_file(output_path)

        if report_path:
            with open(report_path, 'w') as f:
                json.dump(report, f, indent=2)

        return report

    def _execute_python_action(self, editor: HivmOpsEditor, action: Dict) -> Dict:
        """Execute a single edit action using the Python editor."""
        action_id = action.get('action_id', 'unknown')
        mutation_kind = action.get('mutation_kind', '')
        report = {
            "action_id": action_id,
            "mutation_kind": mutation_kind,
            "mutation_performed": False,
            "status": "unknown_action",
        }

        if mutation_kind == 'barrier_to_directional_event_pair':
            return self._execute_barrier_to_sync(editor, action, report)
        elif mutation_kind == 'insert_cv_pipeline_sync':
            return self._execute_cv_sync(editor, action, report)
        elif mutation_kind == 'hoist_q_load':
            return self._execute_q_load_hoist(editor, action, report)
        elif mutation_kind == 'remove_redundant_gm_roundtrip':
            return self._execute_gm_delete(editor, action, report)
        elif mutation_kind == 'insert_double_buffering':
            return self._execute_double_buffering(editor, action, report)

        return report

    def _execute_barrier_to_sync(self, editor: HivmOpsEditor, action: Dict,
                                  report: Dict) -> Dict:
        """Execute barrier→set_flag/wait_flag rewrite."""
        try:
            target_line = action.get('target_line', -1)
            set_pipe_str = action.get('set_pipe', 'PIPE_MTE2')
            wait_pipe_str = action.get('wait_pipe', set_pipe_str)
            event_id_str = action.get('event_id', 'EVENT_ID0')

            set_pipe = PipeAttr[set_pipe_str] if set_pipe_str in PipeAttr.__members__ else PipeAttr.PIPE_MTE2
            wait_pipe = PipeAttr[wait_pipe_str] if wait_pipe_str in PipeAttr.__members__ else set_pipe
            event_id = EventAttr[event_id_str] if event_id_str in EventAttr.__members__ else EventAttr.EVENT_ID0

            ops = editor.list_ops()
            target = None
            for info in ops:
                name = info.qualified_name
                if 'barrier' in name or 'pipe_barrier' in name:
                    if target_line < 0 or info.line == target_line:
                        target = info.op
                        break

            if target is None:
                report['status'] = 'blocked_barrier_not_found'
                return report

            editor.barrier_to_directional_sync(target, set_pipe, wait_pipe, event_id)
            report['mutation_performed'] = True
            report['status'] = 'completed_barrier_to_directional_sync'
            report['set_pipe'] = set_pipe_str
            report['wait_pipe'] = wait_pipe_str
            report['event_id'] = event_id_str
        except Exception as e:
            report['status'] = f'failed: {e}'
        return report

    def _execute_cv_sync(self, editor: HivmOpsEditor, action: Dict,
                          report: Dict) -> Dict:
        """Execute CV pipeline sync insertion."""
        try:
            ops = editor.list_ops()
            # Find the last fixpipe/mmad (cube op) before the first vector op
            cube_op = None
            vector_op = None
            for info in ops:
                name = info.qualified_name
                if any(x in name for x in ('mmad', 'fixpipe', 'matmul')):
                    cube_op = info.op
                elif any(x in name for x in ('vadd', 'vsub', 'vmul', 'vdiv', 'vexp', 'vreduce', 'vrelu')):
                    if vector_op is None:
                        vector_op = info.op
                        break

            if cube_op is None or vector_op is None:
                report['status'] = 'blocked_cube_or_vector_op_not_found'
                return report

            editor.insert_cv_pipeline_sync(cube_op, vector_op)
            report['mutation_performed'] = True
            report['status'] = 'completed_cv_pipeline_sync'
        except Exception as e:
            report['status'] = f'failed: {e}'
        return report

    def _execute_q_load_hoist(self, editor: HivmOpsEditor, action: Dict,
                               report: Dict) -> Dict:
        """Execute Q load hoist."""
        try:
            ops = editor.list_ops()
            q_load = None
            q_nd2nz = None
            for info in ops:
                name = info.qualified_name
                if 'load' in name and 'q_' in info.op.raw_text.lower():
                    q_load = info.op
                elif 'nd2nz' in name and q_load is not None and q_nd2nz is None:
                    q_nd2nz = info.op

            if q_load is None:
                report['status'] = 'blocked_q_load_not_found'
                return report

            editor.hoist_q_load(q_load, q_nd2nz)
            report['mutation_performed'] = True
            report['status'] = 'completed_q_load_hoist'
        except Exception as e:
            report['status'] = f'failed: {e}'
        return report

    def _execute_gm_delete(self, editor: HivmOpsEditor, action: Dict,
                            report: Dict) -> Dict:
        """Execute GM round-trip deletion."""
        try:
            max_pairs = action.get('max_gm_pairs', 1)
            editor.remove_redundant_load_store_pair(max_pairs)
            report['mutation_performed'] = True
            report['status'] = 'completed_gm_roundtrip_deletion'
            report['max_gm_pairs'] = max_pairs
        except Exception as e:
            report['status'] = f'failed: {e}'
        return report

    def _execute_double_buffering(self, editor: HivmOpsEditor, action: Dict,
                                   report: Dict) -> Dict:
        """Execute double buffering insertion."""
        try:
            src = action.get('src', '')
            ub0 = action.get('ub0', '')
            ub1 = action.get('ub1', '')
            set_pipe = PipeAttr.PIPE_MTE2
            wait_pipe = PipeAttr.PIPE_M
            event_id = EventAttr.EVENT_ID0
            editor.insert_double_buffering(src, ub0, ub1, set_pipe, wait_pipe, event_id)
            report['mutation_performed'] = True
            report['status'] = 'completed_double_buffering'
        except Exception as e:
            report['status'] = f'failed: {e}'
        return report


# =============================================================================
# Module-level convenience
# =============================================================================

# Global singleton, lazily initialized
_backend: Optional[HivmBackend] = None


def get_backend() -> HivmBackend:
    """Get the global HivmBackend instance (auto-detected)."""
    global _backend
    if _backend is None:
        _backend = HivmBackend.detect()
    return _backend


def reset_backend():
    """Reset the global backend (for testing)."""
    global _backend
    _backend = None


def force_python_backend():
    """Force the Python backend."""
    global _backend
    _backend = HivmBackend.python_backend()