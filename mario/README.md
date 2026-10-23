# Mario Markets drill sheet (CTC 2026, 20% of the overall score)

Manual trading only (no bots). Four humans (A-D, identical characters and karts) and eight CPUs race; two series of four
races. Only humans have contracts. Points by overall place among all 12: 15 12 10 9 8 7 6 5 4 3 2 1.

## Contracts and settlement

| market | type | limit | settles |
|---|---|---|---|
| Race winner (4 per race) | binary | 100 | 100 for the best-placed human of that race (a CPU may finish ahead), 0 others |
| Series winner (4 per series) | binary | 200 | 100 for the highest series score; 50 each if tied for first; 0 others |
| #1 score, #2 score, top-2 total (3 per series) | numeric | 1000 | the top two human series scores and their sum |

Examples from the packet: scores 49/42/34/28 settle the winner at 100, #1 = 49, #2 = 42, top-2 = 91.
Scores 45/45/34/28: both leaders settle at 50, #1 = #2 = 45, top-2 = 90.

Race-winner contracts settle after each race; series contracts after race 4 and race 8. Anything unsettled trades.

## Pricer

```
python3 mario/pricer.py                       # interactive: "race 1 2 5 9" (overall places of A B C D), "fair", "undo"
python3 mario/pricer.py --races "1 2 5 9" "3 1 7 2"
python3 mario/pricer.py settle 49 42 34 28    # series settlement from cumulative scores
python3 mario/pricer.py points 2 1 5 9        # points of one race and the race-winner settlement
python3 mario/pricer.py calib                 # CPU prior sensitivity table
```

Model: performance = skill + noise per race; human skills share a flat prior (sd 1) and are updated from finishing
places with a particle filter; CPUs have a prior mean of -0.6 (humans usually finish top-5, #1 series score about 48,
which matches the packet's example). If after race 1 the humans are all behind several CPUs, rerun with
`--cpu-skill 0` or `+0.3`; if a human wins outright and the others are top-4, keep -0.6.

## Calibration (2026-10-23)

300 series simulated from the pricer's own model: race-winner Brier score 0.69 / 0.65 / 0.64 after 1 / 2 / 3 races (0.75 for
flat 25% quotes), series-winner Brier 0.50 / 0.34 / 0.21. Predicted race-winner probabilities of 0.15-0.25 came in at 0.22,
0.25-0.35 at 0.30, 0.35-0.50 at 0.40 and 0.50+ at 0.60: slightly over-confident on favourites, so shade a 55% quote to 50-52.
The likelihood temperature (the /8 in `_loglik`) changes the Brier by under 0.01 between 4 and 32.

## Trading rules of thumb

1. Before race 1 every race-winner contract is worth 25 and every series-winner contract 25: fade anything far from
   that unless you know the racers.
2. Race-winner markets are about the next race only: skill estimates from 1-2 races are weak (sd of the skill estimate
   is still about 0.6 after two races), so do not pay more than about 45 for a favourite after one win.
3. The series-winner market is where the information is: after two races a 6-9 point lead is about an 85% favourite and 10+ about 95% (table below).
4. #1 score and top-2 total are nearly linear in the leader's points: each race adds the leader's points; if the leader is
   averaging 13 per race, #1 settles near 52, and the sd of the remaining races is about 3 points per race left.
5. Position limits: 100 race / 200 series / 1000 score contracts. Size the numeric contracts by edge in points, not %.
6. Keep a written ledger of every race result; run `fair` after each race before quoting.

### Series winner probability of the leader, by lead after k races (equal-skill prior)

| races done | lead 0-2 | lead 3-5 | lead 6-9 | lead 10-14 | lead 15+ |
|---|---|---|---|---|---|
| 1 | 47% (n=7649) | 63% (n=23269) | 79% (n=8382) | 90% (n=700) | - |
| 2 | 50% (n=10847) | 67% (n=8637) | 85% (n=10618) | 95% (n=7772) | 99% (n=2126) |
| 3 | 49% (n=7067) | 70% (n=8157) | 91% (n=8825) | 99% (n=8155) | 100% (n=7796) |

The table assumes the four humans are equally skilled; after race 1 the pricer's skill update moves these numbers (a racer who won race 1 is also more likely to be better).

### Top-two score contracts at the start of a series (equal-skill prior, CPU prior -0.6)

| contract | mean | sd | p10 | p90 |
|---|---|---|---|---|
| #1 score | 48.0 | 7.4 | 38 | 57 |
| #2 score | 36.9 | 7.1 | 27 | 46 |
| top-2 total | 84.9 | 12.0 | 69 | 99 |

Maximum possible: #1 score 60, top-2 total 108 (15+12 per race). Minimum #1 score when four humans split evenly is about 30.

### CPU-strength calibration (what to check after race 1)

```
noise sd 1.0, human skill sd 1.0; per CPU-skill prior (mean, sd):
  cpu prior   P(human 1st overall)  median human place  mean pts/human/race  #1 series score mean (sd)  P(race-winner mkt | equal skill)
  (-0.6, 0.5)     65%                 5                  8.1               47.9 (7.4)              25% by symmetry
  (-0.3, 0.5)     55%                 6                  7.6               45.8 (8.1)              25% by symmetry
  (+0.0, 0.5)     45%                 7                  6.9               43.2 (8.8)              25% by symmetry
  (+0.3, 0.5)     35%                 7                  6.3               40.3 (9.2)              25% by symmetry
  (+0.6, 0.5)     27%                 8                  5.7               37.5 (9.5)              25% by symmetry
  (+0.0, 1.0)     33%                 7                  6.8               41.4 (8.6)              25% by symmetry
```
