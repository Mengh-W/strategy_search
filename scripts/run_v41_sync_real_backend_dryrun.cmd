@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0\.."
if "%~1"=="" (
  echo Usage: scripts\run_v41_sync_real_backend_dryrun.cmd path\to\hivm-operation-backend.exe [ir] [selected_plan] [output_dir]
  exit /b 2
)
set BACKEND=%~1
set IR_PATH=%~2
if "%IR_PATH%"=="" set IR_PATH=sample_input\fa_best.hivm.mlir
set SELECTED_PLAN=%~3
if "%SELECTED_PLAN%"=="" set SELECTED_PLAN=artifacts\latest_smoke_run\selected_plan.json
set OUT_DIR=%~4
if "%OUT_DIR%"=="" set OUT_DIR=artifacts\v41_sync_real_backend_dryrun
python tools\execute_sync_precision_contract.py ^
  --backend "%BACKEND%" ^
  --ir "%IR_PATH%" ^
  --selected-plan "%SELECTED_PLAN%" ^
  --output-dir "%OUT_DIR%"
echo V4.1 Sync real backend dry-run outputs: %OUT_DIR%
endlocal
