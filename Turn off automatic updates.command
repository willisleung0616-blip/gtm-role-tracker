#!/bin/bash
# Double-click to stop the background updates and remove them from this Mac.
AGENTS="$HOME/Library/LaunchAgents"
for name in com.gtmtracker.quick com.gtmtracker.full; do
  launchctl unload "$AGENTS/$name.plist" 2>/dev/null
  rm -f "$AGENTS/$name.plist"
done
echo "Automatic updates are OFF. You can still run the tracker by hand."
read -r -p "Press Return to close."
