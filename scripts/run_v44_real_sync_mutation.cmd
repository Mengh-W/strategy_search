@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0\.."
if "%~1"=="" (
  echo Usage: scripts\run_v44_real_sync_mutation.cmd path\to\hivm-operation-backend.exe [ir] [selected_plan] [output_dir]
  echo This runs ONE guarded HivmOpsEditor SyncPlan mutation prototype.
  exit /b 2
)
if not "%HIVM_ALLOW_SYNC_MUTATION%"=="1" (
  echo Refusing to run mutation. Set HIVM_ALLOW_SYNC_MUTATION=1 explicitly.
  echo Example:
  echo   set HIVM_ALLOW_SYNC_MUTATION=1
  echo   scripts\run_v44_real_sync_mutation.cmd path\to\hivm-operation-backend.exe
  exit /b 3
)
set BACKEND=%~1
set IR_PATH=%~2
if "%IR_PATH%"=="" set IR_PATH=sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir
set SELECTED_PLAN=%~3
if "%SELECTED_PLAN%"=="" set SELECTED_PLAN=artifacts\latest_smoke_run\selected_plan.json
set OUT_DIR=%~4
if "%OUT_DIR%"=="" set OUT_DIR=artifacts\v44_real_sync_mutation
set CONTRACT_DIR=%OUT_DIR%\sync_precision_contract
if not exist "%CONTRACT_DIR%" mkdir "%CONTRACT_DIR%"
python tools\build_sync_precision_contract.py --ir "%IR_PATH%" --selected-plan "%SELECTED_PLAN%" --output-dir "%CONTRACT_DIR%"
"%BACKEND%" --mutate --mutation-kind sync_event_insertion ^
  --input "%IR_PATH%" ^
  --edit-script "%CONTRACT_DIR%\sync_precision_contract.json" ^
  --output "%OUT_DIR%\optimized.sync_hivmopseditor.hivm.mlir" ^
  --report "%OUT_DIR%\sync_hivmopseditor_mutation_report.json"
echo V4.4 real SyncPlan mutation prototype outputs: %OUT_DIR%
endlocal
