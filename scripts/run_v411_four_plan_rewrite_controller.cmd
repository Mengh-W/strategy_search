@echo off
setlocal enabledelayedexpansion
set ROOT=%~dp0..
set IR=%~1
set PLAN=%~2
set OUT=%~3
set MAX_SYNC=%~4
set MAX_MB=%~5
set MAX_CV=%~6
set MAX_ANN=%~7
if "%IR%"=="" set IR=%ROOT%\sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir
if "%PLAN%"=="" set PLAN=%ROOT%\artifacts\latest_smoke_run\selected_plan.json
if "%OUT%"=="" set OUT=%ROOT%\artifacts\v411_four_plan_rewrite_controller
if "%MAX_SYNC%"=="" set MAX_SYNC=999999
if "%MAX_MB%"=="" set MAX_MB=80
if "%MAX_CV%"=="" set MAX_CV=50
if "%MAX_ANN%"=="" set MAX_ANN=20
python "%ROOT%\tools\run_four_plan_rewrite_controller.py" ^
  --ir "%IR%" ^
  --selected-plan "%PLAN%" ^
  --output-dir "%OUT%" ^
  --max-sync-actions %MAX_SYNC% ^
  --max-multibuffer-candidates %MAX_MB% ^
  --max-cvpipeline-windows %MAX_CV% ^
  --max-annotations %MAX_ANN%
endlocal
