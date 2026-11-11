@echo off
REM ===========================================================================
REM  Two facts, side by side: what the file says, and what is actually running.
REM
REM  Double-click from the backend folder. Nothing is changed or restarted.
REM
REM  WHAT TO COMPARE
REM  ---------------
REM  The "written" time of chatbot.py against the "started" time of the server.
REM
REM  A server that started BEFORE the file was written is running the old code
REM  and cannot know about the new one: Python reads a module once, at import,
REM  and keeps it in memory for the life of the process. That is the whole bug,
REM  and those two timestamps are the proof of it.
REM
REM  If nothing is listening on 8000 while the website still answers you, then
REM  the website is not talking to this computer, and no file here matters.
REM ===========================================================================
setlocal
cd /d "%~dp0"

if not exist "app\ai\chatbot.py" (
  echo.
  echo  [X] No app\ai\chatbot.py here. Put this file in your backend folder.
  echo.
  pause
  exit /b 1
)

echo.
echo  ================================================================
echo    The file on disk
echo  ================================================================
powershell -NoProfile -Command "$f = Get-Item 'app\ai\chatbot.py'; $s = Get-Content $f.FullName -Raw; $new = ($s -match '_ARABIC_TEXT') -and ($s -match 'capabilities'); Write-Host ('    path    : ' + $f.FullName); Write-Host ('    version : ' + $(if ($new) {'NEW, answers Arabic'} else {'OLD, English only'})); Write-Host ('    written : ' + $f.LastWriteTime)"

echo.
echo  ================================================================
echo    The server on port 8000
echo  ================================================================
powershell -NoProfile -Command "$c = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue); if ($c.Count -eq 0) { Write-Host '    NOTHING is listening on port 8000 on this computer.'; Write-Host ''; Write-Host '    If the website still answers you, it is talking to a backend'; Write-Host '    somewhere else, not to this one.' } else { foreach ($x in $c) { $p = Get-Process -Id $x.OwningProcess -ErrorAction SilentlyContinue; if ($p) { Write-Host ('    pid     : ' + $p.Id); Write-Host ('    started : ' + $p.StartTime); Write-Host ('    exe     : ' + $p.Path); Write-Host '' } } }"

echo  ================================================================
echo    Read it like this
echo  ================================================================
echo.
echo    started EARLIER than written  ^-^-^>  old code in memory.
echo                                       Close that window, run it again.
echo.
echo    started LATER than written    ^-^-^>  it loaded the new file, so the
echo                                       page you are using is calling a
echo                                       different backend.
echo.
echo    nothing listening             ^-^-^>  the page is not calling this
echo                                       computer at all.
echo.
pause
