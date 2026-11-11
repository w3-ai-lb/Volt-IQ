@echo off
REM ===========================================================================
REM  Remove the demo data we invented, leaving the product standing on the
REM  supervisor's own figures.
REM
REM  RUN THIS WHEN YOU ARE READY TO HAND OVER, NOT BEFORE.
REM
REM  WHAT IT REMOVES
REM  ---------------
REM  The records app\pipeline\seed.py generated as a stand-in while there was
REM  no real data: eighteen customers called Rami Khoury and Lara Awad, their
REM  consumption, bills, payments, alerts and chat history. They were a
REM  placeholder for exactly the data that has since arrived, and no figure in
REM  a report may come from them.
REM
REM  WHAT IT KEEPS
REM  -------------
REM  Everything from the supervisor - subscribers, zones, generators,
REM  telemetry, meter readings, invoices, payments, and the loss account
REM  computed from them - and the 300 customer records built on top of them,
REM  whose consumption, balance, zone, plan and status are all measured from
REM  his files rather than invented.
REM
REM  THE ORDER MATTERS, SO THIS FILE ENFORCES IT
REM  -------------------------------------------
REM  Two things have to exist BEFORE the demo goes, or you are left stuck:
REM
REM    1. the customer records. His subscribers.csv carries no names at all,
REM       so purging first would leave the portal with nothing to display.
REM       load-data.bat creates them.
REM
REM    2. an administrator that is not the demo one. admin@nxttrn.com is
REM       deleted by this, and without another account there is nothing left
REM       to sign in with.
REM
REM  This file checks both and offers to fix the second. The purge itself also
REM  refuses if either is missing, so running the command by hand is safe too.
REM
REM  REVERSIBLE
REM  ----------
REM  To bring the demo back:  python -m app.pipeline.seed
REM  That rebuilds the eighteen accounts WITHOUT touching a single row of the
REM  supervisor's data.
REM ===========================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

set VENVDIR=%LOCALAPPDATA%\energy-analytics-venv
if exist "%LOCALAPPDATA%\energy-venv\Scripts\python.exe" set VENVDIR=%LOCALAPPDATA%\energy-venv
if exist "%~dp0venv\Scripts\python.exe" set VENVDIR=%~dp0venv
set PYEXE=%VENVDIR%\Scripts\python.exe

if not exist "%PYEXE%" goto NOVENV

echo.
echo  ================================================================
echo    Step 1 of 3  -  Where every row in this database came from
echo  ================================================================
"%PYEXE%" -m scripts.data_provenance
if errorlevel 1 goto REPORTFAIL

REM ---------- are the customer records there yet? -------------------------
"%PYEXE%" -c "import sys; from app.database import SessionLocal; from app.models.customer import Customer; db=SessionLocal(); n=db.query(Customer).filter(Customer.customer_id.like('GEN-%%')).count(); db.close(); sys.exit(0 if n else 1)"
if errorlevel 1 goto NOIDENTITIES

echo.
echo  ================================================================
echo    Step 2 of 3  -  An administrator that is not the demo one
echo  ================================================================
"%PYEXE%" -c "import sys; from app.database import SessionLocal; from app.models.customer import Customer; db=SessionLocal(); n=db.query(Customer).filter(Customer.role=='admin', Customer.email!='admin@nxttrn.com').count(); db.close(); sys.exit(0 if n else 1)"
if not errorlevel 1 goto HAVEADMIN

echo    There is only the demo administrator, and this removes it.
echo    Let us create yours now so you are not locked out.
echo.
set ADMINEMAIL=
set /p ADMINEMAIL=   Your email:
if "!ADMINEMAIL!"=="" goto CANCELLED
set ADMINNAME=
set /p ADMINNAME=   Your name:
if "!ADMINNAME!"=="" set ADMINNAME=Administrator
echo.
echo    You will be asked for a password. It is not shown as you type.
echo.
"%PYEXE%" -m scripts.create_admin --email "!ADMINEMAIL!" --name "!ADMINNAME!"
if errorlevel 1 goto ADMINFAIL
goto CONFIRM

:HAVEADMIN
echo    Already present. Nothing to do here.

:CONFIRM
echo.
echo  ================================================================
echo    Step 3 of 3  -  Remove the invented records
echo  ================================================================
echo    The supervisor's data is not touched, and neither are the 300
echo    customer records built from it.
echo    Reversible with:  "%PYEXE%" -m app.pipeline.seed
echo.
set GO=
set /p GO=   Remove them now? [y/N]
if /i not "%GO%"=="y" goto CANCELLED
echo.

"%PYEXE%" -m scripts.data_provenance --purge-demo --yes
if errorlevel 1 goto PURGEFAIL

echo.
echo  ================================================================
echo    Done. Start the backend with start.bat and sign in with the
echo    administrator above. The Customers page lists the supervisor's
echo    300 subscribers by name, and every figure on the dashboard is
echo    his.
echo  ================================================================
goto END

:NOIDENTITIES
echo.
echo  ================================================================
echo    STOPPED - the customer records do not exist yet
echo  ================================================================
echo    His subscribers.csv carries no names, so removing the demo now
echo    would leave the portal with nothing at all to show.
echo.
echo    Run load-data.bat first. It creates them in steps 4 and 5,
echo    then come back here.
echo  ================================================================
goto END

:CANCELLED
echo    Cancelled. Nothing was removed.
goto END

:NOVENV
echo  [X] No virtual environment found. Run load-data.bat first.
goto END

:REPORTFAIL
echo  [X] Could not read the database. The message above says why.
goto END

:ADMINFAIL
echo  [X] The administrator could not be created. The message above says
echo      why. Nothing was removed.
goto END

:PURGEFAIL
echo  [X] The removal failed. The message above says why.
echo      Nothing partial: it commits once, at the end.
goto END

:END
echo.
pause
