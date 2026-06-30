@echo off
set IR_PATH=%1
if "%IR_PATH%"=="" set IR_PATH=sample_input\fa_best.hivm.mlir
set PLAN_PATH=%2
if "%PLAN_PATH%"=="" set PLAN_PATH=artifacts\latest_smoke_run\selected_plan.json
set OUT_DIR=%3
if "%OUT_DIR%"=="" set OUT_DIR=artifacts\v55_four_plan_production_candidate_rewrite
python tools\run_four_plan_production_candidate_rewrite.py --ir "%IR_PATH%" --selected-plan "%PLAN_PATH%" --output-dir "%OUT_DIR%"
