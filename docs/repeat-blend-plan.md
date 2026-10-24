# Fixed half-weight recognition experiment

Declared 2026-10-24 09:30 UTC, before implementation or alternative performance
evaluation. Author: Codex, Arjun's systematic-equities workstream.

## Hypothesis

The frozen one-hot recognizer at `357d9986` improves mean capture P&L but fails
its declared risk rules: worse worst loss, more negative settings, new cleanup
attention outcomes and increased residual exposure. It remains rejected.
The capture-244 primary stops much earlier in round 1. Recognizing the weather
does not remove uncertainty about the rest of the season, company valuation,
market prices, or a future departure from a shared historical prefix.

Test exactly one alternative: when the unchanged complete-prefix recognizer
finds a unique row, use **0.5 ordinary ensemble weights + 0.5 one-hot weights**.
The coefficient is fixed before evaluation; do not search other strengths.
The existing ensemble supplies residual forecast dispersion. This is a model-
averaging hypothesis, not a claim that the coefficient is optimal or that the
two components are independent probability models.

Add an explicit `repeat_weight` parameter to `AnalogEnsemble` with default 1.0
to preserve the frozen one-hot experiment's semantics. Keep recognition itself
disabled by default. Validate finite numeric weights in [0,1]; zero must return
the ordinary result exactly. The new comparison explicitly passes 0.5. All
matching criteria and ordinary-cache updates remain unchanged. Preserve exact
one-hot behavior at weight 1 and exact ordinary fallback on unmatched input.
Only `ctc/analog.py` changes among runtime files.

## Verification and fixed inputs

- Write failing tests for the convex combination, zero/one endpoints, invalid
  weights, default disabled behavior and unmatched fallback before implementation.
- Run the full suite and obtain independent review of the delta and both new
  drivers before freezing their source and running performance.
- Copy the already-verified 96-setting spec from
  `out/repeat-prefix-v1-20261024/spec.json` byte-for-byte. Use closed captures
  241–246 at RTT 0/0.05/0.25/1 second, full/half depth, basket off/on, 10% limits,
  90 actions/minute, $250 observed-loss trigger and zero prior P&L.
- Baseline remains `cd3eb23`, including the original cleanup ordering. Reproduce
  all 96 archived baseline results and all seven journals before the alternative.
  Retain full outcomes, profiles, source/input hashes and all existing guards.
- Separately repeat all 75 development pairs, seasons 451–525 only, with 10%
  limits, 0.25-second delay, half-size ladder and 30-second refill. Independently
  checked prior evidence found no matching prefixes in these 225 storms. The
  repeat checks parameter plumbing and exact fallback; it is not a new holdout.
- No active capture 247+, downloaded future outcomes, credentials or network.
  Neither the existing training library nor any frozen forward evaluator changes.

## Decision

Use the same rules as v1, compared with the original baseline: reject for any
guard failure, changed unmatched behavior, new cleanup attention outcomes,
increased residual exposure, increased negative-setting count, worse worst
terminal result, lower mean P&L, development P&L regression, or unexplained
development prefix activation followed by divergence. Explain every individual
regression even if the aggregate gates pass. Require independent result review
before considering an optional integration; this experiment places no orders.

These are reused, correlated execution settings on known training weather.
No improvement establishes unseen-weather skill, consistent live profits or
winning odds. Account ownership is still unresolved. Production stays unchanged.
