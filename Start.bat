@echo off
rem Double-click this file to start the Pokemon GO tier lookup.
cd /d "%~dp0"

set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY where python >nul 2>nul && set PY=python
if not defined PY (
  echo Python 3 wasn't found. Install it from https://www.python.org/downloads/ and try again.
  pause
  exit /b 1
)

if not exist all_rankings.json (
  echo First run: downloading the rankings ^(about 3 minutes^)...
  %PY% refresh_data.py
  if errorlevel 1 (
    echo Download failed.
    pause
    exit /b 1
  )
)

%PY% pogo_ui.py %*

echo.
echo Stopped.
pause
