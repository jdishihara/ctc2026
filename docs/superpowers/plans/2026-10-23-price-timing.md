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

- [x] Write failing tests with a synthetic linear-price sequence and known coefficients: exact lag lookup, no future sample, missing history, reset, invalid price, out-of-range elapsed time.
- [x] Implement the history and predictor; run the tests.
- [x] Implement the fit script using the fixed specification. Refuse training ranges above 450 and reserve a fresh output path.
- [x] Fit the model, store the coefficients with provenance, and verify internal validation metrics reproduce the exploration.
- [x] Commit model, fit script and evidence.

### Task 2: Strategy integration and bounded evaluation

**Files:** Modify `ctc/strategies.py`; create `tests/test_price_timing.py`, `scripts/experiment_price_timing.py`; modify launch/diagnostic commands only if promotion passes.

**Interfaces:** `FairValueTrader(..., price_gate=0.0, price_drift=0.0)` loads `PriceSignal` only when enabled, updates it with public quotes and resets it on round open. A pure target-filter helper may be used to enforce the reduction/flip behavior.

- [x] Write failing behavioral tests for blocked additions, permitted reductions, blocked flips ending at zero, no signal compatibility, exact-final bypass and nonaccumulating fair adjustment.
- [x] Implement disabled-by-default integration; run focused tests and full suite.
- [x] Reproduce accepted tune PnL and evaluate the three predeclared alternatives on all 75 tune seasons, both regimes.
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

2026-10-23, Codex: implementation `693cd17`; full suite 121 passed. Task 1
complete. Task 2 integration was committed with Task 1 because the runtime
model and its disabled strategy consumer share the new tests; no work repeated.
Tune baseline exactly reproduced `aa51985` in both regimes. Outcomes:

| Candidate | Deep mean | Thin mean | Thin p10 | Tune score | Decision |
|---|---:|---:|---:|---:|---|
| baseline | 8643.98 | 5176.69 | -3729.45 | 5045.61 | Reference |
| timing05 | 8750.20 | 5378.12 | -3595.89 | 5266.22 | Freeze |
| timing10 | 8811.26 | 5358.49 | -3694.88 | 5237.44 | Lower eligible score |
| drift1 | 8838.25 | 5306.73 | -5661.16 | 4241.91 | Reject: thin tail |

Ruling: freeze `timing05` (`price_gate=0.005`, `price_drift=0`) before any
price-model verification run. It has the highest predeclared eligible tune
score; all other accepted parameters remain fixed. Confirmation is baseline
versus this candidate only. Stress uses the same pair on all tune seasons at
2s latency, and separately refill 60s / depth 0.25 / normal 0.25s latency.
Source outputs: `out/price-timing-tune/`, revision `693cd17`, clean tree.

2026-10-23, Codex: `timing05` REJECTED for promotion. Confirmation means
fell 9452.36 -> 9277.55 (deep) and 5993.53 -> 5968.32 (thin). Thin p10
improved -2712.92 -> -1969.59, but that does not override the required mean
gates. Severe tune liquidity improved 1671.82 -> 1978.33; also insufficient
to override the gate. Leave `price_gate=0` and `price_drift=0` in launch defaults.
Do not inspect another price candidate on verification.

### Task 3: Internal validation of recent storm observations

**Hypothesis:** Equal weighting of the entire observed path overweights stale
trajectory errors after a storm turns. Exponentially decay position mismatch
with observation age, retaining the same latest cone and advisory likelihoods.

**Screen before implementation:** Build an analog library only from seasons
1–300; evaluate seasons 301–450. Compare equal weights and half-lives 60/120/240s
at storm ages 30/90/150/240/360. Primary screen is 120s-ahead position RMSE;
require at least 5% improvement and no increase in aggregate end-damage RMSE.
Damage parameters were already fit on 1–450, so damage error is a shared
secondary screen, not an independent held-out calibration claim.

- [ ] Run this bounded internal screen and record every candidate.
- [ ] If any pass, implement optional decayed position error with cache/reset
  tests observed RED then GREEN. Equal-weight default must be unchanged.
- [ ] Compare at most the two best eligible internal candidates on all tune
  seasons against `aa51985`, using the same PnL gates and fixed score. Price
  timing stays disabled. Freeze one winner before confirmation; never tune
  half-life on verification.
- [ ] Promote only after the frozen winner passes confirmation and the same
  latency/liquidity stresses. Otherwise retain accepted defaults and publish
  the negative evidence. Include this task in the single final branch review.

Ruling: continue with an independently motivated storm-forecast experiment
after the failed price candidate, as the user requested continued competitive
improvement. Cost if wrong is bounded computation and research time; the
accepted launch strategy remains protected by the same promotion gates.

2026-10-23, Codex: Recency screen rejected all three half-lives. Baseline
120s position / damage RMSE = 96.809 / 7.3025. Half-lives 60, 120, 240 give
92.007 / 7.3207, 95.087 / 7.3133, 98.029 / 7.3081. No candidate satisfies
both criteria; no runtime recency feature or tune/verification run is justified.

### Task 4: Direct forecast-cone centering

**Hypothesis:** Cone likelihoods cannot move the available analog paths toward
the more accurate official position forecast. Centering the projected ensemble
can correct that mismatch while preserving its dispersion and strength paths.

Use the same 1–300 library / 301–450 internal screen, ages and gates as Task 3.
Compare centering fractions 0.5 and 1.0 against zero. At each future cone age,
translate every selected path by the fraction times (cone position minus
weighted ensemble position). Linearly interpolate these offsets from zero at
the current observation through future cone points; fade to zero over 60s after
the last future cone point. Never use expired cone points. Preserve analog
weights, radius/intensity, uncertainty floors and all trading settings.

- [ ] Screen both fixed fractions; no runtime change unless eligible.
- [ ] If eligible, implement with causal/no-cone/cache tests first, run the
  eligible candidates on tune, freeze the best under the same gates, and
  confirm/stress only that frozen candidate. Otherwise record rejection.
- [ ] Finish with one independent review of the whole continuation and publish
  all results, including rejected hypotheses; no claim of guaranteed wins.

Ruling: the recency screen supports looking beyond path weighting; the packet
supplies official future cones as a distinct information source. Test direct
centering using the same predeclared screen and PnL gates. Cost if wrong is one
bounded internal experiment; no live defaults change merely for forecast skill.

2026-10-23, Codex: Both cone fractions passed the internal screen. Baseline
120s position / damage RMSE 96.809 / 7.3025; centering 0.5 gives 86.951 /
7.2202, centering 1.0 gives 82.307 / 7.2140. Evaluate exactly those two on
tune. Production implementation passes scalar exposure, unchanged dispersion,
expired/missing cone, zero-fraction parity, fade-out and library immutability
tests. No launch defaults changed.

Three additional failing tests reproduced defects in the rejected price model's
optional live path: mistaking reconnect for a round boundary, renewing a stale
symbol from other symbols' traffic, and renewing it from cached midpoints.
Fixed with an explicit unknown clock until storm age arrives, per-symbol
freshness, and observed quote timestamps. A storm-age test confirms reanchoring.
These are correctness fixes, not a reason to revisit the rejected PnL decision.
