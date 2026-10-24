# Recorded practice storms overlap model training

Discovered and checked on 2026-10-24 at approximately 08:53 UTC, after captures
241–245 had closed. This changes the interpretation of the practice evidence.
Later closed-capture checks extend the overlap to all 27 complete tracks in
captures 241–249; their separate evidence is linked below.

## Finding

Every one of the 15 complete storm tracks in captures 241–245 exactly matches
one row in the fitted analog library. Equality holds at every observed age
0, 2, …, 480 for all four variables: x, y, radius and intensity. Maximum
absolute error and full-track RMSE are both exactly zero.

| Closed capture | Storms checked | Observations per storm | Exact matching library rows, zero-based |
| --- | ---: | ---: | --- |
| 241 | 3 | 241 | 720, 721, 722 |
| 242 | 3 | 241 | 723, 724, 725 |
| 243 | 3 | 241 | 726, 727, 728 |
| 244 | 3 | 241 | 729, 730, 731 |
| 245 | 3 | 241 | 732, 733, 734 |

The fitted artifact has 1,350 tracks, each with 241 observations and four
variables. The library builder appends the storms from the selected training
seasons; its training entry point selects the first 450 seasons. The exact
row positions above also match that ordering. This is direct weather-training
overlap, beyond the previously disclosed reuse of captures for diagnostics.

Source lineage: `scripts/build_library.py:6` selects the first 450 manifest
entries; `ctc/analog.py:42–54` appends their storms in order. The NPZ does not
retain season IDs, and this audit does not rebuild all 450 seasons from the
downloaded manifest. The numerical overlap finding is independent of that
unreconstructed ID mapping. The model's forecast consumes these tracks'
future suffixes (`ctc/analog.py:191`), so matching a complete track is relevant
to forecasting validation.

The same library bytes are present at its introduction commit `51d48f` and
the frozen runtime `cd3eb2`. Freezing a later execution source does not remove
the earlier fitted-weather overlap.

Library SHA-256:
`22694387c3b612f5c20853feb9143e1bf8b8f5722a845da8ed584ab1b30bdf09`.

## What changes in the interpretation

- A source version can be frozen before a market interval is recorded while
  its forecasting model already contains that interval's weather track.
  “Forward” or “prospective” timing labels therefore describe chronology only;
  these captures do not validate generalization to unfamiliar storms.
- The +$141.16 official completed live receipt remains an actual attributed
  account result. It is one small-size season whose weather overlaps training.
  It does not establish consistent profitability on new competition weather.
- Recorded replays still test the implemented client, request timing,
  reconciliation, risk triggers and cleanup under the stated fill assumptions.
  Paired execution comparisons remain useful on these specific paths.
- Weather equality does not establish identical advisories, market quotes,
  queue conditions, other traders, or fills. No such equality is claimed.
- This audit does not change historical development/confirmation P&L, but
  those datasets have also been used repeatedly for tuning or confirmation.
  Neither those reused results nor the overlapping practice captures establish
  an untouched end-to-end competition result or a win probability.

The frozen evaluations continue unchanged so their chronology and adverse
outcomes remain auditable. Later captures must not be described as unseen
weather merely because they close after a source freeze. Any overlap check
for a later capture must wait for its official closing receipt.

## Verification and scope

The retained audit reads only the existing fitted model and the sealed cached
inputs for closed captures 241–245. All five input hashes match the immutable
comparison specification. Every capture has a matching ready-state official
receipt following its selected frames; the observed captures also have a
matching ending clock. Each round contains every required storm age with no
conflicting repeated observations.

The audit records its script, model, specification and five input hashes and
verifies them again at completion. No source changes, network/credential
access, downloaded-history reads, active-season outcomes, retraining, live
orders or alternative performance runs are involved.

Root audit: [audit.json](evidence/training-overlap/audit.json).
Reproduction script: [audit_analog_overlap.py](../scripts/audit_analog_overlap.py).
Independent verification and source-lineage evidence:
[retained review archive](evidence/training-overlap/independent-review.tar.gz).
The input copies remain under
`out/cleanup-quotes-v1-20261024/inputs/` locally, with hashes in the specification.

```bash
.venv/bin/python scripts/audit_analog_overlap.py \
  --spec out/cleanup-quotes-v1-20261024/spec.json \
  --inputs out/cleanup-quotes-v1-20261024/inputs \
  --library ctc/analog_library.npz \
  --out out/training-overlap-reproduction
```

## Later closed-capture checks

These checks use each capture's official closure and sealed recorded inputs.
They do not inspect active seasons or rebuild the downloaded history. Every
listed match covers all 241 observations in all four weather channels, with
zero error. The original 15-track audit above remains unchanged.

| Closed capture | Exact fitted rows, zero-based | Separate audit and evidence |
| --- | --- | --- |
| 246 | 735, 736, 737 | [Capture 246](observed-season-246.md) |
| 247 | 738, 739, 740 | [Capture 247](observed-season-247.md) |
| 248 | 741, 742, 743 | [Capture 248](observed-season-248.md) |
| 249 | 744, 745, 746 | [Capture 249](observed-season-249.md) |

These 27 complete matches support execution diagnostics on familiar weather;
they do not establish consistent profit on unfamiliar competition storms.
