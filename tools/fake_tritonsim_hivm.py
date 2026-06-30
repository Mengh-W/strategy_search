#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tiny local tritonsim-hivm fixture for Phase-4B tests/demos.

This is not a performance simulator. It accepts the same minimal flags that the
project passes to tritonsim-hivm and writes schema-light DES/trace JSON files so
CI can exercise the DES/trace reporting path without a full vTriton build.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _extract_ops(text: str):
    ops = []
    for idx, line in enumerate(text.splitlines(), start=1):
        m = re.search(r"\b(hivm\.[A-Za-z0-9_\.]+)", line)
        if m:
            ops.append({"id": len(ops), "name": m.group(1), "line": idx})
    return ops


def main() -> int:
    ap = argparse.ArgumentParser(description="Fake tritonsim-hivm fixture")
    ap.add_argument("--npuir-file", required=True)
    ap.add_argument("--des-graph-file", required=True)
    ap.add_argument("--perfetto-trace-file", required=True)
    args = ap.parse_args()

    ir_path = Path(args.npuir_file)
    text = ir_path.read_text(encoding="utf-8", errors="ignore")
    ops = _extract_ops(text)
    edges = [{"src": i, "dst": i + 1, "type": "sequential"} for i in range(max(0, len(ops) - 1))]
    des = {
        "fixture": "fake_tritonsim_hivm",
        "input": str(ir_path),
        "nodes": ops,
        "edges": edges,
        "note": "CI fixture only; not an authoritative DES graph or performance model.",
    }
    trace_events = []
    for op in ops:
        trace_events.append({
            "name": op["name"],
            "cat": "hivm_fixture",
            "ph": "X",
            "ts": op["id"] * 10,
            "dur": 5,
            "pid": 1,
            "tid": 0,
            "args": {"line": op["line"]},
        })
    trace = {
        "fixture": "fake_tritonsim_hivm",
        "traceEvents": trace_events,
        "displayTimeUnit": "ns",
    }

    Path(args.des_graph_file).parent.mkdir(parents=True, exist_ok=True)
    Path(args.perfetto_trace_file).parent.mkdir(parents=True, exist_ok=True)
    Path(args.des_graph_file).write_text(json.dumps(des, indent=2), encoding="utf-8")
    Path(args.perfetto_trace_file).write_text(json.dumps(trace, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "op_count": len(ops), "des_graph_file": args.des_graph_file, "perfetto_trace_file": args.perfetto_trace_file}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
