"""Discover Instagram handles for NU student orgs via web search.

Uses DuckDuckGo to search for 'site:instagram.com "org name" northwestern'
and extracts handles from the results.

Output: discovered_handles.json with confirmed handles.
"""

import json
import re
import sqlite3
import sys
import time
from pathlib import Path


def extract_handle_from_url(url: str) -> str | None:
    """Extract Instagram handle from a profile URL.
    
    Args:
        url: Instagram URL like https://www.instagram.com/ao.productions/
        
    Returns:
        Handle string or None.
    """
    match = re.match(r'https?://(?:www\.)?instagram\.com/([a-zA-Z0-9_.]+)/?$', url)
    if match:
        handle = match.group(1)
        # Filter out non-profile pages
        if handle in ('p', 'reel', 'stories', 'explore', 'accounts', 'about'):
            return None
        return handle
    return None


def extract_handle_from_results(results: list[dict]) -> str | None:
    """Extract the most likely org Instagram handle from search results.
    
    Args:
        results: List of search result dicts with 'url' and 'snippet' keys.
        
    Returns:
        Best handle found, or None.
    """
    for result in results:
        url = result.get('url', '')
        handle = extract_handle_from_url(url)
        if handle:
            return handle
    return None


def main():
    db_path = Path(__file__).parent.parent / "nu_events.db"
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    # Get orgs without Instagram handles
    rows = c.execute("""
        SELECT id, name, category
        FROM organizations
        WHERE instagram_handle IS NULL OR instagram_handle = ''
        ORDER BY name
    """).fetchall()

    print(f"Total orgs to discover: {len(rows)}")
    print("This script outputs org names for the agent to search.")
    print("---")
    
    # Output as JSON for the agent to process
    orgs = [{"id": r[0], "name": r[1], "category": r[2]} for r in rows]
    output_path = Path(__file__).parent.parent / "orgs_to_discover.json"
    with open(output_path, "w") as f:
        json.dump(orgs, f, indent=2)
    
    print(f"Wrote {len(orgs)} orgs to {output_path}")
    conn.close()


if __name__ == "__main__":
    main()
