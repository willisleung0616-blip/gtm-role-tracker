#!/bin/bash
# Double-click to make the tracker update itself in the background:
#   your watchlist and curated startups every 15 minutes,
#   every job board every 2 hours.
# It runs only while this Mac is awake, and uses no Claude usage at all.
cd "$(dirname "$0")" || exit 1
DIR="$(pwd)"
AGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$AGENTS"

if [ ! -x .venv/bin/python ]; then
  echo "Run 'Run Tracker.command' once first, then double-click this file again."
  read -r -p "Press Return to close."; exit 1
fi
chmod +x auto_update.sh

write_agent() {  # name, mode, seconds
  cat > "$AGENTS/$1.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$1</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$DIR/auto_update.sh</string><string>$2</string></array>
  <key>StartInterval</key><integer>$3</integer>
  <key>RunAtLoad</key><false/>
  <key>ProcessType</key><string>Background</string>
  <key>LowPriorityIO</key><true/>
</dict></plist>
PLIST
  launchctl unload "$AGENTS/$1.plist" 2>/dev/null
  launchctl load -w "$AGENTS/$1.plist"
}

write_agent com.gtmtracker.quick quick 900
write_agent com.gtmtracker.full update 7200

if launchctl list | grep -q com.gtmtracker.quick && launchctl list | grep -q com.gtmtracker.full; then
  echo "Automatic updates are ON."
  echo "  Watchlist and curated startups: every 15 minutes"
  echo "  All job boards: every 2 hours"
  echo "Refresh the dashboard page in your browser to see the latest."
  echo "Activity is recorded in auto_update.log in this folder."
  echo "To stop, double-click 'Turn off automatic updates.command'."
else
  echo "Something went wrong turning automatic updates on."
fi
read -r -p "Press Return to close."
