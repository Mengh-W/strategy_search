#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Install the Phase-6D/6E HivmOpsEditor backend adapter into a vTriton tree.

This script intentionally performs a small, auditable integration:
  1. copy vtriton_hivm_operation_backend/ into <vTriton>/tools/hivm-operation-backend/;
  2. add add_subdirectory(hivm-operation-backend) to <vTriton>/tools/CMakeLists.txt if absent;
  3. write a JSON integration report.

It does not build vTriton and does not claim production mutation.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def copytree_clean(src: Path, dst: Path, apply: bool) -> str:
    if not src.exists():
        return "adapter_source_missing"
    if not apply:
        return "dry_run_would_copy"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return "copied"


def patch_tools_cmake(cmake: Path, apply: bool) -> str:
    marker = "add_subdirectory(hivm-operation-backend)"
    if not cmake.exists():
        return "tools_cmakelists_missing"
    text = cmake.read_text(encoding="utf-8", errors="ignore")
    if marker in text:
        return "already_present"
    block = "\n# Phase-6E HIVM Operation backend adapter.\nif(EXISTS \"${CMAKE_CURRENT_SOURCE_DIR}/hivm-operation-backend/CMakeLists.txt\")\n  add_subdirectory(hivm-operation-backend)\nendif()\n"
    if not apply:
        return "dry_run_would_patch"
    cmake.write_text(text.rstrip() + block + "\n", encoding="utf-8")
    return "patched"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vtriton-root", required=True)
    ap.add_argument("--adapter-dir", required=True)
    ap.add_argument("--report", default=None)
    ap.add_argument("--apply", action="store_true", help="Actually copy and patch. Without this, report dry-run actions only.")
    args = ap.parse_args()

    root = Path(args.vtriton_root).resolve()
    src = Path(args.adapter_dir).resolve()
    dst = root / "tools" / "hivm-operation-backend"
    cmake = root / "tools" / "CMakeLists.txt"
    report = {
        "schema_version": "phase6e_vtriton_backend_patch_report_v1",
        "apply": args.apply,
        "vtriton_root": str(root),
        "adapter_source": str(src),
        "adapter_destination": str(dst),
        "tools_cmakelists": str(cmake),
        "root_exists": root.exists(),
        "tools_dir_exists": (root / "tools").exists(),
        "adapter_source_exists": src.exists(),
        "copy_status": copytree_clean(src, dst, args.apply),
        "cmake_patch_status": patch_tools_cmake(cmake, args.apply),
        "next_commands": [
            "cmake -S <vTriton> -B <vTriton>/build <your existing vTriton CMake options>",
            "cmake --build <vTriton>/build --target hivm-operation-backend -j$(nproc)",
            "<vTriton>/build/bin/hivm-operation-backend --print-capabilities",
        ],
    }
    out = Path(args.report) if args.report else Path.cwd() / "phase6e_vtriton_backend_patch_report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
