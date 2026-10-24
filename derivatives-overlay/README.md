# Derivatives Overlay (CTC 2026, Newtonia vs Euleria)

A Chrome extension (Manifest V3) that helps a human trader in the Derivatives case. It watches the exchange page,
prices all 12 options with Black-Scholes at the spot and vol you confirm, ranks the mispricings, and can prefill the
exchange's order form. **You always click Buy/Sell yourself.**

## Safety model

- **Read-only observer.** In the page's own JavaScript world it wraps `fetch`, `XMLHttpRequest` and `WebSocket`,
  copies responses and frames, and passes everything through unchanged. Every hook is wrapped in try/catch.
- **No network traffic of its own.** It makes no requests, opens no socket, and never calls `send()` on the page's
  socket. The exchange only honors the first subscription frame, so a stray frame from us could break the feed.
- **No submissions by default.** Every synthetic click goes through `safeClick`
  ([src/ticket/guard.ts](src/ticket/guard.ts)). It allows only buttons whose text is exactly `BUY`, `SELL`, `Limit`
  or `Market` (not `type=submit`), plus chain price cells found by the chain reader. It refuses anything else,
  including `Buy 50 OIL_0626_P100`, `Confirm` and any submit button. It never dispatches Enter and never calls
  `form.submit()` or `requestSubmit()`. The one exception is the opt-in auto-pilot below: with `auto.submit` on,
  `safeSubmit` may click the order form's own submit button, and only after the form was re-read and found to hold
  exactly the loaded ticket, inside the order-rate budget. It still never clicks confirm dialogs.
- Never touches `/auth/` or `/admin/` URLs, cookies or tokens. No remote code, no CDN, no analytics, no `eval`; the
  build fails if `eval`/`new Function` shows up in a bundle.
- Captures stay in memory. A file is written only when you click **Download capture**.
- The only permission is `storage` (config, UI position and analyst history in `chrome.storage.local`).

## Install (competition build)

```bash
cd derivatives-overlay
npm install
npm run build
```

Then in Chrome:
1. Open `chrome://extensions` and turn on **Developer mode**.
2. Click **Load unpacked** and choose `derivatives-overlay/dist`.
3. **Hard-reload the exchange tab.** The hooks are injected at `document_start`, so a tab opened before the install
   won't have them.

`npm run package` also writes `derivatives-overlay.zip` (a zip of `dist/`) if a teammate needs a copy.

## Practice against the mock exchange

```bash
npm run build:dev          # dist-dev/ also matches http://localhost:5317
npm run mock               # http://localhost:5317/trading
```

Load `dist-dev` as an unpacked extension (you can keep both builds loaded), then open
`http://localhost:5317/trading`.

Mock options:

| Flag | What it does |
|---|---|
| `--port 5317` | Port. The dev manifest only matches 5317. |
| `--fast 4` | Multiply the clock rate (52/39) for quick runs. |
| `--rate N` | Force one clock rate for every day. |
| `--start-event N` | Start just before event N (e.g. `4` for Round 2, `7` for Round 3). |
| `--preroll 8` | Real seconds before the first news. |
| `--scenario file.json` | Another scenario (see `mock-exchange/scenario.default.json`). |
| `--seed N` | Market-maker noise seed. |
| `--no-underlying-quotes` | Don't quote `OIL`/`PLANE`, to practice with the parity spot fallback. |
| `--t-mode fixed` | The Fair tab shows a constant 20 trading days. |
| `--glitch` | Misprice OIL's top-strike call (a riskless monotonicity arb) to practice the Arb tab. |

The mock runs the packet schedule. Option makers quote the old spot/vol, the underlying jumps at +60 s and the vol
snaps at +120 s. Round 2 has three analysts (one accurate, one biased, one noisy) and Round 3 has the same analysts
quoting annual variance. Fills go against the mock book, so PnL and positions update. `GET /__mock/stats` shows how
many order POSTs the server has received.

## First live minutes: the Ready box

The Edge tab starts with **Ready n/m**: case detected, feed frames flowing, contracts parsed per underlying (count and
strikes), quotes fresh, spot source per underlying, exchange clock source and rate (about 52/min in Rounds 1-2, 39 in
Round 3), T, positions source, the order form found (QTY, PRICE, BUY, SELL, Limit, submit), and what the last news
message parsed to. Each amber or red line ends with the fix: the Config field to patch or the key to type. "show all"
lists the green lines too. It is the automatic form of the checklist in NOTES.md ("Verify in the first live minutes").

## Using it

The overlay docks bottom-left. Drag it by its header, collapse it with `—` or hide it with `×` / `Alt+O`. Its
position and tab are remembered.

| Key | Action |
|---|---|
| `Alt+N` | Next ticket: prefill the order form |
| `Alt+F` | Next flatten ticket |
| `Alt+A` | Accept all target suggestions |
| `Alt+1` / `Alt+2` | Focus OIL / PLANE (press again for both) |
| `Alt+S` / `Alt+V` | Jump to the spot / vol input |
| `Alt+O` | Show/hide the overlay |
| `Alt+C` | Capture tab |
| `Alt+P` | Pause / resume auto-submit (when armed) |
| `Esc` | Leave the overlay input |

Hotkeys match `event.code`, so macOS Option works. They're ignored while you're typing in an exchange input (except
Esc). See [GAMEDAY.md](GAMEDAY.md) for the per-event routine.

## Auto-pilot (added 2026-10-23)

Three levels, all in Config under `auto` and toggled on the Config tab:

