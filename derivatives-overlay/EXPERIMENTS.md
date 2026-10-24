
## 2026-10-24 16:21–17:12 — LIVE Derivatives case ("Newtonia vs Euleria"), 10 events over 3 rounds. Realized PnL −7,292.

What the live exchange actually was (none of it in the mock):
- News is not on the API or the socket: headlines are shown on a screen in the room. The overlay never parsed a headline all case; direction/size came from Jayden by chat, typically 30–90 s after the headline, i.e. often after the move.
- The underlying follows `GET /api/v1/symbols/{U}/scheduled-prices` (past points only): clean jumps exactly at the packet's move times (+60 real s at 52/min), small noise between. Moves: OIL −12%, +6%, +2%, +12.5%, −3.5%, 0, 0, −5%, 0, −5.9%; PLANE +5.8%, −3%, 0, −5.6%, +1.7%, −8%, +5.6%, +2%, +7%, −3%.
- Market makers reprice the spot at the move (parity-implied spot within ~0.7 of REST spot 60 s after a move) and run a steep skew at 110–180% IV; IV = baseline + remaining event variance × 252/T (organisers' slide), so it climbs as T shrinks and steps down a little at each snap.
- Touch size ~30 lots; exchange max_position 300/contract; 429s on bursts; the round-2 open was halted for ~20 s after the clock started.

What lost money, by event: E1 −4.5k (pre-news targets accepted by hand → single-leg "vol" trades, net long 358 delta into the −12% jump); E4 ≈ 0 (right call, lopsided fills, flatten after the vol snap); E6 −1.1k (relay arrived after the move; my typed target was 6% beyond the already-moved spot); E7/E8 −0.1k/−0.7k (right calls both; single-leg vol trades vs a flat target vol while makers quote a skew, flatten re-sending before fills showed → overshoot ping-pong); E10 −0.5k (relay 2 s before the move; 300 P100 bought at the jump and sold back at the same price).

Shipped during the case (all pushed): `auto.confirmEach`, `auto.flattenAfterMove` (UNDERLYING_MOVED works the book flat), `thresholds.edgeThroughFrac` (size to perTicketCap, price a fraction of the edge through the touch), `auto.synthOnly` (vega-neutral synthetics only). The last two never ran live: the extension reload did not happen before the final event.

Lessons (for a re-run): (1) direction + size from the screen must reach the bot within ~10 s, otherwise skip the event; (2) trade only synthetics or deep-ITM pairs, never single legs against a flat target vol; (3) flatten right after the move with position-confirmed sizing (poll positions before every re-send); (4) a correct direction call on a 5% jump with 900 delta is ≈ +4.5k, so three good events would have covered the whole loss.
