# V6.1 Linux Handoff 与真机验证落地

V6.1 的目标不是继续增加本地注释或 marker，而是把当前四 Plan real operation materialization 的产物整理成一个可复制到 Ascend Linux 环境的验证包。

## 核心产物

运行：

```bash
bash scripts/run_v61_four_plan_linux_handoff.sh \
  sample_input/fa_best.hivm.mlir \
  artifacts/latest_smoke_run/selected_plan.json \
  artifacts/v61_four_plan_linux_handoff
```

会生成：

```text
artifacts/v61_four_plan_linux_handoff/linux_handoff/
  inputs/baseline.hivm.mlir
  inputs/optimized.hivm.mlir
  inputs/selected_plan.json
  backend_commands.json
  backend_patch_contract.json
  acceptance_gates.json
  run_linux_validation.py
  collect_msprof_compare.py
  README_LINUX_HANDOFF_CN.md
```

## Linux 上怎么用

1. 把 `linux_handoff/` 整个目录复制到 Ascend Linux 环境。
2. 根据真实工具链编辑 `backend_commands.json`。
3. 执行：

```bash
python3 run_linux_validation.py
```

结果会写入：

```text
results/linux_validation_results.json
```

## 什么情况下可以正式性能对比

必须同时满足：

```text
baseline parse/roundtrip/verify/compile/run 通过
optimized parse/roundtrip/verify/compile/run 通过
correctness baseline vs optimized 通过
baseline 和 optimized 都拿到 msprof 数据
```

然后再用：

```bash
python3 collect_msprof_compare.py \
  --baseline path/to/baseline_msprof.csv \
  --optimized path/to/optimized_msprof.csv \
  --out perf_comparison.json
```

## 不能 claim 的内容

V6.1 生成的是 Linux handoff 包，不代表 Linux 已经过。只有真实 backend 的 `linux_validation_results.json` 和 msprof comparison 通过后，才能声称性能提升。
