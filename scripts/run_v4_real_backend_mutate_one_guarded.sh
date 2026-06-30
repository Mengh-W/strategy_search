#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'MESSAGE'
[V4.0 guarded mutation]
This legacy guard has been replaced by:
  scripts/run_v4_real_backend_mutate_selected_guarded.sh

Required sequence:
  1) run_v4_real_backend_dryrun.sh
  2) review backend_dryrun_analysis/guarded_mutation_selection.json
  3) if selected=true, run the new script with HIVM_ALLOW_GUARDED_MUTATION=1
MESSAGE
exit 10
