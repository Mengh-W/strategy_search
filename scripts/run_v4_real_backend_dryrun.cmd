@echo off
setlocal enabledelayedexpansion
REM V4.0 Windows CMD wrapper: real backend dry-run. No mutation.
if "%~1"=="" goto :usage

set ROOT_DIR=%~dp0..
pushd "%ROOT_DIR%"

set BACKEND=%~1
set IR_PATH=%~2
if "%IR_PATH%"=="" set IR_PATH=sample_input\fa_best.hivm.mlir
set SELECTED_PLAN=%~3
if "%SELECTED_PLAN%"=="" set SELECTED_PLAN=artifacts\latest_smoke_run\selected_plan.json
set OUT_ROOT=%~4
if "%OUT_ROOT%"=="" set OUT_ROOT=artifacts\v4_real_backend_dryrun

set CONTRACT_DIR=%OUT_ROOT%\backend_contract
set EXEC_DIR=%OUT_ROOT%\backend_execution
set ANALYSIS_DIR=%OUT_ROOT%\backend_dryrun_analysis

if not exist "%BACKEND%" (
  echo [ERROR] backend not found: %BACKEND%
  popd
  exit /b 3
)
if not exist "%IR_PATH%" (
  echo [ERROR] input IR not found: %IR_PATH%
  popd
  exit /b 4
)
if not exist "%SELECTED_PLAN%" (
  echo [ERROR] selected_plan not found: %SELECTED_PLAN%
  popd
  exit /b 5
)

if not exist "%CONTRACT_DIR%" mkdir "%CONTRACT_DIR%"
if not exist "%EXEC_DIR%" mkdir "%EXEC_DIR%"
if not exist "%ANALYSIS_DIR%" mkdir "%ANALYSIS_DIR%"

echo [V4.0 real dry-run] Build SyncPlan+MultiBufferPlan backend contract
python tools\build_four_plan_backend_contract.py --ir "%IR_PATH%" --selected-plan "%SELECTED_PLAN%" --output-dir "%CONTRACT_DIR%"
if errorlevel 1 goto :error

echo [V4.0 real dry-run] Execute contract against real backend: %BACKEND%
python tools\execute_backend_contract.py --backend "%BACKEND%" --ir "%IR_PATH%" --contract "%CONTRACT_DIR%\sync_multibuffer_backend_contract.json" --output-dir "%EXEC_DIR%"
if errorlevel 1 goto :error

echo [V4.0 real dry-run] Analyze dry-run and guarded mutation eligibility
python tools\analyze_backend_dryrun.py --contract "%CONTRACT_DIR%\sync_multibuffer_backend_contract.json" --dry-run-report "%EXEC_DIR%\backend_dry_run_contract.json" --execution-summary "%EXEC_DIR%\backend_contract_execution_summary.json" --output-dir "%ANALYSIS_DIR%"
if errorlevel 1 goto :error

echo [V4.0 real dry-run] Done.
echo Summary: %EXEC_DIR%\backend_contract_execution_summary.json
echo Guarded selection: %ANALYSIS_DIR%\guarded_mutation_selection.json
popd
exit /b 0

:usage
echo Usage:
echo   scripts\run_v4_real_backend_dryrun.cmd C:\path\to\hivm-operation-backend.exe [input_ir] [selected_plan] [output_root]
echo.
echo This script does NOT mutate IR. It only runs capabilities/inventory/roundtrip/verify/dry-run.
exit /b 2

:error
echo [ERROR] V4.0 real backend dry-run failed. Check the command output above and generated JSON files.
popd
exit /b 1
