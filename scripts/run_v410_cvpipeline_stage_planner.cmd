@echo off
setlocal EnableExtensions EnableDelayedExpansion
set ROOT=%~dp0..
set IR=%~1
if "%IR%"=="" set IR=%ROOT%\sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir
set PLAN=%~2
if "%PLAN%"=="" set PLAN=%ROOT%\artifacts\latest_smoke_run\selected_plan.json
set OUT=%~3
if "%OUT%"=="" set OUT=%ROOT%\artifacts\v410_cvpipeline_stage_planner
set MAX_WINDOWS=%~4
if "%MAX_WINDOWS%"=="" set MAX_WINDOWS=50
set MAX_ANNOTATIONS=%~5
if "%MAX_ANNOTATIONS%"=="" set MAX_ANNOTATIONS=20
set MB_REPORT=%~6
if not exist "%OUT%" mkdir "%OUT%"
if "%MB_REPORT%"=="" (
  python "%ROOT%\tools\run_cvpipeline_stage_planner.py" --ir "%IR%" --selected-plan "%PLAN%" --output-dir "%OUT%" --max-windows %MAX_WINDOWS% --max-annotations %MAX_ANNOTATIONS%
) else (
  python "%ROOT%\tools\run_cvpipeline_stage_planner.py" --ir "%IR%" --selected-plan "%PLAN%" --output-dir "%OUT%" --multibuffer-stage-report "%MB_REPORT%" --max-windows %MAX_WINDOWS% --max-annotations %MAX_ANNOTATIONS%
)
endlocal
