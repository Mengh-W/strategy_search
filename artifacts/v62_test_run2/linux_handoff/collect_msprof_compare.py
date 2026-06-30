#!/usr/bin/env python3
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
