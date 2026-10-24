// End-to-end: armed auto-pilot against the mock exchange in real Chromium. Event 1 at 4x: news at +6 s, the underlying
// moves 15 s later, the makers snap 15 s after that. Expect auto-confirmed targets, auto submissions during the event,
// flatten submissions after the snap, and orders counted by the mock.
import { test, expect, chromium, BrowserContext } from '@playwright/test';
import { spawn, ChildProcess } from 'node:child_process';
import { existsSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '../..');
const EXT = join(ROOT, 'dist-dev');
const PORT = 5317;
const BASE = `http://localhost:${PORT}`;

let server: ChildProcess;
let ctx: BrowserContext | null = null;
let skipReason: string | null = null;

const stats = async () => (await (await fetch(`${BASE}/__mock/stats`)).json()) as { orderPosts: number; wsExtraFrames: number; positions: { symbol: string; quantity: number }[] };

const portFree = async () => {
  try {
    await fetch(`${BASE}/__mock/stats`);
    return false;
  } catch {
    return true;
  }
};

test.beforeAll(async () => {
  if (!existsSync(join(EXT, 'manifest.json'))) throw new Error('run npm run build:dev first');
  for (let i = 0; i < 50 && !(await portFree()); i++) await new Promise((r) => setTimeout(r, 200)); // a previous spec's mock may still be closing
  server = spawn(process.execPath, [join(ROOT, 'mock-exchange/server.mjs'), '--port', String(PORT), '--fast', '4', '--preroll', '8', '--start-event', '1', '--quiet'], { stdio: 'inherit' });
  for (let i = 0; i < 50; i++) {
    try {
      if ((await fetch(`${BASE}/api/v1/competitions/current`)).ok) break;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  try {
    ctx = await chromium.launchPersistentContext(mkdtempSync(join(tmpdir(), 'deriv-auto-')), {
      headless: true, channel: 'chromium', args: [`--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`],
    });
  } catch (e) {
    skipReason = `could not launch Chromium with the extension: ${e}`;
  }
});
test.afterAll(async () => {
  await ctx?.close();
  if (server) {
    const gone = new Promise<void>((r) => server.once('exit', () => r()));
    server.kill();
    await Promise.race([gone, new Promise((r) => setTimeout(r, 3000))]);
  }
  for (let i = 0; i < 25 && !(await portFree()); i++) await new Promise((r) => setTimeout(r, 200));
});

test('armed auto-pilot confirms targets, submits edge tickets, then flattens after the snap', async () => {
  test.skip(!!skipReason, skipReason ?? '');
  test.setTimeout(180_000);
  const page = await ctx!.newPage();
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(`${BASE}/trading`);
  const ov = page.locator('[data-deriv-overlay]');
  await expect(ov.getByText('DERIVATIVES')).toBeVisible({ timeout: 15_000 });
  expect((await stats()).orderPosts).toBe(0);

  // arm: badge appears, nothing is sent before the news
  await ov.getByRole('button', { name: 'arm auto' }).click();
  await expect(ov.getByText('AUTO ON', { exact: true })).toBeVisible();
  await ov.getByRole('button', { name: '📌' }).click();
  await expect(ov.getByText('E1 · R1')).toBeVisible({ timeout: 20_000 });

  // news: targets auto-confirm and the first submissions follow
  await expect(ov.getByText(/auto-confirmed: spot/).first()).toBeVisible({ timeout: 30_000 });
  await expect.poll(async () => (await stats()).orderPosts, { timeout: 30_000 }).toBeGreaterThan(0);
  await expect(ov.getByText(/AUTO: submitted (BUY|SELL) \d+ (OIL|PLANE)_/)).toBeVisible({ timeout: 10_000 });
  const duringEvent = await stats();
  expect(duringEvent.positions.some((p) => p.quantity !== 0)).toBe(true);

  // after the snap the queue flips to flatten tickets and positions shrink back towards zero
  await expect(ov.getByText('SNAPPED')).toBeVisible({ timeout: 60_000 });
  const gross = (s: Awaited<ReturnType<typeof stats>>) => s.positions.reduce((a, p) => a + Math.abs(p.quantity), 0);
  const atSnap = gross(await stats());
  await expect.poll(async () => gross(await stats()), { timeout: 45_000 }).toBeLessThan(atSnap);

  // the log is on the Capture tab; every entry carries the exchange's answer
  await ov.getByRole('button', { name: 'Capture', exact: true }).click();
  await expect(ov.getByText('Auto submissions')).toBeVisible();
  await expect(ov.getByText(/sent · HTTP 200/).first()).toBeVisible();

  // Alt+P pauses: the count stops moving
  await page.keyboard.press('Alt+P');
  await expect(ov.getByText('AUTO PAUSED')).toBeVisible();
  const paused = (await stats()).orderPosts;
  await page.waitForTimeout(4000);
  expect((await stats()).orderPosts).toBe(paused);

  const final = await stats();
  console.log(`[autopilot e2e] orders posted ${final.orderPosts}, open positions ${JSON.stringify(final.positions.filter((p) => p.quantity !== 0))}`);
  expect(final.wsExtraFrames).toBe(0);
  expect(final.orderPosts).toBeLessThanOrEqual(36 * 2);
  expect(errors).toEqual([]);
});
