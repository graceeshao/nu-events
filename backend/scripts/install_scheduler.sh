#!/bin/bash
# Install/uninstall the NU Events scheduled scraper via macOS launchd
#
# Usage:
#   ./scripts/install_scheduler.sh install    # enable auto-scraping every 3h
#   ./scripts/install_scheduler.sh uninstall  # disable
#   ./scripts/install_scheduler.sh status     # check if running
#   ./scripts/install_scheduler.sh logs       # tail recent logs

PLIST_NAME="com.nuevents.scraper"
PLIST_SRC="$(cd "$(dirname "$0")" && pwd)/com.nuevents.scraper.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
LOG_DIR="$(cd "$(dirname "$0")/.." && pwd)/logs"

case "$1" in
    install)
        mkdir -p "$HOME/Library/LaunchAgents"
        mkdir -p "$LOG_DIR"
        cp "$PLIST_SRC" "$PLIST_DEST"
        launchctl load "$PLIST_DEST"
        echo "✅ Installed and started $PLIST_NAME"
        echo "   Runs every 1 hour 15 minutes + on boot"
        echo "   Logs: $LOG_DIR/"
        echo ""
        echo "   To test immediately: launchctl start $PLIST_NAME"
        ;;
    uninstall)
        launchctl unload "$PLIST_DEST" 2>/dev/null
        rm -f "$PLIST_DEST"
        echo "✅ Uninstalled $PLIST_NAME"
        ;;
    status)
        if launchctl list | grep -q "$PLIST_NAME"; then
            echo "✅ $PLIST_NAME is loaded"
            launchctl list "$PLIST_NAME"
        else
            echo "❌ $PLIST_NAME is not loaded"
        fi
        ;;
    logs)
        echo "=== Recent scrape log ==="
        tail -50 "$LOG_DIR"/scrape-*.log 2>/dev/null || echo "No logs yet"
        ;;
    *)
        echo "Usage: $0 {install|uninstall|status|logs}"
        exit 1
        ;;
esac
