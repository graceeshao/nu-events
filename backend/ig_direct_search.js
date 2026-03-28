/**
 * Searches Instagram's web search directly for Northwestern org handles.
 * Uses Instagram's search suggestions API.
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

let processedIds = new Set();
if (existsSync(PROGRESS_FILE)) {
  try { 
    const p = JSON.parse(readFileSync(PROGRESS_FILE, 'utf-8')); 
    processedIds = new Set(p.processed || []);
  } catch {}
}

function getFoundFromDB() {
  const out = execSync(`sqlite3 "${DB_FILE}" "SELECT id, name, instagram_handle FROM organizations WHERE instagram_handle IS NOT NULL AND instagram_handle != '';"`)
    .toString().trim();
  if (!out) return [];
  return out.split('\n').map(line => {
    const parts = line.split('|');
    return { id: parseInt(parts[0]), name: parts[1], handle: parts[2] };
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
    await sleep(3000);
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

// Generate likely handle variations for an org name
function generateHandleGuesses(orgName) {
  const clean = orgName.replace(/[^a-zA-Z0-9\s]/g, '').trim();
  const words = clean.split(/\s+/).map(w => w.toLowerCase());
  const guesses = [];
  
  // Common patterns for NU orgs
  const joined = words.join('');
  const underscored = words.join('_');
  const dotted = words.join('.');
  
  // Add NU prefixed/suffixed variants
  guesses.push(joined);
  guesses.push(underscored);
  guesses.push(dotted);
  guesses.push(`nu_${underscored}`);
  guesses.push(`nu${joined}`);
  guesses.push(`${underscored}_nu`);
  guesses.push(`${joined}nu`);
  guesses.push(`${joined}_northwestern`);
  guesses.push(`northwestern${joined}`);
  guesses.push(`${joined}atnu`);
  guesses.push(`${joined}_at_nu`);
  
  // If name has acronym-like structure (e.g. "ASL Club" -> "aslclub")
  if (words.length <= 4) {
    const acronym = words.map(w => w[0]).join('');
    guesses.push(`${acronym}_nu`);
    guesses.push(`${acronym}nu`);
    guesses.push(`nu${acronym}`);
    guesses.push(`${acronym}_northwestern`);
  }
  
  return [...new Set(guesses)].filter(g => g.length >= 3 && g.length <= 30);
}

async function searchOrgOnInstagram(session, orgName) {
  // Use Instagram search URL
  const query = encodeURIComponent(`${orgName} northwestern`);
  const url = `https://www.instagram.com/explore/search/keyword/?q=${query}`;
  
  await session.navigate(url);
  
  // Look for profile results
  const result = await session.evaluate(`
    (() => {
      const text = document.body.innerText;
      // Instagram search results show handles
      const handlePattern = /@([a-zA-Z0-9_.]+)/g;
      const handles = new Set();
      let match;
      while ((match = handlePattern.exec(text)) !== null) {
        handles.add(match[1]);
      }
      
      // Also look in links
      const links = document.querySelectorAll('a[href*="/"]');
      for (const link of links) {
        const href = link.getAttribute('href') || '';
        const m = href.match(/^\\/([a-zA-Z0-9_.]+)\\/?$/);
        if (m) {
          const h = m[1];
          const skip = new Set(['explore','accounts','about','developer','legal','privacy','terms','directory','static','tags','locations','nametag','direct','tv','lite','web','session','p','reel','reels','stories']);
          if (!skip.has(h.toLowerCase()) && h.length > 1) {
            handles.add(h);
          }
        }
      }
      
      return JSON.stringify({
        handles: [...handles],
        textSnippet: text.substring(0, 500),
        loginRequired: text.includes('Log in') || text.includes('Sign up')
      });
    })()
  `);
  
  try {
    return JSON.parse(result);
  } catch {
    return { handles: [], textSnippet: '', loginRequired: true };
  }
}

// Try fetching an Instagram profile directly to verify it exists
async function verifyHandle(session, handle) {
  await session.navigate(`https://www.instagram.com/${handle}/`);
  
  const result = await session.evaluate(`
    (() => {
      const text = document.body.innerText.toLowerCase();
      const exists = !text.includes("sorry, this page") && !text.includes("page not found");
      const bio = text.substring(0, 1000);
      const nuRelated = bio.includes('northwestern') || bio.includes('evanston') || bio.includes(' nu ') || bio.includes('@nu');
      return JSON.stringify({ exists, nuRelated, bio: bio.substring(0, 300) });
    })()
  `);
  
  try {
    return JSON.parse(result);
  } catch {
    return { exists: false, nuRelated: false };
  }
}

function updateDB(orgId, handle) {
  const escaped = handle.replace(/'/g, "''");
  execSync(`sqlite3 "${DB_FILE}" "UPDATE organizations SET instagram_handle = '${escaped}' WHERE id = ${orgId};"`);
}

async function main() {
  const listResp = await fetch(`${CDP_URL}/json/list`);
  const targets = await listResp.json();
  const target = targets.find(t => t.type === 'page') || targets[0];
  
  const session = await connectToPage(target.webSocketDebuggerUrl);
  await session.send('Page.enable');
  await session.send('Runtime.enable');
  
  // First, navigate to Instagram to establish cookies
  await session.navigate('https://www.instagram.com/');
  await sleep(3000);
  
  const remaining = orgs.filter(o => !processedIds.has(o.id));
  let foundCount = getFoundFromDB().length;
  console.log(`Left: ${remaining.length}, Found: ${foundCount}`);
  
  for (let i = 0; i < remaining.length; i++) {
    const org = remaining[i];
    const { id: orgId, name: orgName } = org;
    
    process.stdout.write(`[${processedIds.size + 1}/${orgs.length}] ${orgName}`);
    
    // Try common handle patterns
    const guesses = generateHandleGuesses(orgName);
    let found = false;
    
    // Only try first few most likely patterns
    for (const guess of guesses.slice(0, 3)) {
      try {
        const result = await verifyHandle(session, guess);
        if (result.exists && result.nuRelated) {
          console.log(` ✓ @${guess}`);
          updateDB(orgId, guess);
          foundCount++;
          found = true;
          break;
        }
      } catch (e) {}
      await sleep(1000);
    }
    
    if (!found) {
      console.log(' ✗');
    }
    
    processedIds.add(orgId);
    
    if ((i + 1) % 5 === 0) {
      saveProgress();
    }
    if ((i + 1) % 25 === 0) {
      console.log(`  --- ${processedIds.size}/${orgs.length}, found: ${foundCount} ---`);
    }
    
    await sleep(2000 + Math.random() * 2000);
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
