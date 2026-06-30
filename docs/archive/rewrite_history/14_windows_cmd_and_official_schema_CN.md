# V4.0 Windows CMD 运行方式与更完整官方 HIVM Dialect 调用说明

## 1. 为什么 ChatGPT 这里不能直接替你跑真实 vTriton/HivmOpsEditor

当前仓库里的 Python 链路、fake backend、JSON contract、pytest，我可以在沙箱里跑。  
但真实 `hivm-operation-backend` 编译和 vTriton 验收依赖你的本地环境，主要包括：

1. 真实 vTriton 源码目录和已经配置过的 build 目录；
2. vTriton 依赖的 MLIR / LLVM / BishengIR / CMake 配置；
3. HivmOpsEditor 的真实头文件、namespace、link target；
4. 可能还包括 Ascend/CANN/BishengIR 环境变量；
5. Windows 或 WSL/Linux 的编译工具链差异。

我这里没有你的本地 `D:\hivm\...`、没有你机器上的 vTriton build cache、也没有 Ascend/CANN runtime，所以不能替你完成真实 C++ 后端编译。  
我能做的是：

```text
1. 写好 adapter / contract / runner / analyzer；
2. 写好 Windows CMD wrapper；
3. 告诉你跑哪条命令；
4. 你把报错或 JSON 输出给我后，我继续修 CMake、API、contract 或 analyzer。
```

## 2. Windows CMD 下怎么跑

### 2.1 fake backend smoke，不需要 vTriton

在 Windows CMD 里进入仓库根目录：

```cmd
cd /d D:\hivm\HIVM_strategy_search_demo_V4.0
```

然后跑：

```cmd
scripts\run_v4_fake_backend_smoke.cmd
```

这一步只验证仓库内部链路：

```text
selected_plan.json
  -> HIVM inventory
  -> backend contract
  -> fake backend execution
  -> dry-run analysis
```

它不会证明真实 rewrite，只证明 V4.0 Python/JSON/脚本链路没有断。

### 2.2 编译真实 hivm-operation-backend

如果你的 vTriton 能在 Windows 下 CMake build，跑：

```cmd
scripts\phase6e_build_hivm_operation_backend.cmd D:\path\to\vTriton D:\path\to\vTriton\build
```

目标是生成类似：

```text
D:\path\to\vTriton\build\bin\Release\hivm-operation-backend.exe
```

如果你的 vTriton/CANN/BishengIR 工具链只支持 Linux，这一步应该在 WSL/Linux 里跑，而不是原生 Windows CMD。Windows CMD wrapper 只是为“Windows 下已经能配置和编译 vTriton”的情况准备。

### 2.3 真实 backend dry-run，不做 mutation

编译成功后，在 Windows CMD 跑：

```cmd
scripts\run_v4_real_backend_dryrun.cmd ^
  D:\path\to\vTriton\build\bin\Release\hivm-operation-backend.exe ^
  sample_input\fa_best.hivm.mlir ^
  artifacts\latest_smoke_run\selected_plan.json ^
  artifacts\v4_real_backend_dryrun
```

这一步只做：

```text
--print-capabilities
--inventory
--roundtrip
--verify-only
--dry-run
```

不要直接 mutation。

### 2.4 真实 guarded mutation，暂时不要跑

只有当 dry-run 输出里：

```json
{"selected": true}
```

并且我看过 `guarded_mutation_selection.json` 和 `single_guarded_action_contract.json` 之后，才考虑跑：

```cmd
set HIVM_ALLOW_GUARDED_MUTATION=1
scripts\run_v4_real_backend_mutate_selected_guarded.cmd ^
  D:\path\to\hivm-operation-backend.exe ^
  sample_input\fa_best.hivm.mlir ^
  artifacts\v4_real_backend_dryrun\backend_dryrun_analysis ^
  artifacts\v4_real_backend_guarded_mutation
```

## 3. 官方 HIVM Dialect 文档如何更完整地接入

V4.0 之前只建了一个最小 schema，主要覆盖：

```text
load / store / nd2nz / copy / mmad / fixpipe / vector ops / set_flag / wait_flag / pipe_barrier
```

这已经够支撑 `fa_best.hivm.mlir` 的第一轮四 Plan rewrite readiness，但还不够覆盖官方 HIVM Dialect 的更多 op。

