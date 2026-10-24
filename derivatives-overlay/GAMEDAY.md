# Game day: Derivatives (Sat Oct 24)

## Before the case opens
- [ ] Load the **prod** build (`dist/`) in `chrome://extensions` and **hard-reload** the exchange tab.
- [ ] Open the Derivatives page early. **Capture** tab: `ws:quote` is counting up for the 12 option symbols, and
      `http:GET /api/v1/competitions/current` is polling. Header says **DERIVATIVES** (not "capture only").
- [ ] **Edge** tab: each underlying shows `spot: WS` (or `DOM`/`parity`), and the header shows `T 20.00d · DOM Fair tab`
      (open the exchange's Fair tab once) or `computed`.
- [ ] Prefill dry run: accept targets (`Alt+A`), press `Alt+N`. The contract, BUY/SELL, Limit, QTY and PRICE get set.
      **Don't submit.** Set QTY to 1 by hand if you want to see the button text.
- [ ] Assign focus: one teammate presses `Alt+1` (OIL), the other `Alt+2` (PLANE).
- [ ] Auto-pilot: header shows `confirm auto`. Leave **arm auto** alone unless the organisers have approved bot
      submission; if they have, arm it on ONE laptop only (two armed overlays would double the orders).
- [ ] If not already confirmed, ask in Slack #questions: "Is read-only DOM/WebSocket monitoring with manual submit OK?"
- [ ] Click **Download capture** after the first minute and keep the file.

## Auto-pilot (what changes with it on)
- **Auto-confirm (default on):** the targets fill and confirm themselves when the news parses completely and the
  numbers are sane. The reader intervenes only when a target shows **"needs you: …"** (incomplete parse, a number out
  of bounds): fix it with `Alt+S` / `Alt+V` or wait for the missing analyst, then `Alt+A`.
- **Round 3 converter (default on):** identified from the first analyst message; the Vol tab says **auto-identified**
  or **not identified** with the candidates. Pick by hand only in the second case (that pick sticks; **re-run** returns
  to auto).
- **Auto-submit (default OFF):** if the organisers say a bot may submit, press **arm auto** in the header. The clicker
  then only watches: tickets load and submit themselves (edge tickets during the event, flatten tickets after the
  snap, product tab switched as needed, 36 orders/min cap). Red **AUTO ON** badge in the header. `Alt+P` pauses
  instantly; **disarm** turns it off. Capture tab → "Auto submissions" shows each order and the exchange's answer;
  a red row is a rejection. If anything looks wrong: `Alt+P`, then go back to `Alt+N` and click by hand.

## Each event (2.5 real minutes)
| When | Do |
|---|---|
| Before news | Be flat. Header says `NEWS IN m:ss`. |
| News (+0 s) | Headline arrives → targets fill in **amber**. Check the spot and vol against the text and fix any typo (`Alt+S`/`Alt+V`, Enter). Then `Alt+A`. |
| +0 to +120 s | `Alt+N` → check the form → **click Buy/Sell yourself** → `Alt+N` again. The queue skips what you just loaded. |
| +60 s | The underlying moves. If the live spot disagrees with the target, a warning appears with a new suggestion: re-check, then `Alt+A`. |
| Snap (+120 s) | Overlay switches to **Risk**: `Alt+F` loads closing tickets (shows the spread cost). True vol is logged at +5 s. |
| Last 30 s | Red **FLATTEN NOW** means delta or vega is still above 10% of the caps. |

Order rate: header `orders n/40` (amber at 30, red at 36). ⏳ in the queue = past this minute's budget.

## Round 2 (no IV announced)
- The analyst grid (**Vol** tab) fills from the news. Type missing values (Tab between cells, Enter applies).
- First event: blend = **median**, and the band = analyst min/max. Edge is the **worst case over the band**, so only
  robust trades show up. Spot edge goes through **synthetic forwards** (vega-neutral, ⛓ linked legs).
- After each snap the accuracy table updates. From the second event, switch the blend to **weighted (learned)**.
  It trusts whichever analyst has been closest.

## Round 3 (a quantity "linked to IV")
- Read the first analyst message. In **Vol → Round 3 converter**, pick what it is: variance, daily move $ or %,
  move to expiry %, ATM straddle $, call/put price @K, P(ITM) @K, vega/pt @K, or a **custom formula** in `x S T K`
  (e.g. `sqrt(x)`, `x/100*sqrt(252)`).
- Use "try x =" to sanity-check: the σ it gives should be near the market IV (Vol tab, bottom).
- Learning measures errors in σ, so the best-converting analyst earns the weight.

## Source tags
`spot: WS` underlying quote · `DOM` chain header "Spot" · `parity` K + C − P (median across strikes) ·
`T … DOM Fair tab` / `computed` / `fixed 20d` / `manual` · `clk REST` / `DOM` / `stale` · amber = unconfirmed
suggestion.

## If something breaks
- **No quotes:** Capture tab, check the frame kinds. If a frame type is new it's flagged. Patch `fields.quote` or
  `symbolRegex` in Config and click **Validate & save** (applies live).
- **Spot wrong:** type it in. **T wrong:** Config `T_mode` → `computed` / `fixed20` / `manual` + `manualTDays`.
- **Prefill fails:** use the card's **copy** button and type the order in. Adjust `dom.buyText` etc. in Config.
- **Positions missing:** Risk tab → Manual positions JSON.
- **Anything else:** `Alt+O` hides the overlay. The exchange works normally without it.

Scoring is Σ rank^1.5 per round, so **one bad round costs a lot**: take the robust edge, flatten between events,
and don't carry vega into a vol you can't pin down.
