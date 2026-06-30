@echo off
setlocal enabledelayedexpansion
set IR_PATH=%~1
if "%IR_PATH%"=="" set IR_PATH=sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir
set SELECTED_PLAN=%~2
if "%SELECTED_PLAN%"=="" set SELECTED_PLAN=artifacts\latest_smoke_run\selected_plan.json
set OUT_DIR=%~3
if "%OUT_DIR%"=="" set OUT_DIR=artifacts\v49_multibuffer_stage_boundary
set MAX_CANDIDATES=%~4
if "%MAX_CANDIDATES%"=="" set MAX_CANDIDATES=80
set MAX_ANNOTATIONS=%~5
if "%MAX_ANNOTATIONS%"=="" set MAX_ANNOTATIONS=30
python tools\run_multibuffer_stage_boundary.py ^
  --ir "%IR_PATH%" ^
  --selected-plan "%SELECTED_PLAN%" ^
  --output-dir "%OUT_DIR%" ^
  --max-candidates "%MAX_CANDIDATES%" ^
  --max-annotations "%MAX_ANNOTATIONS%"
endlocal
