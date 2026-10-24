// Unattended drill: the armed auto-pilot against the mock exchange over all ten events, in real Chromium.
//
//   node scripts/drill-autopilot.mjs [--fast 4] [--seed 1] [--start-event 1] [--events 10] [--out out/deriv_drill] [--headed]
//                                    [--config '{"auto":{"submitRateCap":36}}']   (patched into chrome.storage via the Config tab API)
//
// Needs `npm run build:dev` (dist-dev/). Starts the mock (port 5317), loads the extension, arms auto-submit, then samples
// /api/v1/pnl, /__mock/stats and /__mock/news every second until the last event has snapped and been flattened.
// Prints one line per event: PnL before the news, PnL when the next news arrives (after the flatten), orders sent,
// residual gross position; and a total. Writes the timeline to <out>/timeline-<stamp>.jsonl and a summary JSON.
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, writeFileSync, appendFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const EXT = join(ROOT, 'dist-dev');
const argv = process.argv.slice(2);
const arg = (name, dflt) => {
  const i = argv.indexOf('--' + name);
  if (i < 0) return dflt;
  const v = argv[i + 1];
  return v === undefined || v.startsWith('--') ? true : v;
};
const FAST = Number(arg('fast', 4));
const SEED = String(arg('seed', 1));
const START = Number(arg('start-event', 1));
const NEVENTS = Number(arg('events', 10));
const OUT = String(arg('out', join(ROOT, '..', 'out', 'deriv_drill')));
const HEADED = argv.includes('--headed');
const CONFIG_PATCH = arg('config', null);
const PORT = 5317;
const BASE = `http://localhost:${PORT}`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const get = async (p) => (await fetch(BASE + p)).json();

if (!existsSync(join(EXT, 'manifest.json'))) {
  console.error('run `npm run build:dev` first');
  process.exit(2);
}
mkdirSync(OUT, { recursive: true });
const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
const timelinePath = join(OUT, `timeline-${stamp}.jsonl`);
const diagPath = join(OUT, `overlay-${stamp}.log`);
const DIAG_EVERY = Number(arg('diag-every', 10));

// a previous run's mock may still hold the port
for (let i = 0; i < 50; i++) {
  try { await fetch(`${BASE}/__mock/stats`); await sleep(200); } catch { break; }
}
const server = spawn(process.execPath, [join(ROOT, 'mock-exchange/server.mjs'), '--port', String(PORT), '--fast', String(FAST), '--preroll', '8',
  '--start-event', String(START), '--seed', SEED, '--quiet'], { stdio: 'inherit' });
for (let i = 0; i < 100; i++) {
  try { if ((await fetch(`${BASE}/api/v1/competitions/current`)).ok) break; } catch { /* not up */ }
  await sleep(100);
}

const ctx = await chromium.launchPersistentContext(mkdtempSync(join(tmpdir(), 'deriv-drill-')), {
  headless: !HEADED, channel: 'chromium', args: [`--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`],
});
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
await page.goto(`${BASE}/trading`);
const ov = page.locator('[data-deriv-overlay]');
await ov.getByText('DERIVATIVES').waitFor({ timeout: 20_000 });
if (CONFIG_PATCH) {
  await ov.getByRole('button', { name: 'Config', exact: true }).click();
  const ta = ov.locator('textarea').first();
  const cur = JSON.parse(await ta.inputValue());
  const deepMerge = (a, b) => { for (const [k, v] of Object.entries(b)) a[k] = v && typeof v === 'object' && !Array.isArray(v) ? deepMerge(a[k] ?? {}, v) : v; return a; };
  await ta.fill(JSON.stringify(deepMerge(cur, JSON.parse(CONFIG_PATCH))));
  await ov.getByRole('button', { name: /Validate/ }).click();
  await sleep(300);
}
await ov.getByRole('button', { name: 'arm auto' }).click();
await ov.getByText('AUTO ON', { exact: true }).waitFor({ timeout: 5_000 });
try { await ov.getByRole('button', { name: '📌' }).click({ timeout: 2000 }); } catch { /* already pinned */ }

