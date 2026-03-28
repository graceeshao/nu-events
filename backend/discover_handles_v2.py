#!/usr/bin/env python3
"""Discover Instagram handles for Northwestern orgs using Bing search."""

import json
import re
import time
import urllib.parse
import urllib.request
import sqlite3
import os
import random
import sys

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

def search_bing(query):
    """Search Bing and return raw HTML."""
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.bing.com/search?q={encoded}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode("utf-8", errors="replace")
            return data
    except Exception as e:
        print(f"  Search error: {e}", flush=True)
        return ""

def extract_instagram_handles(html):
    """Extract Instagram profile handles from search results."""
    # Match instagram.com/handle patterns (profile pages only)
    pattern = r'instagram\.com/([a-zA-Z0-9_.]{2,30})(?:/?\b|/?["\s<&?\'#])'
    matches = re.findall(pattern, html)
    
    # Filter out non-profile paths
    skip = {"p", "reel", "reels", "stories", "explore", "accounts", "about", 
            "developer", "legal", "privacy", "terms", "directory", "static",
            "tags", "locations", "nametag", "direct", "tv", "lite", "web"}
    handles = [m.rstrip('/') for m in matches if m.lower() not in skip]
    
    return list(dict.fromkeys(handles))  # dedupe preserving order

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
    
    # Load existing results
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            try:
                existing = json.load(f)
            except:
                existing = []
    else:
        existing = []
    
    remaining = [o for o in orgs if o["id"] not in processed_ids]
    print(f"Total: {len(orgs)}, Done: {len(processed_ids)}, Left: {len(remaining)}", flush=True)
    
    for i, org in enumerate(remaining):
        org_id = org["id"]
        org_name = org["name"]
        
        # Primary search
        query = f'site:instagram.com "{org_name}" northwestern'
        print(f"[{len(processed_ids) + i + 1}/{len(orgs)}] {org_name} (id={org_id})", flush=True)
        
        html = search_bing(query)
        handles = extract_instagram_handles(html)
        
        handle_found = None
        
        if handles:
            # Check if page content mentions northwestern
            lower_html = html.lower()
            nu_mentioned = any(kw in lower_html for kw in ["northwestern", "evanston", " nu ", "@nu"])
            
            if nu_mentioned:
                handle_found = handles[0]
        
        if not handle_found:
            # Try alternate search  
            time.sleep(random.uniform(1, 2))
            query2 = f'instagram.com "{org_name}" northwestern university'
            html2 = search_bing(query2)
            handles2 = extract_instagram_handles(html2)
            if handles2:
                lower_html2 = html2.lower()
                nu_mentioned2 = any(kw in lower_html2 for kw in ["northwestern", "evanston", " nu "])
                if nu_mentioned2:
                    handle_found = handles2[0]
        
        if handle_found:
            print(f"  ✓ @{handle_found}", flush=True)
            update_db(org_id, handle_found)
            result = {"id": org_id, "name": org_name, "handle": handle_found}
            results.append(result)
            existing.append(result)
        else:
            print(f"  ✗ none", flush=True)
        
        processed_ids.add(org_id)
        progress["processed"] = list(processed_ids)
        progress["found"] = results
        
        # Save every 10 orgs
        if (i + 1) % 10 == 0:
            save_progress(progress)
            with open(RESULTS_FILE, "w") as f:
                json.dump(existing, f, indent=2)
            print(f"  --- Saved: {len(processed_ids)}/{len(orgs)}, found: {len(results)} ---", flush=True)
        
        # Rate limit
        time.sleep(random.uniform(2, 4))
    
    # Final save
    save_progress(progress)
    with open(RESULTS_FILE, "w") as f:
        json.dump(existing, f, indent=2)
    
    print(f"\n=== DONE: {len(results)} found / {len(orgs)} total ===", flush=True)

if __name__ == "__main__":
    main()
