@echo off
setlocal
set ROOT=%~dp0..
set IR=%~1
if "%IR%"=="" set IR=%ROOT%\sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir
set PLAN=%~2
if "%PLAN%"=="" set PLAN=%ROOT%\artifacts\latest_smoke_run\selected_plan.json
set OUT=%~3
if "%OUT%"=="" set OUT=%ROOT%\artifacts\v52_tiling_true_rewrite
python "%ROOT%\tools\run_tiling_true_rewrite.py" --ir "%IR%" --selected-plan "%PLAN%" --output-dir "%OUT%"
endlocal
