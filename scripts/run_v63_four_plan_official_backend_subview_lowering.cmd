@echo off
set IR=%1
if "%IR%"=="" set IR=sample_input\fa_best.hivm.mlir
set PLAN=%2
if "%PLAN%"=="" set PLAN=artifacts\latest_smoke_run\selected_plan.json
set OUT=%3
if "%OUT%"=="" set OUT=artifacts\v63_four_plan_official_backend_subview_lowering
python tools\run_four_plan_operation_rewrite.py --ir "%IR%" --selected-plan "%PLAN%" --output-dir "%OUT%"
