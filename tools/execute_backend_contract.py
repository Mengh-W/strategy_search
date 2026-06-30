#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Execute backend-contract smoke checks against a HIVM operation backend."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategy_search.backend_contract_runner import execute_backend_contract


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", required=True, help="Path to hivm-operation-backend or tools/fake_hivm_operation_backend.py")
    ap.add_argument("--ir", required=True, help="Input .hivm.mlir")
    ap.add_argument("--contract", required=True, help="Backend contract/edit-script JSON")
    ap.add_argument("--output-dir", required=True, help="Output directory for backend reports")
    ap.add_argument("--mutation-kind", default="contract_smoke")
    ap.add_argument("--run-mutate", action="store_true", help="Request backend mutation. Do not use until dry-run passes on a real backend.")
    args = ap.parse_args()

    summary = execute_backend_contract(
        Path(args.backend),
        Path(args.ir),
        Path(args.contract),
        Path(args.output_dir),
        run_mutate=args.run_mutate,
        mutation_kind=args.mutation_kind,
    )
    print(json.dumps({
        "summary": str(Path(args.output_dir) / "backend_contract_execution_summary.json"),
        "decision": summary.get("decision"),
        "is_real_mlir_backend": summary.get("is_real_mlir_backend"),
        "all_required_commands_ok": summary.get("all_required_commands_ok"),
        "production_rewrite_claim_allowed": summary.get("production_rewrite_claim_allowed"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
