# Cornell Bot Efficiency Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Reduce forecasting latency and prevent live order replacement on uncertain account state.

**Architecture:** Preserve the fitted model and default strategy. Cache only verified observation prefixes, vectorize company damage across analogs, and make cancellation and refresh success explicit at the exchange boundary.

**Tech Stack:** Python, NumPy, pytest, existing urllib/WebSocket client.

**Spec:** `docs/superpowers/specs/2026-10-23-efficiency-design.md`.

## Global Constraints

- Fit seasons 1–450, tune 451–525, verify 526–600; never edit published data or fitted parameters.
- Preserve the 120-action live budget and existing defaults; compare deep and thin regimes.
- No live deployment or exchange orders in this session.
- Baseline revision `f4eb4dd` is preserved in a separate worktree for comparison.

## Review Focus

- Observation gaps, corrected prefixes, and a new storm must not reuse invalid cached evidence.
- Cancel rejection, timeout, or rate limiting must preserve local reservations and prevent replacement.
- Empty position responses must clear old positions; partial refresh failure must not authorize trading.
- A paused symbol's old orders must be cancelled, including a retry after failure.
- Numerical changes must preserve dense-feed forecasts, uncertainty, and replay trades within floating-point tolerance.

### Task 1: Forecast alignment and speed

Files: `ctc/analog.py`, `ctc/valuation.py`, `tests/test_forecast.py`, `scripts/benchmark_forecast.py`.

- [x] Write independent sparse-observation fixtures with known analog weights/future exposure and compare real library forecasts against baseline values.
- [x] Run the tests and verify the sparse-observation failure in the original implementation.
- [x] Align library tracks by observation age; cache squared errors for unchanged prefixes; use partition for top-k selection with ties preserved.
- [x] Vectorize per-company damage/outage over analogs in `SeasonModel.fair_analog`.
- [x] Verify corrected/replaced/repeated prefixes, late storm, terminal age and original dense-feed output.
- [x] Benchmark representative full forecast calls and compare both full replay regimes against the baseline.

### Task 2: Confirmed order and account state

Files: `bot/live.py`, `ctc/strategies.py`, `ctc/sim.py`, `tests/test_execution.py`.

- [x] Reproduce rejected cancellation freeing capacity, stale refresh permitting orders, missing position rows retaining old quantities, and paused resting quotes remaining live.
- [x] Return explicit cancellation success from both adapters, retain reservations on failure, and gate replacement on success.
- [x] Commit account snapshots only after complete successful polls; suppress new orders after failures/uncertain submissions until reconciliation.
- [x] Cancel paused quotes and retry failed cancellation; count pending simulated orders in reserved capacity.
- [x] Run failure, recovery, limit and paused-order tests against real strategy/adapter logic with HTTP responses stubbed.

### Task 3: Verification and handoff

Files: `README.md`, `EXPERIMENTS.md`, dependency/test configuration, `docs/efficiency-results.md`.

- [x] Run the complete pytest suite and deterministic forecast benchmark.
- [x] Report 526–600 PnL, p10, minimum, fill counts and runtime for deep and thin; distinguish numerical performance from behavior corrections.
- [x] Obtain one independent code review, fix consequential findings with regression tests, and run the full suite.
- [x] Commit and push a reviewable branch/PR with precise reproduction commands and limitations: https://github.com/jdishihara/ctc2026/pull/1.
