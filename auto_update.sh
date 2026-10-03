#!/bin/bash
# Run by the scheduler (not by hand). Usage: auto_update.sh quick|update
# Reads job boards quietly in the background: no Terminal window, no browser.
cd "$(dirname "$0")" || exit 1
MODE="${1:-quick}"
LOG="auto_update.log"
LOCK=".run.lock"

# Keep the log small.
if [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt 1000000 ]; then
  tail -n 400 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

# One run at a time. A lock older than 30 minutes is a crashed run: clear it.
if [ -d "$LOCK" ] && [ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]; then
  rmdir "$LOCK" 2>/dev/null
fi
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') $MODE skipped: another run is in progress" >> "$LOG"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

if [ ! -x .venv/bin/python ]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') $MODE failed: run 'Run Tracker.command' once first" >> "$LOG"
  exit 1
fi
echo "$(date '+%Y-%m-%d %H:%M:%S') $MODE started" >> "$LOG"
.venv/bin/python run.py "$MODE" >> "$LOG" 2>&1
echo "$(date '+%Y-%m-%d %H:%M:%S') $MODE finished (exit $?)" >> "$LOG"
