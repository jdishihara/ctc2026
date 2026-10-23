// End-to-end: real Chromium + the dev build of the extension + the mock exchange.
import { test, expect, chromium, BrowserContext, Page } from '@playwright/test';
import { spawn, ChildProcess } from 'node:child_process';
import { existsSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '../..');
const EXT = join(ROOT, 'dist-dev');
const PORT = 5317; // the dev manifest matches this origin
const BASE = `http://localhost:${PORT}`;

let server: ChildProcess;
let ctx: BrowserContext;
let page: Page;
let skipReason: string | null = null;

const stats = async () => (await (await fetch(`${BASE}/__mock/stats`)).json()) as { orderPosts: number; wsSubscribeFrames: number; wsExtraFrames: number; positions: { symbol: string; quantity: number }[] };

test.beforeAll(async () => {
  if (!existsSync(join(EXT, 'manifest.json'))) throw new Error('run npm run build:dev first');
  server = spawn(process.execPath, [join(ROOT, 'mock-exchange/server.mjs'), '--port', String(PORT), '--fast', '4', '--preroll', '10', '--quiet'], { stdio: 'inherit' });
  for (let i = 0; i < 50; i++) {
    try {
      if ((await fetch(`${BASE}/api/v1/competitions/current`)).ok) break;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  const userDataDir = mkdtempSync(join(tmpdir(), 'deriv-overlay-e2e-'));
  const args = [`--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`];
  try {
    ctx = await chromium.launchPersistentContext(userDataDir, { headless: true, channel: 'chromium', args });
  } catch (e) {
    try {
      ctx = await chromium.launchPersistentContext(userDataDir, { headless: false, args });
    } catch (e2) {
      skipReason = `could not launch Chromium with the extension: ${e} / ${e2}`;
    }
  }
});

test.afterAll(async () => {
  await ctx?.close();
  server?.kill();
});

test('overlay observes the mock exchange, suggests targets, prefills without submitting', async () => {
  test.skip(!!skipReason, skipReason ?? '');
  page = await ctx.newPage();
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(`${BASE}/trading`);

  // 1. overlay mounts (shadow DOM is open, Playwright locators pierce it)
  const overlay = page.locator('[data-deriv-overlay]');
  await expect(overlay).toHaveCount(1, { timeout: 10_000 });
  await expect(overlay.getByText('DERIVATIVES')).toBeVisible({ timeout: 10_000 });

  // 2. capture shows quotes and the clock poll
  await overlay.getByRole('button', { name: 'Capture', exact: true }).click();
  await expect(overlay.getByText('ws:quote', { exact: true })).toBeVisible({ timeout: 10_000 });
  await expect(overlay.getByText('http:GET /api/v1/competitions/current', { exact: true })).toBeVisible();

  // 3. the countdown advances
  const countdown = overlay.locator('.count');
  const c1 = await countdown.textContent();
  await page.waitForTimeout(2200);
  const c2 = await countdown.textContent();
  expect(c1).not.toEqual(c2);

  // 4. event 1 headline → targets suggested (amber) on the Edge tab
  await overlay.getByRole('button', { name: 'Edge', exact: true }).click();
  const spotIn = overlay.locator('[data-field="spot-OIL"]');
  const volIn = overlay.locator('[data-field="vol-OIL"]');
  await expect(spotIn).toHaveValue('108.50', { timeout: 20_000 });
  await expect(volIn).toHaveValue('65.0');
  await expect(spotIn).toHaveClass(/amber/);
  await expect(overlay.locator('[data-field="vol-PLANE"]')).toHaveValue('85.0');

  // 5. Alt+A accepts, Alt+N prefills the order form
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.keyboard.press('Alt+KeyA');
  await expect(spotIn).not.toHaveClass(/amber/);
  await page.keyboard.press('Alt+KeyN');
  await expect(overlay.locator('.ticket')).toContainText('Ready: review and click', { timeout: 5000 });
  const card = (await overlay.locator('.ticket .row').first().textContent()) ?? '';
  const m = /(BUY|SELL)(\d+)((?:OIL|PLANE)_0626_[CP]\d+)@([\d.]+)/.exec(card.replace(/\s+/g, ''));
  expect(m, card).not.toBeNull();
  const [, side, qty, sym, px] = m as RegExpExecArray;
  await expect(page.locator('.osym')).toHaveText(sym);
  await expect(page.locator('input.qty')).toHaveValue(qty);
  expect(Number(await page.locator('input.price').inputValue())).toBeCloseTo(Number(px), 6);
  await expect(page.locator('.sidebtn.active')).toHaveText(side);
  await expect(page.locator('.typebtn.active')).toHaveText('Limit');

  // 6. automation sent zero orders and did not touch the socket
  let s = await stats();
  expect(s.orderPosts).toBe(0);
  expect(s.wsSubscribeFrames).toBe(1);
  expect(s.wsExtraFrames).toBe(0);

  // 7. a human submit: positions update, the Risk tab reflects it
  await page.locator('button.submit').click();
  await expect.poll(async () => (await stats()).orderPosts).toBe(1);
  await expect.poll(async () => (await stats()).positions.find((p) => p.symbol === sym)?.quantity ?? 0, { timeout: 5000 }).not.toBe(0);
  await overlay.getByRole('button', { name: 'Risk', exact: true }).click();
  await expect(overlay.locator('td', { hasText: sym }).first()).toBeVisible({ timeout: 5000 });
  s = await stats();
  expect(s.orderPosts).toBe(1);
  expect(errors).toEqual([]);
});
