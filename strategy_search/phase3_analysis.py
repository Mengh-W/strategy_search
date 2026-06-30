# -*- coding: utf-8 -*-
"""Phase-3A conservative HIVM analysis foundation.

This module starts the Phase-3 correctness infrastructure.  It deliberately does
not introduce new structural rewrites.  Instead it turns HIVM/NPUIR text into a
stable, auditable set of analysis artifacts:

* HIVM operation inventory with role / pipe / memory-space classification.
* Conservative dependency graph v1.
* Event liveness and sync-pair report.
* Phase-3A summary describing what is proven and what remains target-backend work.

The implementation is parser-independent so it can run in CI without a local
vTriton/LLVM build.  It is conservative by design: unknown operation semantics
are marked unknown and must not be used to authorize dangerous rewrites.  A
production implementation should replace the text scanner with vTriton
HivmOpsEditor or MLIR Operation walking while preserving the same JSON contract.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _load_default_semantics() -> Dict[str, Dict[str, Any]]:
    """Return the built-in lightweight HIVM op semantics registry."""
    return {
        "hivm.hir.load": {"role": "load", "pipe": "PIPE_MTE2", "reads_spaces": ["gm"], "writes_spaces": ["ub", "l1", "cbuf"], "memory_effect": "read"},
        "hivm.load": {"role": "load", "pipe": "PIPE_MTE2", "reads_spaces": ["gm"], "writes_spaces": ["ub", "l1", "cbuf"], "memory_effect": "read"},
        "hivm.hir.store": {"role": "store", "pipe": "PIPE_MTE3", "reads_spaces": ["ub", "l1", "cbuf"], "writes_spaces": ["gm"], "memory_effect": "write"},
        "hivm.store": {"role": "store", "pipe": "PIPE_MTE3", "reads_spaces": ["ub", "l1", "cbuf"], "writes_spaces": ["gm"], "memory_effect": "write"},
        "hivm.hir.nd2nz": {"role": "layout", "pipe": "PIPE_MTE2", "reads_spaces": ["ub", "gm"], "writes_spaces": ["l1", "cbuf", "ub"], "memory_effect": "read_write"},
        "hivm.hir.nz2nd": {"role": "layout", "pipe": "PIPE_MTE3", "reads_spaces": ["ub", "l1", "cbuf"], "writes_spaces": ["gm", "ub"], "memory_effect": "read_write"},
        "hivm.hir.mmad": {"role": "cube", "pipe": "PIPE_M", "reads_spaces": ["l1", "l0a", "l0b"], "writes_spaces": ["l0c"], "memory_effect": "read_write"},
        "hivm.hir.mmadL1": {"role": "cube", "pipe": "PIPE_M", "reads_spaces": ["l1", "l0a", "l0b"], "writes_spaces": ["l0c"], "memory_effect": "read_write"},
        "hivm.hir.matmul": {"role": "cube", "pipe": "PIPE_M", "reads_spaces": ["l1", "l0a", "l0b"], "writes_spaces": ["l0c"], "memory_effect": "read_write"},
        "hivm.hir.fixpipe": {"role": "fixpipe", "pipe": "PIPE_FIX", "reads_spaces": ["l0c"], "writes_spaces": ["ub", "l1"], "memory_effect": "read_write"},
        "hivm.hir.vadd": {"role": "vector", "pipe": "PIPE_V", "reads_spaces": ["ub"], "writes_spaces": ["ub"], "memory_effect": "read_write"},
        "hivm.hir.vsub": {"role": "vector", "pipe": "PIPE_V", "reads_spaces": ["ub"], "writes_spaces": ["ub"], "memory_effect": "read_write"},
        "hivm.hir.vmul": {"role": "vector", "pipe": "PIPE_V", "reads_spaces": ["ub"], "writes_spaces": ["ub"], "memory_effect": "read_write"},
        "hivm.hir.vdiv": {"role": "vector", "pipe": "PIPE_V", "reads_spaces": ["ub"], "writes_spaces": ["ub"], "memory_effect": "read_write"},
        "hivm.hir.vexp": {"role": "vector", "pipe": "PIPE_V", "reads_spaces": ["ub"], "writes_spaces": ["ub"], "memory_effect": "read_write"},
        "hivm.hir.vreduce": {"role": "vector", "pipe": "PIPE_V", "reads_spaces": ["ub"], "writes_spaces": ["ub"], "memory_effect": "read_write"},
        "hivm.hir.cast": {"role": "vector", "pipe": "PIPE_V", "reads_spaces": ["ub"], "writes_spaces": ["ub"], "memory_effect": "read_write"},
        "hivm.hir.softmax": {"role": "vector", "pipe": "PIPE_V", "reads_spaces": ["ub"], "writes_spaces": ["ub"], "memory_effect": "read_write"},
        "hivm.hir.set_flag": {"role": "sync_set", "pipe": "PIPE_SYNC", "memory_effect": "sync", "event_def": True},
        "hivm.hir.wait_flag": {"role": "sync_wait", "pipe": "PIPE_SYNC", "memory_effect": "sync", "event_use": True},
        "hivm.hir.barrier": {"role": "barrier", "pipe": "PIPE_SYNC", "memory_effect": "sync", "coarse_ordering": True},
        "hivm.hir.pipe_barrier": {"role": "barrier", "pipe": "PIPE_SYNC", "memory_effect": "sync", "coarse_ordering": True},
    }


# Preferred longer names first so hivm.hir.mmadL1 is not truncated to hivm.hir.mmad.
_OP_NAME_PAT = re.compile(r"\b(hivm(?:\.hir)?\.[A-Za-z_][\w]*)\b")
_MEMREF_VAR_PAT = re.compile(r"(%[\w.$-]+)\s*:\s*memref<[^>]+#hivm\.address_space<([^>]+)>")
_SET_WAIT_PAT = re.compile(r"\bhivm\.(?:hir\.)?(set_flag|wait_flag)\[<([^>]+)>,\s*<([^>]+)>,\s*<([^>]+)>\]")
_BARRIER_ALL_PAT = re.compile(r"\bhivm\.(?:hir\.)?(?:pipe_barrier\[<PIPE_ALL>\]|barrier\b.*mode\s*=\s*\"ALL\")")
_SCF_FOR_PAT = re.compile(r"\bscf\.for\s+(%[\w.$-]+)")


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def export_default_semantics(path: Path) -> None:
    """Write the built-in op semantics registry to a JSON file for review/editing."""
    _write_json(path, {"schema_version": "hivm_op_semantics_registry_v1", "ops": _load_default_semantics()})


def _strip_comment(line: str) -> str:
    return "" if line.lstrip().startswith("//") else line


def _extract_sections(line: str) -> Dict[str, str]:
    out = {"ins": "", "outs": ""}
    for name in out:
        m = re.search(r"\b" + name + r"\s*\((.*?)\)", line)
        if m:
            out[name] = m.group(1)
    return out


def _extract_memrefs_from_section(text: str) -> List[Dict[str, str]]:
    return [{"var": var, "space": space.lower()} for var, space in _MEMREF_VAR_PAT.findall(text)]


def _classify_semantics(op_name: str, registry: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    if op_name in registry:
        sem = dict(registry[op_name])
        sem["known_semantics"] = True
        return sem
    # family fallback for vector ops not explicitly listed
    if re.match(r"hivm\.hir\.v\w+", op_name):
        return {"known_semantics": True, "role": "vector", "pipe": "PIPE_V", "memory_effect": "read_write", "reads_spaces": ["ub"], "writes_spaces": ["ub"], "fallback_family": "vector"}
    return {"known_semantics": False, "role": "unknown", "pipe": "unknown", "memory_effect": "unknown"}


def build_hivm_op_inventory(ir_text: str, semantics_registry: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Build a conservative line-based HIVM op inventory.

    This intentionally mirrors the JSON shape expected from a future
    vTriton/HivmOpsEditor Operation walk.  It should be replaced by the target
    parser when available, but it is useful as a stable CI/audit baseline.
    """
    registry = semantics_registry or _load_default_semantics()
    ops: List[Dict[str, Any]] = []
    loop_stack: List[Dict[str, Any]] = []
    region_depth = 0
    role_counts: Dict[str, int] = {}
    unknown_ops: List[Dict[str, Any]] = []

    for lineno, raw in enumerate(ir_text.splitlines(), 1):
        line = _strip_comment(raw)
        if not line.strip():
            continue
        # Record loop before consuming brace deltas for this line.
        m_loop = _SCF_FOR_PAT.search(line)
        if m_loop:
            loop_stack.append({"line": lineno, "induction": m_loop.group(1), "depth": region_depth})
        m_op = _OP_NAME_PAT.search(line)
        if m_op:
            op_name = m_op.group(1)
            # Ignore HIVM attribute namespaces that can appear on func/op lines.
            # They are metadata, not executable HIVM operations.
            if op_name in {"hivm.strategy", "hivm.cv", "hivm.address_space", "hivm.sync", "hivm.nbuf"}:
                region_depth += line.count("{") - line.count("}")
                while loop_stack and region_depth <= int(loop_stack[-1].get("depth", 0)):
                    loop_stack.pop()
                continue
            sem = _classify_semantics(op_name, registry)
            sections = _extract_sections(line)
            ins = _extract_memrefs_from_section(sections["ins"])
            outs = _extract_memrefs_from_section(sections["outs"])
            sync = _SET_WAIT_PAT.search(line)
            event_info = None
            if sync:
                event_info = {"kind": sync.group(1), "pipe_src": sync.group(2), "pipe_dst": sync.group(3), "event_id": sync.group(4)}
            is_barrier_all = bool(_BARRIER_ALL_PAT.search(line))
            parent_loop = loop_stack[-1] if loop_stack else None
            role = str(sem.get("role", "unknown"))
            op = {
                "op_id": len(ops),
                "line": lineno,
                "op_name": op_name,
                "role": role,
                "pipe": sem.get("pipe", "unknown"),
                "known_semantics": bool(sem.get("known_semantics")),
                "memory_effect": sem.get("memory_effect", "unknown"),
                "region_depth": region_depth,
                "parent_loop": parent_loop,
                "inputs": ins,
                "outputs": outs,
                "event": event_info,
                "barrier_all": is_barrier_all,
                "text": line.strip(),
            }
            ops.append(op)
            role_counts[role] = role_counts.get(role, 0) + 1
            if not op["known_semantics"]:
                unknown_ops.append({"op_id": op["op_id"], "line": lineno, "op_name": op_name, "text": op["text"]})
        # Update brace/loop approximation after scanning the line.
        region_depth += line.count("{") - line.count("}")
        # Pop loops when the depth falls back to/below the loop's starting depth.
        while loop_stack and region_depth <= int(loop_stack[-1].get("depth", 0)):
            loop_stack.pop()

    return {
        "schema_version": "hivm_op_inventory_v1",
        "producer": "strategy_search_demo_v3.3.2_phase3a_dependency_foundation",
        "parser_mode": "conservative_line_scanner__future_target_vtriton_hivmopseditor",
        "op_count": len(ops),
        "role_counts": role_counts,
        "unknown_op_count": len(unknown_ops),
        "unknown_ops": unknown_ops,
        "ops": ops,
        "limitations": [
            "Line scanner is not a substitute for MLIR Operation walking.",
            "Region/loop nesting is approximate and should be rechecked by vTriton/HivmOpsEditor.",
            "Unknown ops are treated as rewrite blockers for dangerous transformations.",
        ],
    }


