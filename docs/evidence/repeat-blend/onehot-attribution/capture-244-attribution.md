# Closed capture 244: accounting and loss-stop attribution

This audit uses the existing independent traces for the frozen baseline and
one-hot candidate at commit `357d9986babf2b21bd3bbdcc2e69550059f16154`.
It runs no strategy, reads no new history, and changes no runtime source.
Both compared settings use 0.25-second RTT and basket enabled. All four runs
make **zero conversions**, finish **verified flat**, and have no fills after
the final receipt. Fill cash reconciles to every terminal result and symbol's
realized P&L. Every producer result field matches the independent result.

Reproducible inputs, hashes, exact timestamps and per-symbol calculations are
in [capture-244-attribution.json](capture-244-attribution.json), produced by
[attribute-capture-244.py](attribute-capture-244.py). This is a selected adverse
capture from the previously evaluated grid, not new performance evidence.

## Observed loss and liquidation

Dollar amounts below are modeled account P&L. Position-response marks belong
to the request's **execution time**, which precedes response observation.
The first cleanup snapshot is 0.875 seconds after cleanup starts; no fills
occur between the last pre-cleanup snapshot and that first cleanup snapshot.

| Variant / depth | Loss-trigger snapshot | Last pre-cleanup snapshot | First cleanup snapshot | Flat cash P&L | First cleanup mark → flat | Cleanup duration |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline / full | −256.260 | −256.860 | −244.110 | −261.000 | −16.890 | 45 s |
| Baseline / half | −257.700 | −258.300 | −245.550 | −303.340 | −57.790 | 45 s |
| Candidate / full | −256.720 | −256.720 | −267.285 | −475.830 | −208.545 | 54 s |
| Candidate / half | −268.940 | −268.940 | −279.505 | −514.880 | −235.375 | 54 s |

The candidate primary stops in round 1 at latest observed storm age 76;
baseline stops at age 274. The $250 trigger is not a bound on final loss.
These mark-to-flat changes combine intervening prices, spread, partial fills
and serialized HTTP actions; they are **not pure execution slippage** or a
measured causal effect of cleanup.

| Variant / depth | Pre-cleanup fill cash | First cleanup inventory mark | Cleanup fill cash | Entry / cleanup fills |
| --- | ---: | ---: | ---: | ---: |
| Baseline / full | 7,526.320 | −7,770.430 | −7,787.320 | 7 / 8 |
| Baseline / half | 7,524.880 | −7,770.430 | −7,828.220 | 10 / 14 |
| Candidate / full | −2,249.060 | 1,981.775 | 1,773.230 | 9 / 12 |
| Candidate / half | −2,261.280 | 1,981.775 | 1,746.400 | 15 / 16 |

For each row: pre-cleanup cash + inventory mark = first cleanup P&L;
pre-cleanup cash + cleanup fill cash = final flat P&L.

### Exposure and symbol contributions

Signed quantity is the position at the first cleanup snapshot. Each variant
has identical quantities across full and half depth. The candidate has six
positions at its 10%-scaled symbol caps: PORT, AQUA, GRID, FERRY, RECON, HAVEN.
All entry fills add the indicated exposure; all cleanup fills reduce it to zero.

| Symbol | Baseline qty | Candidate qty | Baseline full P&L | Candidate full P&L | Candidate half P&L |
| --- | ---: | ---: | ---: | ---: | ---: |
| PORT | −20 | −20 | −18.60 | −160.50 | −168.85 |
| ISLE | −30 | 8 | −73.14 | −1.92 | −1.92 |
| AQUA | −50 | 50 | −95.10 | −4.14 | −12.12 |
| GRID | −40 | −40 | −61.60 | −72.70 | −74.64 |
| FERRY | 2 | 80 | 0.84 | 14.68 | −1.60 |
| RECON | 0 | 50 | 0.00 | −87.50 | −87.50 |
| HAVEN | 0 | −25 | 0.00 | −163.75 | −168.25 |
| REIN | −20 | 0 | −13.40 | 0.00 | 0.00 |
| **Total** | | | **−261.00** | **−475.83** | **−514.88** |

MAT, GEN, ARCH and REBLD have no fills. Candidate PORT/HAVEN/RECON contribute
−$411.75 of the primary's −$475.83. Relative to baseline, candidate primary
loses another $214.83, despite favorable differences in AQUA and ISLE.

Cleanup visits symbols in a fixed sequence and waits for reconciled orders
and account checks. Candidate primary PORT begins filling at cleanup +5.625 s;
RECON closes at +41.125 s; HAVEN closes between +46.125 and +46.635 s.
GRID partially fills, is canceled and is replaced before later legs close.
From the first cleanup snapshot to flat, HAVEN loses another $108.125, RECON
$71.00 and PORT $25.30. These three changes total −$204.425 of the −$208.545
aggregate change. All recorded cleanup fills reduce exposure, and cash and
positions reconcile without unexplained adjustments.

