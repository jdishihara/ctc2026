# Competition rehearsal — October 23, 2026

Tested the combined code at `4de24eaad7b4d7b91b1fe5ff63bc17b54996c633`, then applied the Mario settlement correction in this branch. This includes the merged systematic strategy, announcement controls, derivatives extension, and Mario desk. No strategy parameters were tuned during this rehearsal.

## Results

| Check | Result |
| --- | --- |
| Python suite before the correction | 186 passed |
| New Mario regression tests before the correction | 3 failed for the expected payout error; 3 passed |
| Full Python suite after the correction | **192 passed** |
| Derivatives unit/integration suite | **103 passed** in 17 files |
| Derivatives clock/schedule tests | 11 passed in UTC; the same 11 passed in America/New_York |
| TypeScript check | Passed |
| Development and production extension builds | Passed |
| Derivatives CLI drill | All three rounds completed, three scripted events per round |
| Systematic HTTP/WebSocket rehearsal | Season 451, all three rounds, 87 submitted orders, 24 unique fills; pause/resume/status commands processed |
| Mario HTTP desk rehearsal | All 46 symbols mapped; all eight races observed; simulated fill settled; zero remaining positions or recommendations after settlement |

### Systematic rehearsal

Ran `scripts/mock_exchange.py --season 451 --speed 25 --port 19775` and the default live bot against its localhost HTTP/WebSocket endpoints, using a separate control file. Sent `pause GEN`, `status`, `resume GEN`, and `status`; the log records the expected transitions. The mock reached final settlement and exited normally. A final bot refresh logged one connection-refused warning after the mock server shut down; there were no other error/rejection diagnostics. The runner then terminated its bot and other owned processes.

The mock reported settlement PnL of +10,998. This is a connectivity/accounting smoke result with accelerated time and synthetic fills, **not a performance estimate**. The existing frozen research results and stress limitations remain in [research-continuation.md](research-continuation.md).

### Mario correction

The [official case packet](https://docs.google.com/document/d/1XnZGvu3qPCc0abJYtkax9IyHVbx-LvUH6s1k8Y9j3Ps/edit) pays 50 to each series winner in a tie. Three- and four-way ties therefore make a complete series-winner set pay 150 or 200. The pricer already modeled this rule; the desk's arbitrage calculation incorrectly assumed every set paid exactly 100.

Selling all four contracts for a combined 120 could previously be labeled guaranteed profit even though a four-way tie would lose 80 per set. The correction uses 200 as the conservative upper payout for series-set sales and 100 as the lower payout for purchases. Race-winner sets still pay exactly 100. Six regression cases cover the unsafe sales, the zero-profit boundary, profitable sales above 200, purchases below 100, and the unchanged race-set behavior.

The local Mario mock used seed 3 and a six-second race interval. The desk observed races 0 through 8, mapped every symbol, executed one three-contract simulated trade, and reconciled the final realized PnL of +261 with the mock exchange. All positions and recommendations cleared at settlement. This mock uses assumptions about racer skill and market quotes; its profit does not establish an advantage over actual competitors.

## Reproduce the automated checks

From the repository root:

```sh
.venv/bin/python -m pytest -q
.venv/bin/python derivs/drill.py --round 1 --auto --seed 451
.venv/bin/python derivs/drill.py --round 2 --auto --seed 451
.venv/bin/python derivs/drill.py --round 3 --auto --seed 451
```

From `derivatives-overlay/`:

```sh
npm ci --ignore-scripts
npm test
npm run typecheck
npm run build:dev
npm run build
```

For the Mario localhost rehearsal, start `mario/mock_exchange.py --race-every 6 --seed 3`, then `mario/desk.py --mock --auto-results --no-repl --port 18787 --interval .5`. The dashboard is at `http://127.0.0.1:18787`. Its `fill` command can exercise simulated order execution. Stop both processes after race 8.

Machine-readable results are in [competition-rehearsal.json](competition-rehearsal.json). Local raw logs are under `out/rehearsal-20261024/` (UTC date; ignored by Git).

## Remaining verification

- A real exchange rehearsal is still needed for actual feed schemas, team credentials, rate limits, fills, and account reconciliation. No remote orders were submitted here.
- The derivatives integration suite verifies form prefilling without submitting. Actual installed-extension execution and Mario browser-prefill compatibility were not verified in this run; browser interaction was interrupted by changes to the active Chrome window. The Playwright browser suite was not run. Successful builds and DOM tests do not replace that check.
- Historical systematic data has no live announcements. Control parsing and pause/resume behavior passed, but the announcement re-anchoring strategy has no measured live PnL evidence.
- These checks establish tested software behavior under the stated conditions. They do not establish a win probability; opponent behavior and real execution remain material unknowns.
