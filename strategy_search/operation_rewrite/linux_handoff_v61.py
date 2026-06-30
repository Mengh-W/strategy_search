# -*- coding: utf-8 -*-
"""V6.1 Linux handoff package for four-plan real operation materialization.

This module does not pretend to run the Ascend/HIVM backend inside the portable
repository.  It creates a self-contained handoff directory that can be copied to
an Ascend Linux environment and executed there.  The handoff records baseline and
optimized IR files, selected plan, backend command templates, acceptance gates,
and result collectors for parse / roundtrip / verify / compile / correctness /
msprof comparison.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import statistics
import textwrap
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _script_linux_validation_py() -> str:
    return r'''#!/usr/bin/env python3
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
'''


def _script_msprof_compare_py() -> str:
    return r'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Collect baseline vs optimized msprof/perf numbers from CSV/JSON/text files.

Usage:
  python collect_msprof_compare.py --baseline path/to/baseline.csv --optimized path/to/optimized.csv

The parser is intentionally tolerant: it looks for columns or JSON keys such as
latency_us, duration_us, time_us, elapsed_us, cycles, task_duration, Duration.
"""
from __future__ import annotations
import argparse, csv, json, re, statistics
from pathlib import Path

KEYS = ["latency_us", "duration_us", "time_us", "elapsed_us", "kernel_time_us", "cycles", "task_duration", "Duration", "dur", "duration"]
NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


def nums_from_obj(obj):
    vals = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in KEYS:
                try: vals.append(float(v))
                except Exception: pass
            vals.extend(nums_from_obj(v))
    elif isinstance(obj, list):
        for x in obj: vals.extend(nums_from_obj(x))
    return vals


def read_values(path: Path):
    txt = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() == ".json":
        try:
            return nums_from_obj(json.loads(txt))
        except Exception:
            pass
    if path.suffix.lower() == ".csv":
        vals = []
        try:
            rows = csv.DictReader(txt.splitlines())
            for row in rows:
                for k in KEYS:
                    if k in row and row[k] not in (None, ""):
                        try: vals.append(float(row[k]))
                        except Exception: pass
            if vals: return vals
        except Exception:
            pass
    # fallback: lines containing relevant labels
    vals = []
    for line in txt.splitlines():
        low = line.lower()
        if any(k.lower() in low for k in KEYS):
            vals.extend(float(x) for x in NUM_RE.findall(line))
    return vals


