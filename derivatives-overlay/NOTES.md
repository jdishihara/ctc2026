# Build notes

## Repository inspection (before anything was installed)
- `git status --porcelain`: clean. Branch `main`, last commit `f4eb4dd`.
- Repo root has no `package.json`, `pnpm-workspace.yaml`, `turbo.json`, `nx.json`, `lerna.json`, `tsconfig*.json` or
  `.npmrc`, so no workspace could capture this folder. Root `.gitignore` covers Python artifacts only.
- Existing folders: `bot/`, `ctc/`, `data/`, `derivs/` (Python Black-Scholes and drill tools), `mario/`, `scripts/`.
  None of them were touched.
- Node v22.14.0, npm 10.9.2. Packages were installed from inside the folder with `--workspaces=false`, and
  `.npmrc` pins `workspaces=false` too.
- `.isolation-baseline.txt` was captured right after creating the folder, so its only line is
  `?? derivatives-overlay/`. `verify-isolation` ignores paths inside this folder, so the baseline is effectively
  "clean".
- Playwright 1.64.1 needed Chromium build 1248. It was downloaded to `~/Library/Caches/ms-playwright`, outside the
  repo.

## Decisions
- **Bridge buffering.** `overlay.js` runs at `document_idle` (as specified), which is after the page's first
  requests and the WebSocket subscribe. The MAIN-world hooks keep a buffer of up to 3,000 messages until the
  overlay posts `overlay-ready`, then replay it. Each message carries a sequence number `n` and the overlay
  de-duplicates by it. Without this, the subscribe frame, `/symbols` and the first quotes would be missed.
- **Bridge origin check.** Messages are accepted only when `event.source === window`. jsdom (tests) leaves `source`
  null with an empty origin, so that exact combination is also accepted. Chrome never produces it for a real
  cross-window message.
- **Targets must be confirmed before `Alt+N`** loads an edge ticket. Arb tickets queued by hand and flatten tickets
  don't need confirmation. Confirmation is per event: anything set for an earlier event resets to an unconfirmed
  "pre-news" value at the next NEWS phase.
- **Robust edge** is computed at vol low/mid/high of the band. The band comes from:
  - Round 1 announced IV, or a typed vol: a single point.
  - Analysts with no history: min/max of the analysts.
  - With history, for weighted/single modes: blend ± k·√(Σ wᵢ·MSEᵢ).
  - Configurable via `blend.bandMode`.
- **Analyst weights:** `wᵢ ∝ 1/(MSEᵢ + λ)`, λ = 0.0025 (5 vol points squared). MSEᵢ is the per-underlying MSE
  shrunk toward the pooled MSE, with the pooled value counting as one pseudo-observation. An analyst with no history
  gets MSE = λ.
- **"Passive" pricing:** the spec's `fair ∓ edge/2` lands *beyond* the touch (e.g. above the ask for a buy), which is
  aggressive, not passive. Passive instead rests inside the spread (bid + tick for a buy), never closer to fair than
  `minEdge`. Toggle it on the Edge tab or set `priceMode` in Config.
- **Rounds 2-3 synthetic preference:** a single leg is dropped in favor of a same-direction synthetic forward when
  |spot component| > 2 × |vol component|. In Round 1 (vol known) single legs are used.
- **Risk caps:** tickets that would push |delta| or |vega| past a cap (and away from zero) are kept, marked red and
  moved to the end of the queue. `Alt+N` skips them; the "load" button can still load one.
- **Flatten queue:** closing tickets are ordered by risk reduction relative to the book's direction. Existing
  synthetic pairs (long C + short P at one strike) are kept as linked legs. It does not invent new synthetics to
  close.
