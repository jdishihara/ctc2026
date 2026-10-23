"""Two fixed basket thresholds on top of the accepted fundamental strategy."""
from experiment_execution import main

ACCEPTED = dict(final_exact=True, final_edge=.005, final_edge_full=.005)
CONFIGS = {'baseline': ACCEPTED,
           'basket05': {**ACCEPTED, 'basket_edge': .005},
           'basket10': {**ACCEPTED, 'basket_edge': .01}}
REGIMES = {'deep': (10.0, 1.0), 'thin': (30.0, .5), 'severe': (60.0, .25)}

if __name__ == '__main__':
    main(CONFIGS, REGIMES)
