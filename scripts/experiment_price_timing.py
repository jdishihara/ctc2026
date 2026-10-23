"""Predeclared price-timing candidates against the accepted aa51985 strategy.

    python scripts/experiment_price_timing.py --out out/price-tune-fresh

Fit only 1–450. Select on 451–525. For confirmation, supply --split verify
--configs baseline,<frozen-candidate>. Severe liquidity is a separate --regimes
severe run after the candidate has been frozen.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.experiment_execution import main

ACCEPTED = dict(final_exact=True, final_edge=.005, final_edge_full=.005)
CONFIGS = {'baseline': ACCEPTED,
           'timing05': {**ACCEPTED, 'price_gate': .005},
           'timing10': {**ACCEPTED, 'price_gate': .01},
           'drift1': {**ACCEPTED, 'price_drift': 1.0}}
REGIMES = {'deep': (10., 1.), 'thin': (30., .5), 'severe': (60., .25)}


if __name__ == '__main__':
    main(CONFIGS, REGIMES)
