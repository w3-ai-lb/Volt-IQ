@echo off
setlocal
cd /d "%~dp0"
call "%~dp0python.cmd" launcher.py stop
if errorlevel 1 pause
