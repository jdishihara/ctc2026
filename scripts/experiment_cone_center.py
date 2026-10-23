"""Predeclared cone centering experiments selected by training-only forecast skill."""
from experiment_execution import main

ACCEPTED = dict(final_exact=True, final_edge=.005, final_edge_full=.005)
CONFIGS = {'baseline': ACCEPTED,
           'center05': {**ACCEPTED, 'cone_center': .5},
           'center1': {**ACCEPTED, 'cone_center': 1.0}}
REGIMES = {'deep': (10.0, 1.0), 'thin': (30.0, .5), 'severe': (60.0, .25)}

if __name__ == '__main__':
    main(CONFIGS, REGIMES)
