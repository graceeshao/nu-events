/**
 * Connects to running Chrome via CDP and searches Google for Instagram handles.
 */

const { readFileSync, writeFileSync, existsSync } = require('fs');
const { execSync } = require('child_process');
const { join } = require('path');
const WebSocket = require('ws');

const BASE = '/Users/graceshao/.openclaw/workspace/nu-events/backend';
const ORGS_FILE = join(BASE, 'orgs_to_discover.json');
const RESULTS_FILE = join(BASE, 'discovered_handles.json');
const DB_FILE = join(BASE, 'nu_events.db');
const PROGRESS_FILE = join(BASE, 'discover_progress.json');
const CDP_URL = 'http://127.0.0.1:18800';

const orgs = JSON.parse(readFileSync(ORGS_FILE, 'utf-8'));

// Load progress - just track processed IDs
let processedIds = new Set();
if (existsSync(PROGRESS_FILE)) {
  try { 
    const p = JSON.parse(readFileSync(PROGRESS_FILE, 'utf-8')); 
    processedIds = new Set(p.processed || []);
  } catch {}
}

// Get already-found handles from DB
function getFoundFromDB() {
  const out = execSync(`sqlite3 "${DB_FILE}" "SELECT id, name, instagram_handle FROM organizations WHERE instagram_handle IS NOT NULL AND instagram_handle != '';"`)
    .toString().trim();
  if (!out) return [];
  return out.split('\n').map(line => {
    const [id, name, handle] = line.split('|');
    return { id: parseInt(id), name, handle };
  });
}

function saveProgress() {
  writeFileSync(PROGRESS_FILE, JSON.stringify({ processed: [...processedIds] }));
  const found = getFoundFromDB();
  writeFileSync(RESULTS_FILE, JSON.stringify(found, null, 2));
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

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
      const timer = setTimeout(() => {
        this.callbacks.delete(id);
        reject(new Error(`Timeout: ${method}`));
      }, 20000);
      this.callbacks.set(id, (msg) => {
        clearTimeout(timer);
        if (msg.error) reject(new Error(msg.error.message));
        else resolve(msg.result);
      });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  
  async navigate(url) {
    await this.send('Page.navigate', { url });
    await sleep(2000);
  }
  
  async evaluate(expression) {
    const result = await this.send('Runtime.evaluate', { 
      expression, returnByValue: true, awaitPromise: true 
    });
    return result?.result?.value;
  }
}

function connectToPage(wsUrl) {
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
  
  const result = await session.evaluate(`
    (() => {
      const links = Array.from(document.querySelectorAll('a[href*="instagram.com"]'));
      const profiles = [];
      for (const link of links) {
        const href = link.href;
        const match = href.match(/instagram\\.com\\/([a-zA-Z0-9_.]+)\\/?$/);
        if (match) {
          const handle = match[1];
          const skip = new Set(['p','reel','reels','stories','explore','accounts','about','developer','legal','privacy','terms','directory','static','tags','locations','nametag','direct','tv','lite','web','session']);
          if (!skip.has(handle.toLowerCase()) && handle.length > 1) {
            profiles.push(handle);
          }
        }
      }
      const text = document.body.innerText.toLowerCase();
      const nuMentioned = text.includes('northwestern') || text.includes('evanston');
      const hasCaptcha = text.includes('unusual traffic') || text.includes('not a robot');
      return JSON.stringify({ profiles: [...new Set(profiles)], nuMentioned, hasCaptcha });
    })()
  `);
  
  try {
    const parsed = JSON.parse(result);
    if (parsed.hasCaptcha) return 'CAPTCHA';
    if (parsed.profiles.length > 0 && parsed.nuMentioned) {
      return parsed.profiles[0];
    }
  } catch {}
  
  return null;
}

function updateDB(orgId, handle) {
  const escaped = handle.replace(/'/g, "''");
  execSync(`sqlite3 "${DB_FILE}" "UPDATE organizations SET instagram_handle = '${escaped}' WHERE id = ${orgId};"`);
}

async function main() {
  const listResp = await fetch(`${CDP_URL}/json/list`);
  const targets = await listResp.json();
  const target = targets.find(t => t.type === 'page') || targets[0];
  console.log(`Using tab: ${target.id}`);
  
  const session = await connectToPage(target.webSocketDebuggerUrl);
  console.log('Connected');
  
  await session.send('Page.enable');
  await session.send('Runtime.enable');
  
  const remaining = orgs.filter(o => !processedIds.has(o.id));
  const existingFound = getFoundFromDB();
  let foundCount = existingFound.length;
  console.log(`Total: ${orgs.length}, Done: ${processedIds.size}, Left: ${remaining.length}, Found so far: ${foundCount}`);
  
  let captchaStreak = 0;
  
  for (let i = 0; i < remaining.length; i++) {
    const org = remaining[i];
    const { id: orgId, name: orgName } = org;
    
    process.stdout.write(`[${processedIds.size + 1}/${orgs.length}] ${orgName}`);
    
    try {
      const handle = await searchOrg(session, orgName);
      
      if (handle === 'CAPTCHA') {
        captchaStreak++;
        const waitTime = captchaStreak * 120000; // 2min, 4min, 6min...
        console.log(` ⚠ CAPTCHA (streak: ${captchaStreak}), waiting ${waitTime/1000}s`);
        if (captchaStreak >= 5) {
          console.log('Too many CAPTCHAs. Saving and exiting.');
          saveProgress();
          process.exit(1);
        }
        await sleep(waitTime);
        i--; // Retry
        continue;
      }
      
      captchaStreak = 0;
      
      if (handle) {
        console.log(` ✓ @${handle}`);
        updateDB(orgId, handle);
        foundCount++;
      } else {
        console.log(' ✗');
      }
    } catch (e) {
      console.log(` ERR: ${e.message}`);
    }
    
    processedIds.add(orgId);
    
    // Save every 5 orgs
    if ((i + 1) % 5 === 0) {
      saveProgress();
      if ((i + 1) % 20 === 0) {
        console.log(`  --- ${processedIds.size}/${orgs.length}, found: ${foundCount} ---`);
      }
    }
    
    await sleep(8000 + Math.random() * 7000);
  }
  
  saveProgress();
  console.log(`\n=== DONE: ${foundCount} / ${orgs.length} ===`);
  session.ws.close();
}

main().catch(e => {
  console.error(e);
  saveProgress();
  process.exit(1);
});