V4.0 当前扩展为“更完整但仍保守”的 schema 覆盖。原则是：

```text
1. 官方文档中列出的 op 尽量登记进 schema，避免被误判 unknown；
2. 登记不等于允许 Python 直接 rewrite；
3. 所有真实 mutation 仍要求 HivmOpsEditor backend dry-run 证明；
4. 有 side effect / atomic / sync / custom / pointer cast 的 op 默认作为 blocker 或需要更严格证明。
```

### 3.1 官方文档中的主要 op 大类

根据 AscendNPU-IR 官方 HIVM Dialect 页面，HIVM 是 Hybrid Intelligence Virtual Machine dialect，页面列出了 `hivm.hir.*` operations、attributes 和 enums。

当前 schema 按下面几类使用：

| 大类 | 代表 op | 对四 Plan 的作用 | 默认 mutation 策略 |
|---|---|---|---|
| GM/local data movement | `load`, `store`, `copy`, `load_scalar` | MultiBuffer / CVPipeline 的 producer-consumer anchor | 后端证明后才改 |
| Layout/view/cast | `nd2nz`, `nz2nd`, `convert_layout`, `bitcast`, `pointer_cast` | CVPipeline stage / alias-sensitive anchor | 不在 Python 文本层移动 |
| Cube/matmul | `matmul`, `mix_matmul`, `batchMmadL1`, `mmadL1`, `mmad` | CVPipeline compute stage / Tiling anchor | 后端证明后才改 |
| Vector compute | `vadd`, `vsub`, `vexp`, `vdiv`, `vreduce`, etc. | CVPipeline vector stage | 第一阶段不作为 mutation target |
| Sync/event | `set_flag`, `wait_flag`, `pipe_barrier`, `sync_block*` | SyncPlan / CVPipeline boundary | 只交给 backend 创建或改写 |
| Atomic/side-effect | `atomic_*`, `custom`, `dcci`, `debug`, `set_ffts_base_addr` | alias/safety blocker | 默认禁止移动/删除 |
| System query | `get_block_idx`, `get_block_num`, `get_sys_cnt` | Tiling / mapping anchor | 不跨 control boundary 移动 |

### 3.2 为什么更完整 schema 仍然不能直接生成真实 op

官方文档能告诉我们：

```text
op 名字、语法、operand、attribute、interface、enum
```

但不能单独证明：

```text
1. 这个 op 在当前 block/region 能不能移动；
2. use-def 链是否完整；
3. buffer clone 后所有 uses 是否都替换了；
4. event id 是否冲突；
5. pipe/event/sync 是否可能死锁；
6. loop tiling 后 tail mask 是否正确；
7. backend verifier 是否接受。
```

所以 schema 的定位是：

```text
识别和分类，不负责真实改写。
```

真实改写还是：

```text
mutation contract -> HivmOpsEditor backend dry-run -> guarded mutation
```

## 4. 当前你下一步该做什么

### 如果你只是想确认 V4.0 仓库没坏

跑：

```cmd
scripts\run_v4_fake_backend_smoke.cmd
```

### 如果你准备进入真实后端验证

先跑：

```cmd
scripts\phase6e_build_hivm_operation_backend.cmd D:\path\to\vTriton D:\path\to\vTriton\build
```

成功后跑：

```cmd
scripts\run_v4_real_backend_dryrun.cmd ^
  D:\path\to\vTriton\build\bin\Release\hivm-operation-backend.exe ^
  sample_input\fa_best.hivm.mlir ^
  artifacts\latest_smoke_run\selected_plan.json ^
  artifacts\v4_real_backend_dryrun
```

跑完把这些文件发回来：

```text
artifacts\v4_real_backend_dryrun\backend_execution\backend_capabilities.json
artifacts\v4_real_backend_dryrun\backend_execution\backend_inventory.json
artifacts\v4_real_backend_dryrun\backend_execution\backend_roundtrip.json
artifacts\v4_real_backend_dryrun\backend_execution\backend_verify.json
artifacts\v4_real_backend_dryrun\backend_execution\backend_dry_run_contract.json
artifacts\v4_real_backend_dryrun\backend_dryrun_analysis\guarded_mutation_selection.json
```

如果失败，就把 CMD 终端报错和 `phase6e_vtriton_backend_patch_report.json` 发回来。
