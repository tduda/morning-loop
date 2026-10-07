#!/bin/bash
# Double-click me. If macOS says it can't verify the developer, do ONE of these:
#   - right-click me and choose Open (pre-Sequoia)
#   - System Settings > Privacy & Security, scroll down, click "Open Anyway" (Sequoia+)
#   - run: bash "Start here - Mac.command" (from Terminal)
cd "$(dirname "$0")" || exit 1

# Test that python3 actually runs. The xcode-select stub can open an installer dialog.
if ! python3 -c "import sys" >/dev/null 2>&1; then
  echo "Python 3 isn't installed yet."
  echo "Install it from https://www.python.org/downloads/ or run: xcode-select --install"
  echo "Then try again."
  read -r -p "Press Enter to close."
  exit 1
fi
python3 scripts/quickstart.py
read -r -p "Press Enter to close."
