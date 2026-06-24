# V3.0 · vTriton Bridge and Strategy-to-HIVM Rewrite

V3.0 turns the strategy-search demo into a vTriton-bridge candidate generator.

## What vTriton provides

vTriton can provide structured evidence for the optimizer:

- `.npuir.mlir` / HIVM MLIR dumped from Triton DSL or supplied directly.
- DES graph JSON (`--des-graph-file`) with operation, pipe, duration, dependency and transfer evidence.
- Perfetto/Chrome trace JSON (`--perfetto-trace-file`) for timeline inspection.
- Bound reports and counterfactual reports from its `perfbound` / validation pipeline when available.
- A validation direction: edit → compile → verify → delta, when a working vTriton build and target environment are available.

## What this demo provides

The demo remains the strategy-search layer:

- Parse HIVM/NPUIR MLIR and optional vTriton DES/trace/bound/counterfactual artifacts.
- Generate and rank four-plan strategy candidates.
- Check UB/L1/L0A/L0B/L0C/GM workspace constraints.
- Emit a selected strategy and a vTriton candidate bundle.

## New V3.0 outputs

Enable with `--enable-ir-rewrite`.

```bash
python auto_strategy_search.py \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --candidate-space expanded \
  --search-mode layered \
  --guided-mode diagnosis \
  --des-profile original_repo_outputs/sample_hivm_des.json \
  --trace-profile optional_profiles/prefill_trace.json \
  --bound-report original_repo_outputs/sample_hivm_bound_report.json \
  --counterfactual original_repo_outputs/counterfactual_results.json \
  --enable-ir-rewrite \
  --rewrite-mode both \
  --rewrite-safety conservative \
  --output-dir output_v3
```

The new bridge outputs are:

- `optimized.annotated.hivm.mlir`: original IR plus `hivm.strategy.*` attributes and module sync hint.
- `optimized.safe_structural.hivm.mlir`: conservative structural IR with safe sync/barrier hints and explicit safe buffer hints when selected strategy has per-buffer multipliers.
- `pass_pipeline_config.json`: requested pass pipeline configuration for TileLoop / MarkMultiBuffer / CVPipelining / GraphSyncSolver / PlanMemory.
- `strategy_edit_script.json`: edit primitive script that can be consumed or translated by a vTriton edit/verify harness.
- `rewrite_diff_report.json`: machine-readable rewrite changes and limitations.
- `rewrite_audit.md`: human-readable audit.
- `vtriton_candidate_bundle.json`: manifest with before/after IR paths and suggested `tritonsim-hivm` rerun command.
- `vtriton_integration_report.json`: summary of consumed vTriton evidence and emitted bridge artifacts.

## Important boundary

V3.0 does not claim to produce final compiler-lowered optimized IR. It produces:

1. strategy hints embedded in HIVM/NPUIR;
2. conservative local structural edits;
3. pass configuration and edit script for vTriton / real compiler validation.

The final correctness/performance proof should come from vTriton or the real compiler stack by running reparse / DES-after / compile / output correctness / msprof delta.