def stats(vals):
    vals = [float(v) for v in vals]
    return {"count": len(vals), "median": statistics.median(vals) if vals else None, "mean": statistics.mean(vals) if vals else None, "min": min(vals) if vals else None, "max": max(vals) if vals else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--optimized", required=True)
    ap.add_argument("--out", default="perf_comparison.json")
    args = ap.parse_args()
    b = read_values(Path(args.baseline)); o = read_values(Path(args.optimized))
    bs = stats(b); os = stats(o)
    speedup = None
    if bs["median"] and os["median"] and os["median"] != 0:
        speedup = bs["median"] / os["median"]
    result = {"schema_version":"hivm_v61_perf_compare_v1", "baseline": bs, "optimized": os, "speedup_baseline_over_optimized_median": speedup, "valid": bool(speedup)}
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if speedup else 2

if __name__ == "__main__":
    raise SystemExit(main())
'''


def _readme_cn() -> str:
    return """# V6.1 Linux Handoff 说明

这个目录是为了把四 Plan rewrite 真正拿到 Ascend Linux 环境验证，而不是只在本地 Python 侧看 report。

## 目录内容

- `inputs/baseline.hivm.mlir`：寻优前/原始 HIVM。
- `inputs/optimized.hivm.mlir`：V6.0 四 Plan real operation materialization 后的 optimized HIVM。
- `inputs/selected_plan.json`：本次寻优选中的四 Plan 参数。
- `backend_commands.json`：你需要根据线下环境填写的 parser/verifier/compiler/run/msprof 命令模板。
- `run_linux_validation.py`：按 baseline 和 optimized 分别执行 parse、roundtrip、verify、compile、run、msprof。
- `collect_msprof_compare.py`：从 msprof/CSV/JSON/text 结果里提取 latency/cycles 并计算 median speedup。
- `acceptance_gates.json`：正式性能对比前必须通过的 gate。

## 使用方式

1. 把整个 `linux_handoff/` 目录拷贝到 Ascend Linux 环境。
2. 根据实际工具链编辑 `backend_commands.json`。
3. 运行：

```bash
python3 run_linux_validation.py
```

4. 查看：

```text
results/linux_validation_results.json
```

只有 baseline 和 optimized 都通过 parse / roundtrip / verify / compile / run，才可以进入 msprof 性能对比。

## 命令模板占位符

`backend_commands.json` 支持这些占位符：

- `{ir}`：当前输入 HIVM 文件。
- `{kind}`：`baseline` 或 `optimized`。
- `{out}`：当前 step 的输出目录。
- `{root}`：handoff 根目录。

示例：

```json
{
  "parse": "your_hivm_parser --input {ir} --out {out}/parsed.mlir",
  "verify": "your_mlir_verify {ir}",
  "compile": "your_hivm_compile {ir} -o {out}/{kind}_kernel",
  "run": "your_runner --kernel {out}/{kind}_kernel --output {out}/output.bin",
  "msprof": "msprof --application='your_runner --kernel {out}/{kind}_kernel' --output {out}/msprof"
}
```

## 重要边界

这个 handoff 包不会替你假装 Linux 已经过了。它的作用是把验证链路整理成可以直接落地执行的目录。只有 `linux_validation_results.json` 中 compile/run/msprof gate 通过后，才能正式说进入性能对比阶段。
"""


def create_v61_linux_handoff(
    baseline_ir: str | Path,
    optimized_ir: str | Path,
    selected_plan: str | Path,
    output_dir: str | Path,
    rewrite_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    baseline_ir = Path(baseline_ir)
    optimized_ir = Path(optimized_ir)
    selected_plan = Path(selected_plan)
    output_dir = Path(output_dir)
    handoff = output_dir / "linux_handoff"
    inputs = handoff / "inputs"
    handoff.mkdir(parents=True, exist_ok=True)
    _copy(baseline_ir, inputs / "baseline.hivm.mlir")
    _copy(optimized_ir, inputs / "optimized.hivm.mlir")
    _copy(selected_plan, inputs / "selected_plan.json")

    commands = {
        "parse": "",
        "roundtrip": "",
        "verify": "",
        "compile": "",
        "run": "",
        "msprof": ""
    }
    commands_with_examples = {
        "_comment": "Fill these command templates on Ascend Linux. Placeholders: {ir}, {kind}, {out}, {root}. Empty means SKIPPED.",
        **commands,
        "_examples": {
            "parse": "your_hivm_parser --input {ir} --out {out}/parsed.mlir",
            "roundtrip": "your_hivm_ops_editor --roundtrip {ir} --out {out}/roundtrip.hivm.mlir",
            "verify": "your_mlir_or_hivm_verify {ir}",
            "compile": "your_hivm_compile {ir} -o {out}/{kind}_kernel",
            "run": "your_kernel_runner --kernel {out}/{kind}_kernel --output {out}/output.bin",
            "msprof": "msprof --output {out}/msprof --application='your_kernel_runner --kernel {out}/{kind}_kernel'"
        }
    }
    _write_json(handoff / "backend_commands.json", commands_with_examples)
    _write_json(handoff / "backend_commands.template.json", commands_with_examples)
    (handoff / "run_linux_validation.py").write_text(_script_linux_validation_py(), encoding="utf-8")
    (handoff / "collect_msprof_compare.py").write_text(_script_msprof_compare_py(), encoding="utf-8")
    (handoff / "README_LINUX_HANDOFF_CN.md").write_text(_readme_cn(), encoding="utf-8")

    gates = {
        "schema_version": "hivm_v61_acceptance_gates_v1",
        "gates_before_perf_claim": [
            {"name": "baseline_parse", "required": True},
            {"name": "optimized_parse", "required": True},
            {"name": "baseline_roundtrip", "required": True},
            {"name": "optimized_roundtrip", "required": True},
            {"name": "baseline_verify", "required": True},
            {"name": "optimized_verify", "required": True},
            {"name": "baseline_compile", "required": True},
            {"name": "optimized_compile", "required": True},
            {"name": "correctness_baseline_vs_optimized", "required": True},
            {"name": "baseline_msprof", "required": True},
            {"name": "optimized_msprof", "required": True}
        ],
        "claim_rule": "Do not claim speedup until all required gates pass and repeated msprof medians are compared.",
    }
    _write_json(handoff / "acceptance_gates.json", gates)

    # Contract emphasizes what must be checked by the real backend, especially
    # for Tiling/CVPipeline materialization that cannot be proven in portable Python.
    contract = {
        "schema_version": "hivm_v61_backend_patch_contract_v1",
        "baseline_ir": "inputs/baseline.hivm.mlir",
        "optimized_ir": "inputs/optimized.hivm.mlir",
        "selected_plan": "inputs/selected_plan.json",
        "must_validate": {
            "TilingPlan": [
                "tile_m/tile_n/tile_k are reflected in loop bounds/steps or backend-recognized tile attrs",
                "M/N/K axis binding is accepted by backend",
                "load/store slices and compute tile shapes are consistent",
                "tail_strategy is lowered to valid mask/pad/divisible-fast-path behavior",
                "reduce_tile_policy preserves partial accumulation semantics"
            ],
            "MultiBufferPlan": [
                "ping/pong allocs are legal in UB/L1",
                "producer/consumer use-def replacement is complete",
                "buffer lifetime and capacity are safe"
            ],
            "CVPipelinePlan": [
                "stage graph is accepted",
                "prologue/steady/epilogue schedule or equivalent backend attrs are legal",
                "producer_consumer_distance is reflected in tile-index dependency",
                "stage_buffer_policy is consistent with MultiBufferPlan slots"
            ],
            "SyncPlan": [
                "set_flag/wait_flag event ids are legal",
                "no wait-before-set or event reuse conflict",
                "new schedule dependency graph is synchronized"
            ]
        },
        "portable_claim": "V6.1 creates a runnable Linux handoff directory. Official backend tools decide pass/fail.",
    }
    _write_json(handoff / "backend_patch_contract.json", contract)

    manifest = {
        "schema_version": "hivm_v61_linux_handoff_manifest_v1",
        "handoff_dir": str(handoff),
        "baseline_ir": str(inputs / "baseline.hivm.mlir"),
        "optimized_ir": str(inputs / "optimized.hivm.mlir"),
        "selected_plan": str(inputs / "selected_plan.json"),
        "runner": str(handoff / "run_linux_validation.py"),
        "perf_collector": str(handoff / "collect_msprof_compare.py"),
        "acceptance_gates": str(handoff / "acceptance_gates.json"),
        "backend_patch_contract": str(handoff / "backend_patch_contract.json"),
        "rewrite_summary_linux_ready_claim": False,
        "linux_backend_validation_required": True,
        "next_action": "Copy linux_handoff/ to Ascend Linux, fill backend_commands.json, run python3 run_linux_validation.py.",
    }
    if rewrite_summary:
        manifest["upstream_rewrite_summary"] = {
            "four_plan_operation_rewrite_performed": rewrite_summary.get("four_plan_operation_rewrite_performed"),
            "v60_real_operation_materialization_performed": rewrite_summary.get("v60_real_operation_materialization_performed"),
            "recommended_linux_validation_ir": rewrite_summary.get("recommended_linux_validation_ir"),
            "linux_precompile_blocker_count": rewrite_summary.get("linux_precompile_blocker_count"),
        }
    _write_json(output_dir / "v61_linux_handoff_manifest.json", manifest)
    _write_json(handoff / "v61_linux_handoff_manifest.json", manifest)
    return manifest
