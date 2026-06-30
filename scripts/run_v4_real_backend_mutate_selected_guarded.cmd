@echo off
setlocal enabledelayedexpansion
REM Guarded mutation wrapper for Windows CMD. Requires explicit environment variable.
if not "%HIVM_ALLOW_GUARDED_MUTATION%"=="1" (
  echo [BLOCKED] Set HIVM_ALLOW_GUARDED_MUTATION=1 only after real dry-run selected=true and after review.
  exit /b 10
)
if "%~1"=="" goto :usage
if "%~2"=="" goto :usage
if "%~3"=="" goto :usage

set ROOT_DIR=%~dp0..
pushd "%ROOT_DIR%"
set BACKEND=%~1
set IR_PATH=%~2
set ANALYSIS_DIR=%~3
set OUT_DIR=%~4
if "%OUT_DIR%"=="" set OUT_DIR=artifacts\v4_real_backend_guarded_mutation

if not exist "%BACKEND%" (
  echo [ERROR] backend not found: %BACKEND%
  popd
  exit /b 3
)
if not exist "%ANALYSIS_DIR%\single_guarded_action_contract.json" (
  echo [ERROR] single_guarded_action_contract.json not found under: %ANALYSIS_DIR%
  popd
  exit /b 4
)
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

python tools\execute_backend_contract.py --backend "%BACKEND%" --ir "%IR_PATH%" --contract "%ANALYSIS_DIR%\single_guarded_action_contract.json" --output-dir "%OUT_DIR%" --mutate
if errorlevel 1 goto :error

echo [V4.0 guarded mutation] Done: %OUT_DIR%
popd
exit /b 0

:usage
echo Usage:
echo   set HIVM_ALLOW_GUARDED_MUTATION=1
echo   scripts\run_v4_real_backend_mutate_selected_guarded.cmd C:\path\to\hivm-operation-backend.exe input.hivm.mlir artifacts\v4_real_backend_dryrun\backend_dryrun_analysis [output_dir]
exit /b 2

:error
echo [ERROR] Guarded mutation failed. Check backend output and JSON reports.
popd
exit /b 1
