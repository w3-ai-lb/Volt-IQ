@echo off
REM ===========================================================================
REM  Rebuild the recommendations, alerts and anomalies from the supervisor's
REM  own meter readings.
REM
REM  Double-click this file.
REM
REM  WHY YOU ARE RUNNING IT
REM  ----------------------
REM  purge-demo.bat deleted 592 recommendations and 527 alerts and called them
REM  "records our seeder invented". They were not. They were computed from the
REM  supervisor's 5,400 meter readings, and the purge had them filed under the
REM  wrong heading. That was a fault in scripts\data_provenance.py, it is now
REM  fixed, and it is now tested by scripts\verify_purge.py so it cannot come
REM  back quietly.
REM
REM  This puts the deleted rows back. Nothing is invented: every recommendation
REM  and every alert is recalculated from his readings, so what you get is what
REM  was there before, to the row.
REM
REM  WHAT IT TOUCHES
REM  ---------------
REM  consumption, bills, payments  - rewritten from his readings and invoices
REM  recommendations, alerts       - recalculated from that consumption
REM  anomalies                     - recalculated, where there are enough
REM                                  reading days to say anything honest
REM
REM  It does NOT touch a single row of what he sent: subscribers, meters,
REM  meter readings, invoices, payments, zones, generators and telemetry are
REM  all read and never written.
REM
REM  SAFE TO RUN TWICE
REM  -----------------
REM  It clears its own previous output before writing, so running it again
REM  gives the same numbers rather than doubling them. Running it three times
REM  in a row and running it once give an identical database.
REM ===========================================================================
setlocal
cd /d "%~dp0"

set VENVDIR=%LOCALAPPDATA%\energy-analytics-venv
if exist "%LOCALAPPDATA%\energy-venv\Scripts\python.exe" set VENVDIR=%LOCALAPPDATA%\energy-venv
if exist "%~dp0venv\Scripts\python.exe" set VENVDIR=%~dp0venv
set PYEXE=%VENVDIR%\Scripts\python.exe

if not exist "%PYEXE%" goto NOVENV

echo.
echo  ================================================================
echo    Rebuilding from the supervisor's readings
echo  ================================================================
echo.
"%PYEXE%" -m app.pipeline.portal
if errorlevel 1 goto FAILED

echo.
echo  ================================================================
echo    Done. Checking what is in the database now
echo  ================================================================
echo.
"%PYEXE%" -m scripts.data_provenance
echo.
echo    The recommendations and alerts should now be listed under
echo    "computed from the supervisor's data", not under "invented".
echo.
goto END

:NOVENV
echo.
echo  [X] No virtual environment found at:
echo        %VENVDIR%
echo.
echo      Run load-data.bat first - it builds one if there is none.
goto END

:FAILED
echo.
echo  [X] The rebuild did not finish. The message above says why.
echo.
echo      If it says no subscriber has a customer record yet, run
echo      load-data.bat first and then run this again.
goto END

:END
echo.
pause
