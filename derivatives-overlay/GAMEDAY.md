# Game day: Derivatives (Sat Oct 24, 4:15-5:30 pm)

Organisers confirmed (asked by Jayden ~11:00): **a bot running in our logged-in browser may place orders.** The overlay
therefore trades through the exchange's own API (the same `POST /api/v1/orders` the Buy button sends, authenticated by
the login cookie). Nobody fills forms or clicks Buy. Exactly ONE laptop is armed; the others only watch.

## Before the case opens (one laptop, the "bot" laptop)
1. `cd derivatives-overlay && git pull && npm ci && npm run build` (Node 18+).
2. `chrome://extensions` → Developer mode → remove any older copy of this overlay → **Load unpacked** → `derivatives-overlay/dist`.
3. Log in to https://cornelltradingcompetition.org/trading in that Chrome, open the Derivatives page, **hard-reload** it.
4. Header must say **DERIVATIVES**. Edge tab → **Ready n/m**: wait until every line is green or grey ("wait"):
   - `API` polling · `OIL chain` / `PLANE chain` show spot, T (trading days) and r from the exchange
   - `OIL contracts 6 (strikes …)`, `quotes`, `OIL spot (REST)`, `clock REST · rate ~52` (R3: ~39), `T … d (REST chain)`
   - `positions REST`, `own feed … symbols` (warn is OK: the page socket + chain polling still work)
   - red `underlyings` = the exchange names the underlyings differently → Config `underlyings` (+ `headline.aliases`)
   - `submit API … not armed` until step 6
5. Dry run without arming: when the chain is live, the Edge tab shows fair values, market IV and a ticket queue.
   Press **send** on one tiny ticket if you want to see an order go through (Capture tab → `auto:result`, HTTP 200).
6. **Arm**: header → **arm auto** (red **AUTO ON**). From now on the overlay trades. `Alt+P` pauses, **disarm** stops.
7. Other laptops: load the same build, open the page, do NOT arm. Watch Risk / Timeline / Capture. The `other orders`
   line goes red on the bot laptop if a second copy is armed or someone clicks by hand.

## What happens each event (2.5 real minutes), with nobody typing
| When | Overlay |
|---|---|
| news +0 s | headline parsed → spot and vol targets auto-confirm (R1: announced IV; R2: three analysts, median then learned weights; R3: converter auto-identified) → edge tickets POSTed, 1.5 s apart, both underlyings, within the 36/min budget (12 kept for the flatten) |
| +60 s | underlying moves (REST chain spot updates each second) → targets re-checked, more edge tickets |
| +120 s snap | makers reprice → **cancel-all** resting option orders → flatten tickets through the touch until delta and vega are ~0 → true vol logged, analysts scored |
| next news | cancel-all again, then the next event |

## The only human inputs
- The Ready box shows a **schedule** line in amber when the exchange's fictional date is not the packet's: the overlay
  rebased the three-day layout onto the exchange's dates (day index from the clock's elapsed seconds). Check that the
  E-number and phase in the header match what the exchange shows; if not, patch Config `schedule` dates.
- A target line says **needs you: …** (incomplete or insane parse): `Alt+S` / `Alt+V`, type the number, Enter, `Alt+A`.
  Lines that say **auto: waiting for …** are not requests (analysts still arriving). The other underlying keeps trading
  on its own confirmed targets meanwhile.
- Round 3: Vol tab says **not identified**: pick the converter the analyst message names, check the σ it gives.
- `Alt+P` the moment anything looks wrong (then **disarm** if it stays wrong). Everything else is automatic.

## If something breaks
| Symptom | Do |
|---|---|
| `API` line red "no successful poll" | you are logged out: reload, log in, hard-reload |
| `API … backoff x4` / orders show HTTP 429 | the exchange rate-limits: Config `api.chainMs: 2000`, `positionsMs: 2000`; the auto-pilot already pauses 5 s after a 429 |
| orders REJECTED with a reason (Capture tab) | read it: position limit → the overlay sizes down next cycle; "halted" → wait |
| `underlyings` red | Config `underlyings: ["X","Y"]` and `headline.aliases` to the exchange's names, **Validate & save** (no rebuild) |
| chain never fills | Capture tab → `http:GET /api/v1/options/...` example; patch `fields.quote` in Config |
| overlay in the way | `Alt+O` hides it; the exchange works normally without it |
| fall back to manual | **disarm**, `Alt+N` prefills the page form (`auto.submitVia: "form"` for the clicking auto-pilot) |

Scoring is Σ rank^1.5 per round: one bad round costs more than a great one earns. The overlay flattens after every
snap; if it cannot (red **FLATTEN NOW**), press `Alt+F` and **send** the closing tickets yourself.
