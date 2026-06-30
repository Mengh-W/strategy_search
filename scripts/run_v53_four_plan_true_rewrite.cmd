@echo off
setlocal
set IR=%~1
if "%IR%"=="" set IR=sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir
set PLAN=%~2
if "%PLAN%"=="" set PLAN=artifacts\latest_smoke_run\selected_plan.json
set OUT=%~3
if "%OUT%"=="" set OUT=artifacts\v53_four_plan_true_rewrite
set MAX_MB_CAND=%~4
if "%MAX_MB_CAND%"=="" set MAX_MB_CAND=80
set MAX_MB_ACTIONS=%~5
if "%MAX_MB_ACTIONS%"=="" set MAX_MB_ACTIONS=3
set MAX_CV_WINDOWS=%~6
if "%MAX_CV_WINDOWS%"=="" set MAX_CV_WINDOWS=50
set MAX_CV_ACTIONS=%~7
if "%MAX_CV_ACTIONS%"=="" set MAX_CV_ACTIONS=2
set MAX_SYNC=%~8
if "%MAX_SYNC%"=="" set MAX_SYNC=999999
python tools\run_four_plan_true_rewrite.py ^
  --ir "%IR%" ^
  --selected-plan "%PLAN%" ^
  --output-dir "%OUT%" ^
  --max-multibuffer-candidates "%MAX_MB_CAND%" ^
  --max-multibuffer-actions "%MAX_MB_ACTIONS%" ^
  --max-cvpipeline-windows "%MAX_CV_WINDOWS%" ^
  --max-cvpipeline-actions "%MAX_CV_ACTIONS%" ^
  --max-sync-actions "%MAX_SYNC%"
endlocal
