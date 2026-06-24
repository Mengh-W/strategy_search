# MLIR-derived Artifact Inputs for V3.3

V3.3 uses **MLIR-derived compiler/modeling artifacts** as optional structural inputs. These files are generated from `.npuir.mlir` by vTriton/HIVM analysis tools. They are **not** real-device profiling data and are not treated as measured latency.

Preferred CLI names:

- `--artifact-des-graph <path.json>`: MLIR-derived DES graph artifact, usually named like `prefill_des.json`. It should contain an `operations` array with fields such as `name`, `pipe`, `duration`, `loop_multiplier`, `depends_on`, `is_sync`, `is_barrier`, `event_id`, `bytes`, `flops`, `read_buffers`, `write_buffers`, `src_space`, and `dst_space`.
- `--artifact-trace <path.json>`: MLIR-derived Perfetto/Chrome trace artifact, usually named like `prefill_trace.json`. It should contain `traceEvents` and is used for event-name and sequence evidence.

Deprecated aliases kept for backward compatibility:

- `--des-profile` -> `--artifact-des-graph`
- `--trace-profile` -> `--artifact-trace`

## Important boundary

The default V3.3 online path uses these artifacts only as **structural evidence**:

- pipe/op composition;
- dependency and cross-pipe sync evidence;
- memory space path and bytes proxies;
- buffer read/write and multi-buffer slot evidence;
- loop multiplier and operation sequence patterns;
- trace event-name counts.

It does **not** use:

- real msprof latency;
- measured kernel runtime;
- DES makespan as a target;
- global-scale calibration.

Use the V3.3 default:

```bash
python -m strategy_search.cli \
  --kernel sample_product/kernel_001.npuir.mlir \
  --hardware-config configs/ascend_910b.json \
  --artifact-des-graph sample_product/prefill_des.json \
  --artifact-trace sample_product/prefill_trace.json \
  --artifact-kernel-profile on \
  --des-calibration-mode off \
  --output-dir out_artifact_kernel_profile
```

The legacy `--des-calibration-mode single_trace_prior` path is retained only for offline experiments. It uses DES makespan/global-scale alignment and should not be presented as the V3.3 online cost model.
