#!/bin/bash
# Double-click this file to start the Pokémon GO tier lookup.
cd "$(dirname "$0")" || exit 1

# A bare terminal may not have Python on PATH; add the usual install locations.
export PATH="/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:$PATH"

# Use the project's virtual environment, creating it on first run.
if [ ! -x .venv/bin/python ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 wasn't found. Install it from https://www.python.org/downloads/ and try again."
    read -n 1 -s -r -p "Press any key to close..."
    exit 1
  fi
  echo "First run: setting up the Python environment..."
  python3 -m venv .venv || { read -n 1 -s -r -p "Couldn't create the environment. Press any key to close..."; exit 1; }
fi
source .venv/bin/activate

if ! python -c "import requests, bs4" >/dev/null 2>&1; then
  echo "Installing dependencies..."
  pip install -q -r requirements.txt || { read -n 1 -s -r -p "Install failed. Press any key to close..."; exit 1; }
fi

if [ ! -f data/all_rankings.json ]; then
  echo "First run: downloading the rankings (about 3 minutes)..."
  python src/refresh_data.py || { read -n 1 -s -r -p "Download failed. Press any key to close..."; exit 1; }
fi

python src/pogo_ui.py "$@"

echo
read -n 1 -s -r -p "Stopped. Press any key to close..."
