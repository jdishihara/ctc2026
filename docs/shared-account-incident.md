# Shared-account interference — 2026-10-24

Batch 01 used frozen runtime `59603dd`, 10% position limits, and a $250
cumulative loss trigger. Its first season settled at +$141.16. The next season,
competition `0d7afac2-6acd-4223-aa8a-8c1a067091f0`, contains orders absent
from this runner's journal.

## Verified sequence

Exchange `created_at` timestamps below are local EDT on October 24.

| Time | Order | Source |
| --- | --- | --- |
| 00:56:41.281742 | Sell 200 PORT at 63.17; filled 200 | Unowned ID `6d19d71e-e0bd-47ff-86b0-20a1bbab6971` |
| 00:57:02.594135 | Buy 180 PORT at 62.04 | Our first order; ID `9b4a529d-3101-4479-917a-1e3db7470436` |
| 00:57:10.379719 | Sell 180 PORT at 59.89; filled 180 | Unowned ID `56012b87-37ee-4a83-abe3-d7b4b001f115` |
| 00:58:03.688659 | Sell 200 PORT at 58.02 | Unowned ID `f7a6c6ac-2196-45bb-a8f9-4e6ad1ad7837` |

Our runner was interrupted through SIGINT and exited. Its cleanup bought back
20 PORT, 50 AQUA, and 40 GRID, then observed a flat account. The final receipt
seconds later instead recorded PORT -114 and the unowned partial sell order.
Subsequent read-only API checks showed further full-size orders after exit.
At the history check with elapsed active time 328 seconds, `/orders?limit=500`
returned 23 orders: 8 acknowledged by our journal (5 strategy, 3 cleanup) and
15 unowned. Requests with limit 1 and 2 returned exactly 1 and 2 rows; the
endpoint supplied no pagination metadata.

Only the feed recorder and local status archiver remained among local Python
processes at approximately 05:00 UTC. This does not identify the other trader
or rule out a browser, another language, or another machine. The user was asked
whether a teammate or another bot was operating the shared account.

## Diagnosis and reporting

The original interpretation, a position-limit reset at rollover, was incorrect.
Our first order reduced an already-existing -200 position toward the correct
-20 target. The defect in the practice supervisor is that its ownership check
only inspected **open** orders: an unknown order that fully filled between
polls escaped the check. Cleanup also relied on open-order ownership and could
interact with positions changed by the other trader.

The second trial remains in the raw journal as interrupted. Its recorded
after-cleanup account mark of +$384.68 includes mixed activity and open risk;
it is neither an attributable strategy result nor a completed-season profit.
The final receipt's `verified` flag checked only matching competition identity.
It must not be interpreted as proof of flatness or exclusive account control.

Live submissions remain stopped while the conflict is investigated. Unknown
orders and another trader's positions must not be cancelled or flattened.
Offline development, review, and feed recording continue.

## Resolved 2026-10-24 10:00 EDT: the other trader was our own full-size bot

The "unowned" orders were placed by this repository's production launcher, `zsh bot/run_live.sh` (restart wrapper
around `bot/live.py --rate 120 --feed-log recordings/testnet.jsonl`), started on Jayden's Mac at 00:22:53 EDT on
October 24 and still running at 10:00. Its log, `recordings/bot_live.log`, contains the three orders of the table above
with the same exchange order IDs:

```
ORDER {'symbol': 'PORT', 'side': 'sell', ..., 'quantity': 200, 'price': 63.17} -> {'order_id': '6d19d71e-e0bd-47ff-86b0-20a1bbab6971', ...}
ORDER {'symbol': 'PORT', 'side': 'sell', ..., 'quantity': 180, 'price': 59.89} -> {'order_id': '56012b87-37ee-4a83-abe3-d7b4b001f115', ...}
ORDER {'symbol': 'PORT', 'side': 'sell', ..., 'quantity': 200, 'price': 58.02} -> {'order_id': 'f7a6c6ac-2196-45bb-a8f9-4e6ad1ad7837', ...}
```

Two of our own processes (the full-size live bot and the 10% practice supervisor) traded the one team key at the same
time. No third party was involved, and nothing about the exchange or the account is unexplained. The operational rule
stands: exactly one trading process on the key. On competition day that is `bot/run_live.sh` alone; `bot/practice.py`
must not run.
