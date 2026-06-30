# -*- coding: utf-8 -*-
from strategy_search.structural_edit_schema import structural_edit_schema, validate_structural_edit_script
from strategy_search.structural_rewrite import build_structural_edit_script


def test_structural_edit_schema_has_official_guidance_and_required_fields():
    schema = structural_edit_schema()
    assert schema["schema_version"] == "hivm_structural_edit_script_v1"
    assert "official_rewrite_guidance" in schema
    assert "mlir_pattern_rewriter" in schema["official_rewrite_guidance"]
    assert "legality_contract" in schema["required_top_level_fields"]


def test_generated_structural_edit_script_validates():
    script = build_structural_edit_script({
        "strategy_id": "schema_demo",
        "sync_policy": "graph_sync_solver",
        "cv_pipeline_stage": 2,
        "double_buffer": True,
    }, "balanced")
    ok, errors = validate_structural_edit_script(script)
    assert ok, errors
    assert script["schema_validation"]["passed"] is True
    assert all("legality" in e for e in script["edits"])
    assert any(e["type"] == "replace_barrier_all_with_directional_sync" for e in script["edits"])
