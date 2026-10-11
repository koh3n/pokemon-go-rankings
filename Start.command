#!/bin/bash
# Double-click this file to start the Pokémon GO tier lookup.
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 wasn't found. Install it from https://www.python.org/downloads/ and try again."
  read -n 1 -s -r -p "Press any key to close..."
  exit 1
fi

if [ ! -f data/all_rankings.json ]; then
  echo "First run: downloading the rankings (about 3 minutes)..."
  python3 src/refresh_data.py || { read -n 1 -s -r -p "Download failed. Press any key to close..."; exit 1; }
fi

python3 src/pogo_ui.py "$@"

echo
read -n 1 -s -r -p "Stopped. Press any key to close..."
