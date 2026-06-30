# V6.1 Linux Handoff 说明

这个目录是为了把四 Plan rewrite 真正拿到 Ascend Linux 环境验证，而不是只在本地 Python 侧看 report。

## 目录内容

- `inputs/baseline.hivm.mlir`：寻优前/原始 HIVM。
- `inputs/optimized.hivm.mlir`：V6.0 四 Plan real operation materialization 后的 optimized HIVM。
- `inputs/selected_plan.json`：本次寻优选中的四 Plan 参数。
- `backend_commands.json`：你需要根据线下环境填写的 parser/verifier/compiler/run/msprof 命令模板。
- `run_linux_validation.py`：按 baseline 和 optimized 分别执行 parse、roundtrip、verify、compile、run、msprof。
- `collect_msprof_compare.py`：从 msprof/CSV/JSON/text 结果里提取 latency/cycles 并计算 median speedup。
- `acceptance_gates.json`：正式性能对比前必须通过的 gate。

## 使用方式

1. 把整个 `linux_handoff/` 目录拷贝到 Ascend Linux 环境。
2. 根据实际工具链编辑 `backend_commands.json`。
3. 运行：

```bash
python3 run_linux_validation.py
```

4. 查看：

```text
results/linux_validation_results.json
```

只有 baseline 和 optimized 都通过 parse / roundtrip / verify / compile / run，才可以进入 msprof 性能对比。

## 命令模板占位符

`backend_commands.json` 支持这些占位符：

- `{ir}`：当前输入 HIVM 文件。
- `{kind}`：`baseline` 或 `optimized`。
- `{out}`：当前 step 的输出目录。
- `{root}`：handoff 根目录。

示例：

```json
{
  "parse": "your_hivm_parser --input {ir} --out {out}/parsed.mlir",
  "verify": "your_mlir_verify {ir}",
  "compile": "your_hivm_compile {ir} -o {out}/{kind}_kernel",
  "run": "your_runner --kernel {out}/{kind}_kernel --output {out}/output.bin",
  "msprof": "msprof --application='your_runner --kernel {out}/{kind}_kernel' --output {out}/msprof"
}
```

## 重要边界

这个 handoff 包不会替你假装 Linux 已经过了。它的作用是把验证链路整理成可以直接落地执行的目录。只有 `linux_validation_results.json` 中 compile/run/msprof gate 通过后，才能正式说进入性能对比阶段。
