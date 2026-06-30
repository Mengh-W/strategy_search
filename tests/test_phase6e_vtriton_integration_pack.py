from pathlib import Path
from strategy_search.phase6_analysis import emit_phase6e_outputs


def test_phase6e_emits_build_pack(tmp_path):
    vtriton = tmp_path / "vTriton"
    (vtriton / "tools").mkdir(parents=True)
    (vtriton / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.20)\n", encoding="utf-8")
    (vtriton / "tools" / "CMakeLists.txt").write_text("set(_installed_tools tritonsim-hivm)\n", encoding="utf-8")
    summary = emit_phase6e_outputs(out=tmp_path / "out", vtriton_source_root=str(vtriton))
    assert summary["phase"] == "Phase-6E"
    assert (tmp_path / "out" / "phase6e_vtriton_local_integration_report.json").exists()
    assert (tmp_path / "out" / "phase6e_backend_build_plan.json").exists()
    assert summary["ready_to_run_local_install_script"] is True
    assert summary["compiled_backend_accepted"] is False


def test_phase6e_apply_patch_script_dry_run(tmp_path):
    project = Path(__file__).resolve().parents[1]
    script = project / "scripts" / "phase6e_apply_vtriton_backend_patch.py"
    assert script.exists()
    vtriton = tmp_path / "vTriton"
    (vtriton / "tools").mkdir(parents=True)
    (vtriton / "tools" / "CMakeLists.txt").write_text("# tools\n", encoding="utf-8")
    import subprocess, json
    report = tmp_path / "report.json"
    proc = subprocess.run([
        "python", str(script),
        "--vtriton-root", str(vtriton),
        "--adapter-dir", str(project / "vtriton_hivm_operation_backend"),
        "--report", str(report),
    ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert proc.returncode == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["copy_status"] == "dry_run_would_copy"
    assert data["cmake_patch_status"] == "dry_run_would_patch"