- **Guard and chain cells:** a chain cell is clickable only if the chain reader located it (it's registered in a
  WeakSet). That is stricter than "any cell in a table". The spec rule "inside a form and not a toggle → blocked"
  is applied to everything except those registered cells. A `<button>` with no `type` inside a form counts as
  submit (that's what the browser does with it) and is refused even if its text is `BUY`.
- **No product-tab clicks:** the click allowlist is exactly the four toggles plus chain cells, so the overlay won't
  switch OIL↔PLANE for you. If the visible chain is the other underlying (told apart by its strike set), prefill
  stops and says so. After any cell click, the order panel's contract label is still checked.
- **Spot priority:**
  1. WS underlying quote less than 30 s old (it may legitimately not tick between events).
  2. DOM "Spot" when the visible chain is that underlying.
  3. Parity.
  4. Stale WS.
- **T:** `T_mode: "dom"` uses the Fair-tab value while that tab is visible and was read in the last 5 s; otherwise
  T is computed. In replay (1800-dates) the computed T maps time of day onto the first scheduled day.
- **Clock:** interpolation uses local receipt time only. A "paused"/non-running state does not advance. DOM clock
  fallback uses the fallback rates (52 / 39).
- **Shadow root is `open`** so Playwright, and you in DevTools, can inspect it. The page's CSS still can't reach it.
- **Edge captured** (Timeline): our fills from `/api/v1/trades` during the event, valued at the post-snap spot and
  market IV. **Fills vs quote** (Risk tab): checks whether fills land at the quoted mid (the glossary's "execute at
  the midpoint" claim).
- **Learning trigger:** the store's 200 ms tick starts a timer at the SNAPPED transition; learning runs 5 real
  seconds later (`thresholds.learnDelayRealSec`).
- **Dialog-free UI:** "Reset history" and "Reset to defaults" use click-twice confirmation, not `window.confirm`.
- **Canvas in the mock page** is decorative and guarded for jsdom.

## Deviations from the prompt
- The prompt was cut off at build-order step 8, so sections 12-13 (including the full Definition of Done) were never
  seen. I treated the acceptance criteria in section 9, the docs in section 10 and the "Repo checks" line as the
  definition of done.
- `src/core/classify.ts` (frame classifier) and `src/ui/{controller.ts,fmt.ts,DraftInput.tsx}` were added beyond the
  listed layout. `src/env.d.ts` declares the `.css` text import and `__DEV__`.
- `tests/helpers/` holds shared fixtures (chain builder, mock page loader).
- `npm test` runs the whole Vitest suite, then re-runs the clock/schedule/trading-time tests under `TZ=UTC` and
  `TZ=America/New_York`. The clock test also switches `process.env.TZ` at runtime.

## Skipped tests
- None. Two Playwright specs run headless with the extension loaded (Chromium build 1248, `channel: 'chromium'`):
  - `overlay.spec.ts`: event 1, prefill, the human submit and the Risk tab.
  - `rounds.spec.ts` (about 1.7 min): arb flags with `--glitch`, analyst learning over events 4-6, and the Round 3
    variance converter.
- The prod `dist/` was also loaded in Chromium and checked via `chrome://extensions`: enabled, no manifest or runtime
  errors, host `https://cornelltradingcompetition.org/*` only.
- Not covered by a browser test: the capture-only badge on another case's page. It's covered by the store's
  case-detection unit test (Hurricane frames stay capture-only). If
  extensions can't load on another machine, the spec falls back to headed mode, then skips with the reason. The
  spec file stays.

## Verify in the first live minutes (the real Derivatives page has never been observed)
1. **Symbols:** do the contracts match `^(OIL|PLANE)_(\d{4})_([CP])(\d+(?:\.\d+)?)$`? (Capture → `ws:quote` example;
   `http:GET /api/v1/symbols`.) Are strikes 60/100/140 or something else?
2. **Spot source:** are `OIL`/`PLANE` quoted on the WebSocket? If not, the tag shows `DOM` or `parity`. Check that it
   matches the chain header "Spot".
3. **News format:** the shape of headline, announcement and analyst messages (Capture → `ws:news:*`). Does the
   parser read the announced spot/IV (Round 1) and analyst numbers (Round 2)? Is the analyst number in the text or
   in a field? Round 3: what quantity is it?
4. **Positions fields:** the `/api/v1/positions` response shape and the qty field name. Set `fields.positions` if
   needed.
5. **`clock_rate`:** expect about 52 in Rounds 1-2 and 39 in Round 3. Does the header countdown match the exchange
   clock?
6. **T behavior:** does the Fair tab's "trading days" decay with the clock or stay at 20.00? Compare
   `T … DOM Fair tab` with `computed`.
7. **Midpoint fills:** after the first fills, check the Risk tab's "Fills vs quote" line.
8. **Order panel text:** are the toggles exactly `BUY`/`SELL`/`Limit`/`Market`, and are the labels `QTY`/`PRICE`?
   Does clicking a chain price cell select the contract (and is the order panel label the full symbol)?
9. **Order book channel:** does an `orderbook` frame type exist (flagged as orderbook-like / new-type in Capture)?
