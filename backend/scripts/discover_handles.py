"""Discover Instagram handles for NU student organizations.

Strategy:
1. Generate candidate handles from org names (common patterns)
2. Verify each candidate exists on Instagram using Instaloader
3. Check bio for "Northwestern" or "NU" to confirm it's the right account
4. Update the organizations table with confirmed handles

Usage:
    python scripts/discover_handles.py [--verify] [--limit N] [--dry-run]
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import instaloader

# Rate limits
DELAY_BETWEEN_CHECKS = 4  # seconds between profile lookups


def generate_candidates(org_name: str) -> list[str]:
    """Generate likely Instagram handle candidates from an org name.

    Most NU orgs follow patterns like:
    - @nu_orgname
    - @nuorgname
    - @orgname_nu
    - @orgnamenu
    - @northwestern_orgname
    - @orgname.nu
    - @orgname_northwestern
    - Just @orgname (less specific)

    Args:
        org_name: Full organization name.

    Returns:
        List of candidate handles, most likely first.
    """
    # Clean the name
    clean = org_name.lower().strip()
    # Remove common suffixes
    for suffix in [
        " at northwestern", " at nu", " - northwestern",
        " (northwestern)", " northwestern university",
        " northwestern", " at northwestern university",
    ]:
        clean = clean.replace(suffix, "")

    # Create a slug (letters, numbers, underscores)
    slug = re.sub(r'[^a-z0-9]+', '', clean)
    slug_under = re.sub(r'[^a-z0-9]+', '_', clean).strip('_')

    # Create abbreviation (first letters of each word)
    words = re.sub(r'[^a-z0-9\s]', '', clean).split()
    abbrev = ''.join(w[0] for w in words if w) if len(words) > 2 else ''

    candidates = []

    # Most common patterns for NU orgs
    if slug:
        candidates.extend([
            f"nu{slug}",
            f"nu_{slug_under}",
            f"{slug}nu",
            f"{slug_under}_nu",
            f"{slug_under}nu",
            f"northwestern{slug}",
            f"{slug_under}_northwestern",
            slug_under,
            slug,
        ])

    if abbrev and len(abbrev) >= 2:
        candidates.extend([
            f"nu{abbrev}",
            f"nu_{abbrev}",
            f"{abbrev}nu",
            f"{abbrev}_nu",
            abbrev,
        ])

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for c in candidates:
        if c not in seen and len(c) >= 3:
            seen.add(c)
            unique.append(c)

    return unique


def check_handle(
    loader: instaloader.Instaloader,
    handle: str,
) -> dict | None:
    """Check if an Instagram handle exists and looks like an NU org.

    Args:
        loader: Instaloader instance.
        handle: Handle to check.

    Returns:
        Dict with handle info if found and likely NU-related, else None.
    """
    try:
        profile = instaloader.Profile.from_username(loader.context, handle)
    except instaloader.exceptions.ProfileNotExistsException:
        return None
    except instaloader.exceptions.ConnectionException:
        return None

    bio = (profile.biography or "").lower()
    full_name = (profile.full_name or "").lower()

    # Check if it's likely a Northwestern account
    nu_signals = [
        "northwestern" in bio,
        "northwestern" in full_name,
        " nu " in f" {bio} ",
        " nu " in f" {full_name} ",
        "evanston" in bio,
        "wildcat" in bio,
        "@northwestern" in bio,
        "go cats" in bio,
        "go 'cats" in bio,
    ]

    is_nu = any(nu_signals)

    return {
        "handle": handle,
        "full_name": profile.full_name,
        "bio": profile.biography,
        "followers": profile.followers,
        "posts": profile.mediacount,
        "is_private": profile.is_private,
        "is_nu_likely": is_nu,
    }


def main():
    parser = argparse.ArgumentParser(description="Discover NU org Instagram handles")
    parser.add_argument("--verify", action="store_true", help="Verify candidates on Instagram")
    parser.add_argument("--limit", type=int, default=None, help="Max orgs to process")
    parser.add_argument("--dry-run", action="store_true", help="Don't update the database")
    parser.add_argument("--db", default="nu_events.db", help="Database path")
    parser.add_argument("--output", default="discovered_handles.json", help="Output JSON file")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        # Try relative to backend dir
        db_path = Path(__file__).parent.parent / args.db
    
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    # Get orgs without Instagram handles
    rows = c.execute("""
        SELECT id, name, category, website
        FROM organizations
        WHERE instagram_handle IS NULL OR instagram_handle = ''
        ORDER BY name
    """).fetchall()

    if args.limit:
        rows = rows[:args.limit]

    print(f"Processing {len(rows)} organizations...")

    results = []

    if args.verify:
        loader = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
        )

        for i, (org_id, name, category, website) in enumerate(rows):
            print(f"\n[{i+1}/{len(rows)}] {name}")
            candidates = generate_candidates(name)
            print(f"  Candidates: {candidates[:5]}...")

            found = None
            for handle in candidates[:5]:  # Check top 5 candidates
                time.sleep(DELAY_BETWEEN_CHECKS)
                info = check_handle(loader, handle)
                if info and info["is_nu_likely"]:
                    found = info
                    print(f"  ✅ Found: @{handle} ({info['full_name']}, {info['followers']} followers)")
                    break
                elif info:
                    print(f"  ⚠️  @{handle} exists but doesn't look NU-related")

            if found:
                results.append({
                    "org_id": org_id,
                    "org_name": name,
                    "instagram_handle": found["handle"],
                    "full_name": found["full_name"],
                    "bio": found["bio"],
                    "followers": found["followers"],
                    "posts": found["posts"],
                    "is_private": found["is_private"],
                })

                if not args.dry_run:
                    c.execute(
                        "UPDATE organizations SET instagram_handle = ? WHERE id = ?",
                        (found["handle"], org_id),
                    )
                    conn.commit()
            else:
                print(f"  ❌ No NU Instagram found")

    else:
        # Just generate candidates without verifying
        for org_id, name, category, website in rows:
            candidates = generate_candidates(name)
            results.append({
                "org_id": org_id,
                "org_name": name,
                "candidates": candidates[:8],
            })

    # Save results
    output_path = Path(__file__).parent.parent / args.output
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to {output_path}")
    if args.verify:
        found_count = len([r for r in results if "instagram_handle" in r])
        print(f"Found {found_count}/{len(rows)} handles")

    conn.close()


if __name__ == "__main__":
    main()