def _vars(xs: Iterable[Dict[str, str]]) -> List[str]:
    return [x.get("var", "") for x in xs if x.get("var")]


def build_dependency_graph(inventory: Dict[str, Any]) -> Dict[str, Any]:
    """Build a conservative dependency graph from the op inventory."""
    ops = list(inventory.get("ops") or [])
    edges: List[Dict[str, Any]] = []
    last_writer: Dict[str, int] = {}
    last_readers: Dict[str, List[int]] = {}
    last_set_by_event: Dict[str, int] = {}
    last_barrier: Optional[int] = None

    def add_edge(src: int, dst: int, typ: str, resource: Optional[str] = None, confidence: str = "medium", reason: str = "") -> None:
        if src == dst or src is None or dst is None:
            return
        edges.append({"src": src, "dst": dst, "type": typ, "resource": resource, "confidence": confidence, "reason": reason})

    for op in ops:
        oid = int(op["op_id"])
        read_vars = _vars(op.get("inputs") or [])
        write_vars = _vars(op.get("outputs") or [])

        # Barrier conservatively orders nearby subsequent ops after the barrier.
        if last_barrier is not None and op.get("role") not in {"barrier", "sync_set", "sync_wait"}:
            add_edge(last_barrier, oid, "coarse_barrier_order", "PIPE_ALL", "medium", "previous barrier conservatively orders later non-sync op")

        # Memory edges.
        for v in read_vars:
            if v in last_writer:
                add_edge(last_writer[v], oid, "memory_raw", v, "high", "same SSA memref writer reaches reader")
            last_readers.setdefault(v, []).append(oid)
        for v in write_vars:
            if v in last_writer:
                add_edge(last_writer[v], oid, "memory_waw", v, "high", "same SSA memref written again")
            for r in last_readers.get(v, []):
                add_edge(r, oid, "memory_war", v, "medium", "same SSA memref read before later write")
            last_writer[v] = oid
            last_readers[v] = []

        # Sync edges.
        event = op.get("event") or {}
        event_id = event.get("event_id")
        if op.get("role") == "sync_set" and event_id:
            if event_id in last_set_by_event:
                add_edge(last_set_by_event[event_id], oid, "event_redefinition", event_id, "high", "same event id set again before all uses can be proven closed")
            last_set_by_event[event_id] = oid
        if op.get("role") == "sync_wait" and event_id:
            if event_id in last_set_by_event:
                add_edge(last_set_by_event[event_id], oid, "event_set_wait", event_id, "high", "wait is paired with previous set of same event id")
            else:
                edges.append({"src": None, "dst": oid, "type": "event_wait_without_visible_set", "resource": event_id, "confidence": "high", "reason": "wait has no visible dominating set in inventory order"})

        if op.get("role") == "barrier" or op.get("barrier_all"):
            last_barrier = oid

    edge_counts: Dict[str, int] = {}
    for e in edges:
        edge_counts[e["type"]] = edge_counts.get(e["type"], 0) + 1
    return {
        "schema_version": "hivm_dependency_graph_v1",
        "producer": "strategy_search_demo_v3.3.2_phase3a_dependency_foundation",
        "node_count": len(ops),
        "edge_count": len(edges),
        "edge_counts": edge_counts,
        "edges": edges,
        "legality_implication": {
            "barrier_or_sync_rewrite": "must preserve high-confidence memory_raw and event_set_wait edges or provide directional sync coverage",
            "op_motion_or_hoist": "must not move an op across high-confidence RAW/WAW/WAR edges involving its buffers",
            "gm_roundtrip_deletion": "requires additional alias/MemorySSA proof; this graph alone is insufficient",
        },
    }


def build_event_liveness_report(inventory: Dict[str, Any]) -> Dict[str, Any]:
    """Build a conservative event set/wait pairing and liveness report."""
    events: Dict[str, List[Dict[str, Any]]] = {}
    warnings: List[str] = []
    for op in inventory.get("ops") or []:
        event = op.get("event") or {}
        eid = event.get("event_id")
        if not eid:
            continue
        events.setdefault(eid, []).append({
            "op_id": op.get("op_id"),
            "line": op.get("line"),
            "kind": event.get("kind"),
            "pipe_src": event.get("pipe_src"),
            "pipe_dst": event.get("pipe_dst"),
            "text": op.get("text"),
        })

    records: List[Dict[str, Any]] = []
    safe_pairs = 0
    unpaired_waits = 0
    overlapping_or_redefined = 0
    for eid, ops in sorted(events.items()):
        pending_sets: List[Dict[str, Any]] = []
        pairs: List[Dict[str, Any]] = []
        local_warnings: List[str] = []
        for item in ops:
            if item.get("kind") == "set_flag":
                if pending_sets:
                    overlapping_or_redefined += 1
                    local_warnings.append(f"event {eid} has another set before previous set is visibly waited")
                pending_sets.append(item)
            elif item.get("kind") == "wait_flag":
                if pending_sets:
                    s = pending_sets.pop(0)
                    pairs.append({"set": s, "wait": item, "live_range": [s.get("op_id"), item.get("op_id")], "pipe_pair_match": (s.get("pipe_src"), s.get("pipe_dst")) == (item.get("pipe_src"), item.get("pipe_dst"))})
                else:
                    unpaired_waits += 1
                    local_warnings.append(f"event {eid} wait has no visible previous set")
        if pending_sets:
            local_warnings.append(f"event {eid} has {len(pending_sets)} visible set(s) without visible wait")
        safe_pairs += sum(1 for p in pairs if p.get("pipe_pair_match"))
        records.append({"event_id": eid, "ops": ops, "pairs": pairs, "unclosed_sets": pending_sets, "warnings": local_warnings, "safe_pair_count": sum(1 for p in pairs if p.get("pipe_pair_match"))})
        warnings.extend(local_warnings)

    return {
        "schema_version": "hivm_event_liveness_report_v1",
        "producer": "strategy_search_demo_v3.3.2_phase3a_dependency_foundation",
        "event_count": len(records),
        "safe_pair_count": safe_pairs,
        "unpaired_wait_count": unpaired_waits,
        "overlap_or_redefinition_count": overlapping_or_redefined,
        "passed_local_event_liveness": unpaired_waits == 0 and overlapping_or_redefined == 0,
        "events": records,
        "warnings": warnings,
        "limitations": [
            "Dominance and loop-carried event semantics require target MLIR/vTriton verification.",
            "This report is a local line-order liveness approximation, not a deadlock proof.",
        ],
    }



# ---------------------------------------------------------------------------
# Phase-3B: buffer liveness / GM alias / capacity precheck
# ---------------------------------------------------------------------------

_ALLOC_PAT = re.compile(r"(?P<var>%[\w.$-]+)\s*=\s*memref\.alloc\([^)]*\)\s*(?:\{[^}]*\})?\s*:\s*memref<(?P<body>[^>]+#hivm\.address_space<(?P<space>[^>]+)>[^>]*)>")
_FUNC_ARG_MEMREF_PAT = re.compile(r"(?P<var>%[\w.$-]+)\s*:\s*memref<(?P<body>[^>]+#hivm\.address_space<(?P<space>[^>]+)>[^>]*)>")
_DTYPE_BYTES = {"f16": 2, "bf16": 2, "f32": 4, "i8": 1, "i16": 2, "i32": 4, "i64": 8, "u8": 1, "u16": 2, "u32": 4, "u64": 8}
_SPACE_ALIAS_PHASE3 = {"cbuf": "l1", "cc": "l0c", "hbm": "gm", "global": "gm"}
_DEFAULT_LOCAL_LIMITS_BYTES = {"ub": 256 * 1024, "l1": 1024 * 1024, "l0a": 64 * 1024, "l0b": 64 * 1024, "l0c": 256 * 1024}


def _norm_mem_space(space: str) -> str:
    return _SPACE_ALIAS_PHASE3.get(str(space or "").lower(), str(space or "").lower())


def _parse_memref_body_details(body: str) -> Dict[str, Any]:
    """Parse a static memref body enough for auditing capacity and alias gates."""
    main = str(body).split(",")[0].strip()
    parts = [x.strip() for x in main.split("x") if x.strip()]
    dims: List[int] = []
    dtype = "unknown"
    static = True
    if len(parts) >= 2:
        dtype = parts[-1]
        for d in parts[:-1]:
            if d.isdigit():
                dims.append(int(d))
            else:
                static = False
    else:
        static = False
    size_bytes = None
    if static and dtype in _DTYPE_BYTES:
        prod = 1
        for d in dims:
            prod *= d
        size_bytes = prod * _DTYPE_BYTES[dtype]
    return {"dims": dims, "dtype": dtype, "static_shape": static, "size_bytes": size_bytes, "memref_main": main}


def _buffer_role_from_name(var: str, space: str) -> str:
    name = str(var).lstrip("%").lower()
    if space == "gm":
        if name.startswith("o") or "out" in name or name in {"%o_gm", "o_gm"}:
            return "gm_output_or_boundary"
        return "gm_input_or_boundary"
    if any(tok in name for tok in ["acc", "l0c", "sum"]):
        return "accumulator"
    if name.startswith("o") or "out" in name or "dst" in name:
        return "output"
    if any(tok in name for tok in ["q_", "k_", "v_"]):
        return "stream_buffer"
    if any(tok in name for tok in ["m_", "l_", "p_", "s_"]):
        return "softmax_or_score_buffer"
    return "unknown_local_buffer"


def _collect_buffer_declarations(ir_text: str) -> Dict[str, Dict[str, Any]]:
    """Collect memref allocations and function boundary buffers."""
    buffers: Dict[str, Dict[str, Any]] = {}
    for lineno, line in enumerate(ir_text.splitlines(), 1):
        for m in _ALLOC_PAT.finditer(line):
            var = m.group("var")
            space = _norm_mem_space(m.group("space"))
            details = _parse_memref_body_details(m.group("body"))
            buffers[var] = {
                "var": var,
                "declaration_kind": "alloc",
                "decl_line": lineno,
                "space": space,
                "address_space_raw": m.group("space"),
                **details,
                "buffer_role": _buffer_role_from_name(var, space),
            }
        # Function arguments / op operands may expose GM boundaries.  Do not let
        # later operand mentions overwrite an allocation declaration.
        if "func.func" in line or ("%" in line and "memref<" in line and "memref.alloc" not in line):
            for m in _FUNC_ARG_MEMREF_PAT.finditer(line):
                var = m.group("var")
                if var in buffers:
                    continue
                space = _norm_mem_space(m.group("space"))
                if space != "gm":
                    continue
                details = _parse_memref_body_details(m.group("body"))
                buffers[var] = {
                    "var": var,
                    "declaration_kind": "boundary_or_operand",
                    "decl_line": lineno,
                    "space": space,
                    "address_space_raw": m.group("space"),
                    **details,
                    "buffer_role": _buffer_role_from_name(var, space),
                }
    return buffers


