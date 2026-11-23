@echo off
REM ===========================================================================
REM  Take port 8000 back, then start the backend on the file that is on disk.
REM
REM  Double-click from the backend folder, instead of start.bat.
REM
REM  WHAT WENT WRONG, AND WHAT THIS DOES ABOUT IT
REM  --------------------------------------------
REM  A server started days ago was still holding port 8000. Every restart since
REM  then began, failed to bind with
REM
REM      [Errno 10048] only one usage of each socket address ... is permitted
REM
REM  and shut itself down again, leaving the old process serving the website.
REM  So the new chatbot.py sat on disk, correct and unread, while the browser
REM  talked to code loaded before it existed. The one visible symptom was that
REM  the answers never changed.
REM
REM  The previous version of this file tried to kill that process and did not
REM  check whether it worked. It usually does not, for one reason: start.bat
REM  runs uvicorn with --reload, and --reload runs TWO processes, a supervisor
REM  and a worker. Killing either one leaves the other holding the socket.
REM
REM  So this kills the whole process tree, waits, looks again, and repeats. It
REM  refuses to start the server until the port is actually free, and says so
REM  plainly instead of failing eight lines later in a message about sockets.
REM ===========================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not exist "app\ai\chatbot.py" (
  echo.
  echo  [X] No app\ai\chatbot.py here. Put this file in your backend folder.
  echo.
  pause
  exit /b 1
)

set VENVDIR=%LOCALAPPDATA%\energy-analytics-venv
if exist "%LOCALAPPDATA%\energy-venv\Scripts\python.exe" set VENVDIR=%LOCALAPPDATA%\energy-venv
if exist "%~dp0venv\Scripts\python.exe" set VENVDIR=%~dp0venv
set PYEXE=%VENVDIR%\Scripts\python.exe

if not exist "%PYEXE%" (
  echo.
  echo  [X] No virtual environment at:
  echo        %VENVDIR%
  echo      Run load-data.bat once; it builds one.
  echo.
  pause
  exit /b 1
)

echo.
echo  ================================================================
echo    Restarting the backend
echo  ================================================================
echo.
echo  [1/3] Clearing port 8000...

set TRIES=0

:KILLLOOP
set /a TRIES+=1
set BUSY=0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
  set BUSY=1
  echo        stopping process %%p and anything it started
  taskkill /F /T /PID %%p >nul 2>&1
)
if "!BUSY!"=="0" goto PORTFREE
REM Give Windows a moment: a killed socket is not free the instant the process
REM dies, it sits in TIME_WAIT briefly.
ping -n 3 127.0.0.1 >nul
if !TRIES! LSS 5 goto KILLLOOP

echo.
echo        Still held after five attempts. Killing every Python process.
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM pythonw.exe >nul 2>&1
ping -n 3 127.0.0.1 >nul

set BUSY=0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do set BUSY=1
if "!BUSY!"=="0" goto PORTFREE

echo.
echo  ================================================================
echo    [X] Port 8000 is still held by something this cannot stop.
echo  ================================================================
echo.
netstat -ano | findstr ":8000"
echo.
echo    Open Task Manager, Details tab, find the PID in the last column
echo    above, and End task on it. Then run this file again.
echo.
pause
exit /b 1

:PORTFREE
echo        Port 8000 is free.
echo.

echo  [2/3] Reading app\ai\chatbot.py from disk...
"%PYEXE%" -m scripts.which_chatbot
echo.

echo  [3/3] Starting the server WITHOUT --reload, so what runs is exactly
echo        what that file said just now. Leave this window open.
echo.
echo  ================================================================
echo    API   http://localhost:8000
echo.
echo    Ask the assistant, in Arabic, what it can do. An English reply
echo    beginning "I can help with billing questions" means the old
echo    code is still answering. An Arabic reply means the new one.
echo.
echo    Press CTRL+C to stop.
echo  ================================================================
echo.
"%PYEXE%" -m uvicorn app.main:app --port 8000
pause
