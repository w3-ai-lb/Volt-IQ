@echo off
REM ===========================================================================
REM  Sign in as one of the provider's real subscribers.
REM
REM  Double-click this file.
REM
REM  WHAT IT DOES
REM  ------------
REM  All 300 subscribers already exist in the database with their real
REM  readings, invoices and payments. What none of them has is a password,
REM  because a password is something the customer chooses when they register.
REM
REM  This attaches a password to one of them so you can open the customer side
REM  and see it on real data. It changes ONE column. The name, the email, the
REM  region, the plan, every reading and every invoice are left exactly as the
REM  supervisor sent them.
REM
REM  WHY IT ALSO REPAIRS THE EMAIL ADDRESSES FIRST
REM  ----------------------------------------------
REM  The generated addresses used to end in "@generated.local". That looks like
REM  an address and is not one: .local is reserved for something else entirely,
REM  so the email check in the login refused it before it ever looked at the
REM  password. 298 of the 300 subscribers could not sign in at all, and nothing
REM  on any screen said so.
REM
REM  They are moved to "@example.com", which is the domain reserved for exactly
REM  this purpose: a valid address that can never receive real mail. This runs
REM  once and does nothing on later runs.
REM ===========================================================================
setlocal
cd /d "%~dp0"

set VENVDIR=%LOCALAPPDATA%\energy-analytics-venv
if exist "%LOCALAPPDATA%\energy-venv\Scripts\python.exe" set VENVDIR=%LOCALAPPDATA%\energy-venv
if exist "%~dp0venv\Scripts\python.exe" set VENVDIR=%~dp0venv
set PYEXE=%VENVDIR%\Scripts\python.exe

if not exist "%PYEXE%" goto NOVENV

"%PYEXE%" -m app.pipeline.identities --repair-emails
if errorlevel 1 goto FAILED

"%PYEXE%" -m scripts.portal_access --list
if errorlevel 1 goto FAILED

echo.
set /p CID=  Type a Customer ID from the list above (or press Enter for GEN-00018):
if "%CID%"=="" set CID=GEN-00018

echo.
REM  No built-in password: press Enter and portal_access generates a random
REM  one for this account and prints it once, beside the email to sign in with.
set "PWD="
set /p PWD=  Choose a password, at least 6 characters (or press Enter to generate one):

if "%PWD%"=="" (
    "%PYEXE%" -m scripts.portal_access %CID%
) else (
    "%PYEXE%" -m scripts.portal_access %CID% --password "%PWD%"
)
if errorlevel 1 goto FAILED

echo.
echo  ================================================================
echo    Now start the website with start.bat, choose Sign in, and use
echo    the email and password printed above.
echo.
echo    To take the password away again:
echo      "%PYEXE%" -m scripts.portal_access %CID% --revoke
echo  ================================================================
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
echo  [X] That did not finish. The message above says why.
echo      If it mentions a missing table, run load-data.bat first.
goto END

:END
echo.
pause
