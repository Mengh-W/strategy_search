@echo off
set IR=%1
if "%IR%"=="" set IR=sample_input\fa_best.hivm.mlir
set PLAN=%2
if "%PLAN%"=="" set PLAN=artifacts\latest_smoke_run\selected_plan.json
set OUT=%3
if "%OUT%"=="" set OUT=artifacts\v60_four_plan_real_operation_materialization
python tools\run_four_plan_operation_rewrite.py --ir "%IR%" --selected-plan "%PLAN%" --output-dir "%OUT%"
echo [V6.0] recommended Linux validation IR: %OUT%\optimized.four_plan_real_operation_materialized.hivm.mlir
