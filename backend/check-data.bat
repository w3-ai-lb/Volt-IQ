@echo off
REM ===========================================================================
REM  Where every row in this database came from.
REM
REM  Double-click this file. Nothing is changed or deleted by it.
REM
REM  WHY THIS FILE EXISTS INSTEAD OF JUST TYPING THE COMMAND
REM  ------------------------------------------------------
REM  Typing  python -m scripts.data_provenance  in a normal terminal fails,
REM  and the error does not say why. Two reasons, both invisible:
REM
REM    1. Bare "python" is whichever Python is first on PATH, and the project's
REM       packages are not installed there. They live in a virtual environment
REM       kept in %LOCALAPPDATA%, deliberately outside the project folder,
REM       because Documents is synced by OneDrive and OneDrive locks files
REM       while pip is still writing them.
REM
REM    2. The command has to be run from the backend folder, because
REM       "-m scripts.data_provenance" resolves the module relative to the
REM       working directory.
REM
REM  This finds the same environment start.bat and load-data.bat use, and runs
REM  it from the right place, so neither has to be remembered.
REM
REM  WHAT THE REPORT TELLS YOU
REM  -------------------------
REM  Four tiers, and which rows belong to each: what our seeder invented, what
REM  the supervisor sent, what was computed from his files, and the customer
REM  records generated to his instruction. It also warns about anything stale,
REM  such as a chatbot reply stored before the currency was corrected.
REM ===========================================================================
setlocal
cd /d "%~dp0"

set VENVDIR=%LOCALAPPDATA%\energy-analytics-venv
if exist "%LOCALAPPDATA%\energy-venv\Scripts\python.exe" set VENVDIR=%LOCALAPPDATA%\energy-venv
if exist "%~dp0venv\Scripts\python.exe" set VENVDIR=%~dp0venv
set PYEXE=%VENVDIR%\Scripts\python.exe

if not exist "%PYEXE%" goto NOVENV

"%PYEXE%" -m scripts.data_provenance
if errorlevel 1 goto REPORTFAIL

echo.
echo  ================================================================
echo    Nothing was changed. This report only reads.
echo.
echo    If it warned about stored chat replies, clear the test
echo    transcripts with:
echo      "%PYEXE%" -m scripts.data_provenance --clear-chat
echo.
echo    That removes conversation history only. No reading, invoice,
echo    payment or customer record is touched.
echo  ================================================================
goto END

:NOVENV
echo.
echo  [X] No virtual environment found at:
echo        %VENVDIR%
echo.
echo      Run load-data.bat first - it builds one if there is none.
goto END

:REPORTFAIL
echo.
echo  [X] Could not read the database. The message above says why.
echo      If it mentions a missing table, run load-data.bat first.
goto END

:END
echo.
pause
