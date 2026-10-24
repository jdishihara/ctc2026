# Recognizing repeated training-weather prefixes

Declared 2026-10-24 09:10 UTC before implementation or candidate performance
evaluation. Author: Codex, Arjun's systematic-equities workstream.

## Hypothesis and scope

Closed captures 241–246 contain weather tracks exactly present in the existing
fitted library. The current broad analog kernel still blends many different
tracks. An optional recognizer may improve forecasts when the received weather
prefix uniquely identifies a historical track. This is explicitly a strategy
for repeated training weather, not evidence about unfamiliar weather or an
assumption that a matching prefix guarantees an identical future.

Add `repeat_prefix=False` to `AnalogEnsemble`. When enabled, require every
received age from 0 through the current age, in ascending two-second steps,
with at least 21 points (current age at least 40). All four values x, y, radius
and intensity must be finite numeric values and exactly equal to exactly one
library row over the entire observed prefix. Only then replace the ordinary
weights with a one-hot weight on that row. No tolerance or threshold search.
Zero matches, multiple matches, missing ages, duplicate ages, corrections or
invalid strength fields retain the ordinary weights. A later divergence
immediately restores the ordinary forecast. The ordinary weight cache must
remain current even while recognition is active.

Matching reads only library columns at or before the newest observed age.
Historical continuation remains a forecast, as in the existing analog model.
No downloaded current/future-season outcome, active capture 247+, credential or
network access is permitted. Existing training library bytes remain unchanged.
The option stays disabled by default. Production and the three frozen forward
evaluators stay unchanged throughout this experiment.

## Preflight and verification

- Write failing tests first: activation boundary, all four channels, ambiguity,
  incomplete/duplicate/off-grid prefixes, corrections, truncation, new storms,
  divergence and recovery, exact fallback, disabled behavior, and independence
  of selection from unobserved library suffixes.
- Maintain incremental matching without retaining mutable feed references.
- Preserve every execution guard, strategy parameter and risk limit. The only
  runtime file changed is `ctc/analog.py`.
- Independently review implementation and guarded comparison driver; commit
  their exact source before candidate performance evaluation.

## Fixed evaluation

Use all six already-closed captures 241–246, all 16 settings each: RTT
0/0.05/0.25/1 second, full/half displayed depth, basket off/on, 10% limits,
90 actions/minute, $250 observed-loss trigger, zero prior P&L. Primary stays
0.25 second/full depth/basket on. Preserve every result and stop/attention state.
Use the existing cached 241–245 specification and sealed capture-246 inputs,
binding all bytes to their completed supervised archives. Reproduce all 96
baseline results and all seven journals per run before starting the candidate.
Candidate differs only by enabling the recognizer; performance is allowed to
change before cleanup. Retain complete trace hashes, journals, source hashes,
and guarded settlement/history/identity checks. Network and downloaded-history
access are forbidden within this capture comparison.

Separately inspect only development seasons 451–525 (225 storms) for prefix
activations and later divergence. Do not read 526–600 or an active season.
Compare baseline/candidate on all 75 development seasons at one fixed setting:
10% limits, 0.25-second delay and thin liquidity. This is reused development
data, not an untouched holdout. Report unmatched behavior and any false match.
Use synthetic shared-prefix/divergent-suffix tests even if no development
prefixes match. No timing, threshold, or split selection after results.

## Decision rule

Reject promotion for any guard failure, changed fallback behavior on unmatched
storms, new residual/attention outcomes, more losing settings, worse worst
terminal result, or lower mean terminal P&L in the 96-setting capture grid.
Also reject for a development P&L regression or an unexplained false-match
activation. Explain individual regressions even if aggregate gates pass.
Passing these checks allows consideration of an explicitly optional repeated-
weather mode after independent review; it does not justify silently enabling
the mode in production, changing the frozen forward runs, or claiming a live
profitability guarantee. Account exclusivity remains unresolved.
