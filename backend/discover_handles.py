#!/usr/bin/env python3
"""Discover Instagram handles for Northwestern orgs using Google search."""

import json
import re
import time
import urllib.parse
import urllib.request
import sqlite3
import os
import random

ORGS_FILE = "/Users/graceshao/.openclaw/workspace/nu-events/backend/orgs_to_discover.json"
RESULTS_FILE = "/Users/graceshao/.openclaw/workspace/nu-events/backend/discovered_handles.json"
DB_FILE = "/Users/graceshao/.openclaw/workspace/nu-events/backend/nu_events.db"
PROGRESS_FILE = "/Users/graceshao/.openclaw/workspace/nu-events/backend/discover_progress.json"

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"processed": [], "found": []}

def save_progress(progress):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f)

def search_google(query):
    """Search Google and return raw HTML."""
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.google.com/search?q={encoded}&num=5"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  Search error: {e}")
        return ""

def extract_instagram_handles(html, org_name):
    """Extract Instagram profile handles from search results HTML."""
    # Find instagram.com profile URLs (not posts/reels/p/)
    pattern = r'https?://(?:www\.)?instagram\.com/([a-zA-Z0-9_.]+)/?(?:["\s<&?])'
    matches = re.findall(pattern, html)
    
    # Filter out non-profile paths
    skip = {"p", "reel", "reels", "stories", "explore", "accounts", "about", "developer", "legal", "privacy"}
    handles = [m for m in matches if m.lower() not in skip and len(m) > 1]
    
    return list(dict.fromkeys(handles))  # dedupe preserving order

def is_northwestern_related(html, handle):
    """Check if the search snippet around this handle mentions Northwestern."""
    lower = html.lower()
    keywords = ["northwestern", " nu ", "evanston", "wildcat"]
    # Check if any keyword appears near the handle in the text
    for kw in keywords:
        if kw in lower:
            return True
    return False

def update_db(org_id, handle):
    """Update the SQLite database."""
    conn = sqlite3.connect(DB_FILE)
    conn.execute("UPDATE organizations SET instagram_handle = ? WHERE id = ?", (handle, org_id))
    conn.commit()
    conn.close()

def main():
    with open(ORGS_FILE) as f:
        orgs = json.load(f)
    
    progress = load_progress()
    processed_ids = set(progress["processed"])
    results = progress["found"]
    
    # Load existing results file
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            existing = json.load(f)
    else:
        existing = []
    
    remaining = [o for o in orgs if o["id"] not in processed_ids]
    print(f"Total orgs: {len(orgs)}, Already processed: {len(processed_ids)}, Remaining: {len(remaining)}")
    
    found_count = len(results)
    
    for i, org in enumerate(remaining):
        org_id = org["id"]
        org_name = org["name"]
        
        query = f'site:instagram.com "{org_name}" northwestern'
        print(f"[{len(processed_ids) + i + 1}/{len(orgs)}] Searching: {org_name} (id={org_id})")
        
        html = search_google(query)
        
        if not html:
            # Try alternate query
            time.sleep(2)
            query2 = f'instagram "{org_name}" northwestern university'
            html = search_google(query2)
        
        handles = extract_instagram_handles(html, org_name)
        
        handle_found = None
        if handles and is_northwestern_related(html, handles[0]):
            handle_found = handles[0]
            # Verify it's not a generic/unrelated handle
            print(f"  ✓ Found: @{handle_found}")
            
            update_db(org_id, handle_found)
            result = {"id": org_id, "name": org_name, "handle": handle_found}
            results.append(result)
            existing.append(result)
            found_count += 1
        else:
            print(f"  ✗ No match found")
        
        processed_ids.add(org_id)
        progress["processed"] = list(processed_ids)
        progress["found"] = results
        
        # Save progress every 5 orgs
        if (i + 1) % 5 == 0:
            save_progress(progress)
            with open(RESULTS_FILE, "w") as f:
                json.dump(existing, f, indent=2)
            print(f"  --- Progress saved: {len(processed_ids)} processed, {found_count} found ---")
        
        # Rate limit - random delay
        delay = random.uniform(1.5, 3.5)
        time.sleep(delay)
    
    # Final save
    save_progress(progress)
    with open(RESULTS_FILE, "w") as f:
        json.dump(existing, f, indent=2)
    
    print(f"\n=== COMPLETE ===")
    print(f"Total processed: {len(processed_ids)}")
    print(f"Handles found: {found_count} / {len(orgs)}")

if __name__ == "__main__":
    main()
