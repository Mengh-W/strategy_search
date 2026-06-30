@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0\.."
set IR_PATH=%~1
if "%IR_PATH%"=="" set IR_PATH=sample_input\fa_best.hivm.mlir
set SELECTED_PLAN=%~2
if "%SELECTED_PLAN%"=="" set SELECTED_PLAN=artifacts\latest_smoke_run\selected_plan.json
set OUT_DIR=%~3
if "%OUT_DIR%"=="" set OUT_DIR=artifacts\v41_sync_fake_backend_dryrun
python tools\execute_sync_precision_contract.py ^
  --backend tools\fake_hivm_operation_backend.py ^
  --ir "%IR_PATH%" ^
  --selected-plan "%SELECTED_PLAN%" ^
  --output-dir "%OUT_DIR%"
echo V4.1 Sync fake backend dry-run outputs: %OUT_DIR%
endlocal
