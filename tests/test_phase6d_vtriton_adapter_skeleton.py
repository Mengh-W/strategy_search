from pathlib import Path

from strategy_search.phase6_analysis import build_phase6d_vtriton_source_integration_report, emit_phase6d_outputs


def test_phase6d_generates_adapter_files_without_source(tmp_path):
    summary = emit_phase6d_outputs(out=tmp_path, vtriton_source_root=None)
    assert (tmp_path / "phase6d_vtriton_source_integration_report.json").exists()
    assert (tmp_path / "phase6d_generated_backend_files_manifest.json").exists()
    assert summary["production_mutation_allowed"] is False


def test_phase6d_detects_minimal_vtriton_source_tree(tmp_path):
    src = tmp_path / "vTriton"
    (src / "include" / "AscendModel" / "Transforms").mkdir(parents=True)
    (src / "lib" / "AscendModel" / "Transforms").mkdir(parents=True)
    (src / "tools" / "hivm-crud").mkdir(parents=True)
    (src / "tools" / "tritonsim-hivm").mkdir(parents=True)
    (src / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.20)\n", encoding="utf-8")
    (src / "include" / "AscendModel" / "Transforms" / "HivmOpsEditor.h").write_text(
        "class HivmOpsEditor { static void loadFromFile(); void exportToFile(); void listOps(); void removeRedundantLoadStorePair(); };",
        encoding="utf-8",
    )
    (src / "lib" / "AscendModel" / "Transforms" / "HivmOpsEditor.cpp").write_text(
        "void HivmOpsEditor::exportToFile(){} void HivmOpsEditor::listOps(){}",
        encoding="utf-8",
    )
    (src / "tools" / "hivm-crud" / "hivm-crud.cpp").write_text(
        "Upper-level C++ code should call HivmOpsEditor directly instead of this CLI tool.",
        encoding="utf-8",
    )
    (src / "tools" / "tritonsim-hivm" / "tritonsim-hivm.cpp").write_text("int main(){}", encoding="utf-8")
    report = build_phase6d_vtriton_source_integration_report(out=tmp_path, vtriton_source_root=str(src))
    assert report["located_files"]["HivmOpsEditor.h"] is not None
    assert report["observed_hivmopseditor_api"]["loadFromFile"] is True
    assert report["observed_hivmopseditor_api"]["listOps"] is True
    assert report["generated_adapter"]["files"]
