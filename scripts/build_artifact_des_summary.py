# -*- coding: utf-8 -*-
"""Build lightweight MLIR-derived DES artifact summaries.

Preferred V3.3 name for the old build_des_profile_summary helper.
The input is a compiler/modeling artifact generated from MLIR, not real profiling data.

Examples:
  python scripts/build_artifact_des_summary.py \
    --artifact-des-graph profiles/raw/chunk_kernel_des.json \
    --mlir sample_input/chunk_kernel.npuir.mlir \
    --sample-id chunk_kernel_001 \
    --output profiles/summaries/chunk_kernel_001_summary.json

  python scripts/build_artifact_des_summary.py \
    --manifest profiles/des_calibration_manifest.example.json \
    --output-dir profiles/summaries
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategy_search.des_profile import summarize_des_trace, summarize_manifest, write_des_profile_summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Build MLIR-derived artifact DES summary JSON files.")
    ap.add_argument("--artifact-des-graph", default=None, help="Raw MLIR-derived artifact DES graph JSON containing an operations array.")
    ap.add_argument("--des-profile", default=None, help="Deprecated alias for --artifact-des-graph.")
    ap.add_argument("--mlir", default="", help="Optional MLIR/HIVM file associated with --artifact-des-graph.")
    ap.add_argument("--sample-id", default="", help="Optional sample id for a single artifact DES graph.")
    ap.add_argument("--output", default=None, help="Output summary JSON for a single artifact DES graph.")
    ap.add_argument("--manifest", default=None, help="Optional manifest with multiple artifact DES samples.")
    ap.add_argument("--output-dir", default=None, help="Directory for summaries when --manifest is used.")
    args = ap.parse_args()

    if args.manifest:
        out_dir = Path(args.output_dir or "profiles/summaries")
        out_dir.mkdir(parents=True, exist_ok=True)
        summaries = summarize_manifest(args.manifest)
        for s in summaries:
            out = out_dir / f"{s.sample_id or Path(s.des_trace_file).stem}_summary.json"
            write_des_profile_summary(s, out)
            print(f"[OK] {s.sample_id}: ops={s.num_ops}, makespan={s.makespan_cycles:.2f}, overlap={s.observed_overlap_ratio:.4f} -> {out}")
        print(f"[DONE] wrote {len(summaries)} summaries to {out_dir}")
        return

    artifact_des_graph = args.artifact_des_graph or args.des_profile
    if not artifact_des_graph or not args.output:
        raise SystemExit("Either use --manifest --output-dir, or use --artifact-des-graph --output.")
    summary = summarize_des_trace(artifact_des_graph, mlir_file=args.mlir, sample_id=args.sample_id)
    write_des_profile_summary(summary, args.output)
    print(f"[OK] sample_id={summary.sample_id}")
    print(f"     num_ops={summary.num_ops}")
    print(f"     makespan_cycles={summary.makespan_cycles:.2f}")
    print(f"     total_duration_cycles={summary.total_duration_cycles:.2f}")
    print(f"     observed_overlap_ratio={summary.observed_overlap_ratio:.4f}")
    print(f"     dominant_pipe={summary.dominant_pipe}")
    print(f"     output={args.output}")


if __name__ == "__main__":
    main()
