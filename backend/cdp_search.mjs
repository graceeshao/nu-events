/**
 * Connects to the running Chrome via CDP and searches for Instagram handles.
 * Uses the already-running OpenClaw browser (port 18800).
 */

import { readFileSync, writeFileSync, existsSync } from 'fs';
import { join } from 'path';

const BASE = '/Users/graceshao/.openclaw/workspace/nu-events/backend';
const ORGS_FILE = join(BASE, 'orgs_to_discover.json');
const RESULTS_FILE = join(BASE, 'discovered_handles.json');
const DB_FILE = join(BASE, 'nu_events.db');
const PROGRESS_FILE = join(BASE, 'discover_progress.json');
const CDP_URL = 'http://127.0.0.1:18800';

// Load orgs
const orgs = JSON.parse(readFileSync(ORGS_FILE, 'utf-8'));

// Load progress
let progress = { processed: [], found: [] };
if (existsSync(PROGRESS_FILE)) {
  progress = JSON.parse(readFileSync(PROGRESS_FILE, 'utf-8'));
}
const processedIds = new Set(progress.processed);

// Load existing results
let existing = [];
if (existsSync(RESULTS_FILE)) {
  try { existing = JSON.parse(readFileSync(RESULTS_FILE, 'utf-8')); } catch {}
}

function saveProgress() {
  writeFileSync(PROGRESS_FILE, JSON.stringify(progress));
  writeFileSync(RESULTS_FILE, JSON.stringify(existing, null, 2));
}

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function getTargets() {
  const resp = await fetch(`${CDP_URL}/json/list`);
  return resp.json();
}

async function createTarget() {
  const resp = await fetch(`${CDP_URL}/json/new?about:blank`);
  return resp.json();
}

// Simple CDP WebSocket client
class CDPSession {
  constructor(ws) {
    this.ws = ws;
    this.id = 1;
    this.callbacks = new Map();
    ws.on('message', (data) => {
      const msg = JSON.parse(data.toString());
      if (msg.id && this.callbacks.has(msg.id)) {
        this.callbacks.get(msg.id)(msg);
        this.callbacks.delete(msg.id);
      }
    });
  }
  
  send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = this.id++;
      this.callbacks.set(id, (msg) => {
        if (msg.error) reject(new Error(msg.error.message));
        else resolve(msg.result);
      });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  
  async navigate(url) {
    await this.send('Page.navigate', { url });
    await sleep(2000); // Wait for page load
  }
  
  async evaluate(expression) {
    const result = await this.send('Runtime.evaluate', { 
      expression, 
      returnByValue: true,
      awaitPromise: true 
    });
    return result?.result?.value;
  }
}

async function connectToPage(wsUrl) {
  const { WebSocket } = await import('ws');
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl);
    ws.on('open', () => resolve(new CDPSession(ws)));
    ws.on('error', reject);
  });
}

async function searchOrg(session, orgName) {
  const query = encodeURIComponent(`site:instagram.com "${orgName}" northwestern`);
  const url = `https://www.google.com/search?q=${query}&num=5`;
  
  await session.navigate(url);
  
  // Extract Instagram profile links and check for Northwestern mentions
  const result = await session.evaluate(`
    (() => {
      const links = Array.from(document.querySelectorAll('a[href*="instagram.com"]'));
      const profiles = [];
      for (const link of links) {
        const href = link.href;
        const match = href.match(/instagram\\.com\\/([a-zA-Z0-9_.]+)\\/?$/);
        if (match) {
          const handle = match[1];
          const skip = new Set(['p','reel','reels','stories','explore','accounts','about','developer','legal','privacy','terms','directory','static','tags','locations','nametag','direct','tv','lite','web']);
          if (!skip.has(handle.toLowerCase())) {
            profiles.push(handle);
          }
        }
      }
      const text = document.body.innerText.toLowerCase();
      const nuMentioned = text.includes('northwestern') || text.includes('evanston');
      return JSON.stringify({ profiles: [...new Set(profiles)], nuMentioned });
    })()
  `);
  
  try {
    const parsed = JSON.parse(result);
    if (parsed.profiles.length > 0 && parsed.nuMentioned) {
      return parsed.profiles[0];
    }
  } catch {}
  
  return null;
}

async function updateDB(orgId, handle) {
  // Use sqlite3 CLI since we can't easily use node sqlite bindings
  const { execSync } = await import('child_process');
  const escaped = handle.replace(/'/g, "''");
  execSync(`sqlite3 "${DB_FILE}" "UPDATE organizations SET instagram_handle = '${escaped}' WHERE id = ${orgId};"`);
}

async function main() {
  // Check if ws is available
  try {
    await import('ws');
  } catch {
    const { execSync } = await import('child_process');
    console.log('Installing ws...');
    execSync('npm install -g ws', { stdio: 'inherit' });
  }
  
  // Create a new tab for searching
  const target = await createTarget();
  console.log(`Created tab: ${target.id}`);
  
  const session = await connectToPage(target.webSocketDebuggerUrl);
  console.log('Connected to CDP');
  
  // Enable required domains
  await session.send('Page.enable');
  await session.send('Runtime.enable');
  
  const remaining = orgs.filter(o => !processedIds.has(o.id));
  console.log(`Total: ${orgs.length}, Done: ${processedIds.size}, Left: ${remaining.length}`);
  
  let foundCount = progress.found.length;
  
  for (let i = 0; i < remaining.length; i++) {
    const org = remaining[i];
    const { id: orgId, name: orgName } = org;
    
    process.stdout.write(`[${processedIds.size + 1}/${orgs.length}] ${orgName}`);
    
    try {
      const handle = await searchOrg(session, orgName);
      
      if (handle) {
        console.log(` ✓ @${handle}`);
        await updateDB(orgId, handle);
        const result = { id: orgId, name: orgName, handle };
        progress.found.push(result);
        existing.push(result);
        foundCount++;
      } else {
        console.log(' ✗');
      }
    } catch (e) {
      console.log(` ERROR: ${e.message}`);
    }
    
    processedIds.add(orgId);
    progress.processed = [...processedIds];
    
    if ((i + 1) % 10 === 0) {
      saveProgress();
      console.log(`  --- ${processedIds.size}/${orgs.length}, found: ${foundCount} ---`);
    }
    
    // Rate limit
    await sleep(2000 + Math.random() * 2000);
  }
  
  saveProgress();
  console.log(`\n=== DONE: ${foundCount} / ${orgs.length} ===`);
  
  session.ws.close();
}

main().catch(console.error);
