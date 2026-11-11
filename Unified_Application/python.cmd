@echo off
if defined UNIFIED_PYTHON (
  "%UNIFIED_PYTHON%" %*
  exit /b
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 %*
  exit /b
)
where python >nul 2>nul
if not errorlevel 1 (
  python %*
  exit /b
)
set "BUNDLED_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%BUNDLED_PYTHON%" (
  "%BUNDLED_PYTHON%" %*
  exit /b
)
echo Python 3.11 or 3.12 is required. Install Python, or set UNIFIED_PYTHON to python.exe.
exit /b 1
