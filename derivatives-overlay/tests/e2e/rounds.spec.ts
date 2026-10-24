// End-to-end through Rounds 2 and 3 on the mock: arb flags, analyst learning across events 4-6, Round 3 converter.
import { test, expect, chromium, BrowserContext } from '@playwright/test';
import { spawn, ChildProcess } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '../..');
const EXT = join(ROOT, 'dist-dev');
const BASE = 'http://localhost:5317';

let server: ChildProcess;
let ctx: BrowserContext | null = null;
let skipReason: string | null = null;

test.beforeAll(async () => {
  // wait for a previous spec's mock exchange to release the port
  for (let i = 0; i < 50; i++) {
    try {
      await fetch(`${BASE}/__mock/stats`);
      await new Promise((r) => setTimeout(r, 200));
    } catch {
      break;
    }
  }
  server = spawn(process.execPath, [join(ROOT, 'mock-exchange/server.mjs'), '--port', '5317', '--fast', '6', '--preroll', '4', '--start-event', '4', '--glitch', '--quiet'], { stdio: 'inherit' });
  for (let i = 0; i < 50; i++) {
    try {
      if ((await fetch(`${BASE}/api/v1/competitions/current`)).ok) break;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  try {
    ctx = await chromium.launchPersistentContext(mkdtempSync(join(tmpdir(), 'deriv-rounds-')), {
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
});

test('arb flags, Round 2 analyst learning, Round 3 variance converter', async () => {
  test.skip(!!skipReason, skipReason ?? '');
  test.setTimeout(240_000);
  const page = await ctx!.newPage();
  await page.goto(`${BASE}/trading`);
  const ov = page.locator('[data-deriv-overlay]');
  await expect(ov.getByText('DERIVATIVES')).toBeVisible({ timeout: 15_000 });
  await ov.getByRole('button', { name: '📌' }).click(); // pin tabs: no auto-switching during this test

  // Arb tab: the --glitch monotonicity violation is flagged with its legs and can be queued
  await ov.getByRole('button', { name: 'Arb', exact: true }).click();
  await expect(ov.getByText('monotonicity', { exact: true }).first()).toBeVisible({ timeout: 10_000 });
  await expect(ov.getByText(/BUY OIL_0626_C100@.*SELL OIL_0626_C140@/).first()).toBeVisible();
  await ov.getByRole('button', { name: 'Queue tickets' }).first().click();
  await expect(ov.getByText(/linked tickets queued/)).toBeVisible();

  // Round 2: the analyst grid fills from the news; learning accumulates over events 4-6
  await ov.getByRole('button', { name: 'Vol', exact: true }).click();
  await expect(ov.getByText('Analysts · event 4 (IV)')).toBeVisible({ timeout: 15_000 });
  const accRow = (a: string) => ov.locator('.box', { hasText: 'Analyst accuracy' }).locator('tbody tr').filter({ has: page.locator('td:first-child', { hasText: new RegExp(`^${a}$`) }) });
  // n counts (event, underlying) records: 2 per event
  await expect(accRow('A2').locator('td').nth(1)).toHaveText(/^[2-9]$/, { timeout: 60_000 });
  await expect(ov.getByText(/Analysts · event [56] \(IV\)/)).toBeVisible({ timeout: 60_000 });
  await expect(accRow('A2').locator('td').nth(1)).toHaveText(/^[4-9]$/, { timeout: 60_000 });
  const rmse = async (a: string) => Number(await accRow(a).locator('td').nth(2).textContent());
  expect(await rmse('A2')).toBeLessThan(2); // accurate analyst: < 2 vol points
  expect(await rmse('A1')).toBeGreaterThan(5); // biased analyst
  // the learned blend trusts Analyst 2
  await ov.locator('select', { has: page.locator('option[value="weighted"]') }).selectOption('weighted');
  const wText = (await ov.getByText(/A1 \d+% A2 \d+% A3 \d+%/).first().textContent()) ?? '';
  const w2 = Number(/A2 (\d+)%/.exec(wText)?.[1]);
  expect(w2, wText).toBeGreaterThan(60);

  // Round 3 (after the day-2 close and break): variance quotes converted to sigma
  await expect(ov.getByText(/Analysts · event 7 \(raw → σ via Annual variance/)).toBeVisible({ timeout: 120_000 });
  const grid = ov.locator('.box', { hasText: 'Analysts · event 7' });
  // Analyst 2 quotes OIL variance 0.49 → 70.0%, PLANE 1.0 → 100.0%
  await expect(grid.locator('tbody tr').filter({ hasText: /^A2/ })).toContainText('70.0%', { timeout: 15_000 });
  await expect(grid.locator('tbody tr').filter({ hasText: /^A2/ })).toContainText('100.0%');
  // switching the converter re-converts the same raw numbers
  await ov.locator('select', { has: page.locator('option[value="custom"]') }).selectOption('dailyMovePct'); // 0.49 read as a 0.49% daily move → 7.8%
  await expect(grid.locator('tbody tr').filter({ hasText: /^A2/ })).not.toContainText('70.0%');
  await ov.locator('select', { has: page.locator('option[value="custom"]') }).selectOption('variance');
  await expect(grid.locator('tbody tr').filter({ hasText: /^A2/ })).toContainText('70.0%');

  const stats = await (await fetch(`${BASE}/__mock/stats`)).json();
  expect(stats.orderPosts).toBe(0);
  expect(stats.wsExtraFrames).toBe(0);
});
