@echo off
REM ===========================================================================
REM  Which chatbot file is the backend really running, and what does it say?
REM
REM  Double-click this file from the backend folder.
REM
REM  WHY IT LOOKS FOR PYTHON IN %LOCALAPPDATA%
REM  ------------------------------------------
REM  The first version of this file looked for the environment inside the
REM  project, at backend\venv, did not find one, and fell back to whatever
REM  "python" happens to be on PATH. That Python has none of the project's
REM  packages, so the check died on "No module named 'pandas'" and told us
REM  nothing about the chatbot at all.
REM
REM  This project's environment is not in the project. start.bat puts it in
REM  %LOCALAPPDATA% on purpose: Documents is synced by OneDrive, OneDrive locks
REM  files while pip is still writing them, and that breaks the install of
REM  large packages such as pandas with "WinError 32".
REM
REM  So this uses the same search order as start.bat and load-data.bat, which
REM  is the environment the backend itself runs in. That matters here more than
REM  anywhere: the whole point is to inspect the Python the server uses.
REM ===========================================================================
setlocal
cd /d "%~dp0"

if not exist "app\ai\chatbot.py" (
  echo.
  echo  [X] Cannot find app\ai\chatbot.py under:
  echo        %CD%
  echo.
  echo      Put this file inside your backend folder, next to start.bat.
  echo.
  pause
  exit /b 1
)

set VENVDIR=%LOCALAPPDATA%\energy-analytics-venv
if exist "%LOCALAPPDATA%\energy-venv\Scripts\python.exe" set VENVDIR=%LOCALAPPDATA%\energy-venv
if exist "%~dp0venv\Scripts\python.exe" set VENVDIR=%~dp0venv
set PYEXE=%VENVDIR%\Scripts\python.exe

if not exist "%PYEXE%" goto NOVENV

echo.
echo  ================================================================
echo    Checking the chatbot
echo  ================================================================
echo    Environment: %VENVDIR%
echo.

"%PYEXE%" -m scripts.check_chatbot
if errorlevel 1 goto SHOWFILE

:SHOWFILE
echo.
if exist chatbot-check.txt start notepad chatbot-check.txt
goto END

:NOVENV
echo.
echo  [X] No virtual environment found at:
echo        %VENVDIR%
echo.
echo      This is the same place start.bat and load-data.bat look. If the
echo      backend runs for you, it is finding Python somewhere else. Run
echo      load-data.bat once - it builds the environment if there is none.
goto END

:END
echo.
pause
