"""
M3 — HIVM Runner.

Thin runner that invokes the C++ HIVM analysis tool (tritonsim-hivm or
tritonsim-opt) on an NPUIR file and returns an HIVMExtract object.

This is the primary API for A.4 to consume Tier 2 data:
    extract = extract_from_npuir("kernel.npuir.mlir")

No network, no remote profiling, no compile-run search.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from .hivm_extractor import HIVMExtract, extract_hivm


# Binary paths (relative to project root)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TRITONSIM_HIVM = _PROJECT_ROOT / "build" / "bin" / "tritonsim-hivm"
_TRITONSIM_OPT = _PROJECT_ROOT / "build" / "bin" / "tritonsim-opt"


def _find_tool(preferred: Path | None = None) -> Path:
    """Find an available HIVM analysis tool."""
    if preferred and preferred.exists():
        return preferred
    if _TRITONSIM_HIVM.exists():
        return _TRITONSIM_HIVM
    if _TRITONSIM_OPT.exists():
        return _TRITONSIM_OPT
    raise FileNotFoundError(
        "No HIVM analysis tool found. Build the project first: "
        "cd build && ninja"
    )


def extract_from_npuir(
    npuir_path: str | Path,
    *,
    tool: str | Path | None = None,
    hardware_config: str | Path | None = None,
    arg_bindings: dict[str, int] | None = None,
    scheduler: str = "des",
    busiest_core_id: int = 0,
    out_dir: str | Path | None = None,
) -> HIVMExtract:
    """Extract Tier 2 data from an NPUIR file via the C++ analysis tool.

    Invokes ``tritonsim-hivm --npuir-file ... --des-graph-file tmp/des.json``
    (or ``tritonsim-opt --analyze-hivm``) and returns an HIVMExtract.

    Args:
        npuir_path: Path to the .npuir.mlir file.
        tool: Override path to the analysis tool.
        hardware_config: Path to hardware config JSON.
        arg_bindings: Dynamic argument bindings (e.g., {"arg7": 4096}).
        scheduler: Scheduler mode ("des" or "static").
        busiest_core_id: Core ID to focus on (from A.2 GridInfo).
        out_dir: Directory for generated JSON files. Defaults to temp dir.

    Returns:
        HIVMExtract with per-component aggregates, handoffs, and metadata.

    Raises:
        FileNotFoundError: If the tool or NPUIR file is not found.
        subprocess.CalledProcessError: If the tool fails.
    """
    npuir_path = Path(npuir_path)
    if not npuir_path.exists():
        raise FileNotFoundError(f"NPUIR file not found: {npuir_path}")

    tool_path = _find_tool(Path(tool) if tool else None)

    # Output directory
    if out_dir is None:
        tmp = tempfile.TemporaryDirectory(prefix="vtriton_a3_")
        out_dir = Path(tmp.name)
    else:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        tmp = None

    des_graph_file = out_dir / "des.json"

    # Build command
    tool_name = tool_path.name
    if "tritonsim-hivm" in tool_name:
        cmd = [
            str(tool_path),
            "--npuir-file", str(npuir_path),
            "--des-graph-file", str(des_graph_file),
            "--scheduler", scheduler,
        ]
        if hardware_config:
            cmd.extend(["--hardware-config", str(hardware_config)])
        if arg_bindings:
            bindings_str = ",".join(
                f"{k}={v}" for k, v in arg_bindings.items()
            )
            cmd.extend(["--arg-bindings", bindings_str])
    elif "tritonsim-opt" in tool_name:
        opts = []
        if hardware_config:
            opts.append(f"hardware-config={hardware_config}")
        opts.append(f"des-graph-file={des_graph_file}")
        if arg_bindings:
            bindings_str = ",".join(
                f"{k}={v}" for k, v in arg_bindings.items()
            )
            opts.append(f"arg-bindings={bindings_str}")
        cmd = [
            str(tool_path),
            str(npuir_path),
            "--allow-unregistered-dialect",
            f"--analyze-hivm={','.join(opts)}",
        ]
    else:
        raise ValueError(f"Unsupported tool: {tool_path}")

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, result.stdout, result.stderr,
        )

    if not des_graph_file.exists():
        raise FileNotFoundError(
            f"DES graph file not created: {des_graph_file}. "
            f"Tool stderr: {result.stderr[:500]}"
        )

    extract = extract_hivm(des_graph_file)

    # Cleanup temp dir if we created it
    if tmp is not None:
        try:
            tmp.cleanup()
        except Exception:
            pass

    return extract
