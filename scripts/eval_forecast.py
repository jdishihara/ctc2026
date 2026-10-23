"""Forecast skill on holdout storms: error of predicted end-of-storm company damage at several ages,
constant-velocity projection vs analog ensemble. Also pattern-posterior accuracy."""
import json, sys, numpy as np
from pathlib import Path
sys.path.insert(0, '.')
from ctc.valuation import SeasonModel
from ctc.analog import AnalogEnsemble
from ctc.wind import PHYS
root=Path('data'); case=json.load(open(root/'case.json')); man=json.load(open(root/'history/manifest.json'))
AGES=[30,90,150,240,360]
args=dict(sigma=float(sys.argv[1]) if len(sys.argv)>1 else 25.0, k=int(sys.argv[2]) if len(sys.argv)>2 else 50, shift=(sys.argv[3]!='noshift') if len(sys.argv)>3 else True, cone_w=float(sys.argv[4]) if len(sys.argv)>4 else 0.0, isl_w=float(sys.argv[5]) if len(sys.argv)>5 else 0.0, cone_s0=float(sys.argv[6]) if len(sys.argv)>6 else 10.0)
err={('cv',a):[] for a in AGES}; err.update({('an',a):[] for a in AGES}); hit={a:[] for a in AGES}; sdcal={a:[] for a in AGES}
for s in man['seasons'][450:530]:
    feed=[json.loads(l) for l in open(root/'history'/s['dir']/'feed.jsonl')]
    md=SeasonModel(case); md.ensemble=AnalogEnsemble(case, **args)
    for st in s['storms']:
        truth=np.array([st['damage_pct'][k] for k in PHYS])
        for m in feed:
            if m['round']!=st['round']: continue
            md.on_message(m)
            if m['type']=='storm' and m['age'] in AGES:
                a=m['age']
                base={k: md.states[k].cum_damage() for k in PHYS}
                cv,_=md.current_storm_damage(case['timing']['storm'])
                err[('cv',a)].append(np.array([cv[k] for k in PHYS])-truth)
                w=md.ensemble.weights(md.obs, md.official, md.wire, md.adv); E,O,sel=md.ensemble.future_exposure(md.obs,w)
                preds=np.array([[md.states[k].storm_damage(list(E[k][i])) for k in PHYS] for i in range(len(sel))])
                mean=(w[sel][:,None]*preds).sum(0); sd=np.sqrt((w[sel][:,None]*(preds-mean)**2).sum(0))
                err[('an',a)].append(mean-truth); sdcal[a].append((np.abs(mean-truth)/(sd+1e-6)))
                post=md.ensemble.pattern_posterior(w); flip=st['turned_erratic_at']
                tr='erratic' if flip is not None and a>=flip else st['pattern']
                hit[a].append(max(post,key=post.get)==tr)
print(f'analog params {args}; holdout storms {len(hit[30])}')
print('age | RMSE constant-velocity | RMSE analog ensemble (per company, damage points) | pattern top-1 acc | |err|/sd median')
for a in AGES:
    cv=np.sqrt((np.array(err[('cv',a)])**2).mean(0)); an=np.sqrt((np.array(err[('an',a)])**2).mean(0))
    print(f'{a:3d} | '+' '.join(f'{v:5.1f}' for v in cv)+' | '+' '.join(f'{v:5.1f}' for v in an)+f' | {np.mean(hit[a]):.0%} | {np.median(np.concatenate(sdcal[a])):.2f}')