Half depth has the same candidate holdings and snapshot midpoints as full
depth, but its final result is $39.05 worse: $12.22 less favorable entry cash
and $26.83 less favorable cleanup cash. This is a fill-cash decomposition;
different partial-fill times prevent labeling all of it spread cost.

## Ex-post payoff diagnostic — no further trading

The **already-audited closed input** `244.json` contains the official receipt
for CID `2cf67e88-9081-4258-aa6a-3648c41925de`, year 1783. Its SHA256 is
`99226507701f6ba1b368d9e3190245195cb1bc0048fb2ddd5120682d10080b91`, exactly as
recorded in the frozen specification. Both receipt clocks are ready and agree;
the receipt reports contiguous news 0–870 and all three final reports.

This calculation freezes the first cleanup quantities, allows **no further
trading**, and substitutes terminal settlement prices for contemporaneous
midpoints. It is an ex-post valuation, **not a realizable alternative policy**,
not actual profit, and not a measured saving obtainable by avoiding cleanup.

| Variant / depth | Inventory at contemporary mark | Inventory at terminal payoff | Pre-cleanup cash + terminal payoff | Change from first cleanup P&L |
| --- | ---: | ---: | ---: | ---: |
| Baseline / full | −7,770.430 | −7,402.900 | 123.420 | 367.530 |
| Baseline / half | −7,770.430 | −7,402.900 | 121.980 | 367.530 |
| Candidate / full | 1,981.775 | 3,867.350 | 1,618.290 | 1,885.575 |
| Candidate / half | 1,981.775 | 3,867.350 | 1,606.070 | 1,885.575 |

Every candidate symbol's entry cash plus eventual payoff is positive on this
path. In the primary: PORT +$427.60, ISLE +$55.76, AQUA +$295.60, GRID +$169.20,
FERRY +$77.88, RECON +$203.50 and HAVEN +$388.75. Thus these traces do not
support calling the candidate loss a wrong eventual payoff direction. They
show favorable eventual payoff exposure subjected to adverse interim marks,
a loss stop, and liquidation. They do not establish that holding through the
interim risk was feasible, that forecasts were calibrated, or that removing
the stop would improve an implementable policy.

## Model / risk interaction and one testable hypothesis

The recognizer reports 11 matches to row 729 at ages 42–62. In the frozen
source, a match sets the current-storm analog weights to one-hot
(`ctc/analog.py:218–225`). This changes the fair mean, analog dispersion and
pattern entropy together. In-storm `fair_sd` combines current analog
dispersion and model residual uncertainty, while future-storm `future_sd`
is calculated separately (`ctc/valuation.py:401–409`). The strategy uses
`fair_sd` in its entry floor and pattern entropy in an add-exposure guard
(`ctc/strategies.py:210–218,360–364`). Six capped candidate positions are an
observed consequence of the complete candidate policy, not proof that any
one of these channels caused the loss.

The candidate's cached forecast at age 76 and baseline's at age 274 are
**not a same-time ablation**. Exact recognition of one weather trajectory
also does not eliminate later storms, valuation residuals or interim price
and liquidation risk.

**Untested offline hypothesis:** retaining a future-storm uncertainty floor
during a recognized current storm may reduce early exposure concentration
and loss-stop liquidation while preserving the one-hot fair mean. A narrow
ablation would add the already-computed `future_sd` in quadrature to the
in-storm entry uncertainty with one predeclared fixed weight, leaving the
mean, entropy rule, caps, loss stop and cleanup unchanged. Assess the complete
frozen grid, stop incidence and flat/attention outcomes; improvement on these
reused captures would still require later independent validation. This audit
does not recommend production activation or changing the risk-rule rejection.

## Reproduce the accounting

```sh
python3 docs/evidence/repeat-prefix/attribute-capture-244.py \
  --baseline /var/folders/5_/4_9w4ch971l2mm9c6fqtg5400000gn/T/repeat-prefix-independent-baseline-ihx0dkmp \
  --candidate /var/folders/5_/4_9w4ch971l2mm9c6fqtg5400000gn/T/repeat-prefix-independent-candidate-tvc8zp_t \
  --producer /Users/arjunhans/Documents/ctc2026/out/repeat-prefix-v1-20261024 \
  --closed-capture /var/folders/5_/4_9w4ch971l2mm9c6fqtg5400000gn/T/practice-independent-audit-471iu5fj/244.json \
  --out docs/evidence/repeat-prefix/capture-244-attribution.json
```
