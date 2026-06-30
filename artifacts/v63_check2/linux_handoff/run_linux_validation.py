#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run Linux backend validation for baseline/optimized HIVM files.

Edit backend_commands.json or export environment variables using the same keys.
Each command is a shell template.  Available placeholders:
  {ir}    input HIVM file path
  {kind}  baseline or optimized
  {out}   output directory for this kind/step
  {root}  linux_handoff directory

Empty commands are marked SKIPPED, not passed.
"""
from __future__ import annotations
import json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMMANDS_PATH = ROOT / "backend_commands.json"
INPUTS = {
    "baseline": ROOT / "inputs" / "baseline.hivm.mlir",
    "optimized": ROOT / "inputs" / "optimized.hivm.mlir",
}
STEPS = ["parse", "roundtrip", "verify", "compile", "run", "msprof"]


def load_commands():
    commands = {}
    if COMMANDS_PATH.exists():
        commands.update(json.loads(COMMANDS_PATH.read_text(encoding="utf-8")))
    for step in STEPS:
        env = os.environ.get(f"HIVM_{step.upper()}_CMD")
        if env:
            commands[step] = env
    return commands


def run_one(kind: str, step: str, template: str):
    out = ROOT / "results" / kind / step
    out.mkdir(parents=True, exist_ok=True)
    ir = INPUTS[kind]
    if not template or template.strip().startswith("#"):
        return {"kind": kind, "step": step, "status": "SKIPPED", "reason": "empty command template", "command": template or ""}
    cmd = template.format(ir=str(ir), kind=kind, out=str(out), root=str(ROOT))
    t0 = time.time()
    proc = subprocess.run(cmd, shell=True, cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out / "stdout.log").write_text(proc.stdout, encoding="utf-8", errors="ignore")
    (out / "stderr.log").write_text(proc.stderr, encoding="utf-8", errors="ignore")
    (out / "command.sh").write_text(cmd + "\n", encoding="utf-8")
    return {
        "kind": kind,
        "step": step,
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "returncode": proc.returncode,
        "elapsed_sec": round(time.time() - t0, 4),
        "command": cmd,
        "stdout_log": str(out / "stdout.log"),
        "stderr_log": str(out / "stderr.log"),
    }


def main() -> int:
    commands = load_commands()
    results = []
    for kind in ["baseline", "optimized"]:
        for step in STEPS:
            results.append(run_one(kind, step, commands.get(step, "")))
    gate_order = ["parse", "roundtrip", "verify", "compile", "run", "msprof"]
    gates = {}
    for step in gate_order:
        rows = [r for r in results if r["step"] == step]
        gates[step] = all(r["status"] == "PASS" for r in rows)
    summary = {
        "schema_version": "hivm_v61_linux_validation_results_v1",
        "baseline_ir": str(INPUTS["baseline"]),
        "optimized_ir": str(INPUTS["optimized"]),
        "results": results,
        "gates": gates,
        "ready_for_perf_comparison": all(gates.get(x) for x in ["parse", "roundtrip", "verify", "compile", "run"]),
        "performance_comparison_completed": bool(gates.get("msprof")),
        "claim_rule": "Only claim speedup after baseline and optimized pass parse/roundtrip/verify/compile/run and msprof results are collected under results/.",
    }
    out = ROOT / "results" / "linux_validation_results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if all(gates.get(x) for x in ["parse", "roundtrip", "verify", "compile", "run"]) else 2

if __name__ == "__main__":
    raise SystemExit(main())
