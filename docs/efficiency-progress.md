# CTC efficiency implementation progress

Plan: `docs/superpowers/plans/2026-10-23-efficiency.md`.

## 2026-10-23 — Codex

- Read full official packet via Google Docs export; local PDF omitted detailed tabs.
- Cloned `jdishihara/ctc2026` at `f4eb4dd`, working branch `arjun/ctc-efficiency`.
- Downloaded official 600-season archive; case.json matches the repository exactly. Extracted only ignored history files.
- Baseline pytest: no existing tests (exit 5). Baseline season 451: PnL 11,481, 323 fills, zero rejections.
- Profile: fair_analog 1.284s cumulative across 177 calls; future_exposure 0.322s, weights 0.318s, expected_values 0.255s. A substantial remainder is per-analog Python damage/outage work.
- Independent builder check: nothing important left.
- Ruling: keep financial model and fitted parameters unchanged; improve computation and execution correctness. This permits direct baseline comparisons and avoids overfitting the verification set.
- Ruling: use a separate baseline worktree and the existing new implementation clone; this provides isolation without modifying Arjun's unrelated Martingale project.

## Forecast implementation — Codex

- Four independent regression failures reproduced: gaps/fractional ages selected the wrong historical times; a late observation projected too much remaining storm; age 480 incorrectly still projected future exposure.
- Fixed age alignment with linear interpolation, verified-prefix incremental squared-distance caching, tie-preserving partition selection, and vectorized per-company damage/outage.
- `python -m pytest tests/test_forecast.py -q`: 7 passed after 4 failed / 3 passed on the original implementation.
- Benchmark: 1,419 complete forecasts per implementation over tune seasons 451/470/500, 3 repeats. Baseline 8,235.53 ms vs candidate 4,817.48 ms (1.7095x); maximum absolute fair/uncertainty difference 1.1369e-13. Median 6.798 -> 3.488 ms; p95 7.088 -> 5.804 ms.
- Initial execution regressions: all 10 failed against the old adapter/strategy/simulator. After cancellation, atomic refresh, timeout gating, paused-order cancellation, and pending-order reservation fixes, all 17 tests passed.
- Added a passive-fill replenishment regression: failed before correction. Full suite now 23 passing, including cancellation retry, malformed snapshots, and passive replacement rejection.
- Ruling: passive replenishment changes trading behavior; assess it on tune seasons before running verification. No new strategy parameters are fitted.

## Execution review and final evidence — Codex

- Tune means deep/thin: 8,572.12 / 5,154.10 -> 8,577.71 / 5,155.03. Both rose; proceeded with the fixed candidate to verification.
- Verification means deep/thin: 9,343.72 / 5,924.82 -> 9,345.51 / 5,927.40. Thin p10 -2,680.858 -> -2,682.242 (0.052% worse), within the existing 10% acceptance bound. Zero simulated rejections in both versions and regimes.
- One independent code review found four important defects: acknowledgements without usable IDs/quantities, truncated HTTP replies, fills racing with refresh/cancel, and paused orders hidden after a lost acknowledgement. Regressions reproduced the failures; all four are fixed.
- Added two failing quantity-validation cases (boolean/fractional accepted quantities), then rejected those malformed acknowledgements. Complete suite: **40 passed in 0.59s**, including real local HTTP cancellation/recovery.
- Ruling: cancellation is confirmed by refreshing the account and checking target orders are gone, not by guessing the response body's schema. Replacement sizes use the refreshed position.
- Ruling: read open orders before positions to conservatively retain capacity for racing fills. Required reads must all succeed before publishing account state; the API still does not provide a transactional account snapshot.
- Ruling: defer the review's minor fractional-duration exposure issue. Supplied dense history uses two-second steps; arbitrary fractional ages still need interval-weighted integration. This limitation is explicit in the results report.
- Ruling: preserve fitted strategy/parameters; do not add unverified ETF arbitrage or claim reconstruction of missing historical damage. Keep the existing feed-log replay path. No competition/testnet orders or deployment.
- Full results, reproducible commands, and limitations are in `docs/efficiency-results.md`; README and EXPERIMENTS link the evidence.
- Post-review verification repeated all 75 seasons in each regime (49s deep / 50s thin); both output CSVs are byte-for-byte identical to the reported candidate results. Final full suite again: 40 passed in 0.59s. `git diff --check` passed; fetched origin/main has no new commits relative to the branch base.
