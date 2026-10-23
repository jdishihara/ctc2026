"""One predeclared basket candidate sized to half the displayed executable depth."""
from experiment_execution import main

ACCEPTED = dict(final_exact=True, final_edge=.005, final_edge_full=.005)
CONFIGS = {'baseline': ACCEPTED,
           'basket_depth': {**ACCEPTED, 'basket_edge': .01, 'basket_participation': .5}}
REGIMES = {'deep': (10.0, 1.0), 'thin': (30.0, .5), 'severe': (60.0, .25)}

if __name__ == '__main__':
    main(CONFIGS, REGIMES)
