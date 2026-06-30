@echo off
setlocal enabledelayedexpansion
REM V4.0 Windows CMD wrapper: fake backend smoke. Does not require vTriton.
set ROOT_DIR=%~dp0..
pushd "%ROOT_DIR%"

set IR_PATH=%~1
if "%IR_PATH%"=="" set IR_PATH=sample_input\fa_best.hivm.mlir
set SELECTED_PLAN=%~2
if "%SELECTED_PLAN%"=="" set SELECTED_PLAN=artifacts\latest_smoke_run\selected_plan.json
set OUT_ROOT=%~3
if "%OUT_ROOT%"=="" set OUT_ROOT=artifacts\v4_fake_backend_smoke

set CONTRACT_DIR=%OUT_ROOT%\backend_contract
set EXEC_DIR=%OUT_ROOT%\backend_execution
set ANALYSIS_DIR=%OUT_ROOT%\backend_dryrun_analysis

if not exist "%CONTRACT_DIR%" mkdir "%CONTRACT_DIR%"
if not exist "%EXEC_DIR%" mkdir "%EXEC_DIR%"
if not exist "%ANALYSIS_DIR%" mkdir "%ANALYSIS_DIR%"

echo [V4.0 fake smoke] Build backend contract
python tools\build_four_plan_backend_contract.py --ir "%IR_PATH%" --selected-plan "%SELECTED_PLAN%" --output-dir "%CONTRACT_DIR%"
if errorlevel 1 goto :error

echo [V4.0 fake smoke] Execute contract with bundled fake backend
python tools\execute_backend_contract.py --backend tools\fake_hivm_operation_backend.py --ir "%IR_PATH%" --contract "%CONTRACT_DIR%\sync_multibuffer_backend_contract.json" --output-dir "%EXEC_DIR%"
if errorlevel 1 goto :error

echo [V4.0 fake smoke] Analyze dry-run and guarded mutation eligibility
python tools\analyze_backend_dryrun.py --contract "%CONTRACT_DIR%\sync_multibuffer_backend_contract.json" --dry-run-report "%EXEC_DIR%\backend_dry_run_contract.json" --execution-summary "%EXEC_DIR%\backend_contract_execution_summary.json" --output-dir "%ANALYSIS_DIR%"
if errorlevel 1 goto :error

echo [V4.0 fake smoke] Done.
echo Summary: %EXEC_DIR%\backend_contract_execution_summary.json
echo Dry-run analysis: %ANALYSIS_DIR%\backend_dryrun_analysis_summary.json
popd
exit /b 0

:error
echo [ERROR] V4.0 fake backend smoke failed. Check the command output above.
popd
exit /b 1
