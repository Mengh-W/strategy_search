@echo off
setlocal enabledelayedexpansion
set IR_PATH=%1
if "%IR_PATH%"=="" set IR_PATH=sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir
set PLAN_PATH=%2
if "%PLAN_PATH%"=="" set PLAN_PATH=artifacts\latest_smoke_run\selected_plan.json
set OUT_DIR=%3
if "%OUT_DIR%"=="" set OUT_DIR=artifacts\v412_controller_acceptance_report
set MAX_SYNC=%4
if "%MAX_SYNC%"=="" set MAX_SYNC=999999
set MAX_MB=%5
if "%MAX_MB%"=="" set MAX_MB=80
set MAX_CV=%6
if "%MAX_CV%"=="" set MAX_CV=50
set MAX_ANN=%7
if "%MAX_ANN%"=="" set MAX_ANN=20
python tools\run_controller_acceptance_report.py ^
  --ir "%IR_PATH%" ^
  --selected-plan "%PLAN_PATH%" ^
  --output-dir "%OUT_DIR%" ^
  --max-sync-actions "%MAX_SYNC%" ^
  --max-multibuffer-candidates "%MAX_MB%" ^
  --max-cvpipeline-windows "%MAX_CV%" ^
  --max-annotations "%MAX_ANN%"
endlocal
