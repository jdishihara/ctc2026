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