const t0 = Date.now();
const events = []; // { n, round, headline, tNews, pnlBefore, ordersBefore, pnlAfter, ordersAfter, grossEnd, maxGross }
let lastNewsCount = 0;
let lastState = null;
let quietSince = null;
let nextDiag = 0;
const maxRealMs = (NEVENTS * 150 + 120) * 1000 / FAST + 60_000;
while (Date.now() - t0 < maxRealMs) {
  let stats, pnl, news;
  try {
    [stats, pnl, news] = await Promise.all([get('/__mock/stats'), get('/api/v1/pnl'), get('/__mock/news')]);
  } catch (e) {
    await sleep(500);
    continue;
  }
  const gross = stats.positions.reduce((a, p) => a + Math.abs(p.quantity), 0);
  const row = { t: (Date.now() - t0) / 1000, ft: stats.fictional_time, state: stats.state, pnl: pnl.total_pnl, orders: stats.orderPosts, gross, news: news.length };
  appendFileSync(timelinePath, JSON.stringify(row) + '\n');
  const headlines = news.filter((m) => m.type === 'headline');
  if (news.length > lastNewsCount) {
    if (headlines.length > events.length) {
      const prev = events[events.length - 1];
      if (prev && prev.pnlAfter == null) { prev.pnlAfter = pnl.total_pnl; prev.ordersAfter = stats.orderPosts; prev.grossEnd = gross; }
      for (const m of headlines.slice(events.length)) {
        events.push({ n: m.event, round: m.round, headline: m.headline.slice(0, 90), tNews: row.t, pnlBefore: pnl.total_pnl, ordersBefore: stats.orderPosts, maxGross: 0 });
      }
    }
    lastNewsCount = news.length;
    nextDiag = 0; // sample the overlay right after any news
  }
  if (row.t >= nextDiag) {
    nextDiag = row.t + DIAG_EVERY;
    try {
      const txt = (await page.evaluate(() => {
        const root = document.querySelector('[data-deriv-overlay]')?.shadowRoot;
        const el = root?.querySelector('div');
        return el ? el.innerText : '';
      })).replace(/\n{2,}/g, '\n');
      appendFileSync(diagPath, `\n===== t=${row.t.toFixed(0)} ft=${stats.fictional_time} ${stats.state} news=${news.length} pnl=${pnl.total_pnl} gross=${gross}\n${txt.slice(0, 2500)}\n`);
    } catch { /* overlay busy */ }
  }
  const cur = events[events.length - 1];
  if (cur) cur.maxGross = Math.max(cur.maxGross, gross);
  if (stats.state !== lastState) { lastState = stats.state; }
  // done: all events seen, the last one snapped (clock paused for the break or closed) and we are flat for 15 s
  if (events.length >= NEVENTS) {
    const sinceNews = row.t - cur.tNews;
    if (sinceNews > (150 / FAST) + 5 && (gross === 0 || sinceNews > (150 / FAST) + 60)) {
      if (quietSince == null) quietSince = row.t;
      if (row.t - quietSince > 5) { cur.pnlAfter = pnl.total_pnl; cur.ordersAfter = stats.orderPosts; cur.grossEnd = gross; break; }
    } else quietSince = null;
  }
  await sleep(1000);
}

// the overlay's own auto log (rejections, refusals) from the Capture tab
let autoLog = '';
try {
  await ov.getByRole('button', { name: 'Capture', exact: true }).click();
  await sleep(300);
  const txt = await page.evaluate(() => document.querySelector('[data-deriv-overlay]')?.shadowRoot?.querySelector('div')?.innerText ?? '');
  const i = txt.indexOf('Auto submissions');
  autoLog = i >= 0 ? txt.slice(i, i + 4000) : '';
} catch { /* ignore */ }
const finalStats = await get('/__mock/stats').catch(() => ({}));
await ctx.close();
server.kill();

const fmt = (x, w = 9) => (x == null ? '-' : x.toFixed(2)).padStart(w);
console.log(`\nauto-pilot drill  fast ${FAST}  seed ${SEED}  events ${START}-${START + NEVENTS - 1}  (${((Date.now() - t0) / 1000).toFixed(0)} s real)`);
console.log('ev rd  pnl before  pnl after    delta  orders  maxGross  grossEnd  headline');
let total = 0;
for (const e of events) {
  const d = e.pnlAfter != null ? e.pnlAfter - e.pnlBefore : null;
  if (d != null) total += d;
  console.log(`${String(e.n).padStart(2)} ${String(e.round ?? '?').padStart(2)} ${fmt(e.pnlBefore, 11)} ${fmt(e.pnlAfter, 10)} ${fmt(d, 8)} ${String((e.ordersAfter ?? finalStats.orderPosts ?? 0) - e.ordersBefore).padStart(7)} ${String(e.maxGross).padStart(9)} ${String(e.grossEnd ?? '-').padStart(9)}  ${e.headline}`);
}
console.log(`total PnL ${total.toFixed(2)}  orders ${finalStats.orderPosts}  extra ws frames ${finalStats.wsExtraFrames}  page errors ${errors.length}`);
if (errors.length) console.log(errors.slice(0, 5).join('\n'));
if (autoLog) console.log('\n' + autoLog.split('\n').slice(0, 60).join('\n'));
writeFileSync(join(OUT, `summary-${stamp}.json`), JSON.stringify({ fast: FAST, seed: SEED, events, total, finalStats, errors, configPatch: CONFIG_PATCH }, null, 1));
console.log(`timeline ${timelinePath}\noverlay text samples ${diagPath}`);
