@echo off
setlocal enabledelayedexpansion

REM V4.0 SyncPlan precise dry-run contract builder for Windows CMD.
REM Usage:
REM   scripts\run_v4_sync_precision_contract.cmd [IR_PATH] [SELECTED_PLAN] [OUTPUT_DIR]

set IR_PATH=%~1
set SELECTED_PLAN=%~2
set OUTPUT_DIR=%~3

if "%IR_PATH%"=="" set IR_PATH=sample_input\fa_best.hivm.mlir
if "%SELECTED_PLAN%"=="" set SELECTED_PLAN=artifacts\latest_smoke_run\selected_plan.json
if "%OUTPUT_DIR%"=="" set OUTPUT_DIR=artifacts\latest_sync_precision_contract

python tools\build_sync_precision_contract.py ^
  --ir "%IR_PATH%" ^
  --selected-plan "%SELECTED_PLAN%" ^
  --output-dir "%OUTPUT_DIR%"

if errorlevel 1 (
  echo [ERROR] Sync precision contract generation failed.
  exit /b 1
)

echo [OK] Sync precision contract generated at %OUTPUT_DIR%
endlocal
