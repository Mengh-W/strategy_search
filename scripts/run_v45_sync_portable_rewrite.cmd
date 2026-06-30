@echo off
setlocal
set IR=%~1
set SELECTED=%~2
set OUT=%~3
if "%IR%"=="" set IR=sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir
if "%SELECTED%"=="" set SELECTED=artifacts\latest_smoke_run\selected_plan.json
if "%OUT%"=="" set OUT=artifacts\v45_sync_portable_rewrite
python tools\run_sync_rewrite_closure.py --ir "%IR%" --selected-plan "%SELECTED%" --output-dir "%OUT%" --max-actions 1
endlocal
