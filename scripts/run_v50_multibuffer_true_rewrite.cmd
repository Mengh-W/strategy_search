@echo off
setlocal
set IR_PATH=%~1
if "%IR_PATH%"=="" set IR_PATH=sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir
set SELECTED_PLAN=%~2
if "%SELECTED_PLAN%"=="" set SELECTED_PLAN=artifacts\latest_smoke_run\selected_plan.json
set OUT_DIR=%~3
if "%OUT_DIR%"=="" set OUT_DIR=artifacts\v50_multibuffer_true_rewrite
set MAX_CANDIDATES=%~4
if "%MAX_CANDIDATES%"=="" set MAX_CANDIDATES=80
set MAX_ACTIONS=%~5
if "%MAX_ACTIONS%"=="" set MAX_ACTIONS=3
python tools\run_multibuffer_true_rewrite.py ^
  --ir "%IR_PATH%" ^
  --selected-plan "%SELECTED_PLAN%" ^
  --output-dir "%OUT_DIR%" ^
  --max-candidates %MAX_CANDIDATES% ^
  --max-actions %MAX_ACTIONS%
endlocal
