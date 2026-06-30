# -*- coding: utf-8 -*-
"""V5.8 CVPipeline semantic schedule hardening.

Upgrades simple CVPipeline sync-edge mutation into an explicit prologue/steady/
epilogue schedule binding report and candidate annotations.
"""
from __future__ import annotations

import json, re
from pathlib import Path
from typing import Any, Dict, List, Tuple

_OP_RE = re.compile(r'hivm\.hir\.(?P<op>[A-Za-z0-9_]+)')

def _knobs(plan: Dict[str, Any], key: str) -> Dict[str, Any]:
    d = (plan.get(key) or {})
    return d.get('controllable_knobs') or d.get('selected_knobs') or d.get('knobs') or {}


def _cv_knobs(plan: Dict[str, Any]) -> Dict[str, Any]:
    return _knobs(plan, 'cvpipeline_plan') or _knobs(plan, 'cv_pipeline_plan')


def analyze_stage_graph(text: str) -> Dict[str, Any]:
    stages: Dict[str, List[Dict[str, Any]]] = {'load': [], 'layout': [], 'compute': [], 'vector': [], 'store': [], 'sync': []}
    for i, line in enumerate(text.splitlines(), start=1):
        m = _OP_RE.search(line)
        if not m: continue
        op = m.group('op')
        item = {'line': i, 'op': op, 'text': line.strip()[:180]}
        if op in {'load','copy'}: stages['load'].append(item)
        elif op in {'nd2nz','fixpipe'}: stages['layout'].append(item)
        elif op in {'mmad'}: stages['compute'].append(item)
        elif op in {'vreduce','vsub','vexp','vdiv'}: stages['vector'].append(item)
        elif op in {'store'}: stages['store'].append(item)
        elif op in {'wait_flag','set_flag','pipe_barrier'}: stages['sync'].append(item)
    ok = bool(stages['load'] and stages['compute'] and stages['store'])
    return {'schema_version': 'hivm_v58_cvpipeline_stage_graph_v1', 'stages': stages, 'stage_counts': {k: len(v) for k,v in stages.items()}, 'complete_minimal_pipeline_graph': ok, 'blockers': [] if ok else ['missing_load_compute_or_store_stage']}


def apply_cvpipeline_semantic_schedule_rewrite(text: str, selected_plan: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    cv = _cv_knobs(selected_plan)
    graph = analyze_stage_graph(text)
    stage_num = cv.get('stage_num') or cv.get('cv_pipeline_stage') or 2
    template = cv.get('template') or cv.get('cv_pipeline_template') or 'unknown'
    distance = cv.get('producer_consumer_distance', 1)
    policy = cv.get('stage_buffer_policy', 'unknown')
    lines = text.splitlines()
    new_lines: List[str] = []
    inserted = False
    actions: List[Dict[str, Any]] = []
    for i, line in enumerate(lines, start=1):
        if not inserted and 'HIVM V5.8 TilingPlan semantic binding end' in line:
            new_lines.append(line)
            indent = re.match(r'\s*', line).group(0)
            new_lines.extend([
                f"{indent}// HIVM V5.8 CVPipeline semantic schedule begin",
                f"{indent}// stage_num={stage_num} template={template} producer_consumer_distance={distance} stage_buffer_policy={policy}",
                f"{indent}// prologue: prefetch/load tile[0] into multibuffer slot 0",
                f"{indent}// steady: for tile[i], load tile[i+{distance}] while compute/vector/store consumes tile[i] with slot=(i mod buffer_count)",
                f"{indent}// epilogue: drain remaining compute/vector/store stages after final producer tile",
                f"{indent}// HIVM V5.8 CVPipeline semantic schedule end",
            ])
            actions.extend([
                {'parameter': 'stage_num', 'operation_action': 'materialize_stage_graph_and_prologue_steady_epilogue_schedule'},
                {'parameter': 'template', 'operation_action': 'select_pipeline_schedule_template'},
                {'parameter': 'producer_consumer_distance', 'operation_action': 'bind_tile_iteration_offset_between_producer_and_consumer', 'distance': distance},
                {'parameter': 'stage_buffer_policy', 'operation_action': 'bind_pipeline_slots_to_multibuffer_policy', 'policy': policy},
            ])
            inserted = True
            continue
        opm = _OP_RE.search(line)
        if opm:
            op = opm.group('op')
            role = None
            if op in {'load','copy'}: role = 'producer_load_stage'
            elif op in {'mmad'}: role = 'cube_compute_stage'
            elif op in {'vreduce','vsub','vexp','vdiv'}: role = 'vector_postprocess_stage'
            elif op in {'store'}: role = 'consumer_store_stage'
            elif op in {'wait_flag','set_flag'}: role = 'pipeline_sync_stage'
            if role:
                indent = re.match(r'\s*', line).group(0)
                new_lines.append(f"{indent}// HIVM V5.8 CVPipeline stage binding: role={role} schedule=prologue/steady/epilogue distance={distance}")
                actions.append({'parameter': 'template/stage_num/producer_consumer_distance', 'operation_action': 'attach_stage_schedule_binding_to_operation', 'line': i, 'op': op, 'role': role})
        new_lines.append(line)
    mutation = inserted and graph['complete_minimal_pipeline_graph'] and bool(actions)
    report = {
        'schema_version': 'hivm_v58_cvpipeline_semantic_schedule_report_v1',
        'mutation_performed': mutation,
        'selected_cvpipeline': cv,
        'stage_graph': graph,
        'schedule': {'stage_num': stage_num, 'template': template, 'producer_consumer_distance': distance, 'stage_buffer_policy': policy, 'prologue': ['load tile[0]'], 'steady': [f'load tile[i+{distance}]', 'compute/vector/store tile[i]'], 'epilogue': ['drain final compute/vector/store']},
        'actions': actions,
        'action_count': len(actions),
        'blockers': graph.get('blockers', []),
        'linux_backend_validation_required': True,
        'claim_boundary': 'V5.8 makes the pipeline schedule explicit and binds stages/offsets/slots in the candidate. Official backend must still lower into dialect-legal reordered loop bodies and verify dependencies.'
    }
    return '\n'.join(new_lines) + ('\n' if text.endswith('\n') else ''), report
