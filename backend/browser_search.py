#!/usr/bin/env python3
"""
Use playwright to search Google for Instagram handles of Northwestern orgs.
This script runs headless Chrome to avoid bot detection.
"""

import json
import re
import time
import sqlite3
import os
import sys
import subprocess
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

def update_db(org_id, handle):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("UPDATE organizations SET instagram_handle = ? WHERE id = ?", (handle, org_id))
    conn.commit()
    conn.close()

def search_and_extract(page, org_name):
    """Search Google for the org's Instagram handle."""
    import urllib.parse
    query = f'site:instagram.com "{org_name}" northwestern'
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.google.com/search?q={encoded}&num=5"
    
    try:
        page.goto(url, timeout=15000, wait_until="domcontentloaded")
        time.sleep(1)
        
        # Get all links from the page
        links = page.eval_on_selector_all("a[href*='instagram.com']", """
            elements => elements.map(el => ({
                href: el.href,
                text: el.textContent
            }))
        """)
        
        # Extract profile handles
        for link in links:
            href = link.get("href", "")
            text = link.get("text", "")
            
            # Match profile URLs (not posts/reels)
            m = re.match(r'https?://(?:www\.)?instagram\.com/([a-zA-Z0-9_.]+)/?$', href)
            if m:
                handle = m.group(1)
                skip = {"p", "reel", "reels", "stories", "explore", "accounts", "about", 
                        "developer", "legal", "privacy", "terms", "directory", "static",
                        "tags", "locations", "nametag", "direct", "tv", "lite", "web"}
                if handle.lower() not in skip:
                    # Verify it mentions Northwestern in the text
                    page_text = page.inner_text("body").lower()
                    if any(kw in page_text for kw in ["northwestern", "evanston", " nu "]):
                        return handle
        
        return None
    except Exception as e:
        print(f"  Error: {e}", flush=True)
        return None

def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Installing playwright...", flush=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        from playwright.sync_api import sync_playwright
    
    with open(ORGS_FILE) as f:
        orgs = json.load(f)
    
    progress = load_progress()
    processed_ids = set(progress["processed"])
    results = progress["found"]
    
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            try: existing = json.load(f)
            except: existing = []
    else:
        existing = []
    
    remaining = [o for o in orgs if o["id"] not in processed_ids]
    print(f"Total: {len(orgs)}, Done: {len(processed_ids)}, Left: {len(remaining)}", flush=True)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        for i, org in enumerate(remaining):
            org_id = org["id"]
            org_name = org["name"]
            
            print(f"[{len(processed_ids) + i + 1}/{len(orgs)}] {org_name}", flush=True)
            
            handle = search_and_extract(page, org_name)
            
            if handle:
                print(f"  ✓ @{handle}", flush=True)
                update_db(org_id, handle)
                result = {"id": org_id, "name": org_name, "handle": handle}
                results.append(result)
                existing.append(result)
            else:
                print(f"  ✗", flush=True)
            
            processed_ids.add(org_id)
            progress["processed"] = list(processed_ids)
            progress["found"] = results
            
            if (i + 1) % 10 == 0:
                save_progress(progress)
                with open(RESULTS_FILE, "w") as f:
                    json.dump(existing, f, indent=2)
                print(f"  --- {len(processed_ids)}/{len(orgs)}, found: {len(results)} ---", flush=True)
            
            time.sleep(random.uniform(2, 4))
        
        browser.close()
    
    save_progress(progress)
    with open(RESULTS_FILE, "w") as f:
        json.dump(existing, f, indent=2)
    
    print(f"\n=== DONE: {len(results)} / {len(orgs)} ===", flush=True)

if __name__ == "__main__":
    main()
