# vTriton Adapter for HIVM Strategy Rewrite

This directory contains the Phase-2D backend boundary for operation-sequence HIVM rewrite.

## Current status

`hivm_strategy_rewrite.cpp` is a buildable standalone strict bridge. It consumes:

```bash
--input original.hivm.mlir
--edit-script structural_edit_script.json
--output optimized.structural.hivm.mlir
--report structural_rewrite.external_vtriton_report.json
```

and currently implements two conservative structural edits:

```text
1. replace_barrier_all_with_directional_sync
2. insert_sync_before_first_vector_op
```

### 1. Barrier replacement

Explicit anchors such as:

```mlir
hivm.hir.barrier {mode = "ALL"}
```

can be replaced with:

```mlir
hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_M>, <EVENT_IDk>]
hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_M>, <EVENT_IDk>]
```

### 2. CV boundary sync insertion

If the edit script enables `insert_sync_before_first_vector_op`, the bridge identifies a simple local pattern:

```text
cube/fixpipe anchor
  ...
first vector op
```

and inserts a directional sync before the vector stage:

```mlir
hivm.hir.set_flag[<PIPE_FIX>, <PIPE_V>, <EVENT_IDk>]
hivm.hir.wait_flag[<PIPE_FIX>, <PIPE_V>, <EVENT_IDk>]
```

This is a local sync-boundary materialization only. It does not implement full cube/vector overlap scheduling, event reuse, stage-buffer cloning, or loop reordering.

## Build

Standalone demo build:

```bash
mkdir -p build_phase2d
g++ -std=c++17 vtriton_adapter/hivm_strategy_rewrite.cpp -o build_phase2d/hivm-strategy-rewrite
```

CMake build:

```bash
cmake -S vtriton_adapter -B build_phase2d
cmake --build build_phase2d
```

## Use from the Python search pipeline

```bash
python -m strategy_search.cli \
  --kernel sample_input/fa_bad_inefficient.hivm.mlir \
  --hardware-config configs/ascend_910b.json \
  --enable-ir-rewrite \
  --rewrite-mode both \
  --rewrite-safety balanced \
  --enable-structural-rewrite \
  --structural-rewrite-safety balanced \
  --structural-rewrite-backend vtriton \
  --vtriton-strategy-rewriter build_phase2d/hivm-strategy-rewrite \
  --output-dir output_phase2d_demo
```

## Important boundary

This bridge is not the final production compiler pass. It is intentionally narrow and auditable so the project has a C++ executable backend boundary before a full local vTriton/MLIR integration is available.

Production target:

```text
vTriton/HivmOpsEditor or MLIR PatternRewriter/RewriterBase operation-level mutation
+ target HIVM/NPUIR dialect parser verification
+ dependency / buffer-liveness legality checker
+ tritonsim-hivm DES/trace validation
```

## Next backend features

Recommended next edits:

```text
1. remove_adjacent_duplicate_sync_pairs
2. remove_redundant_gm_roundtrip with GM-base legality checker
3. loop-invariant Q load hoist with buffer liveness checker
4. real double-buffer rewrite after UB/L1 liveness and capacity validation
```

## Phase-2E update

The standalone C++ bridge now reports itself as Phase-2E and supports:

- real mutation: `replace_barrier_all_with_directional_sync`
- real mutation: `insert_sync_before_first_vector_op`
- precheck only: `remove_redundant_gm_roundtrip`

`remove_redundant_gm_roundtrip` is intentionally not erased by this standalone bridge.  It only detects nearby same-GM store/load candidates and records a deferred reason.  Production deletion requires target MLIR/vTriton alias/dependency proof through HivmOpsEditor or an MLIR PatternRewriter/RewriterBase pass.

## Phase-2G update: capability handshake and adapter manifest

The standalone C++ bridge now supports a capability handshake:

```bash
hivm-strategy-rewrite --print-capabilities
```

The Python pipeline records this handshake in:

```text
vtriton_adapter_manifest.json
```

The manifest includes:

```text
backend execution plan
external bridge capabilities
requested edit types
coverage by edit type
binary sha256
required CLI and report contract
runtime guards for production vTriton/HivmOpsEditor integration
```

This is a pre-production boundary.  The standalone bridge still performs strict local rewrites only.  The final backend should use vTriton/HivmOpsEditor or MLIR PatternRewriter/RewriterBase APIs inside a target HIVM/NPUIR dialect context.