def build_buffer_liveness_report(ir_text: str, inventory: Dict[str, Any]) -> Dict[str, Any]:
    """Build conservative buffer liveness and local capacity recheck.

    The report intentionally over-approximates local peak bytes as the sum of all
    local allocations because a line scanner cannot prove non-overlap.  This is
    suitable as a safety gate: if the conservative bound already exceeds the
    hardware budget, later hoist/double-buffer rewrites must be blocked.
    """
    buffers = _collect_buffer_declarations(ir_text)
    access_by_buffer: Dict[str, List[Dict[str, Any]]] = {k: [] for k in buffers}
    unknown_refs: List[str] = []
    for op in inventory.get("ops") or []:
        parent_loop = op.get("parent_loop")
        for io_kind, acc_kind in [("inputs", "read"), ("outputs", "write")]:
            for ref in op.get(io_kind) or []:
                var = ref.get("var")
                if not var:
                    continue
                if var not in buffers:
                    unknown_refs.append(var)
                    buffers.setdefault(var, {
                        "var": var,
                        "declaration_kind": "implicit_operand",
                        "decl_line": None,
                        "space": _norm_mem_space(ref.get("space", "unknown")),
                        "address_space_raw": ref.get("space", "unknown"),
                        "dims": [],
                        "dtype": "unknown",
                        "static_shape": False,
                        "size_bytes": None,
                        "buffer_role": _buffer_role_from_name(var, _norm_mem_space(ref.get("space", "unknown"))),
                    })
                    access_by_buffer.setdefault(var, [])
                access_by_buffer.setdefault(var, []).append({
                    "op_id": op.get("op_id"),
                    "line": op.get("line"),
                    "access": acc_kind,
                    "op_name": op.get("op_name"),
                    "role": op.get("role"),
                    "parent_loop": parent_loop,
                })

    records: List[Dict[str, Any]] = []
    peak_by_space: Dict[str, int] = {}
    static_known_bytes_by_space: Dict[str, int] = {}
    unknown_size_buffers: List[str] = []
    rewrite_blockers: List[Dict[str, Any]] = []
    for var, meta in sorted(buffers.items()):
        accesses = sorted(access_by_buffer.get(var, []), key=lambda x: (x.get("line") or 0, x.get("op_id") or -1))
        reads = [a for a in accesses if a.get("access") == "read"]
        writes = [a for a in accesses if a.get("access") == "write"]
        lines = [a.get("line") for a in accesses if a.get("line")]
        first_use = min(lines) if lines else None
        last_use = max(lines) if lines else None
        loops = sorted({(a.get("parent_loop") or {}).get("line") for a in accesses if a.get("parent_loop")})
        live_across_loop = bool(loops and first_use is not None and last_use is not None and first_use < last_use)
        size = meta.get("size_bytes")
        space = str(meta.get("space"))
        if space != "gm":
            if size is None:
                unknown_size_buffers.append(var)
            else:
                static_known_bytes_by_space[space] = static_known_bytes_by_space.get(space, 0) + int(size)
                # Conservative peak: all local buffers are treated as possibly live together.
                peak_by_space[space] = peak_by_space.get(space, 0) + int(size)
        role = meta.get("buffer_role")
        can_extend = bool(space in {"ub", "l1", "l0a", "l0b", "l0c"} and size is not None and role in {"stream_buffer", "softmax_or_score_buffer"})
        if role in {"accumulator", "output", "gm_output_or_boundary"}:
            rewrite_blockers.append({"buffer": var, "reason": f"{role} should not be hoisted/double-buffered without stronger proof"})
        records.append({
            **meta,
            "first_use_line": first_use,
            "last_use_line": last_use,
            "read_count": len(reads),
            "write_count": len(writes),
            "access_count": len(accesses),
            "loop_lines_touched": [x for x in loops if x is not None],
            "live_across_loop_approx": live_across_loop,
            "eligible_for_lifetime_extension_candidate": can_extend,
            "accesses": accesses,
        })

    capacity_by_space: Dict[str, Any] = {}
    for space, used in sorted(peak_by_space.items()):
        limit = _DEFAULT_LOCAL_LIMITS_BYTES.get(space)
        capacity_by_space[space] = {
            "conservative_peak_bytes": used,
            "default_limit_bytes": limit,
            "within_default_limit": (limit is None or used <= limit),
            "utilization": (round(used / limit, 6) if limit else None),
        }
    capacity_ok = all(v.get("within_default_limit", True) for v in capacity_by_space.values()) and not unknown_size_buffers
    return {
        "schema_version": "hivm_buffer_liveness_report_v1",
        "producer": "strategy_search_demo_v3.3.2_phase3b_buffer_liveness",
        "parser_mode": "conservative_line_scanner__future_target_vtriton_hivmopseditor",
        "buffer_count": len(records),
        "local_buffer_count": sum(1 for r in records if r.get("space") != "gm"),
        "gm_buffer_count": sum(1 for r in records if r.get("space") == "gm"),
        "capacity_recheck": {
            "policy": "conservative_sum_of_static_local_allocations",
            "default_limits_source": "Ascend 910B defaults from project hardware config; target backend should override with exact hardware JSON",
            "peak_by_space": capacity_by_space,
            "unknown_size_buffers": sorted(set(unknown_size_buffers)),
            "passed_conservative_capacity_recheck": capacity_ok,
        },
        "rewrite_implications": {
            "q_load_hoist": "allowed only if target buffer lifetime extension remains within capacity and dependency graph has no intervening overwrite",
            "real_double_buffer": "requires multiplying selected buffer size by nbuf and re-running this capacity gate",
            "real_cv_overlap": "requires stage buffer live ranges and event liveness beyond this approximation",
        },
        "rewrite_blockers": rewrite_blockers,
        "buffers": records,
        "limitations": [
            "Peak local bytes are over-approximated because this line scanner cannot prove non-overlapping lifetimes.",
            "Precise lifetime and alias proof require MLIR Operation walk / vTriton HivmOpsEditor.",
        ],
    }


def _gm_refs_for_op(op: Dict[str, Any]) -> List[Dict[str, Any]]:
    refs: List[Dict[str, Any]] = []
    for kind in ["inputs", "outputs"]:
        access = "read" if kind == "inputs" else "write"
        for ref in op.get(kind) or []:
            if _norm_mem_space(ref.get("space", "")) == "gm":
                refs.append({"var": ref.get("var"), "access": access, "kind": kind})
    return refs


def build_gm_alias_report(ir_text: str, inventory: Dict[str, Any]) -> Dict[str, Any]:
    """Build a conservative GM alias and round-trip candidate report.

    Phase-3B still does not delete GM traffic.  It only identifies exact same-GM
    store->load candidates and marks deletion as forbidden until MemorySSA-like
    proof and observable-boundary checks are added in Phase-3C.
    """
    buffers = _collect_buffer_declarations(ir_text)
    gm_buffers = {k: v for k, v in buffers.items() if v.get("space") == "gm"}
    gm_accesses: List[Dict[str, Any]] = []
    for op in inventory.get("ops") or []:
        for ref in _gm_refs_for_op(op):
            gm_accesses.append({
                "op_id": op.get("op_id"),
                "line": op.get("line"),
                "op_name": op.get("op_name"),
                "role": op.get("role"),
                "gm_var": ref.get("var"),
                "access": ref.get("access"),
                "parent_loop": op.get("parent_loop"),
                "text": op.get("text"),
            })
    by_var: Dict[str, List[Dict[str, Any]]] = {}
    for a in gm_accesses:
        by_var.setdefault(str(a.get("gm_var")), []).append(a)

    candidates: List[Dict[str, Any]] = []
    for var, accs in sorted(by_var.items()):
        ordered = sorted(accs, key=lambda x: (x.get("line") or 0, x.get("op_id") or -1))
        for i, a in enumerate(ordered):
            if a.get("access") != "write":
                continue
            for b in ordered[i + 1:]:
                if b.get("access") == "write":
                    break
                if b.get("access") == "read":
                    same_loop_depth = (a.get("parent_loop") or {}).get("line") == (b.get("parent_loop") or {}).get("line")
                    candidates.append({
                        "gm_var": var,
                        "store_op_id": a.get("op_id"),
                        "store_line": a.get("line"),
                        "load_op_id": b.get("op_id"),
                        "load_line": b.get("line"),
                        "same_loop_anchor_approx": same_loop_depth,
                        "alias_confidence": "exact_same_ssa_var_textual",
                        "delete_permission": False,
                        "deferred_reason": "Phase-3C must prove same address/offset, no intervening MemoryDef/Use/Phi, and non-observable GM boundary before deletion.",
                    })
                    break
    ambiguity: List[Dict[str, Any]] = []
    for var, meta in sorted(gm_buffers.items()):
        accs = by_var.get(var, [])
        if not accs:
            ambiguity.append({"gm_var": var, "reason": "declared GM buffer has no visible access in inventory"})
        if meta.get("buffer_role") == "gm_output_or_boundary":
            ambiguity.append({"gm_var": var, "reason": "GM output/boundary buffer is observable; deletion requires stronger proof"})
    return {
        "schema_version": "hivm_gm_alias_report_v1",
        "producer": "strategy_search_demo_v3.3.2_phase3b_buffer_liveness",
        "gm_buffer_count": len(gm_buffers),
        "gm_access_count": len(gm_accesses),
        "gm_access_counts_by_var": {k: len(v) for k, v in sorted(by_var.items())},
        "gm_roundtrip_candidate_count": len(candidates),
        "gm_roundtrip_candidates": candidates,
        "ambiguities": ambiguity,
        "deletion_unlocked": False,
        "required_next_gates": [
            "same-GM-base plus same static offset/slice proof",
            "MemorySSA-like reaching-definition proof",
            "no intervening unknown GM side effect",
            "observable output/boundary check",
        ],
        "gm_accesses": gm_accesses,
    }


