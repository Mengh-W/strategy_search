@echo off
set IR_PATH=%1
set PLAN_PATH=%2
set OUT_DIR=%3
if "%IR_PATH%"=="" set IR_PATH=sample_input\fa_best.hivm.mlir
if "%PLAN_PATH%"=="" set PLAN_PATH=artifacts\latest_smoke_run\selected_plan.json
if "%OUT_DIR%"=="" set OUT_DIR=artifacts\v54_tiling_operation_readiness
python tools\run_tiling_operation_readiness.py --ir "%IR_PATH%" --selected-plan "%PLAN_PATH%" --output-dir "%OUT_DIR%"
