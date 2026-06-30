# vTriton HIVM Operation Backend Adapter

This directory contains the V4.0 HivmOpsEditor-aligned backend adapter. It is designed to be copied into a vTriton checkout as `<vTriton>/tools/hivm-operation-backend/` and built beside the existing `hivm-crud` tool.

## Source alignment

The implementation is intentionally modeled after vTriton's existing `tools/hivm-crud/hivm-crud.cpp`:

1. register HIVM/BiShengIR and MLIR dialects;
2. call `HivmOpsEditor::loadFromFile(ctx, input)`;
3. create `HivmOpsEditor editor(*module)`;
4. use `listOps()`, `opCounts()`, `exportToFile()`, and `mlir::verify()`;
5. only expose guarded mutation where the real API already exists.

## Current mutation boundary

Supported as real backend operations:

- `--inventory`
- `--roundtrip`
- `--verify-only`
- `--dry-run`
- `--mutate --mutation-kind gm_roundtrip_deletion --max-gm-pairs N`, as a limited prototype using `HivmOpsEditor::removeRedundantLoadStorePair`.

Intentionally rejected for production mutation until new HivmOpsEditor APIs/proofs are added:

- `sync_event_insertion`: APIs exist to insert set/wait, but contract must provide exact target op, event allocation proof, and deadlock check.
- `multibuffer_clone`: needs buffer clone and scoped use-replacement APIs.
- `cv_pipeline_stage_reorder`: needs operation region-motion/dominance APIs.
- `tiling_loop_split`: needs loop split, index remap, slice rewrite, and tail-mask APIs.
- `q_load_hoist`: needs dominance and region-motion proof.

## Build integration

Recommended patch in `vtriton_integration_patch.diff` adds:

```cmake
if(TRITONSIM_HAS_BISHENGIR_HIVM AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/hivm-operation-backend/CMakeLists.txt")
  add_subdirectory(hivm-operation-backend)
  list(APPEND _installed_tools hivm-operation-backend)
endif()
```

This follows the same build guard as `hivm-crud`, because `HivmOpsEditor` is compiled only when `TRITONSIM_HAS_BISHENGIR_HIVM` is enabled.
