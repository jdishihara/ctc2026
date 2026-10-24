# Announcements: what the bot does and what the human at the log decides

The packet: "Announcements can change the economics of a company at any point in the season", "the research seasons
have no news and no announcements", and the house "reacts slowly. After an announcement, it takes about 45 real seconds
to adjust fully." The feed message is `{"type": "announcement", "headline": "<what changed>", "symbols": ["<ticker>"]}`:
free text and a ticker list, no numbers. Nothing in the model has seen one.

## What happens without anyone doing anything

1. The bot logs `ANNOUNCEMENT [HAVEN]: <headline> -> pausing those symbols; re-anchor to the house mid in 60 s ...`,
   cancels its resting orders in those symbols and places none.
2. 60 s later (`--announce-wait`) it reads the house mid, shifts that symbol's fair so it equals the mid, and resumes.
   The model's storm dynamics keep moving the fair from there (the shift is an additive offset). ETF fairs follow their
   baskets. Log: `announcement wait over: HAVEN fair anchored to house mid 31.20 (offset -6.35); trading resumes`.

This gives up the 45 s during which we could beat the house to the new price, and it trusts the house's reading of the
headline. It cannot lose money on a misread headline, which is the failure mode that matters with 45% of the score on
this case. Treat it as the default; intervene only when the headline is unambiguous.

## When to intervene, and how

Append one line to `recordings/control.txt` from any terminal on the bot's Mac (polled every 3 s, no restart):

```bash
echo "HAVEN -6%" >> recordings/control.txt     # fair = model fair x 0.94 from now; HAVEN resumes immediately
echo "GEN +3"    >> recordings/control.txt     # fair = model fair + 3 points
echo "PORT =61.5" >> recordings/control.txt    # fair is 61.5 now; the model moves it from there (same as the auto-anchor)
echo "resume HAVEN" >> recordings/control.txt  # the announcement does not change value: trade on the plain model now
echo "clear HAVEN" >> recordings/control.txt   # undo an adjustment
echo "status" >> recordings/control.txt        # paused symbols and adjustments appear in the log
```

Decision rule, in order:

1. **Is the effect obvious in sign and rough size within 20 s of reading it?** If not, do nothing; the auto-anchor
   handles it. A wrong sign on a 200-lot PORT position costs far more than the house's 45 s of lag is worth.
2. **If yes, type the percentage.** The point of acting is to be ahead of the house, so send it before the house has
   moved. After the house has moved (about 45 s) there is nothing to gain by typing a number; let the anchor run.
3. **Never `resume` without thinking.** `resume` says "value unchanged". Use it only for headlines that are clearly
   cosmetic (a name change, a management statement with no economics).
4. **Watch the next log line.** Mid, fair and position print every 10 s. If fair and the house mid disagree by more than
   a few percent a minute later and you cannot say why, `pause` the symbol and let the final report settle it.

## How to size a percentage: what each symbol's value is made of

Settlement rules (fitted, R² about 1): the value is a fixed start minus damage and outage terms, or for the rebuilders
a saturating function of damage, or for the insurers a layer on the season's insured loss. An announcement changes one
of these pieces; translate it into the piece, then into the price.

| Symbol | Value = | A headline that... | Direction | Size reasoning |
|---|---|---|---|---|
| PORT | 100 - 0.549 x cumulative damage - 0.0197 x weighted outage s | repairs/upgrades the port, or raises its throughput | up | damage repaired x 0.549 points; 10 damage points repaired is about +5.5 points (+9% at 60) |
|  |  | extends a closure (e.g. inspection, strike) | down | 0.0197 per weighted outage second; a 30-minute market-clock closure is 60 real s, about -1.2 points |
| ISLE | 60 - 0.380 x damage | resort reopening/renovation, tourism demand | up / down | 0.38 per damage point |
| AQUA | 35 - 0.200 x damage | fleet recovered, farm restocked, fishing ban | up / down | 0.2 per damage point; a ban is like an outage with no formula, think 2-5% |
| GRID | 50 - 0.244 x damage - 0.048 x outage s | grid hardening, substation back online early, regulator rate cut | up / down | 0.244 per damage point |
| FERRY | 25 - 0.050 x damage - 0.059 x outage s | terminal reopened, service suspended, fuel subsidy | up / down | outage dominates: 0.059 per second |
| RECON | 37.3 + 31.5 x (1 - exp(-(PORT+GRID+FERRY damage)/190)) | wins/loses a repair contract, crew capacity up | up / down | capacity change moves the 31.5 ceiling; a 10% capacity increase is roughly +1 to +3 points |
| MAT | 27.2 + 14.4 x (1 - exp(-total damage/204)) | supply shortage (prices up), import tariff on materials | up (shortage) / down (tariff on them) | ceiling 14.4, so a few points at most |
| GEN | 30.2 + 4.4 x (1 - exp(-GRID damage/10.6)) + 0.074 x GRID outage s | generator fleet expanded, grid restored early | up / down | GRID outage seconds dominate: 0.074 per second |
| HAVEN | 75 at season loss <= $400M, linear to 21 at $1,300M | layer bounds change, government relief covers losses, premium rebate | depends | pays the first layer: a $100M change in covered loss is about 6 points (9%) inside the layer; above $1,300M HAVEN is already at 21 and only REIN moves |
| REIN | 90 until $1,300M, then -0.035 per $M | retrocession bought, attachment point lowered | depends | below $1,300M of season loss REIN does not move at all; only act if losses are near or past the attachment |
| ARCH | 1 PORT + 1 ISLE + 2 AQUA + 1 GRID + 2 FERRY + 1 HAVEN | (never named directly) | follows | the bot recomputes it from the adjusted components |
| REBLD | 2 RECON + 2 MAT + 1 GEN | (never named directly) | follows | same |

Things to keep in mind:

- **Insurers depend on where the season total lands, not on the storm.** Check the `pnl` log line's HAVEN fair before
  acting: if HAVEN is already near 21 the layer is exhausted and a loss-reducing announcement helps REIN, not HAVEN.
- **Rebuilders gain from damage.** A headline that is bad for PORT (more damage, longer closure) is good for RECON and
  GEN. If the announcement names only PORT, the model already propagates PORT's damage to the rebuilders through the
  settlement rules; adjust PORT only.
- **Permanent versus temporary.** Damage is permanent; a closure costs outage seconds while it lasts. "Reopens
  tomorrow" on day 2 is worth little; "closed for the season" on day 1 is a large outage number.
- **The house is usually right within a minute.** If your number and the house's post-move mid disagree by more than
  5%, the house is the better guess; `clear` the adjustment and let the anchor take over, or `PORT =<mid>`.

## Rehearsal (no exchange needed)

The mock exchange (`scripts/mock_exchange.py`) replays research seasons, which have no announcements. The behaviour is
covered by `tests/test_control.py`. To see the log lines once, start the bot against the mock and append commands to
`recordings/control.txt`; `status` prints the current state.