def build_phase3b_analysis(ir_text: str, phase3a_reports: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build Phase-3B buffer liveness and GM alias artifacts."""
    if phase3a_reports and phase3a_reports.get("inventory"):
        inventory = phase3a_reports["inventory"]
    else:
        inventory = build_hivm_op_inventory(ir_text)
    buffer_liveness = build_buffer_liveness_report(ir_text, inventory)
    gm_alias = build_gm_alias_report(ir_text, inventory)
    blockers: List[str] = []
    cap = buffer_liveness.get("capacity_recheck", {})
    if not cap.get("passed_conservative_capacity_recheck", False):
        blockers.append("conservative local capacity recheck did not pass; lifetime-extending rewrites must remain blocked")
    if gm_alias.get("gm_roundtrip_candidate_count", 0) and not gm_alias.get("deletion_unlocked"):
        blockers.append("GM round-trip candidates exist but deletion is still deferred until Phase-3C alias/MemorySSA proof")
    summary = {
        "schema_version": "hivm_phase3b_analysis_summary_v1",
        "producer": "strategy_search_demo_v3.3.2_phase3b_buffer_liveness",
        "phase": "Phase-3B",
        "purpose": "Add memory correctness evidence before enabling GM deletion, Q-load hoist, double-buffer or CV overlap rewrites.",
        "buffer_liveness": {
            "buffer_count": buffer_liveness.get("buffer_count"),
            "local_buffer_count": buffer_liveness.get("local_buffer_count"),
            "gm_buffer_count": buffer_liveness.get("gm_buffer_count"),
            "capacity_recheck": buffer_liveness.get("capacity_recheck"),
        },
        "gm_alias": {
            "gm_buffer_count": gm_alias.get("gm_buffer_count"),
            "gm_access_count": gm_alias.get("gm_access_count"),
            "gm_roundtrip_candidate_count": gm_alias.get("gm_roundtrip_candidate_count"),
            "deletion_unlocked": gm_alias.get("deletion_unlocked"),
        },
        "rewrite_gates_unlocked": {
            "gm_roundtrip_deletion": False,
            "q_load_hoist_with_proof": False,
            "real_double_buffer": False,
            "real_cv_overlap": False,
            "real_tiling_loop_lowering": False,
        },
        "blockers": blockers,
        "next_phase3_steps": [
            "Phase-3C: add MemorySSA-like GM reaching-definition and observable-boundary gate.",
            "Phase-3D: add loop-invariant load hoist proof using dependency graph + buffer liveness + capacity recheck.",
            "Phase-3E: add tritonsim-hivm DES/trace validation comparison.",
        ],
    }
    return {"buffer_liveness": buffer_liveness, "gm_alias": gm_alias, "summary": summary}


def emit_phase3b_analysis_outputs(out: Path, ir_text: str, phase3a_reports: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Write Phase-3B analysis artifacts and return the summary."""
    reports = build_phase3b_analysis(ir_text, phase3a_reports)
    _write_json(out / "buffer_liveness_report.json", reports["buffer_liveness"])
    _write_json(out / "capacity_recheck_report.json", reports["buffer_liveness"].get("capacity_recheck", {}))
    _write_json(out / "gm_alias_report.json", reports["gm_alias"])
    _write_json(out / "phase3b_analysis_summary.json", reports["summary"])
    return reports["summary"]



# ---------------------------------------------------------------------------
# Phase-3C: GM MemorySSA-like checker / deletion decision gate
# ---------------------------------------------------------------------------

def _is_observable_gm_boundary(buffer_meta: Dict[str, Any]) -> bool:
    """Return whether a GM buffer should be treated as externally observable.

    Phase-3C remains conservative: function boundary GM buffers and names that
    look like outputs are observable.  Deleting stores/loads around them requires
    target-level proof that the memory traffic is not externally visible.
    """
    if not buffer_meta:
        return True
    if buffer_meta.get("declaration_kind") in {"boundary_or_operand", "implicit_operand"}:
        return True
    return buffer_meta.get("buffer_role") in {"gm_output_or_boundary", "gm_input_or_boundary"}


def _gm_accesses_by_line(inventory: Dict[str, Any]) -> List[Dict[str, Any]]:
    accesses: List[Dict[str, Any]] = []
    for op in inventory.get("ops") or []:
        for ref in _gm_refs_for_op(op):
            accesses.append({
                "op_id": op.get("op_id"),
                "line": op.get("line"),
                "op_name": op.get("op_name"),
                "role": op.get("role"),
                "gm_var": ref.get("var"),
                "access": ref.get("access"),
                "parent_loop": op.get("parent_loop"),
                "text": op.get("text"),
            })
    return sorted(accesses, key=lambda x: (x.get("line") or 0, x.get("op_id") or -1))


def build_gm_memory_ssa_report(ir_text: str, inventory: Dict[str, Any], gm_alias_report: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build a lightweight, conservative MemorySSA-like report for GM accesses.

    This does not use LLVM MemorySSA directly.  It mirrors the idea at HIVM-text
    level: GM stores are MemoryDef, GM loads are MemoryUse, and loop/unknown
    boundaries are treated as possible MemoryPhi/barriers.  The report is a
    proof gate for future GM traffic deletion; it is intentionally conservative.
    """
    buffers = _collect_buffer_declarations(ir_text)
    accesses = _gm_accesses_by_line(inventory)
    memory_events: List[Dict[str, Any]] = []
    last_def_by_var: Dict[str, Dict[str, Any]] = {}
    last_unknown_barrier_line: Optional[int] = None
    reaching_use_records: List[Dict[str, Any]] = []
    unknown_side_effects: List[Dict[str, Any]] = []

    # Unknown HIVM ops are considered possible GM side effects if they have an
    # unknown memory effect.  This blocks deletion across them.
    unknown_ops = [op for op in inventory.get("ops") or [] if op.get("known_semantics") is False]
    for op in unknown_ops:
        unknown_side_effects.append({"op_id": op.get("op_id"), "line": op.get("line"), "reason": "unknown HIVM op may have GM side effect", "op_name": op.get("op_name")})

    for acc in accesses:
        var = str(acc.get("gm_var"))
        meta = buffers.get(var, {})
        observable = _is_observable_gm_boundary(meta)
        if acc.get("access") == "write":
            ev = {
                "kind": "MemoryDef",
                "gm_var": var,
                "op_id": acc.get("op_id"),
                "line": acc.get("line"),
                "op_name": acc.get("op_name"),
                "observable_boundary": observable,
                "parent_loop": acc.get("parent_loop"),
                "text": acc.get("text"),
            }
            memory_events.append(ev)
            last_def_by_var[var] = ev
        elif acc.get("access") == "read":
            reaching = last_def_by_var.get(var)
            ev = {
                "kind": "MemoryUse",
                "gm_var": var,
                "op_id": acc.get("op_id"),
                "line": acc.get("line"),
                "op_name": acc.get("op_name"),
                "observable_boundary": observable,
                "reaching_def_op_id": reaching.get("op_id") if reaching else None,
                "reaching_def_line": reaching.get("line") if reaching else None,
                "unique_reaching_def": bool(reaching),
                "blocked_by_observable_boundary": observable or bool(reaching and reaching.get("observable_boundary")),
                "blocked_by_unknown_side_effect": False,
                "parent_loop": acc.get("parent_loop"),
                "text": acc.get("text"),
            }
            # Any unknown side-effect line between reaching def and use blocks deletion.
            if reaching:
                lo, hi = reaching.get("line") or -1, acc.get("line") or -1
                ev["blocked_by_unknown_side_effect"] = any((u.get("line") or -1) > lo and (u.get("line") or -1) < hi for u in unknown_side_effects)
            memory_events.append(ev)
            reaching_use_records.append(ev)

    candidates = list((gm_alias_report or {}).get("gm_roundtrip_candidates") or [])
    for c in candidates:
        use = next((u for u in reaching_use_records if u.get("op_id") == c.get("load_op_id") and u.get("reaching_def_op_id") == c.get("store_op_id")), None)
        c["memory_ssa_gate"] = {
            "unique_reaching_def": bool(use and use.get("unique_reaching_def")),
            "blocked_by_unknown_side_effect": bool(use and use.get("blocked_by_unknown_side_effect")),
            "blocked_by_observable_boundary": bool(use and use.get("blocked_by_observable_boundary", True)),
            "status": "passed" if (use and use.get("unique_reaching_def") and not use.get("blocked_by_unknown_side_effect") and not use.get("blocked_by_observable_boundary")) else "failed_or_deferred",
        }

    return {
        "schema_version": "hivm_gm_memory_ssa_report_v1",
        "producer": "strategy_search_demo_v3.3.2_phase3c_gm_memoryssa_gate",
        "policy": "conservative_memoryssa_like_text_gate__future_target_mlir_analysis",
        "gm_access_count": len(accesses),
        "memory_event_count": len(memory_events),
        "unknown_side_effect_count": len(unknown_side_effects),
        "unique_reaching_use_count": sum(1 for u in reaching_use_records if u.get("unique_reaching_def")),
        "candidate_count": len(candidates),
        "candidate_memoryssa_updates": candidates,
        "memory_events": memory_events,
        "unknown_side_effects": unknown_side_effects,
        "limitations": [
            "This is a MemorySSA-like conservative report, not LLVM/MLIR MemorySSA.",
            "Static offset/slice equivalence is not yet proven; same SSA GM var is not enough for deletion.",
            "Function-boundary GM buffers are treated as observable unless target backend proves otherwise.",
        ],
    }


def build_gm_roundtrip_deletion_decision_report(
    ir_text: str,
    inventory: Dict[str, Any],
    gm_alias_report: Dict[str, Any],
    gm_memory_ssa_report: Dict[str, Any],
) -> Dict[str, Any]:
    """Decide whether each GM round-trip candidate is deletable.

    Phase-3C still defaults to no deletion.  A candidate may become a future
    deletion candidate only if all gates are passed.  Current gate set is stricter
    than Phase-3B but still lacks target offset/slice proof, so most real inputs
    remain deferred.
    """
    candidates = list(gm_alias_report.get("gm_roundtrip_candidates") or [])
    memory_updates = {(c.get("store_op_id"), c.get("load_op_id")): c.get("memory_ssa_gate", {}) for c in gm_memory_ssa_report.get("candidate_memoryssa_updates") or []}
    decisions: List[Dict[str, Any]] = []
    allowed = 0
    deferred = 0
    for c in candidates:
        mem_gate = memory_updates.get((c.get("store_op_id"), c.get("load_op_id")), {})
        gates = {
            "same_textual_gm_var": bool(c.get("alias_confidence") == "exact_same_ssa_var_textual"),
            "same_static_offset_slice_proven": False,  # requires target parser / index analysis
            "memoryssa_unique_reaching_def": bool(mem_gate.get("unique_reaching_def")),
            "no_unknown_side_effect": not bool(mem_gate.get("blocked_by_unknown_side_effect")),
            "not_observable_boundary": not bool(mem_gate.get("blocked_by_observable_boundary", True)),
        }
        delete_allowed = all(gates.values())
        if delete_allowed:
            allowed += 1
            status = "allowed_by_phase3c_gate"
            reason = "all conservative gates passed"
        else:
            deferred += 1
            status = "deferred"
            failed = [k for k, v in gates.items() if not v]
            reason = "blocked gates: " + ", ".join(failed)
        decisions.append({
            "gm_var": c.get("gm_var"),
            "store_op_id": c.get("store_op_id"),
            "store_line": c.get("store_line"),
            "load_op_id": c.get("load_op_id"),
            "load_line": c.get("load_line"),
            "gates": gates,
            "decision": status,
            "delete_permission": delete_allowed,
            "reason": reason,
        })
    return {
        "schema_version": "hivm_gm_roundtrip_deletion_decision_v1",
        "producer": "strategy_search_demo_v3.3.2_phase3c_gm_memoryssa_gate",
        "candidate_count": len(candidates),
        "delete_allowed_count": allowed,
        "deferred_count": deferred,
        "deletion_unlocked": allowed > 0,
        "decisions": decisions,
        "global_policy": "delete only if same-address/slice, MemorySSA, side-effect and observable-boundary gates all pass",
        "current_phase_note": "Phase-3C introduces the decision gate. It does not force deletion when target offset/slice proof is missing.",
    }


def build_rewrite_legality_gate_report(
    inventory: Dict[str, Any],
    dependency_graph: Dict[str, Any],
    event_liveness: Dict[str, Any],
    buffer_liveness: Dict[str, Any],
    gm_alias_report: Dict[str, Any],
    gm_memory_ssa_report: Dict[str, Any],
    gm_deletion_decision: Dict[str, Any],
) -> Dict[str, Any]:
    """Aggregate Phase-3 legality gates for future dangerous rewrites."""
    cap = buffer_liveness.get("capacity_recheck", {}) if buffer_liveness else {}
    unknown_ops = int(inventory.get("unknown_op_count", 0) or 0)
    event_ok = bool(event_liveness.get("passed_local_event_liveness", False))
    capacity_ok = bool(cap.get("passed_conservative_capacity_recheck", False))
    dep_edges = dependency_graph.get("edge_counts", {}) if dependency_graph else {}
    return {
        "schema_version": "hivm_rewrite_legality_gate_report_v1",
        "producer": "strategy_search_demo_v3.3.2_phase3c_gm_memoryssa_gate",
        "global_principle": "cannot prove safe -> do not rewrite",
        "base_gates": {
            "known_op_semantics": unknown_ops == 0,
            "local_event_liveness": event_ok,
            "conservative_capacity_recheck": capacity_ok,
            "dependency_graph_available": bool(dependency_graph.get("edge_count", 0) >= 0),
            "gm_memoryssa_available": gm_memory_ssa_report.get("schema_version") == "hivm_gm_memory_ssa_report_v1",
        },
        "rewrite_gate_status": {
            "barrier_or_sync_local_rewrite_audit": event_ok,
            "gm_roundtrip_deletion": bool(gm_deletion_decision.get("deletion_unlocked")),
            "q_load_hoist_with_proof": False,
            "real_double_buffer": False,
            "real_cv_overlap": False,
            "real_tiling_loop_lowering": False,
        },
        "why_still_locked": {
            "q_load_hoist_with_proof": "requires loop-invariance proof, no intervening overwrite, event coverage and capacity recheck after lifetime extension",
            "real_double_buffer": "requires per-buffer duplication footprint, producer/consumer schedule, event liveness and UB/L1 capacity after nbuf multiplier",
            "real_cv_overlap": "requires stage graph, stage buffer liveness, event allocation and trace validation",
            "real_tiling_loop_lowering": "requires loop/index/subview/reduction/tail legality proof",
        },
        "evidence_summary": {
            "unknown_op_count": unknown_ops,
            "dependency_edge_counts": dep_edges,
            "event_count": event_liveness.get("event_count"),
            "buffer_count": buffer_liveness.get("buffer_count"),
            "gm_roundtrip_candidate_count": gm_alias_report.get("gm_roundtrip_candidate_count"),
            "gm_deletion_allowed_count": gm_deletion_decision.get("delete_allowed_count"),
        },
    }


def build_phase3c_analysis(ir_text: str, phase3a_reports: Optional[Dict[str, Any]] = None, phase3b_reports: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build Phase-3C GM MemorySSA-like reports and aggregate legality gates."""
    phase3a_reports = phase3a_reports or build_phase3a_analysis(ir_text)
    inventory = phase3a_reports.get("inventory") or build_hivm_op_inventory(ir_text)
    dependency_graph = phase3a_reports.get("dependency_graph") or build_dependency_graph(inventory)
    event_liveness = phase3a_reports.get("event_liveness") or build_event_liveness_report(inventory)
    phase3b_reports = phase3b_reports or build_phase3b_analysis(ir_text, {"inventory": inventory})
    buffer_liveness = phase3b_reports.get("buffer_liveness") or build_buffer_liveness_report(ir_text, inventory)
    gm_alias = phase3b_reports.get("gm_alias") or build_gm_alias_report(ir_text, inventory)
    gm_memory_ssa = build_gm_memory_ssa_report(ir_text, inventory, gm_alias)
    gm_decision = build_gm_roundtrip_deletion_decision_report(ir_text, inventory, gm_alias, gm_memory_ssa)
    gate = build_rewrite_legality_gate_report(inventory, dependency_graph, event_liveness, buffer_liveness, gm_alias, gm_memory_ssa, gm_decision)
    summary = {
        "schema_version": "hivm_phase3c_analysis_summary_v1",
        "producer": "strategy_search_demo_v3.3.2_phase3c_gm_memoryssa_gate",
        "phase": "Phase-3C",
        "purpose": "Add MemorySSA-like GM reaching-definition and deletion decision gates before any GM round-trip deletion.",
        "gm_memory_ssa": {
            "gm_access_count": gm_memory_ssa.get("gm_access_count"),
            "memory_event_count": gm_memory_ssa.get("memory_event_count"),
            "unknown_side_effect_count": gm_memory_ssa.get("unknown_side_effect_count"),
            "candidate_count": gm_memory_ssa.get("candidate_count"),
        },
        "gm_roundtrip_deletion_decision": {
            "candidate_count": gm_decision.get("candidate_count"),
            "delete_allowed_count": gm_decision.get("delete_allowed_count"),
            "deferred_count": gm_decision.get("deferred_count"),
            "deletion_unlocked": gm_decision.get("deletion_unlocked"),
        },
        "rewrite_gates_unlocked": gate.get("rewrite_gate_status", {}),
        "next_phase3_steps": [
            "Phase-3D: prove loop-invariant load hoist with dependency/buffer/event/capacity gates.",
            "Phase-3E: run tritonsim-hivm DES/trace validation comparison.",
            "Phase-3F: close Phase 3 and decide whether Phase 4 can enable real double-buffer/CV overlap prototypes.",
        ],
    }
    return {"gm_memory_ssa": gm_memory_ssa, "gm_deletion_decision": gm_decision, "rewrite_legality_gate": gate, "summary": summary}


def emit_phase3c_analysis_outputs(out: Path, ir_text: str, phase3a_reports: Optional[Dict[str, Any]] = None, phase3b_reports: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Write Phase-3C GM MemorySSA / deletion-decision artifacts."""
    reports = build_phase3c_analysis(ir_text, phase3a_reports, phase3b_reports)
    _write_json(out / "gm_memory_ssa_report.json", reports["gm_memory_ssa"])
    _write_json(out / "gm_roundtrip_deletion_decision.json", reports["gm_deletion_decision"])
    _write_json(out / "rewrite_legality_gate_report.json", reports["rewrite_legality_gate"])
    _write_json(out / "phase3c_analysis_summary.json", reports["summary"])
    return reports["summary"]



# ---------------------------------------------------------------------------
# Phase-3D: loop-invariant load hoist proof gate
# ---------------------------------------------------------------------------

def _name_looks_like_q_stream(var: str) -> bool:
    name = str(var or "").lstrip("%").lower()
    return name.startswith("q") or "q_" in name or name in {"q", "qgm", "q_gm", "q_ub", "q_l1"}


def _local_written_buffers_by_loop(inventory: Dict[str, Any]) -> Dict[int, Dict[str, List[int]]]:
    """Map parent-loop line -> buffer var -> writer op ids inside that loop."""
    out: Dict[int, Dict[str, List[int]]] = {}
    for op in inventory.get("ops") or []:
        loop = op.get("parent_loop") or {}
        loop_line = loop.get("line")
        if loop_line is None:
            continue
        for ref in op.get("outputs") or []:
            var = ref.get("var")
            if not var:
                continue
            out.setdefault(int(loop_line), {}).setdefault(var, []).append(int(op.get("op_id")))
    return out


def _ops_by_id(inventory: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    return {int(op.get("op_id")): op for op in inventory.get("ops") or [] if op.get("op_id") is not None}


def build_loop_invariant_load_hoist_report(
    ir_text: str,
    inventory: Dict[str, Any],
    dependency_graph: Dict[str, Any],
    event_liveness: Dict[str, Any],
    buffer_liveness: Dict[str, Any],
) -> Dict[str, Any]:
    """Find conservative loop-invariant Q/stream load-hoist candidates.

    This is a proof report, not a mutation pass.  A candidate is considered only
    when a GM->local load appears inside a loop and the line text does not depend
    on the visible loop induction variable.  The report then checks whether the
    local destination buffer is overwritten elsewhere in the same loop, whether
    local event liveness is clean, and whether the conservative capacity gate
    still passes.  Target MLIR/vTriton verification remains required before a
    production hoist because line-level parsing cannot prove dominance or exact
    region boundaries.
    """
    ops = list(inventory.get("ops") or [])
    op_by_id = _ops_by_id(inventory)
    writes_by_loop = _local_written_buffers_by_loop(inventory)
    capacity = (buffer_liveness or {}).get("capacity_recheck", {})
    capacity_ok = bool(capacity.get("passed_conservative_capacity_recheck", False))
    event_ok = bool((event_liveness or {}).get("passed_local_event_liveness", False))
    dep_edges = list((dependency_graph or {}).get("edges") or [])

    candidates: List[Dict[str, Any]] = []
    for op in ops:
        if op.get("role") != "load":
            continue
        loop = op.get("parent_loop") or {}
        if loop.get("line") is None:
            continue
        gm_inputs = [r for r in op.get("inputs") or [] if _norm_mem_space(r.get("space", "")) == "gm"]
        local_outputs = [r for r in op.get("outputs") or [] if _norm_mem_space(r.get("space", "")) != "gm"]
        if not gm_inputs or not local_outputs:
            continue
        # Phase-3D initially focuses on Q/stream-like hoist because FA-style Q
        # load is the common invariant load across the KV loop.  K/V loads are
        # usually loop-variant and should not be hoisted by name heuristic.
        if not any(_name_looks_like_q_stream(r.get("var", "")) for r in gm_inputs + local_outputs):
            continue
        induction = str(loop.get("induction") or "")
        text = str(op.get("text") or "")
        loop_invariant_by_text = bool(induction) and induction not in text
        dst_vars = [r.get("var") for r in local_outputs if r.get("var")]
        writer_conflicts: List[Dict[str, Any]] = []
        loop_writes = writes_by_loop.get(int(loop.get("line")), {})
        for dst in dst_vars:
            writers = [w for w in loop_writes.get(dst, []) if w != int(op.get("op_id"))]
            if writers:
                writer_conflicts.append({"buffer": dst, "other_writer_op_ids_in_same_loop": writers})
        # RAW/WAW/WAR edges involving destination buffers are evidence to keep in
        # the decision report.  They are not automatically blockers unless they
        # reveal a same-loop overwrite, because exact motion legality requires a
        # structured parser.
        relevant_edges = [e for e in dep_edges if e.get("resource") in dst_vars]
        candidate = {
            "candidate_id": len(candidates),
            "load_op_id": op.get("op_id"),
            "load_line": op.get("line"),
            "parent_loop": loop,
            "gm_inputs": gm_inputs,
            "local_outputs": local_outputs,
            "loop_induction": induction,
            "loop_invariant_by_text": loop_invariant_by_text,
            "writer_conflicts_in_loop": writer_conflicts,
            "capacity_after_lifetime_extension_ok_conservative": capacity_ok,
            "event_liveness_ok": event_ok,
            "relevant_dependency_edges": relevant_edges[:20],
            "text": op.get("text"),
        }
        # Try to attach a following layout conversion from q_ub -> q_l1 in same loop.
        following_layout: Optional[Dict[str, Any]] = None
        for later in ops:
            if int(later.get("op_id")) <= int(op.get("op_id")):
                continue
            if (later.get("parent_loop") or {}).get("line") != loop.get("line"):
                continue
            if later.get("role") != "layout":
                continue
            later_inputs = {r.get("var") for r in later.get("inputs") or []}
            if any(dst in later_inputs for dst in dst_vars):
                following_layout = {"op_id": later.get("op_id"), "line": later.get("line"), "op_name": later.get("op_name"), "outputs": later.get("outputs"), "text": later.get("text")}
                break
        if following_layout:
            candidate["following_layout_candidate"] = following_layout
        candidates.append(candidate)

    return {
        "schema_version": "hivm_loop_invariant_load_hoist_report_v1",
        "producer": "strategy_search_demo_v3.3.2_phase3d_load_hoist_proof",
        "policy": "proof_report_only__no_default_mutation",
        "candidate_count": len(candidates),
        "candidates": candidates,
        "global_requirements": [
            "GM load must be inside a loop and not reference the visible induction variable.",
            "The destination local buffer must not be overwritten elsewhere in the same loop.",
            "Local event liveness must be clean.",
            "Conservative capacity recheck must pass after lifetime extension.",
            "Target MLIR/vTriton parser must confirm dominance, exact region boundaries and buffer lifetime before production mutation.",
        ],
        "limitations": [
            "This scanner cannot prove exact affine dependence on loop IVs.",
            "This scanner cannot prove dominance or region motion legality.",
            "Capacity is conservative allocation-sum, not exact interval overlap.",
        ],
    }


def build_q_load_hoist_decision_report(
    hoist_report: Dict[str, Any],
    inventory: Dict[str, Any],
    dependency_graph: Dict[str, Any],
    event_liveness: Dict[str, Any],
    buffer_liveness: Dict[str, Any],
) -> Dict[str, Any]:
    """Convert hoist candidates into explicit allow/defer decisions."""
    decisions: List[Dict[str, Any]] = []
    allowed = 0
    deferred = 0
    for cand in hoist_report.get("candidates") or []:
        gates = {
            "q_or_stream_load_anchor_found": True,
            "inside_loop": bool((cand.get("parent_loop") or {}).get("line") is not None),
            "loop_invariant_by_visible_text": bool(cand.get("loop_invariant_by_text")),
            "no_same_loop_destination_overwrite": not bool(cand.get("writer_conflicts_in_loop")),
            "event_liveness_ok": bool(cand.get("event_liveness_ok")),
            "capacity_after_lifetime_extension_ok": bool(cand.get("capacity_after_lifetime_extension_ok_conservative")),
            "target_parser_region_motion_proof": False,
        }
        # Phase-3D deliberately keeps production mutation locked until a target
        # parser confirms dominance/region motion.  We can still mark the local
        # proof as passed for ranking and future backend handoff.
        local_proof_passed = all(v for k, v in gates.items() if k != "target_parser_region_motion_proof")
        delete_or_hoist_allowed = local_proof_passed and gates["target_parser_region_motion_proof"]
        if delete_or_hoist_allowed:
            allowed += 1
            status = "allow"
            reason = "all local and target parser gates passed"
        else:
            deferred += 1
            status = "deferred"
            missing = [k for k, v in gates.items() if not v]
            reason = "missing gate(s): " + ", ".join(missing)
        decisions.append({
            "candidate_id": cand.get("candidate_id"),
            "load_op_id": cand.get("load_op_id"),
            "load_line": cand.get("load_line"),
            "decision": status,
            "local_proof_passed": local_proof_passed,
            "hoist_allowed": delete_or_hoist_allowed,
            "gates": gates,
            "reason": reason,
            "recommended_backend_action": "emit_to_vtriton_hivmopseditor_for_region_motion_proof" if local_proof_passed else "keep_as_noop_or_hint",
        })
    return {
        "schema_version": "hivm_q_load_hoist_decision_v1",
        "producer": "strategy_search_demo_v3.3.2_phase3d_load_hoist_proof",
        "candidate_count": len(decisions),
        "local_proof_passed_count": sum(1 for d in decisions if d.get("local_proof_passed")),
        "hoist_allowed_count": allowed,
        "deferred_count": deferred,
        "hoist_unlocked": allowed > 0,
        "decisions": decisions,
        "global_policy": "local proof can nominate a candidate, but production hoist requires target parser region-motion proof",
    }


def build_phase3d_analysis(ir_text: str, phase3a_reports: Optional[Dict[str, Any]] = None, phase3b_reports: Optional[Dict[str, Any]] = None, phase3c_reports: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build Phase-3D loop-invariant load-hoist proof reports."""
    phase3a_reports = phase3a_reports or build_phase3a_analysis(ir_text)
    inventory = phase3a_reports.get("inventory") or build_hivm_op_inventory(ir_text)
    dependency_graph = phase3a_reports.get("dependency_graph") or build_dependency_graph(inventory)
    event_liveness = phase3a_reports.get("event_liveness") or build_event_liveness_report(inventory)
    phase3b_reports = phase3b_reports or build_phase3b_analysis(ir_text, {"inventory": inventory})
    buffer_liveness = phase3b_reports.get("buffer_liveness") or build_buffer_liveness_report(ir_text, inventory)
    hoist_report = build_loop_invariant_load_hoist_report(ir_text, inventory, dependency_graph, event_liveness, buffer_liveness)
    decision = build_q_load_hoist_decision_report(hoist_report, inventory, dependency_graph, event_liveness, buffer_liveness)
    summary = {
        "schema_version": "hivm_phase3d_analysis_summary_v1",
        "producer": "strategy_search_demo_v3.3.2_phase3d_load_hoist_proof",
        "phase": "Phase-3D",
        "purpose": "Add loop-invariant load-hoist proof gates without enabling default mutation.",
        "hoist_candidates": {
            "candidate_count": hoist_report.get("candidate_count"),
            "local_proof_passed_count": decision.get("local_proof_passed_count"),
            "hoist_allowed_count": decision.get("hoist_allowed_count"),
            "hoist_unlocked": decision.get("hoist_unlocked"),
        },
        "rewrite_gates_unlocked": {
            "q_load_hoist_with_local_proof": decision.get("local_proof_passed_count", 0) > 0,
            "q_load_hoist_production_mutation": bool(decision.get("hoist_unlocked")),
            "real_double_buffer": False,
            "real_cv_overlap": False,
            "real_tiling_loop_lowering": False,
        },
        "next_phase3_steps": [
            "Phase-3E: add tritonsim-hivm DES/trace validation wrapper and comparison report.",
            "Phase-3F: close Phase 3 and decide which proven candidates can enter Phase 4 mutation prototypes.",
        ],
    }
    return {"loop_invariant_load_hoist": hoist_report, "q_load_hoist_decision": decision, "summary": summary}


def emit_phase3d_analysis_outputs(out: Path, ir_text: str, phase3a_reports: Optional[Dict[str, Any]] = None, phase3b_reports: Optional[Dict[str, Any]] = None, phase3c_reports: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Write Phase-3D hoist proof artifacts."""
    reports = build_phase3d_analysis(ir_text, phase3a_reports, phase3b_reports, phase3c_reports)
    _write_json(out / "loop_invariant_load_hoist_report.json", reports["loop_invariant_load_hoist"])
    _write_json(out / "q_load_hoist_decision.json", reports["q_load_hoist_decision"])
    _write_json(out / "phase3d_analysis_summary.json", reports["summary"])
    return reports["summary"]


def _safe_load_json_file(path: Optional[str]) -> Optional[Any]:
    if not path:
        return None
    p = Path(path)
    if not p.exists() or not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _des_graph_brief(path: Optional[str]) -> Dict[str, Any]:
    """Best-effort DES graph summary for vTriton-generated JSON artifacts."""
    p = Path(path) if path else None
    exists = bool(p and p.exists())
    payload = _safe_load_json_file(str(p)) if exists else None
    node_count = edge_count = None
    if isinstance(payload, dict):
        for key in ("nodes", "ops", "vertices"):
            if isinstance(payload.get(key), list):
                node_count = len(payload.get(key) or [])
                break
        for key in ("edges", "deps", "dependencies"):
            if isinstance(payload.get(key), list):
                edge_count = len(payload.get(key) or [])
                break
    elif isinstance(payload, list):
        node_count = len(payload)
    return {
        "path": str(p) if p else None,
        "exists": exists,
        "json_parse_ok": payload is not None if exists else False,
        "node_count": node_count,
        "edge_count": edge_count,
        "note": "best-effort schema-agnostic DES summary; exact interpretation depends on local vTriton build",
    }


def _trace_artifact_brief(path: Optional[str]) -> Dict[str, Any]:
    p = Path(path) if path else None
    exists = bool(p and p.exists())
    size = p.stat().st_size if exists else 0
    payload = _safe_load_json_file(str(p)) if exists and size < 200 * 1024 * 1024 else None
    event_count = None
    if isinstance(payload, dict):
        for key in ("traceEvents", "events", "displayTimeUnit"):
            if key == "displayTimeUnit":
                continue
            if isinstance(payload.get(key), list):
                event_count = len(payload.get(key) or [])
                break
    elif isinstance(payload, list):
        event_count = len(payload)
    return {
        "path": str(p) if p else None,
        "exists": exists,
        "size_bytes": size,
        "json_parse_ok": payload is not None if exists and size else False,
        "event_count": event_count,
        "note": "best-effort trace artifact summary; Perfetto/Chrome trace schemas vary by vTriton build",
    }


def build_phase3e_validation_report(
    original_ir_text: str,
    optimized_ir_text: str,
    tritonsim_validation_report: Optional[Dict[str, Any]] = None,
    structural_validation_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build Phase-3E DES/trace validation-wrapper artifacts.

    This function does not require a local vTriton binary. If the wrapper was
    not run, it emits a pending status and the exact expected artifacts. If it
    was run, it summarizes return codes and generated DES/trace files. It also
    compares local inventory/dependency summaries for original and optimized IR
    so reports remain useful even before external DES/trace is available.
    """
    original_a = build_phase3a_analysis(original_ir_text)
    optimized_a = build_phase3a_analysis(optimized_ir_text)
    tr = tritonsim_validation_report or {}
    input_run = tr.get("input_ir") or {}
    opt_run = tr.get("optimized_structural_ir") or {}
    original_des = _des_graph_brief(input_run.get("des_graph_file") or input_run.get("expected_des_graph_file"))
    optimized_des = _des_graph_brief(opt_run.get("des_graph_file") or opt_run.get("expected_des_graph_file"))
    original_trace = _trace_artifact_brief(input_run.get("perfetto_trace_file") or input_run.get("expected_perfetto_trace_file"))
    optimized_trace = _trace_artifact_brief(opt_run.get("perfetto_trace_file") or opt_run.get("expected_perfetto_trace_file"))

    ran_both = bool(input_run.get("ran")) and bool(opt_run.get("ran"))
    returncode_ok = (input_run.get("returncode") == 0 and opt_run.get("returncode") == 0) if ran_both else False
    artifacts_exist = bool(original_des.get("exists") and optimized_des.get("exists") and original_trace.get("exists") and optimized_trace.get("exists"))
    status = "passed_external_des_trace_validation" if (ran_both and returncode_ok and artifacts_exist) else "pending_or_failed_external_des_trace_validation"
    reasons: List[str] = []
    if not ran_both:
        reasons.append("tritonsim-hivm was not run for both original and optimized IR")
    if ran_both and not returncode_ok:
        reasons.append("tritonsim-hivm returned non-zero for original or optimized IR")
    if ran_both and not artifacts_exist:
        reasons.append("DES graph and/or Perfetto trace artifacts were not generated for both IRs")

    original_inv = (original_a.get("inventory") or {})
    optimized_inv = (optimized_a.get("inventory") or {})
    original_dep = (original_a.get("dependency_graph") or {})
    optimized_dep = (optimized_a.get("dependency_graph") or {})
    local_delta = {
        "op_count_delta": int(optimized_inv.get("op_count") or 0) - int(original_inv.get("op_count") or 0),
        "dependency_edge_count_delta": int(optimized_dep.get("edge_count") or 0) - int(original_dep.get("edge_count") or 0),
        "unknown_op_count_delta": int(optimized_inv.get("unknown_op_count") or 0) - int(original_inv.get("unknown_op_count") or 0),
    }

    return {
        "schema_version": "hivm_phase3e_des_trace_validation_report_v1",
        "producer": "strategy_search_demo_v3.3.2_phase3e_vtriton_validation_wrapper",
        "phase": "Phase-3E",
        "purpose": "Connect original/optimized HIVM IR to tritonsim-hivm DES/Perfetto validation without claiming speedup unless external artifacts exist.",
        "validation_status": status,
        "reasons": reasons,
        "external_tritonsim": {
            "input_ir": input_run,
            "optimized_structural_ir": opt_run,
            "ran_both": ran_both,
            "returncode_ok": returncode_ok,
        },
        "des_graph_artifacts": {
            "original": original_des,
            "optimized": optimized_des,
        },
        "perfetto_trace_artifacts": {
            "original": original_trace,
            "optimized": optimized_trace,
        },
        "local_inventory_comparison": {
            "original": {"op_count": original_inv.get("op_count"), "unknown_op_count": original_inv.get("unknown_op_count"), "role_counts": original_inv.get("role_counts")},
            "optimized": {"op_count": optimized_inv.get("op_count"), "unknown_op_count": optimized_inv.get("unknown_op_count"), "role_counts": optimized_inv.get("role_counts")},
            "delta": local_delta,
        },
        "local_dependency_comparison": {
            "original": {"edge_count": original_dep.get("edge_count"), "edge_counts": original_dep.get("edge_counts")},
            "optimized": {"edge_count": optimized_dep.get("edge_count"), "edge_counts": optimized_dep.get("edge_counts")},
        },
        "structural_validation_summary": structural_validation_summary or {},
        "interpretation": {
            "what_this_proves_if_passed": "Both original and optimized IR were accepted by the configured tritonsim-hivm command and DES/Perfetto artifacts were generated for comparison.",
            "what_this_does_not_prove": "It still does not prove numerical correctness or msprof real-hardware speedup; those remain target runtime/profile validations.",
            "safe_policy": "If external validation is missing or failed, dangerous Phase-4 mutations remain locked.",
        },
    }


def build_trace_comparison_html(report: Dict[str, Any]) -> str:
    """Render a compact human-readable Phase-3E comparison report."""
    def esc(x: Any) -> str:
        return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    status = report.get("validation_status")
    reasons = report.get("reasons") or []
    local = report.get("local_inventory_comparison") or {}
    deps = report.get("local_dependency_comparison") or {}
    des = report.get("des_graph_artifacts") or {}
    trace = report.get("perfetto_trace_artifacts") or {}
    rows = []
    for name, obj in [("Original DES", (des.get("original") or {})), ("Optimized DES", (des.get("optimized") or {})), ("Original Trace", (trace.get("original") or {})), ("Optimized Trace", (trace.get("optimized") or {}))]:
        rows.append(f"<tr><td>{esc(name)}</td><td>{esc(obj.get('exists'))}</td><td>{esc(obj.get('path'))}</td><td>{esc(obj.get('node_count') or obj.get('event_count') or '')}</td></tr>")
    return f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><title>Phase-3E vTriton DES/Trace Validation</title>
<style>body{{font-family:Arial,sans-serif;line-height:1.45;margin:24px}} table{{border-collapse:collapse}} td,th{{border:1px solid #ccc;padding:6px 10px}} code{{background:#f5f5f5;padding:2px 4px}}</style></head>
<body>
<h1>Phase-3E vTriton DES / Trace Validation</h1>
<p><b>Status:</b> <code>{esc(status)}</code></p>
<h2>Reasons / Pending items</h2>
<ul>{''.join('<li>'+esc(r)+'</li>' for r in reasons) if reasons else '<li>None</li>'}</ul>
<h2>Artifacts</h2>
<table><tr><th>Artifact</th><th>Exists</th><th>Path</th><th>Nodes / Events</th></tr>{''.join(rows)}</table>
<h2>Local inventory comparison</h2>
<pre>{esc(json.dumps(local, ensure_ascii=False, indent=2))}</pre>
<h2>Local dependency comparison</h2>
<pre>{esc(json.dumps(deps, ensure_ascii=False, indent=2))}</pre>
<p>Note: this HTML is an audit/validation wrapper. Real performance claims still require target compiler/runtime correctness checks and msprof.</p>
</body></html>"""


def emit_phase3e_validation_outputs(
    out: Path,
    original_ir_text: str,
    optimized_ir_text: str,
    tritonsim_validation_report: Optional[Dict[str, Any]] = None,
    structural_validation_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Write Phase-3E vTriton DES/trace validation-wrapper outputs."""
    report = build_phase3e_validation_report(original_ir_text, optimized_ir_text, tritonsim_validation_report, structural_validation_summary)
    summary = {
        "schema_version": "hivm_phase3e_analysis_summary_v1",
        "producer": "strategy_search_demo_v3.3.2_phase3e_vtriton_validation_wrapper",
        "phase": "Phase-3E",
        "validation_status": report.get("validation_status"),
        "external_tritonsim_ran_both": (report.get("external_tritonsim") or {}).get("ran_both"),
        "external_tritonsim_returncode_ok": (report.get("external_tritonsim") or {}).get("returncode_ok"),
        "des_trace_artifacts_available": bool(((report.get("des_graph_artifacts") or {}).get("original") or {}).get("exists") and ((report.get("des_graph_artifacts") or {}).get("optimized") or {}).get("exists") and ((report.get("perfetto_trace_artifacts") or {}).get("original") or {}).get("exists") and ((report.get("perfetto_trace_artifacts") or {}).get("optimized") or {}).get("exists")),
        "phase4_mutation_gates": {
            "real_gm_roundtrip_deletion": False,
            "q_load_hoist_production_mutation": False,
            "real_double_buffer": False,
            "full_cv_overlap": False,
            "real_tiling_loop_lowering": False,
        },
        "next_phase3_steps": [
            "Phase-3F: close Phase 3 and decide which locally proven candidates are eligible for Phase 4 prototype mutation.",
            "Run with --run-vtriton-validation --tritonsim-hivm /path/to/tritonsim-hivm in a real vTriton build to generate DES/Perfetto artifacts.",
        ],
    }
    _write_json(out / "vtriton_des_trace_validation_report.json", report)
    _write_json(out / "phase3e_analysis_summary.json", summary)
    (out / "trace_comparison_report.html").write_text(build_trace_comparison_html(report), encoding="utf-8")
    return summary

def build_phase3a_analysis(ir_text: str) -> Dict[str, Any]:
    """Build all Phase-3A analysis artifacts in memory."""
    inventory = build_hivm_op_inventory(ir_text)
    dep_graph = build_dependency_graph(inventory)
    event_liveness = build_event_liveness_report(inventory)
    blockers: List[str] = []
    if inventory.get("unknown_op_count", 0):
        blockers.append("unknown HIVM ops present; dangerous rewrites must skip or require target semantics")
    if not event_liveness.get("passed_local_event_liveness", False):
        blockers.append("event liveness has warnings; sync deletion/motion/event reuse is not allowed")
    summary = {
        "schema_version": "hivm_phase3a_analysis_summary_v1",
        "producer": "strategy_search_demo_v3.3.2_phase3a_dependency_foundation",
        "phase": "Phase-3A",
        "purpose": "Build dependency/event evidence before allowing more dangerous HIVM structural rewrites.",
        "inventory": {"op_count": inventory.get("op_count"), "unknown_op_count": inventory.get("unknown_op_count"), "role_counts": inventory.get("role_counts")},
        "dependency_graph": {"node_count": dep_graph.get("node_count"), "edge_count": dep_graph.get("edge_count"), "edge_counts": dep_graph.get("edge_counts")},
        "event_liveness": {"event_count": event_liveness.get("event_count"), "safe_pair_count": event_liveness.get("safe_pair_count"), "passed_local_event_liveness": event_liveness.get("passed_local_event_liveness"), "warnings": event_liveness.get("warnings")},
        "rewrite_gates_unlocked": {
            "barrier_or_sync_local_rewrite_audit": True,
            "event_reuse": False,
            "sync_motion": False,
            "gm_roundtrip_deletion": False,
            "q_load_hoist_with_proof": False,
            "real_double_buffer": False,
            "real_cv_overlap": False,
            "real_tiling_loop_lowering": False,
        },
        "blockers": blockers,
        "next_phase3_steps": [
            "Phase-3B: add buffer liveness and GM alias checker.",
            "Phase-3C: add MemorySSA-like GM round-trip deletion gate.",
            "Phase-3D: add loop-invariant Q-load hoist proof and capacity recheck.",
            "Phase-3E: run tritonsim-hivm DES/trace validation for original and optimized IR.",
        ],
    }
    return {"inventory": inventory, "dependency_graph": dep_graph, "event_liveness": event_liveness, "summary": summary}


def emit_phase3a_analysis_outputs(out: Path, ir_text: str) -> Dict[str, Any]:
    """Write Phase-3A analysis artifacts to ``out`` and return the summary."""
    reports = build_phase3a_analysis(ir_text)
    export_default_semantics(out / "hivm_op_semantics_registry.json")
    _write_json(out / "hivm_ir_inventory.json", reports["inventory"])
    _write_json(out / "dependency_graph_report.json", reports["dependency_graph"])
    _write_json(out / "event_liveness_report.json", reports["event_liveness"])
    _write_json(out / "phase3a_analysis_summary.json", reports["summary"])
    return reports["summary"]


# ---------------------------------------------------------------------------
# Phase-3F: closure / Phase-4 handoff
# ---------------------------------------------------------------------------

def build_phase3f_closure_report(
    phase3a_summary: Optional[Dict[str, Any]] = None,
    phase3b_summary: Optional[Dict[str, Any]] = None,
    phase3c_summary: Optional[Dict[str, Any]] = None,
    phase3d_summary: Optional[Dict[str, Any]] = None,
    phase3e_summary: Optional[Dict[str, Any]] = None,
    structural_validation_summary: Optional[Dict[str, Any]] = None,
    vtriton_adapter_manifest: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Close Phase 3 and define the Phase-4 handoff gates.

    Phase 3 is deliberately an analysis/proof foundation.  This closure report
    consolidates the evidence emitted by Phase-3A..3E and decides which rewrite
    families may enter Phase-4 *prototype* mutation.  The policy is conservative:
    missing target-parser / DES-trace / alias / liveness evidence keeps dangerous
    rewrites locked.
    """
    p3a = phase3a_summary or {}
    p3b = phase3b_summary or {}
    p3c = phase3c_summary or {}
    p3d = phase3d_summary or {}
    p3e = phase3e_summary or {}
    sv = structural_validation_summary or {}
    manifest = vtriton_adapter_manifest or {}

    inv = p3a.get("inventory") or {}
    dep = p3a.get("dependency_graph") or {}
    ev = p3a.get("event_liveness") or {}
    bl = p3b.get("buffer_liveness") or {}
    cap = (bl.get("capacity_recheck") or {}) if isinstance(bl, dict) else {}
    gm_alias = p3b.get("gm_alias") or {}
    gmssa = p3c.get("gm_memory_ssa") or {}
    gm_dec = p3c.get("gm_roundtrip_deletion_decision") or {}
    gates = p3c.get("rewrite_gates_unlocked") or {}
    hoist = p3d.get("hoist_candidates") or {}

    external_des_ok = bool(p3e.get("validation_status") == "passed_external_des_trace_validation")
    tritonsim_ran = bool(p3e.get("external_tritonsim_ran_both"))
    des_artifacts = bool(p3e.get("des_trace_artifacts_available"))
    local_event_ok = bool(ev.get("passed_local_event_liveness"))
    local_capacity_ok = bool(cap.get("passed_conservative_capacity_recheck"))
    unknown_ops = int(inv.get("unknown_op_count") or 0)

    # Evidence matrix: what Phase 3 actually established.
    evidence_matrix = {
        "op_inventory": {
            "available": bool(inv),
            "op_count": inv.get("op_count"),
            "unknown_op_count": unknown_ops,
            "status": "usable_with_conservative_unknown_op_blockers" if bool(inv) else "missing",
        },
        "dependency_graph_v1": {
            "available": bool(dep),
            "edge_count": dep.get("edge_count"),
            "edge_counts": dep.get("edge_counts"),
            "status": "local_conservative_evidence_only" if bool(dep) else "missing",
        },
        "event_liveness": {
            "available": bool(ev),
            "passed_local_event_liveness": local_event_ok,
            "event_count": ev.get("event_count"),
            "status": "local_pass" if local_event_ok else "missing_or_not_passed",
        },
        "buffer_liveness_capacity": {
            "available": bool(bl),
            "buffer_count": bl.get("buffer_count"),
            "passed_conservative_capacity_recheck": local_capacity_ok,
            "status": "local_capacity_pass" if local_capacity_ok else "missing_or_not_passed",
        },
        "gm_alias_memoryssa": {
            "available": bool(gm_alias) and bool(gmssa) and bool(gm_dec),
            "gm_access_count": gm_alias.get("gm_access_count"),
            "candidate_count": gm_dec.get("candidate_count"),
            "delete_allowed_count": gm_dec.get("delete_allowed_count"),
            "status": "deletion_gate_available_but_locked_unless_all_candidates_pass" if bool(gm_dec) else "missing",
        },
        "load_hoist_proof": {
            "available": bool(hoist),
            "candidate_count": hoist.get("candidate_count"),
            "local_proof_passed_count": hoist.get("local_proof_passed_count"),
            "hoist_allowed_count": hoist.get("hoist_allowed_count"),
            "status": "local_proof_only_target_region_motion_required" if bool(hoist) else "missing",
        },
        "external_vtriton_des_trace": {
            "available": external_des_ok,
            "tritonsim_ran_both": tritonsim_ran,
            "des_trace_artifacts_available": des_artifacts,
            "status": "passed" if external_des_ok else "pending_or_failed",
        },
        "structural_validation": {
            "available": bool(sv),
            "evidence_checks": sv.get("evidence_checks"),
            "op_count_delta": (sv.get("op_count_delta") if isinstance(sv, dict) else None),
            "status": "local_structural_audit_available" if bool(sv) else "missing",
        },
        "external_backend_manifest": {
            "available": bool(manifest),
            "missing_required_edits": manifest.get("missing_required_edits_in_external_backend"),
            "status": "capability_handshake_available" if bool(manifest) else "missing",
        },
    }

    # Phase-4 handoff decisions.  Prototype means allowed to develop in Phase 4,
    # not enabled as default production mutation.
    phase4_candidates = {
        "sync_rewrite_audit_and_refinement": {
            "phase4_status": "eligible_for_prototype",
            "why": "Phase 2 C++ bridge already mutates barrier/CV boundary sync and Phase 3 has local event-liveness/dependency evidence.",
            "required_before_default_enable": ["external tritonsim-hivm DES/trace pass", "target HivmOpsEditor/MLIR parser verification", "msprof/runtime validation for performance claims"],
        },
        "gm_roundtrip_deletion": {
            "phase4_status": "locked" if int(gm_dec.get("delete_allowed_count") or 0) <= 0 else "eligible_for_limited_prototype",
            "why": "GM deletion requires same-address, unique reaching MemoryDef, no unknown side effect, and non-observable-boundary proof.",
            "required_before_default_enable": ["nonzero delete_allowed_count", "target alias/dependency proof", "external DES/trace pass", "msprof validation"],
        },
        "q_load_hoist": {
            "phase4_status": "eligible_for_guarded_prototype" if int(hoist.get("local_proof_passed_count") or 0) > 0 else "locked",
            "why": "Local proof may find invariant candidates, but production mutation still requires target region-motion/dominance proof.",
            "required_before_default_enable": ["target parser region-motion proof", "buffer lifetime/capacity pass", "external DES/trace pass", "runtime correctness validation"],
        },
        "real_double_buffer_pingpong": {
            "phase4_status": "locked",
            "why": "Requires buffer cloning, live-range extension, ping/pong binding, event insertion, and capacity proof beyond Phase 3 local reports.",
            "required_before_default_enable": ["buffer live-range proof", "capacity recheck after duplication", "event liveness proof", "target parser codegen"],
        },
        "full_cv_pipeline_overlap": {
            "phase4_status": "locked",
            "why": "Requires stage graph, cross-tile schedule, stage buffer proof, and event/liveness verification.",
            "required_before_default_enable": ["cv_stage_graph_report", "buffer/event liveness proof", "external trace shows expected overlap", "runtime validation"],
        },
        "real_tiling_loop_lowering": {
            "phase4_status": "locked",
            "why": "Requires loop anchor, index remapping, tail mask, reduction semantics, and target verifier support.",
            "required_before_default_enable": ["tiling anchor detection", "target parser transformation", "correctness tests", "DES/trace/msprof validation"],
        },
    }

    remaining_blockers: List[str] = []
    if unknown_ops:
        remaining_blockers.append(f"{unknown_ops} unknown op(s) remain; dangerous rewrites must treat them as blockers")
    if not external_des_ok:
        remaining_blockers.append("external tritonsim-hivm DES/trace validation is pending or failed")
    if not local_event_ok:
        remaining_blockers.append("local event liveness did not pass")
    if not local_capacity_ok:
        remaining_blockers.append("conservative capacity recheck did not pass or is missing")
    if int(gm_dec.get("delete_allowed_count") or 0) <= 0:
        remaining_blockers.append("no GM round-trip candidate is proven safe to delete")
    if int(hoist.get("hoist_allowed_count") or 0) <= 0:
        remaining_blockers.append("no Q-load hoist candidate has production-level region-motion proof")

    phase4_plan = [
        {
            "phase": "Phase-4A",
            "title": "target parser / HivmOpsEditor integration hardening",
            "goal": "replace conservative text-scanner evidence with target Operation-level inventory/dependency/liveness where possible",
            "risk": "vTriton/MLIR build and dialect version mismatch",
        },
        {
            "phase": "Phase-4B",
            "title": "guarded Q-load hoist prototype",
            "goal": "move only locally proven and target-parser-proven invariant Q load candidates",
            "risk": "region motion can violate dominance, buffer lifetime, or loop-carried dependency if proof is incomplete",
        },
        {
            "phase": "Phase-4C",
            "title": "limited GM round-trip deletion prototype",
            "goal": "delete only candidates passing all GM MemorySSA/alias/observable-boundary gates",
            "risk": "false alias proof can change observable memory behavior",
        },
        {
            "phase": "Phase-4D",
            "title": "CV stage graph and overlap prototype planning",
            "goal": "build CV stage graph and decide whether a toy/simple overlap rewrite is safe",
            "risk": "stage-buffer and event-liveness proof is required before real scheduling changes",
        },
        {
            "phase": "Phase-4E",
            "title": "Phase-4 validation closure",
            "goal": "run DES/trace/msprof validation on any newly enabled prototype mutation",
            "risk": "simulation may diverge from hardware; performance claims need msprof",
        },
    ]

    return {
        "schema_version": "hivm_phase3f_closure_report_v1",
        "producer": "strategy_search_demo_v3.3.2_phase3f_closure_phase4_handoff",
        "phase": "Phase-3F",
        "phase3_status": "closed_analysis_foundation",
        "scope": "Phase 3 built dependency/liveness/legality/validation evidence. It does not default-enable dangerous production mutations.",
        "evidence_matrix": evidence_matrix,
        "rewrite_gate_status": {
            "safe_local_sync_audit": bool(gates.get("barrier_or_sync_local_rewrite_audit", True)) and local_event_ok,
            "gm_roundtrip_deletion": bool(gates.get("gm_roundtrip_deletion", False)) and int(gm_dec.get("delete_allowed_count") or 0) > 0 and external_des_ok,
            "q_load_hoist_production_mutation": bool(gates.get("q_load_hoist_with_proof", False)) and int(hoist.get("hoist_allowed_count") or 0) > 0 and external_des_ok,
            "real_double_buffer": False,
            "full_cv_overlap": False,
            "real_tiling_loop_lowering": False,
        },
        "phase4_candidates": phase4_candidates,
        "remaining_blockers": remaining_blockers,
        "phase4_plan": phase4_plan,
        "policy": {
            "default_mutation_policy": "keep dangerous rewrites locked unless all local and target/external gates pass",
            "performance_claim_policy": "Level-1 structural validation is not a speedup claim; require DES/trace and msprof for performance claims",
            "unknown_semantics_policy": "unknown ops or unknown memory effects block deletion/motion rewrites",
        },
    }


def emit_phase3f_closure_outputs(
    out: Path,
    phase3a_summary: Optional[Dict[str, Any]] = None,
    phase3b_summary: Optional[Dict[str, Any]] = None,
    phase3c_summary: Optional[Dict[str, Any]] = None,
    phase3d_summary: Optional[Dict[str, Any]] = None,
    phase3e_summary: Optional[Dict[str, Any]] = None,
    structural_validation_summary: Optional[Dict[str, Any]] = None,
    vtriton_adapter_manifest: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Write Phase-3F closure and Phase-4 handoff reports."""
    report = build_phase3f_closure_report(
        phase3a_summary=phase3a_summary,
        phase3b_summary=phase3b_summary,
        phase3c_summary=phase3c_summary,
        phase3d_summary=phase3d_summary,
        phase3e_summary=phase3e_summary,
        structural_validation_summary=structural_validation_summary,
        vtriton_adapter_manifest=vtriton_adapter_manifest,
    )
    summary = {
        "schema_version": "hivm_phase3f_analysis_summary_v1",
        "producer": "strategy_search_demo_v3.3.2_phase3f_closure_phase4_handoff",
        "phase": "Phase-3F",
        "phase3_status": report.get("phase3_status"),
        "remaining_blocker_count": len(report.get("remaining_blockers") or []),
        "phase4_candidate_status": {k: v.get("phase4_status") for k, v in (report.get("phase4_candidates") or {}).items()},
        "rewrite_gate_status": report.get("rewrite_gate_status"),
        "next_phase": "Phase-4A target parser / HivmOpsEditor integration hardening",
    }
    _write_json(out / "phase3_closure_report.json", report)
    _write_json(out / "phase3f_analysis_summary.json", summary)
    return summary
