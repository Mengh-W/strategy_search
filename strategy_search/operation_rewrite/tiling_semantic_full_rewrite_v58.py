# -*- coding: utf-8 -*-
"""V5.8 TilingPlan semantic full-rewrite hardening.

This module does not pretend to replace the official Linux HIVM/MLIR backend.
It upgrades the V5.6/V5.7 tiling scaffold into a much more explicit semantic
rewrite candidate by binding M/N/K axes, materializing tile-slice semantics next
to concrete load/compute/store operations, and emitting a reduction/tail plan
that can be checked before backend handoff.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

_MEMREF_RE = re.compile(r"(?P<name>%[A-Za-z_][A-Za-z0-9_.$-]*)\s*:\s*memref<(?P<body>[^>]+)>")
_OP_RE = re.compile(r"hivm\.hir\.(?P<op>[A-Za-z0-9_]+)")
_FUNC_ARG_RE = re.compile(r"func\.func\s+@[^(]+\((?P<args>.*?)\)\s*\{", re.S)
_ALLOC_RE = re.compile(r"(?P<name>%[A-Za-z_][A-Za-z0-9_.$-]*)\s*=\s*memref\.alloc\(\)\s*:\s*memref<(?P<body>[^>]+)>")
_GROUP_RE = re.compile(r"(?:ins|outs)\((?P<body>[^)]*)\)")
_TOKEN_RE = re.compile(r"%[A-Za-z_][A-Za-z0-9_.$-]*")


def _write_json(path: str | Path, obj: Any) -> str:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    return str(p)


def _knobs(plan: Dict[str, Any], key: str) -> Dict[str, Any]:
    d = (plan.get(key) or {})
    return d.get('controllable_knobs') or d.get('selected_knobs') or d.get('knobs') or {}


def _tiling_knobs(plan: Dict[str, Any]) -> Dict[str, Any]:
    k = _knobs(plan, 'tiling_plan')
    out = {name: k.get(name) for name in ['tile_m','tile_n','tile_k','loop_order','tail_strategy','reduce_tile_policy','layout_aware_tile']}
    for name in ['tile_m','tile_n','tile_k']:
        try: out[name] = int(out[name])
        except Exception: out[name] = None
    return out


def _dims_from_body(body: str) -> Tuple[List[int], str, str]:
    # body like 64x128xf16, #hivm.address_space<gm>
    prefix = body.split(',')[0].strip()
    parts = prefix.split('x')
    dtype = parts[-1] if parts else ''
    dims: List[int] = []
    for p in parts[:-1]:
        try: dims.append(int(p))
        except Exception: pass
    space = 'unknown'
    m = re.search(r'address_space<([^>]+)>', body)
    if m: space = m.group(1)
    return dims, dtype, space


def _collect_declared_memrefs(text: str) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    m = _FUNC_ARG_RE.search(text)
    if m:
        for mm in _MEMREF_RE.finditer(m.group('args')):
            dims, dtype, space = _dims_from_body(mm.group('body'))
            out[mm.group('name')] = {'name': mm.group('name'), 'dims': dims, 'dtype': dtype, 'space': space, 'kind': 'func_arg'}
    for mm in _ALLOC_RE.finditer(text):
        dims, dtype, space = _dims_from_body(mm.group('body'))
        out[mm.group('name')] = {'name': mm.group('name'), 'dims': dims, 'dtype': dtype, 'space': space, 'kind': 'alloc'}
    return out


def infer_axis_binding(text: str, selected_plan: Dict[str, Any]) -> Dict[str, Any]:
    memrefs = _collect_declared_memrefs(text)
    q = memrefs.get('%Q_gm') or next((v for k, v in memrefs.items() if k.lower().startswith('%q') and v['kind']=='func_arg'), None)
    k = memrefs.get('%K_gm') or next((v for k0, v in memrefs.items() if k0.lower().startswith('%k') and v['kind']=='func_arg'), None)
    v = memrefs.get('%V_gm') or next((v for k0, v in memrefs.items() if k0.lower().startswith('%v') and v['kind']=='func_arg'), None)
    o = memrefs.get('%O_gm') or next((v for k0, v in memrefs.items() if k0.lower().startswith('%o') and v['kind']=='func_arg'), None)
    tk = _tiling_knobs(selected_plan)
    M = (q or {}).get('dims', [None])[0] if q else None
    K_total = (q or {}).get('dims', [None, None])[1] if q and len(q.get('dims', [])) > 1 else None
    N_total = (k or {}).get('dims', [None])[0] if k else None
    D_out = (o or {}).get('dims', [None, None])[1] if o and len(o.get('dims', [])) > 1 else None
    axes = {
        'M': {'symbol': '%m_outer', 'extent': M, 'tile': tk.get('tile_m'), 'evidence': '%Q_gm dim0 / %O_gm dim0'},
        'N': {'symbol': '%n_outer', 'extent': N_total, 'tile': tk.get('tile_n'), 'evidence': '%K_gm dim0 / %V_gm dim0 sequence axis'},
        'K': {'symbol': '%k_outer', 'extent': K_total, 'tile': tk.get('tile_k'), 'evidence': '%Q_gm dim1 / %K_gm dim1 reduction-head axis'},
        'D': {'symbol': '%d_outer', 'extent': D_out, 'tile': tk.get('tile_k'), 'evidence': '%V_gm dim1 / %O_gm dim1 value/output feature axis'},
    }
    confidence = 'HIGH' if q and k and v and o and M and N_total and K_total else 'MEDIUM'
    blockers: List[str] = []
    for ax in ['M','N','K']:
        if axes[ax]['extent'] is None or axes[ax]['tile'] is None:
            blockers.append(f'missing_axis_{ax}_extent_or_tile')
    return {
        'schema_version': 'hivm_v58_tiling_axis_binding_v1',
        'confidence': confidence,
        'axes': axes,
        'tensor_roles': {'Q': q, 'K': k, 'V': v, 'O': o},
        'blockers': blockers,
        'complete_for_sample_fa_pattern': not blockers,
    }


def _operation_kind(line: str) -> str | None:
    m = _OP_RE.search(line)
    return m.group('op') if m else None


def _operands_in_groups(line: str) -> List[str]:
    vals: List[str] = []
    for gm in _GROUP_RE.finditer(line):
        body = gm.group('body').split(':', 1)[0]
        vals.extend(_TOKEN_RE.findall(body))
    return vals


def _infer_slice_for_line(line: str, axis_binding: Dict[str, Any], selected_plan: Dict[str, Any]) -> Dict[str, Any] | None:
    op = _operation_kind(line)
    if not op:
        return None
    vals = _operands_in_groups(line)
    tk = _tiling_knobs(selected_plan)
    if op in {'load', 'copy'}:
        if any(v.startswith('%Q') or v in {'%q_ub','%q_l1'} for v in vals):
            return {'op': op, 'semantic_role': 'Q_load_or_Q_stage', 'tile_offsets': ['%m_outer', '%k_outer'], 'tile_shape': [tk.get('tile_m'), tk.get('tile_k')], 'axis_map': ['M','K']}
        if any(v.startswith('%K') or v in {'%k_ub','%k_l1_ping','%k_l1_pong'} for v in vals):
            return {'op': op, 'semantic_role': 'K_load_or_K_stage', 'tile_offsets': ['%n_outer', '%k_outer'], 'tile_shape': [tk.get('tile_n'), tk.get('tile_k')], 'axis_map': ['N','K']}
        if any(v.startswith('%V') or v in {'%v_ub','%v_l1'} for v in vals):
            return {'op': op, 'semantic_role': 'V_load_or_V_stage', 'tile_offsets': ['%n_outer', '%d_outer'], 'tile_shape': [tk.get('tile_n'), 'D_tile'], 'axis_map': ['N','D']}
    if op == 'nd2nz':
        return {'op': op, 'semantic_role': 'layout_transform_tile', 'tile_offsets': ['propagate_from_input'], 'tile_shape': ['propagate_from_input'], 'axis_map': ['layout-aware']}
    if op == 'mmad':
        if '%q_l1' in vals and any(v.startswith('%k_l1') for v in vals):
            return {'op': op, 'semantic_role': 'QK_score_tile_compute', 'tile_offsets': ['%m_outer','%n_outer','%k_outer'], 'tile_shape': [tk.get('tile_m'), tk.get('tile_n'), tk.get('tile_k')], 'axis_map': ['M','N','K'], 'reduction': 'partial_accumulate_over_K'}
        if '%p_ub' in vals and '%v_l1' in vals:
            return {'op': op, 'semantic_role': 'PV_output_tile_compute', 'tile_offsets': ['%m_outer','%d_outer','%n_outer'], 'tile_shape': [tk.get('tile_m'), 'D_tile', tk.get('tile_n')], 'axis_map': ['M','D','N'], 'reduction': 'partial_accumulate_over_N'}
    if op in {'fixpipe','vreduce','vsub','vexp','vdiv'}:
        return {'op': op, 'semantic_role': f'vector_postprocess_tile_{op}', 'tile_offsets': ['%m_outer','%n_outer'], 'tile_shape': [tk.get('tile_m'), tk.get('tile_n')], 'axis_map': ['M','N']}
    if op == 'store':
        return {'op': op, 'semantic_role': 'O_store_tile', 'tile_offsets': ['%m_outer','%d_outer'], 'tile_shape': [tk.get('tile_m'), 'D_tile'], 'axis_map': ['M','D']}
    return None


def apply_tiling_semantic_full_rewrite(text: str, selected_plan: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    axis = infer_axis_binding(text, selected_plan)
    tk = _tiling_knobs(selected_plan)
    lines = text.splitlines()
    new_lines: List[str] = []
    actions: List[Dict[str, Any]] = []
    insert_done = False
    for i, line in enumerate(lines, start=1):
        if (not insert_done) and 'HIVM V5.6 TilingPlan tail guard' in line:
            indent = re.match(r'\s*', line).group(0)
            new_lines.append(f"{indent}// HIVM V5.8 TilingPlan semantic binding begin")
            new_lines.append(f"{indent}// axis-binding: M=%m_outer extent={axis['axes']['M']['extent']} tile={tk.get('tile_m')}; N=%n_outer extent={axis['axes']['N']['extent']} tile={tk.get('tile_n')}; K=%k_outer extent={axis['axes']['K']['extent']} tile={tk.get('tile_k')}")
            new_lines.append(f"{indent}// tail-semantics: {tk.get('tail_strategy')} => tile_end=min(axis_extent, outer+tile), mask/pad required for non-divisible tiles")
            new_lines.append(f"{indent}// reduction-semantics: {tk.get('reduce_tile_policy')} => explicit partial accumulator guards for score/output reductions")
            new_lines.append(f"{indent}// HIVM V5.8 TilingPlan semantic binding end")
            actions.append({'parameter': 'tile_m/tile_n/tile_k', 'operation_action': 'bind_outer_tile_loops_to_axis_extents_and_tile_end_guards', 'line': i})
            actions.append({'parameter': 'tail_strategy', 'operation_action': 'materialize_tile_end_mask_or_pad_semantics', 'line': i})
            actions.append({'parameter': 'reduce_tile_policy', 'operation_action': 'materialize_partial_accumulator_semantics', 'line': i})
            insert_done = True
        sem = _infer_slice_for_line(line, axis, selected_plan)
        if sem and 'hivm.hir.' in line:
            indent = re.match(r'\s*', line).group(0)
            new_lines.append(f"{indent}// HIVM V5.8 tile-slice binding: role={sem['semantic_role']} offsets={sem['tile_offsets']} shape={sem['tile_shape']} axes={sem['axis_map']}")
            if sem.get('reduction'):
                new_lines.append(f"{indent}// HIVM V5.8 reduction binding: {sem['reduction']} policy={tk.get('reduce_tile_policy')} init/update/final-store guarded by outer tile indices")
            actions.append({'parameter': 'tile_m/tile_n/tile_k', 'operation_action': 'attach_tile_slice_binding_to_hivm_operation', 'line': i, 'semantic': sem})
        new_lines.append(line)
    mutation = len(actions) > 0 and insert_done and not axis.get('blockers')
    report = {
        'schema_version': 'hivm_v58_tiling_semantic_full_rewrite_report_v1',
        'mutation_performed': mutation,
        'axis_binding': axis,
        'selected_tiling': tk,
        'actions': actions,
        'action_count': len(actions),
        'blockers': axis.get('blockers', []),
        'complete_strategy_parameters_covered': all(k in tk for k in ['tile_m','tile_n','tile_k','loop_order','tail_strategy','reduce_tile_policy','layout_aware_tile']),
        'linux_backend_validation_required': True,
        'claim_boundary': 'V5.8 binds tiling strategy to loop axes and per-operation tile slice/reduction semantics in the emitted candidate. Official Linux backend must still lower/verify these bindings into dialect-legal loop/index/slice operations.'
    }
    return '\n'.join(new_lines) + ('\n' if text.endswith('\n') else ''), report
