@echo off
setlocal
set ROOT_DIR=%~dp0\..
cd /d "%ROOT_DIR%"
set IR=%~1
if "%IR%"=="" set IR=sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir
set PLAN=%~2
if "%PLAN%"=="" set PLAN=artifacts\latest_smoke_run\selected_plan.json
set OUT=%~3
if "%OUT%"=="" set OUT=artifacts\v46_sync_full_portable_rewrite
set MAX_ACTIONS=%~4
if "%MAX_ACTIONS%"=="" set MAX_ACTIONS=999999
python tools\run_sync_full_rewrite.py --ir "%IR%" --selected-plan "%PLAN%" --output-dir "%OUT%" --max-actions %MAX_ACTIONS%
if errorlevel 1 exit /b 1
endlocal
