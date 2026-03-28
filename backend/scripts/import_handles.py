"""Import Instagram handles from a JSON file into the organizations table.

Expected input format (JSON array):
[
  {"name": "Org Name", "handle": "instagram_handle"},
  {"name": "Another Org", "handle": "another_handle"},
  ...
]

OR (with org ID):
[
  {"id": 123, "handle": "instagram_handle"},
  ...
]

Usage:
    python scripts/import_handles.py handles.json [--dry-run]
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Import Instagram handles")
    parser.add_argument("file", help="JSON file with handles")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    parser.add_argument("--db", default=None, help="Database path")
    args = parser.parse_args()

    db_path = args.db or str(Path(__file__).parent.parent / "nu_events.db")
    
    with open(args.file) as f:
        data = json.load(f)

    if not isinstance(data, list):
        print("Error: Expected a JSON array")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    updated = 0
    not_found = 0
    skipped = 0

    for item in data:
        handle = item.get("handle", "").lstrip("@").strip()
        if not handle:
            skipped += 1
            continue

        org_id = item.get("id")
        name = item.get("name", "").strip()

        if org_id:
            existing = c.execute("SELECT id, name FROM organizations WHERE id = ?", (org_id,)).fetchone()
        elif name:
            # Fuzzy match by name prefix
            existing = c.execute(
                "SELECT id, name FROM organizations WHERE name LIKE ?",
                (name[:30] + "%",),
            ).fetchone()
        else:
            skipped += 1
            continue

        if existing:
            if not args.dry_run:
                c.execute(
                    "UPDATE organizations SET instagram_handle = ? WHERE id = ?",
                    (handle, existing[0]),
                )
            print(f"  ✅ {existing[1][:40]:<40} → @{handle}")
            updated += 1
        else:
            print(f"  ❌ Not found: {name or org_id}")
            not_found += 1

    if not args.dry_run:
        conn.commit()

    print(f"\nUpdated: {updated} | Not found: {not_found} | Skipped: {skipped}")
    if args.dry_run:
        print("(dry run — no changes written)")

    conn.close()


if __name__ == "__main__":
    main()
