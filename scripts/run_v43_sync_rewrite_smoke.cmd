@echo off
setlocal
set IR=%~1
set PLAN=%~2
set OUT=%~3
if "%IR%"=="" set IR=sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir
if "%PLAN%"=="" set PLAN=artifacts\latest_smoke_run\selected_plan.json
if "%OUT%"=="" set OUT=artifacts\v43_sync_rewrite_smoke
set PYTHONPATH=.
python tools\apply_sync_rewrite.py --ir "%IR%" --selected-plan "%PLAN%" --output-dir "%OUT%" --max-actions 1
endlocal
