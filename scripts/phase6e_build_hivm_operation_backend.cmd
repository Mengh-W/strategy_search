@echo off
setlocal enabledelayedexpansion
REM Windows CMD wrapper for backend adapter patch/build.
REM Note: many Ascend/vTriton/CANN builds are Linux-oriented. If CMake/vTriton build is not Windows-ready,
REM use WSL/Linux. This wrapper is only for environments where vTriton is already configured under Windows.
if "%~1"=="" goto :usage

set VTRITON_ROOT=%~1
set BUILD_DIR=%~2
if "%BUILD_DIR%"=="" set BUILD_DIR=%VTRITON_ROOT%\build
set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..

python "%SCRIPT_DIR%phase6e_apply_vtriton_backend_patch.py" --vtriton-root "%VTRITON_ROOT%" --adapter-dir "%PROJECT_ROOT%\vtriton_hivm_operation_backend" --report "%PROJECT_ROOT%\phase6e_vtriton_backend_patch_report.json" --apply
if errorlevel 1 goto :error

if not exist "%BUILD_DIR%" (
  echo [ERROR] Build dir does not exist: %BUILD_DIR%
  echo Re-run your vTriton CMake configure first.
  echo Example: cmake -S "%VTRITON_ROOT%" -B "%BUILD_DIR%" ^<your existing vTriton MLIR/BishengIR options^>
  exit /b 3
)

cmake --build "%BUILD_DIR%" --target hivm-operation-backend --config Release --parallel
if errorlevel 1 goto :error

set BIN=%BUILD_DIR%\bin\Release\hivm-operation-backend.exe
if not exist "%BIN%" set BIN=%BUILD_DIR%\bin\hivm-operation-backend.exe
if not exist "%BIN%" set BIN=%BUILD_DIR%\tools\hivm-operation-backend\Release\hivm-operation-backend.exe
if not exist "%BIN%" (
  echo [ERROR] Build finished but hivm-operation-backend.exe was not found in common Windows output paths.
  echo Please search under: %BUILD_DIR%
  exit /b 4
)

"%BIN%" --print-capabilities
exit /b 0

:usage
echo Usage:
echo   scripts\phase6e_build_hivm_operation_backend.cmd C:\path\to\vTriton [C:\path\to\vTriton\build]
exit /b 2

:error
echo [ERROR] Build failed. Check CMake/include/link output above.
exit /b 1
