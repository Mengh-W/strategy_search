#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 /path/to/hivm-operation-backend fixture.hivm.mlir output_dir [tritonsim-hivm]" >&2
  exit 2
fi
BACKEND="$1"
FIXTURE="$2"
OUT="$3"
TRITONSIM="${4:-}"
mkdir -p "$OUT"

"$BACKEND" --print-capabilities | tee "$OUT/capabilities.json"
"$BACKEND" --inventory --input "$FIXTURE" --report "$OUT/inventory.json"
"$BACKEND" --roundtrip --input "$FIXTURE" --output "$OUT/roundtrip.hivm.mlir" --report "$OUT/roundtrip.json"
"$BACKEND" --verify-only --input "$OUT/roundtrip.hivm.mlir" --report "$OUT/verify.json"

# Limited mutation trial is optional and should be run only on a restricted GM fixture.
"$BACKEND" \
  --mutate \
  --mutation-kind gm_roundtrip_deletion \
  --max-gm-pairs 1 \
  --input "$FIXTURE" \
  --output "$OUT/optimized.gm_removed.hivm.mlir" \
  --report "$OUT/gm_mutation.json" || true

if [[ -n "$TRITONSIM" && -x "$TRITONSIM" ]]; then
  "$TRITONSIM" \
    --npuir-file "$OUT/optimized.gm_removed.hivm.mlir" \
    --scheduler des \
    --des-graph-file "$OUT/optimized_des_graph.json" \
    --perfetto-trace-file "$OUT/optimized_perfetto_trace.json" || true
fi

echo "Phase 6F compiled-backend acceptance smoke finished. Inspect $OUT/*.json"
