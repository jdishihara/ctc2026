# Price Timing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan inline. Steps use checkbox syntax for tracking.

**Goal:** Find a material increase in competition PnL by learning causal short-horizon house-price drift and improving entry timing.

**Architecture:** Fit a small per-symbol, per-phase linear price model on seasons 1–450. Maintain timestamped public-price history online. Test two entry gates and one fair-value adjustment against the accepted `aa51985` strategy, using tune only for selection.

**Tech Stack:** Existing Python/NumPy/SciPy, deterministic replay simulator and pytest. No new runtime dependency.

**Spec:** This document's design below; continuation of the user's explicit request to keep improving the competition model.

## Design and authority

The user wants a strategy capable of winning, rather than stopping at the earlier
1% improvement. That authorizes continued model/strategy experiments and fixes,
not a claim that opponents can never beat it. Continue on the existing feature
branch and PR. Agent chooses the implementation and experiments without a new
approval round, consistent with the user's repeated request to keep going.

Official packet: the house adjusts slowly, over about 45 seconds, and its errors
are present in research data. Source:
https://docs.google.com/document/d/1XnZGvu3qPCc0abJYtkax9IyHVbx-LvUH6s1k8Y9j3Ps/edit

Exploration used only seasons 1–450. Damage-kernel radial power 2 lowered PORT
internal-validation RMSE 5.81 -> 5.42 points, insufficient evidence for replacing
the whole physical model. Price drift has a clearer independent signal. Fit on
1–300, validation on 301–450, five past returns at lags 2/10/30/60/120 seconds,
separate storm/aftermath coefficients. Horizons 30/60/120 seconds yielded
prediction/realized-return correlations .165/.216/.271. At 120s, predictions
above 0.5% in magnitude correspond to 1.20% average signed gross return and
65.4% direction accuracy. These are correlated observations, not independent
trading results, and exclude execution costs.

Choose the 120s horizon using internal training validation, then refit all 1–450.
Features are [1, (p_now - p_lag)/p_now for lag in 2,10,30,60,120]. Use samples
every 10 seconds, elapsed round time 120–650 inclusive, and targets strictly
inside the same round. Ridge penalty .01 except intercept 1e-6. Fit each symbol
and phase (storm/prelim boundary at elapsed 540 seconds) separately. No future
weather, future prices or season labels enter live features.

The online model uses the latest known price at or before each lag timestamp.
Keep one observation preceding the largest lag. Reset all history at each round
open. Missing history, invalid/nonfinite prices, unknown symbols or unsupported
round times produce no signal; never manufacture a zero-return prediction.

Predeclared strategy candidates on top of the accepted configuration:

- `timing05`: prevent new exposure when predicted 120s return is at least 0.5%
  against the proposed position. Allow reductions; a proposed flip may close
  existing exposure but cannot open the blocked side.
- `timing10`: same, at 1.0% against the proposed position.
- `drift1`: add predicted 120s price change once to the terminal fair value used
  for orders. Preserve the original fair for model diagnostics; do not accumulate
  the correction across calls.
- `accepted`: unchanged `aa51985` reference.

Do not apply either mechanism after the trusted exact-final gate. Keep 15s
rebalance cadence, 120 actions/minute, original order handling, residual floors,
carry rule and all other accepted parameters.

## Global Constraints

- Fit only seasons 1–450; select on 451–525; freeze one candidate before 526–600.
- Previously inspected verification seasons are reused confirmation data, not a fresh untouched holdout.
- Promote only if deep and thin mean PnL rise and thin p10 deteriorates less than 10%, on tune and verification.
- Choose by the existing tune score; do not promote a signal just because return RMSE improves.
- Preserve the live/account fixes and final-phase defaults from `aa51985`.
- Raw history and API keys remain untracked. No remote orders or deployment.
- Every experiment invocation reserves a fresh directory and records full parameters and source revision.
- A rejected strategy remains disabled; a larger claimed edge needs actual execution evidence.

## Review Focus

- Price samples just after a requested lag must not be used for that lag.
- Reconnects, round resets and gaps must not supply stale cross-round momentum.
- Entry gating must permit risk reduction and cap blocked position flips at zero.
- Fair adjustments must be applied once and leave model uncertainty unchanged.
- Fitting/sample boundaries must exclude later seasons and cross-round targets.

## Tasks

### Task 1: Causal price model and reproducible fitting

**Files:** Create `ctc/price_signal.py`, `scripts/fit_price_signal.py`, `ctc/price_signal.json`, `tests/test_price_signal.py`.

**Interfaces:** `PriceSignal(path=..., max_lag=120)` exposes `reset()`, `observe(t, prices)`, `predict(symbol, t, elapsed) -> float | None`. The artifact records training range, horizon, lags, feature normalization, phase boundary and coefficient arrays.

- [ ] Write failing tests with a synthetic linear-price sequence and known coefficients: exact lag lookup, no future sample, missing history, reset, invalid price, out-of-range elapsed time.
- [ ] Implement the history and predictor; run the tests.
- [ ] Implement the fit script using the fixed specification. Refuse training ranges above 450 and reserve a fresh output path.
- [ ] Fit the model, store the coefficients with provenance, and verify internal validation metrics reproduce the exploration.
- [ ] Commit model, fit script and evidence.

### Task 2: Strategy integration and bounded evaluation

**Files:** Modify `ctc/strategies.py`; create `tests/test_price_timing.py`, `scripts/experiment_price_timing.py`; modify launch/diagnostic commands only if promotion passes.

**Interfaces:** `FairValueTrader(..., price_gate=0.0, price_drift=0.0)` loads `PriceSignal` only when enabled, updates it with public quotes and resets it on round open. A pure target-filter helper may be used to enforce the reduction/flip behavior.

- [ ] Write failing behavioral tests for blocked additions, permitted reductions, blocked flips ending at zero, no signal compatibility, exact-final bypass and nonaccumulating fair adjustment.
- [ ] Implement disabled-by-default integration; run focused tests and full suite.
- [ ] Reproduce accepted tune PnL and evaluate the three predeclared alternatives on all 75 tune seasons, both regimes.
- [ ] If eligible, freeze the single best candidate, then confirm it against accepted on verification. Stress it at 2s latency and at refill 60s/quarter depth on tune.
- [ ] Promote defaults only if gates pass. Otherwise record rejection and continue from the next evidence-supported lead without searching verification.
- [ ] Get one fresh independent review, fix important findings with failing tests first, publish results and update PR.

## Progress and rulings

2026-10-23, Codex: clean checkout at `aa51985`; pulled feature branch. Remote
`derivatives-overlay` belongs to a separate track and is left untouched.
Ruling: preserve native execution and the existing feature branch; the user's
instruction to keep working supplies authorization for these bounded experiments.
Cost if wrong: time spent on a signal that may not survive fill costs; promotion
gates prevent it from replacing the accepted strategy without evidence.
