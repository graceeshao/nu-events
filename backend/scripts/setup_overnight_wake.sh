#!/bin/bash
# Setup overnight wake for nu-events scraper
# Run this once with: sudo bash setup_overnight_wake.sh
#
# This does two things:
# 1. Sets pmset to wake the Mac at 2:00 AM daily
# 2. Allows the scraper to schedule additional wakes without a password via sudoers

set -e

echo "=== Setting up overnight wake for nu-events scraper ==="

# Must be run as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Please run with sudo: sudo bash setup_overnight_wake.sh"
    exit 1
fi

# Resolve the real username (not root)
REAL_USER="${SUDO_USER:-$(logname 2>/dev/null)}"
if [ -z "$REAL_USER" ]; then
    echo "ERROR: Could not determine the real username. Run with sudo, not as root directly."
    exit 1
fi
echo "Configuring for user: $REAL_USER"

# Find pmset — it should always be here on macOS
PMSET_PATH=$(which pmset 2>/dev/null || echo "/usr/bin/pmset")
if [ ! -x "$PMSET_PATH" ]; then
    echo "ERROR: pmset not found at $PMSET_PATH"
    exit 1
fi
echo "Found pmset at: $PMSET_PATH"

# 1. Set repeating wake at 2:00 AM every day
echo "Setting pmset repeat wakeorpoweron at 02:00 daily..."
"$PMSET_PATH" repeat wakeorpoweron MTWRFSU 02:00:00
echo "Repeating wake set. Current schedule:"
"$PMSET_PATH" -g sched

# 2. Allow passwordless pmset schedule for the real user
SUDOERS_FILE="/etc/sudoers.d/nuevents-pmset"

echo ""
echo "Creating sudoers entry for $REAL_USER..."
cat > "$SUDOERS_FILE" << SUDOERS
# Allow nu-events scraper to schedule/cancel wake events without a password
$REAL_USER ALL=(ALL) NOPASSWD: $PMSET_PATH schedule wake *
$REAL_USER ALL=(ALL) NOPASSWD: $PMSET_PATH schedule cancel *
SUDOERS

chmod 0440 "$SUDOERS_FILE"

# Validate the sudoers file before accepting it
if visudo -cf "$SUDOERS_FILE" > /dev/null 2>&1; then
    echo "Sudoers entry validated OK"
else
    echo "ERROR: Sudoers validation failed — removing bad file"
    rm -f "$SUDOERS_FILE"
    exit 1
fi

# 3. Quick smoke test — try a no-op sudo as the real user
echo ""
echo "Testing passwordless sudo for pmset..."
if sudo -u "$REAL_USER" sudo -n "$PMSET_PATH" schedule wake "01/01/2099 03:00:00" 2>/dev/null; then
    # Clean up the test wake immediately
    sudo -u "$REAL_USER" sudo -n "$PMSET_PATH" schedule cancel wake "01/01/2099 03:00:00" 2>/dev/null || true
    echo "Smoke test PASSED — passwordless sudo is working ✓"
else
    echo "WARNING: Smoke test failed. The sudoers entry may not be effective yet."
    echo "         Try opening a new terminal and running: sudo -n pmset schedule wake '01/01/2099 03:00:00'"
fi

echo ""
echo "=== Done! ==="
echo "  - Mac will wake at 2:00 AM nightly (pmset repeat)"
echo "  - Scraper can chain additional wakes every 2 hours overnight"
echo "  - Verify schedule anytime with: pmset -g sched"
echo "  - Verify sudoers with: sudo -n pmset schedule wake '01/01/2099 03:00:00'"