| Setting | Default | What it does |
|---|---|---|
| `auto.confirm` | **on** | Accepts the parsed targets without `Alt+A` when the parse is complete and sane: spot present; Round 1 the announced IV present; Rounds 2 and 3 all three analysts present (Round 3 also needs an identified converter). Bounds: spot within `spotBoundPct` (40%) of the live or pre-news spot, vol inside `volMin`–`volMax` (5%–300%). Otherwise the target stays amber and the Edge tab says why ("needs you: waiting for analyst A3 (2/3)", "spot 8.00 is 92% from live 100.00"). The live spot after the +60 s move is accepted the same way. |
| `auto.converter` | **on** | Round 3: on each analyst message, every converter is tried on the raw numbers; the one whose σ lands nearest the market IV wins if it is within `converterTolPts` (12) and beats the runner-up by `converterTieMarginPts` (3), or if the message names it (variance, straddle, daily move, …) and it is within tolerance. Otherwise the Vol tab says "not identified" with the ranked candidates and you pick by hand. A hand pick switches auto off until **re-run**. `$` or `%` in the quotes narrows the candidates to price-like or percent-like converters. |
| `auto.submit` | **off** | The overlay runs the queue itself: edge tickets during NEWS/UNDERLYING_MOVED (once targets are confirmed), flatten tickets after the snap. Each step picks the next ticket, prefills the form exactly as `Alt+N` does, re-reads the form, and clicks the submit button through `safeSubmit`, which refuses unless armed, the form matches (contract, qty, price, and the button's own "Buy 50 OIL_…" text), and observed order actions are below `submitRateCap` (36/min). It also clicks the OIL/PLANE product tab when the chain shows the other underlying (`auto.switchTabs`). Arm with **arm auto** in the header or the Config checkbox; **Alt+P** pauses/resumes; the header shows a red **AUTO ON** badge. Every submission and the exchange's HTTP answer are listed on the Capture tab and in the capture file (`auto:submit`, `auto:result`). The same contract/side is not re-sent for `resubmitAfterMs` (20 s) unless the position changed; submissions are spaced by `submitIntervalMs` (1.5 s). |

Turn `auto.submit` on only if the organisers confirm that a bot may click submit; the packet says trading is manual.
The flow with everything on: news arrives → targets auto-confirm (or tell you why not) → tickets are submitted →
the underlying moves and the live spot is accepted → the snap flips the queue to flatten tickets → flat before the
next event. The human watches the Edge and Risk tabs and types only when a line says "needs you".

## Editing the config

Open the **Config** tab, edit the JSON, and click **Validate & save**. Changes apply immediately and persist in
`chrome.storage.local`; no rebuild needed. **Reset to defaults** (click twice) restores the built-in values. What you
can change:

- `symbolRegex`, `underlyings`, `caseNameRegex`, `mode` (`auto` / `derivatives` / `capture-only`)
- `fields.*`: response field names to try, in order (e.g. `positions.qty`)
- `dom.*`: the visible texts and patterns used to find the order form, chain, LATEST bar, Spot and Fair-tab T
- `schedule`, `session` (expiry, open/close, holidays), `T_mode` (`dom` / `computed` / `fixed20` / `manual`) and
  `manualTDays`
- `thresholds` (min edge, IV outlier points, arb ε, position limit, per-ticket cap, delta/vega caps, staleness,
  `flattenThroughPct` / `flattenThroughTicks`: how far through the touch flatten tickets are priced, default 2% / 5 ticks)
- `blend` (analyst blend mode, λ, band k), `headline.aliases`, `priceMode`, `prefillEnabled`, `focus`, `multiplier`,
  `tick`

To change the defaults in code, edit [src/core/config.ts](src/core/config.ts), run `npm run build`, click reload on
the extension in `chrome://extensions`, then hard-reload the exchange tab.

## Downloading a capture

**Capture** tab → **Download capture** saves `ctc-capture-<case>-<timestamp>.json`, which holds the last 5,000
messages plus one example of each message kind. Capture runs on every page of the exchange site, including the
Hurricane and Mario cases, where the overlay stays a small "Overlay: capture only" badge.

## Troubleshooting

- **The overlay doesn't appear.** Reload the page after enabling the extension.
- **Quotes are stale (red `quotes Ns` tag).** Open the Capture tab. Are `ws:quote` counts increasing? If the
  WebSocket closed, the page normally reconnects on its own. If quotes come under a different `type`, fix
  `fields.quote` or the symbol regex in Config.
- **Prefill fails.** The ticket card shows which step failed and has a **copy** button, so you can enter the order by
  hand. Then adjust `dom.*` in Config, e.g. if the side toggle reads `Buy` instead of `BUY`. "The chain shows
  PLANE" means: switch the exchange's product tab and press `Alt+N` again. The overlay deliberately won't click
  product tabs.
- **Wrong spot or T.** The header and Edge tab show each number's source: `spot: WS` (underlying quote),
  `DOM` (the chain's "Spot" text) or `parity` (put-call parity). For T, set `T_mode` in Config.

## Development

```bash
npm run typecheck          # tsc --noEmit (strict)
npm test                   # unit + integration (Vitest), then the clock tests under TZ=UTC and America/New_York
npm run test:e2e           # builds dist-dev, starts the mock, runs Playwright with the extension loaded
npm run verify-isolation   # nothing outside derivatives-overlay/ changed
```

Layout:

| Path | Contents |
|---|---|
| `src/main-world/` | Hooks |
| `src/content/` | Isolated-world entry |
| `src/core/` | Bridge, capture, config, storage, DOM readers, hotkeys |
| `src/engine/` | Pure pricing and planning code; no DOM, fully unit-tested |
| `src/state/` | The store |
| `src/ticket/` | Selectors, guard, prefill |
| `src/ui/` | Preact, rendered in a Shadow DOM |
| `mock-exchange/` | The mock exchange |
