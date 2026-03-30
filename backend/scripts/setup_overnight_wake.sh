#!/bin/bash
# Setup overnight wake for nu-events scraper
# Run this once with: sudo bash setup_overnight_wake.sh
#
# This does two things:
# 1. Sets pmset to wake the Mac at 2:00 AM daily
# 2. Allows the scraper to schedule additional wakes (4 AM, 6 AM)
#    without a password via sudoers

set -e

echo "=== Setting up overnight wake for nu-events scraper ==="

# 1. Set repeating wake at 2:00 AM
echo "Setting pmset repeat wakeorpoweron at 02:00 daily..."
pmset repeat wakeorpoweron MTWRFSU 02:00:00

# 2. Allow passwordless pmset schedule for the current user
SUDOERS_FILE="/etc/sudoers.d/nuevents-pmset"
USER=$(logname 2>/dev/null || echo "$SUDO_USER")

if [ -z "$USER" ]; then
    echo "ERROR: Could not determine username"
    exit 1
fi

echo "Creating sudoers entry for $USER to run 'pmset schedule' without password..."
cat > "$SUDOERS_FILE" << EOF
# Allow nu-events scraper to schedule wake events
$USER ALL=(ALL) NOPASSWD: /usr/bin/pmset schedule wake *
$USER ALL=(ALL) NOPASSWD: /usr/bin/pmset schedule cancel *
EOF

chmod 0440 "$SUDOERS_FILE"

# Validate sudoers
if visudo -cf "$SUDOERS_FILE" > /dev/null 2>&1; then
    echo "Sudoers entry validated OK"
else
    echo "ERROR: Sudoers validation failed, removing file"
    rm -f "$SUDOERS_FILE"
    exit 1
fi

echo ""
echo "=== Done! ==="
echo "  - Mac will wake at 2:00 AM daily"
echo "  - Scraper can schedule 4:00 AM and 6:00 AM wakes automatically"
echo "  - Verify with: pmset -g sched"
