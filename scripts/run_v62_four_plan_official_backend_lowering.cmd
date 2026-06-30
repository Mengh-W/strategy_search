@echo off
set IR=%1
if "%IR%"=="" set IR=sample_input\fa_best.hivm.mlir
set PLAN=%2
if "%PLAN%"=="" set PLAN=artifacts\latest_smoke_run\selected_plan.json
set OUT=%3
if "%OUT%"=="" set OUT=artifacts\v62_four_plan_official_backend_lowering
python tools\run_four_plan_operation_rewrite.py --ir "%IR%" --selected-plan "%PLAN%" --output-dir "%OUT%"
echo.
echo Recommended optimized HIVM for Linux backend validation:
echo %OUT%\linux_handoff\inputs\optimized.hivm.mlir
echo V6.2 audit: %OUT%\v62_official_backend_handoff_audit.json
