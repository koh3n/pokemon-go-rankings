@echo off
rem Double-click this file to start the Pokemon GO tier lookup.
cd /d "%~dp0"

rem Use the project's virtual environment, creating it on first run.
if not exist .venv\Scripts\python.exe (
  set PY=
  where py >nul 2>nul && set PY=py -3
  if not defined PY where python >nul 2>nul && set PY=python
  if not defined PY (
    echo Python 3 wasn't found. Install it from https://www.python.org/downloads/ and try again.
    pause
    exit /b 1
  )
  echo First run: setting up the Python environment...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Couldn't create the environment.
    pause
    exit /b 1
  )
)
call .venv\Scripts\activate.bat

python -c "import requests, bs4" >nul 2>nul
if errorlevel 1 (
  echo Installing dependencies...
  pip install -q -r requirements.txt
  if errorlevel 1 (
    echo Install failed.
    pause
    exit /b 1
  )
)

if not exist data\all_rankings.json (
  echo First run: downloading the rankings ^(about 3 minutes^)...
  python src\refresh_data.py
  if errorlevel 1 (
    echo Download failed.
    pause
    exit /b 1
  )
)

python src\pogo_ui.py %*

echo.
echo Stopped.
pause
