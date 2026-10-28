#!/bin/zsh
# Install (or refresh) the weekly self-improvement job: Mondays 09:00 local time, via launchd.
# Runs only while this Mac is awake; launchd runs a missed job at the next wake.
set -eu
HERE="$(cd "$(dirname "$0")/.." && pwd)"
PLIST=~/Library/LaunchAgents/io.orkes.oncall-agent.weekly.plist
mkdir -p ~/.oncall-agent ~/Library/LaunchAgents
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>io.orkes.oncall-agent.weekly</string>
  <key>ProgramArguments</key><array><string>/bin/zsh</string><string>$HERE/scripts/weekly.sh</string></array>
  <key>StartCalendarInterval</key><dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>$HOME/.oncall-agent/weekly.log</string>
  <key>StandardErrorPath</key><string>$HOME/.oncall-agent/weekly.log</string>
</dict></plist>
PL
launchctl bootout gui/$(id -u) "$PLIST" 2>/dev/null || true
launchctl bootstrap gui/$(id -u) "$PLIST"
echo "installed: $PLIST (Mondays 09:00 local)"
