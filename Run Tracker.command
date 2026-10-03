#!/bin/bash
# Double-click this file to read every job board and open the dashboard.
cd "$(dirname "$0")" || exit 1
MODE="${1:-update}"

PY=""
for candidate in python3.13 python3.12 python3.11 python3 \
    /opt/homebrew/bin/python3 /usr/local/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
  if command -v "$candidate" >/dev/null 2>&1 && \
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY="$candidate"; break
  fi
done
if [ -z "$PY" ]; then
  echo "This tracker needs Python 3.11 or newer, and none was found."
  echo "Install it from https://www.python.org/downloads/ and double-click this file again."
  read -r -p "Press Return to close."; exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "First run: setting up (about a minute)..."
  "$PY" -m venv .venv || { echo "Could not set up Python."; read -r -p "Press Return to close."; exit 1; }
fi
.venv/bin/python -c 'import httpx' 2>/dev/null || \
  .venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt || \
  { echo "Could not install the one library the tracker needs (httpx)."; read -r -p "Press Return to close."; exit 1; }

.venv/bin/python run.py "$MODE" 2>&1 | tee last_run.log
STATUS=${PIPESTATUS[0]}
if [ "$STATUS" -eq 0 ] && [ -f docs/index.html ]; then
  open docs/index.html
else
  echo; echo "The run did not finish. The details are saved in last_run.log."
fi
read -r -p "Press Return to close."
