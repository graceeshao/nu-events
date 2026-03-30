#!/bin/bash
exec >> /Users/graceshao/Downloads/nu-events/backend/logs/wrapper-debug.log 2>&1
echo "=== $(date) ==="
echo "PATH=$PATH"
echo "PWD=$PWD"
echo "Python: /Users/graceshao/Downloads/nu-events/backend/.venv/bin/python"
/Users/graceshao/Downloads/nu-events/backend/.venv/bin/python --version
echo "Running scheduled_scrape.py..."
/Users/graceshao/Downloads/nu-events/backend/.venv/bin/python /Users/graceshao/Downloads/nu-events/backend/scripts/scheduled_scrape.py
echo "Exit code: $?"
