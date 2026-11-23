@echo off
REM ==================================================================
REM  AI-Powered Energy Analytics Platform - Backend launcher
REM  Double-click this file to set up and start the backend.
REM
REM  IMPORTANT DESIGN NOTE:
REM  The virtual environment is created in %LOCALAPPDATA%, NOT inside
REM  this project folder. Documents is usually synced by OneDrive, and
REM  OneDrive (or antivirus) locks files while pip is still writing
REM  them, which causes "WinError 32 - file used by another process"
REM  when installing large packages such as pandas.
REM  Keeping the venv outside the synced folder avoids that entirely.
REM ==================================================================
setlocal
cd /d "%~dp0"

REM Reuse whichever virtual environment already exists, so the 550 MB
REM download is never repeated. Checked newest-name-first.
set VENVDIR=%LOCALAPPDATA%\energy-analytics-venv
if exist "%LOCALAPPDATA%\energy-venv\Scripts\python.exe" set VENVDIR=%LOCALAPPDATA%\energy-venv
if exist "%~dp0venv\Scripts\python.exe" set VENVDIR=%~dp0venv
set PYEXE=%VENVDIR%\Scripts\python.exe

echo.
echo  ================================================
echo    Backend setup - AI Energy Analytics Platform
echo  ================================================
echo.

REM ---------- 1. Python -------------------------------------------------
echo  [1/4] Checking Python...
python --version >nul 2>&1
if errorlevel 1 goto NOPYTHON
python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 goto OLDPYTHON
python --version
echo.

REM ---------- 2. Virtual environment ------------------------------------
echo  [2/4] Setting up the virtual environment...
echo        Location: %VENVDIR%
if not exist "%PYEXE%" (
    echo        Creating it... about 30 seconds.
    python -m venv "%VENVDIR%"
)
if not exist "%PYEXE%" goto VENVFAIL

REM Skip the download entirely if everything is already installed.
"%PYEXE%" -c "import fastapi, sqlalchemy, pandas, sklearn, statsmodels, bcrypt" >nul 2>&1
if not errorlevel 1 (
    echo        Dependencies already installed - skipping download.
    goto DBSTEP
)

echo        Installing dependencies - 3 to 5 minutes, about 550 MB.
echo        Please wait and do not close this window.
echo.
"%PYEXE%" -m pip install --upgrade pip
"%PYEXE%" -m pip install -r requirements.txt
if errorlevel 1 goto PIPFAIL
echo.
echo        Dependencies installed.

:DBSTEP
echo.

REM ---------- 3. Database ------------------------------------------------
echo  [3/4] Preparing the database...
if not exist .env copy .env.example .env >nul
"%PYEXE%" -m app.pipeline.seed
if errorlevel 1 goto SEEDFAIL
echo.

REM ---------- 4. Server --------------------------------------------------
REM
REM  CLEAR THE PORT BEFORE BINDING IT
REM  --------------------------------
REM  A server left running from an earlier session keeps port 8000, and this
REM  one then fails to bind with
REM
REM      [Errno 10048] only one usage of each socket address ... is permitted
REM
REM  eight lines below the point where anyone stops reading. The old process
REM  carries on serving the website from whatever code it loaded when it
REM  started, so edited files appear to have no effect at all. That cost an
REM  afternoon once: a new chatbot sat on disk, correct and unread, while the
REM  browser talked to a process from two days earlier.
REM
REM  uvicorn --reload runs a supervisor AND a worker, so the whole tree has to
REM  go, not just the process that owns the socket.
echo  [4/4] Starting the API server...
echo.
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
  echo        A server was already on port 8000. Stopping it.
  taskkill /F /T /PID %%p >nul 2>&1
)
ping -n 2 127.0.0.1 >nul
echo.
echo  ================================================================
echo    API    http://localhost:8000
echo    Docs   http://localhost:8000/docs
echo.
echo    Admin      admin@nxttrn.com     / admin123
echo    Customer   customer@nxttrn.com  / customer123
echo.
echo    KEEP THIS WINDOW OPEN.  Press CTRL+C to stop the server.
echo  ================================================================
echo.
"%PYEXE%" -m uvicorn app.main:app --reload --port 8000
echo.
echo  The server has stopped.
goto END

REM ---------- Error messages --------------------------------------------
:NOPYTHON
echo.
echo  ERROR: Python is not installed, or Windows cannot find it.
echo.
echo  Fix: install Python 3.11 or newer from
echo       https://www.python.org/downloads/
echo  IMPORTANT: on the first installer screen, tick the box
echo       "Add python.exe to PATH"
echo  Then close this window and double-click start.bat again.
goto END

:OLDPYTHON
echo.
echo  ERROR: This project needs Python 3.11 or newer. You have:
python --version
echo.
echo  Fix: install a newer Python from https://www.python.org/downloads/
goto END

:VENVFAIL
echo.
echo  ERROR: could not create the virtual environment at
echo         %VENVDIR%
echo  Try this command manually in PowerShell:
echo      python -m venv "%%LOCALAPPDATA%%\energy-analytics-venv"
goto END

:PIPFAIL
echo.
echo  ERROR: installing the dependencies failed.
echo  Scroll up to read the real error message.
echo.
echo  If you see "WinError 32 - file used by another process":
echo    1. Pause OneDrive syncing (right-click the cloud icon in the
echo       taskbar, then "Pause syncing").
echo    2. Close any other PowerShell or Python windows.
echo    3. Run this file again.
echo.
echo  If you see a network or SSL error, check your internet connection.
goto END

:SEEDFAIL
echo.
echo  ERROR: preparing the database failed.
echo  Scroll up to read the real error message.
goto END

:END
echo.
echo  ----------------------------------------------------------
echo   Press any key to close this window.
echo  ----------------------------------------------------------
pause >nul
endlocal
