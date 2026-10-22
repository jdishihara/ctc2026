"""Residual sd of the valuation per symbol on holdout seasons (exact end-of-season state), written to valuation_params.json.
Also tests a per-storm diminishing-returns form for the rebuilders."""
import json, sys, numpy as np
from pathlib import Path
from scipy.optimize import least_squares
sys.path.insert(0, '.')
from ctc.valuation import SeasonModel, SYMS, values, P
from ctc.wind import PHYS
root=Path('data'); case=json.load(open(root/'case.json')); man=json.load(open(root/'history/manifest.json'))
res={s:[] for s in SYMS}; feats=[]
for s in man['seasons']:
    md=SeasonModel(case)
    for line in open(root/'history'/s['dir']/'feed.jsonl'):
        md.on_message(json.loads(line))
    sett=json.load(open(root/'history'/s['dir']/'settlement.json'))
    f=md.fair(project=False)
    for k in SYMS: res[k].append(f[k]-sett[k])
    feats.append((s, sett))
n=len(man['seasons']); te=slice(450,n)
sd={}
for k in SYMS:
    r=np.array(res[k]); sd[k]=float(r[te].std())
    print(f'{k:6s} end-of-season valuation residual: mean {r[te].mean():+.2f} sd {r[te].std():.2f} maxabs {np.abs(r[te]).max():.2f}')
# rebuilder refinement: per-storm saturation
print('\n-- rebuilders, per-storm saturation: settle = base + sum_storms A*(1-exp(-D_storm/s)) --')
for k,fn in [('RECON',lambda d: d['PORT']+d['GRID']+d['FERRY']),('MAT',lambda d: sum(d.values())),('GEN',lambda d: d['GRID'])]:
    D=np.array([[fn(st['damage_pct']) for st in s['storms']] for s,_ in feats]); y=np.array([sett[k] for _,sett in feats])
    f=lambda p,D: p[0]+(p[1]*(1-np.exp(-D/p[2]))).sum(1)
    r=least_squares(lambda p: f(p,D[:450])-y[:450], x0=[30,10,50], bounds=([0,0,1],[100,100,1000]))
    pred=f(r.x,D[te]); r2=1-((pred-y[te])**2).sum()/((y[te]-y[te].mean())**2).sum()
    print(f'{k}: base {r.x[0]:.2f} A {r.x[1]:.2f} s {r.x[2]:.1f}  test R2 {r2:.3f} resid sd {np.std(pred-y[te]):.2f}  (season-cum form sd {sd[k]:.2f})')
    if np.std(pred-y[te]) < sd[k]*0.9 and k!='GEN':
        P[k]=dict(kind='rebuild_perstorm',params=r.x.tolist()); sd[k]=float(np.std(pred-y[te])); print(f'   -> adopting per-storm form for {k}')
P['resid_sd']=sd
json.dump(P, open('ctc/valuation_params.json','w'), indent=1)
