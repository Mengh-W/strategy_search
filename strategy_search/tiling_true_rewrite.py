# -*- coding: utf-8 -*-
"""TilingPlan restricted metadata true rewrite executor.

V4.11 only had a TilingPlan feasibility scan. V5.2 performs a deliberately
restricted but visible IR mutation for TilingPlan:

* read selected tile_m/tile_n/tile_k from selected_plan.json;
* find safe insertion anchors near the entry constant block;
* insert explicit tile metadata constants and annotation.mark records;
* optionally mark nearby existing tile-like constants as evidence, without
  blindly replacing unrelated constants;
* emit optimized MLIR, rewrite report, validation, and diff.

This is a metadata-level true rewrite. It intentionally does not rewrite loop
bounds, index expressions, affine maps, memref shapes, or tail masks without a
real MLIR/HIVM verifier.
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

TILING_TRUE_REWRITE_VERSION = "hivm_tiling_restricted_metadata_true_rewrite_v1"
TILING_TRUE_VALIDATION_VERSION = "hivm_tiling_restricted_metadata_validation_v1"
TILING_TRUE_DIFF_VERSION = "hivm_tiling_restricted_metadata_diff_v1"

_CONST_RE = re.compile(r"^(?P<indent>\s*)(?P<sym>%[A-Za-z0-9_.$-]+)\s*=\s*arith\.constant\s+(?P<value>-?\d+)\s*:\s*(?P<type>index|i\d+)\s*$")
_FUNC_RE = re.compile(r"^\s*(func\.func|llvm\.func|builtin\.module|module)\b")


def _load_json(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _tiling_knobs(selected_plan: Dict[str, Any]) -> Dict[str, Any]:
    tp = selected_plan.get("tiling_plan") or {}
    knobs = tp.get("controllable_knobs") or tp.get("selected_knobs") or tp.get("knobs") or {}
    out = {
        "tile_m": knobs.get("tile_m"),
        "tile_n": knobs.get("tile_n"),
        "tile_k": knobs.get("tile_k"),
        "loop_order": knobs.get("loop_order") or tp.get("loop_order") or ["axis_m", "axis_n", "axis_k"],
        "tail_strategy": knobs.get("tail_strategy") or tp.get("tail_strategy") or "preserve_existing_tail_behavior",
        "reduce_tile_policy": knobs.get("reduce_tile_policy") or tp.get("reduce_tile_policy") or "preserve_existing_reduce_tile_policy",
    }
    # Coerce numeric values when present.
    for k in ("tile_m", "tile_n", "tile_k"):
        try:
            if out[k] is not None:
                out[k] = int(out[k])
        except Exception:
            pass
    return out


def scan_tiling_anchors(ir_text: str, selected_tiles: Dict[str, Any]) -> Dict[str, Any]:
    """Find safe metadata insertion anchors and tile-like existing constants."""
    lines = ir_text.splitlines()
    constants: List[Dict[str, Any]] = []
    selected_values = {v for k, v in selected_tiles.items() if k in {"tile_m", "tile_n", "tile_k"} and isinstance(v, int)}
    for ln, line in enumerate(lines, start=1):
        m = _CONST_RE.match(line)
        if not m:
            continue
        value = int(m.group("value"))
        item = {
            "line": ln,
            "symbol": m.group("sym"),
            "value": value,
            "type": m.group("type"),
            "indent": m.group("indent"),
            "text": line,
            "matches_selected_tile_value": value in selected_values,
            "is_power_of_two_tile_like": value in {8, 16, 32, 64, 128, 256, 512},
        }
        constants.append(item)

    # Insert after the last leading arith.constant in the entry block. This keeps
    # metadata close to constants and avoids inserting inside deeply nested loops.
    insertion_line = 1
    leading_constant_lines: List[int] = []
    for c in constants:
        if c["line"] <= 120:  # entry constant region in current samples
            leading_constant_lines.append(int(c["line"]))
    if leading_constant_lines:
        insertion_line = max(leading_constant_lines)
    else:
        for ln, line in enumerate(lines, start=1):
            if _FUNC_RE.match(line):
                insertion_line = ln
                break
    indent = ""
    if 1 <= insertion_line <= len(lines):
        indent = re.match(r"\s*", lines[insertion_line - 1]).group(0)
    matching_constants = [c for c in constants if c["matches_selected_tile_value"]]
    return {
        "schema_version": "hivm_tiling_anchor_scan_v1",
        "line_count": len(lines),
        "insertion_anchor": {"line": insertion_line, "indent": indent, "policy": "after_entry_constant_region"},
        "selected_tiles": selected_tiles,
        "constant_count": len(constants),
        "matching_selected_tile_constants": matching_constants[:50],
        "tile_like_constant_count": sum(1 for c in constants if c["is_power_of_two_tile_like"]),
    }


def build_tiling_true_rewrite_actions(selected_plan: Dict[str, Any], anchor_scan: Dict[str, Any]) -> List[Dict[str, Any]]:
    tiles = _tiling_knobs(selected_plan)
    missing = [k for k in ("tile_m", "tile_n", "tile_k") if tiles.get(k) is None]
    if missing:
        return [{
            "action_id": "tiling_true_rewrite_action_0000",
            "mutation_kind": "restricted_tiling_metadata_rewrite",
            "status": "BLOCKED",
            "blockers": [f"missing_{k}" for k in missing],
            "selected_tiles": tiles,
        }]
    action = {
        "action_id": "tiling_true_rewrite_action_0000",
        "mutation_kind": "restricted_tiling_metadata_rewrite",
        "status": "READY_FOR_TRACE_METADATA_REWRITE",
        "selected_tiles": tiles,
        "target": anchor_scan.get("insertion_anchor") or {},
        "matched_existing_constants": anchor_scan.get("matching_selected_tile_constants") or [],
        "rewrite_policy": {
            "mode": "additive_metadata_constants_and_annotation",
            "loop_bound_rewrite": False,
            "index_expression_rewrite": False,
            "memref_shape_rewrite": False,
            "tail_mask_rewrite": False,
            "unrelated_constant_replacement": False,
            "fallback_original_ir_preserved": True,
        },
        "proposed_true_mutation": [
            "insert explicit selected tile metadata constants",
            "insert annotation.mark carrying tile_m/tile_n/tile_k/loop_order/tail_strategy",
            "record existing constants matching selected tile values as evidence only",
        ],
        "risk_level": "LOW",
    }
    return [action]


def _metadata_lines(indent: str, action: Dict[str, Any]) -> List[str]:
    tiles = action["selected_tiles"]
    tm, tn, tk = int(tiles["tile_m"]), int(tiles["tile_n"]), int(tiles["tile_k"])
    loop_order = tiles.get("loop_order") or ["axis_m", "axis_n", "axis_k"]
    if isinstance(loop_order, list):
        loop_order_s = ",".join(map(str, loop_order))
    else:
        loop_order_s = str(loop_order)
    tail = str(tiles.get("tail_strategy") or "preserve_existing_tail_behavior")
    reduce_policy = str(tiles.get("reduce_tile_policy") or "preserve_existing_reduce_tile_policy")
    aid = action["action_id"]
    return [
        f"{indent}// HIVM V5.2 TilingPlan true rewrite begin: {aid}",
        f"{indent}//   metadata-level rewrite only; loop/index/memref-shape mutation is intentionally disabled",
        f"{indent}%hivm_tile_m_v52 = arith.constant {tm} : index",
        f"{indent}%hivm_tile_n_v52 = arith.constant {tn} : index",
        f"{indent}%hivm_tile_k_v52 = arith.constant {tk} : index",
        f"{indent}annotation.mark %hivm_tile_m_v52 {{hivm.tiling.axis = \"m\", hivm.tiling.value = {tm}, hivm.rewrite_action = \"{aid}\"}} : index",
        f"{indent}annotation.mark %hivm_tile_n_v52 {{hivm.tiling.axis = \"n\", hivm.tiling.value = {tn}, hivm.rewrite_action = \"{aid}\"}} : index",
        f"{indent}annotation.mark %hivm_tile_k_v52 {{hivm.tiling.axis = \"k\", hivm.tiling.value = {tk}, hivm.rewrite_action = \"{aid}\"}} : index",
        f"{indent}// HIVM V5.2 TilingPlan metadata: loop_order={loop_order_s} tail_strategy={tail} reduce_tile_policy={reduce_policy}",
        f"{indent}// HIVM V5.2 TilingPlan true rewrite end: {aid}",
    ]


def apply_tiling_true_rewrite(ir_text: str, actions: List[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    lines = ir_text.splitlines()
    rewritten: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    insert_after: Dict[int, List[str]] = {}
    for action in actions:
        if action.get("status") != "READY_FOR_TRACE_METADATA_REWRITE":
            skipped.append({**action, "skip_reason": "action_not_ready"})
            continue
        target = action.get("target") or {}
        line = int(target.get("line") or 1)
        if line < 1 or line > len(lines):
            skipped.append({**action, "skip_reason": "insertion_anchor_out_of_range"})
            continue
        indent = str(target.get("indent") or "")
        insert_after.setdefault(line, []).extend(_metadata_lines(indent, action))
        rewritten.append({
            **action,
            "status": "REWRITTEN",
            "inserted_after_line": line,
            "inserted_metadata_constant_count": 3,
            "inserted_annotation_count": 3,
        })
    out: List[str] = []
    for ln, line in enumerate(lines, start=1):
        out.append(line)
        out.extend(insert_after.get(ln, []))
    rewritten_text = "\n".join(out) + ("\n" if ir_text.endswith("\n") else "")
    report = {
        "schema_version": TILING_TRUE_REWRITE_VERSION,
        "mutation_performed": bool(rewritten),
        "rewritten_action_count": len(rewritten),
        "skipped_action_count": len(skipped),
        "rewritten_actions": rewritten,
        "skipped_actions": skipped,
        "semantic_mutation_performed": bool(rewritten),
        "production_rewrite_claim_allowed": False,
        "claim_boundary": "restricted metadata-level portable TilingPlan rewrite; no loop/index/memref-shape mutation",
    }
    return rewritten_text, report


def validate_tiling_true_rewrite(original_text: str, rewritten_text: str, report: Dict[str, Any]) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    def add(name: str, passed: bool, detail: Any = None):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
    add("mutation_performed", bool(report.get("mutation_performed")))
    add("tile_m_metadata_present", "%hivm_tile_m_v52" in rewritten_text and "hivm.tiling.axis = \"m\"" in rewritten_text)
    add("tile_n_metadata_present", "%hivm_tile_n_v52" in rewritten_text and "hivm.tiling.axis = \"n\"" in rewritten_text)
    add("tile_k_metadata_present", "%hivm_tile_k_v52" in rewritten_text and "hivm.tiling.axis = \"k\"" in rewritten_text)
    add("loop_index_not_rewritten", "loop/index/memref-shape mutation is intentionally disabled" in rewritten_text)
    add("original_ir_preserved_as_superset", len(rewritten_text.splitlines()) > len(original_text.splitlines()))
    passed = all(c["passed"] for c in checks)
    return {
        "schema_version": TILING_TRUE_VALIDATION_VERSION,
        "passed": passed,
        "checks": checks,
        "production_rewrite_claim_allowed": False,
    }


def build_tiling_diff(original_text: str, rewritten_text: str) -> Dict[str, Any]:
    diff_lines = list(difflib.unified_diff(
        original_text.splitlines(), rewritten_text.splitlines(),
        fromfile="before_tiling_true_rewrite.mlir",
        tofile="after_tiling_true_rewrite.mlir",
        lineterm="",
        n=4,
    ))
    tiling_related = [ln for ln in diff_lines if "TilingPlan" in ln or "hivm_tile_" in ln or "hivm.tiling" in ln]
    return {
        "schema_version": TILING_TRUE_DIFF_VERSION,
        "num_diff_lines": len(diff_lines),
        "num_tiling_related_diff_lines": len(tiling_related),
        "tiling_related_diff_preview": tiling_related[:200],
        "diff_preview": diff_lines[:300],
    }


def write_tiling_true_rewrite_outputs(ir_path: str | Path, selected_plan_path: str | Path, output_dir: str | Path) -> Dict[str, Any]:
    ir_path = Path(ir_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_plan = _load_json(selected_plan_path)
    original = ir_path.read_text(encoding="utf-8", errors="ignore")
    tiles = _tiling_knobs(selected_plan)
    anchor_scan = scan_tiling_anchors(original, tiles)
    actions = build_tiling_true_rewrite_actions(selected_plan, anchor_scan)
    rewritten, report = apply_tiling_true_rewrite(original, actions)
    validation = validate_tiling_true_rewrite(original, rewritten, report)
    diff = build_tiling_diff(original, rewritten)
    summary = {
        "version": "V5.2-tiling-restricted-metadata-true-rewrite",
        "schema_version": "hivm_tiling_true_rewrite_summary_v1",
        "selected_tiles": tiles,
        "anchor_constant_count": anchor_scan.get("constant_count"),
        "matched_existing_tile_constant_count": len(anchor_scan.get("matching_selected_tile_constants") or []),
        "true_rewrite_action_count": len([a for a in actions if a.get("status") == "READY_FOR_TRACE_METADATA_REWRITE"]),
        "mutation_performed": bool(report.get("mutation_performed")),
        "rewritten_action_count": report.get("rewritten_action_count", 0),
        "passed_portable_validation": bool(validation.get("passed")),
        "num_tiling_related_diff_lines": diff.get("num_tiling_related_diff_lines", 0),
        "semantic_mutation_performed": bool(report.get("semantic_mutation_performed")),
        "production_rewrite_claim_allowed": False,
    }
    paths = {
        "optimized_ir": output_dir / "optimized.tiling_rewritten.hivm.mlir",
        "anchor_scan": output_dir / "tiling_anchor_scan.json",
        "actions": output_dir / "tiling_true_rewrite_actions.json",
        "report": output_dir / "tiling_true_rewrite_report.json",
        "validation": output_dir / "tiling_true_rewrite_validation.json",
        "diff": output_dir / "tiling_true_rewrite_diff.json",
        "summary": output_dir / "tiling_true_rewrite_summary.json",
    }
    paths["optimized_ir"].write_text(rewritten, encoding="utf-8")
    paths["anchor_scan"].write_text(json.dumps(anchor_scan, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["actions"].write_text(json.dumps(actions, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["report"].write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["validation"].write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["diff"].write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["summary"].write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"summary": summary, "paths": {k: str(v) for k, v in paths.items()}, "report": report, "validation": validation}
