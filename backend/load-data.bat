@echo off
REM ===========================================================================
REM  Load the supervisor's ishtirak dataset (Project 3, Phase 1), rebuild the
REM  loss account, give every subscriber a customer record, and put those
REM  measurements behind the portal screens.
REM
REM  Double-click this file, or run it from the backend folder.
REM
REM  WHY THIS EXISTS RATHER THAN "python -m app.pipeline.ishtirak"
REM  -------------------------------------------------------------
REM  That command uses whichever Python is first on PATH, and the project's
REM  packages are not installed there. They live in a virtual environment that
REM  start.bat deliberately keeps in %LOCALAPPDATA% rather than inside the
REM  project: Documents is synced by OneDrive, and OneDrive locks files while
REM  pip is still writing them, which breaks the install of large packages such
REM  as pandas with "WinError 32".
REM
REM  So this finds the same environment start.bat uses, checks the packages are
REM  there, and runs the loader with THAT Python.
REM ===========================================================================
setlocal
cd /d "%~dp0"

REM The same search order as start.bat, newest name first.
set VENVDIR=%LOCALAPPDATA%\energy-analytics-venv
if exist "%LOCALAPPDATA%\energy-venv\Scripts\python.exe" set VENVDIR=%LOCALAPPDATA%\energy-venv
if exist "%~dp0venv\Scripts\python.exe" set VENVDIR=%~dp0venv
set PYEXE=%VENVDIR%\Scripts\python.exe

echo.
echo  ================================================================
echo    Loading the ishtirak dataset
echo  ================================================================
echo    Environment: %VENVDIR%
echo.

if not exist "data\ishtirak\zones.csv" goto NODATA

REM ---------- create the environment if there is not one yet -------------
REM start.bat normally does this, but it also seeds the demo database and
REM starts the server, which is a lot to sit through just to load data. So
REM this makes its own if it has to, in the same place and by the same rules.
if exist "%PYEXE%" goto HAVEVENV

echo  [0/3] No virtual environment yet. Creating one.
echo        Location: %VENVDIR%
echo        It goes here rather than inside the project because Documents is
echo        synced by OneDrive, and OneDrive locks files while pip is writing
echo        them, which breaks the install of large packages such as pandas.
echo.

REM Find a Python to build it with. The launcher (py) is the reliable one on
REM Windows; plain "python" can be the Microsoft Store stub that does nothing.
set BUILDER=
py -3.11 --version >nul 2>&1 && set BUILDER=py -3.11
if not defined BUILDER (py -3 --version >nul 2>&1 && set BUILDER=py -3)
if not defined BUILDER (python --version >nul 2>&1 && set BUILDER=python)
if not defined BUILDER goto NOPYTHON

echo        Building with: %BUILDER%
%BUILDER% -m venv "%VENVDIR%"
if not exist "%PYEXE%" goto VENVFAIL
echo        Created.
echo.

:HAVEVENV
echo  [1/5] Checking the packages the loader needs...
"%PYEXE%" -c "import pandas, sqlalchemy, sklearn" >nul 2>&1
if not errorlevel 1 goto LOAD

echo        Some are missing. Installing - a few minutes, about 550 MB.
echo        Please wait and do not close this window.
"%PYEXE%" -m pip install --upgrade pip
"%PYEXE%" -m pip install -r requirements.txt
if errorlevel 1 goto PIPFAIL
echo        Installed.
echo.

:LOAD
echo  [2/5] Loading all fourteen files and rebuilding the loss account...
echo.
"%PYEXE%" -m app.pipeline.ishtirak --dir data\ishtirak
if errorlevel 1 goto LOADFAIL

echo.
echo  [3/5] Checking every row arrived and the account reconciles...
echo.
"%PYEXE%" -m scripts.verify_ishtirak_load --dir data\ishtirak
if errorlevel 1 goto VERIFYFAIL

echo.
echo  [4/5] Giving each subscriber a customer record.
echo        His files give no names at all, so 45 come from the customer-side
echo        project's own seed and the rest are built in the same style. The
echo        figures on them - consumption, balance, zone, plan, status - are
echo        measured from his readings and invoices, not invented.
echo.
"%PYEXE%" -m app.pipeline.identities --replace
if errorlevel 1 goto IDENTITYFAIL

echo.
echo  [5/5] Putting his readings and invoices behind the portal screens.
echo.
"%PYEXE%" -m app.pipeline.portal --replace
if errorlevel 1 goto PORTALFAIL

echo.
echo  ================================================================
echo    Done. Start the backend with start.bat, sign in as the
echo    administrator, and open   Energy Loss   in the sidebar.
echo.
echo    The Customers page now lists 300 named subscribers, and the
echo    admin dashboard reports his figures rather than the demo's.
echo.
echo    To see where every row came from:
echo      "%PYEXE%" -m scripts.data_provenance
echo  ================================================================
goto END

:NOPYTHON
echo  [X] No Python was found.
echo      Install Python 3.11 from https://www.python.org/downloads/
echo      and tick "Add Python to PATH" during the install.
goto END

:VENVFAIL
echo  [X] The virtual environment could not be created at:
echo        %VENVDIR%
echo      Check there is disk space and that antivirus is not blocking it.
goto END

:NODATA
echo  [X] Cannot find data\ishtirak\zones.csv
echo      The fourteen CSV files belong in:
echo        %~dp0data\ishtirak\
goto END

:PIPFAIL
echo.
echo  [X] Installing the packages failed.
echo      If the error mentions a version that could not be found, your
echo      Python is probably newer or older than the pinned packages
echo      expect. Check with:  "%PYEXE%" --version
echo      The project is developed against Python 3.11.
goto END

:LOADFAIL
echo.
echo  [X] The load failed. The message above says why.
echo      Nothing was left half-loaded: the loader clears the ishtirak
echo      tables before it starts and commits each file as it goes.
goto END

:IDENTITYFAIL
echo.
echo  [X] The customer records could not be created. The message above
echo      says why. The supervisor's data is untouched: this step only
echo      writes to the customers table.
goto END

:PORTALFAIL
echo.
echo  [X] The portal projection failed. The message above says why.
echo      Re-run this file to try again: the step clears its own rows
echo      first, so nothing is left half-written.
goto END

:VERIFYFAIL
echo.
echo  [X] The data loaded but the checks did not all pass. The list
echo      above shows which. Do not quote figures from this database
echo      until they do.
goto END

:END
echo.
pause
