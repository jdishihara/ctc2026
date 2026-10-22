import json, numpy as np
from pathlib import Path
from scipy.optimize import least_squares, minimize_scalar
root=Path('data'); case=json.load(open(root/'case.json')); man=json.load(open(root/'history/manifest.json'))
PHYS=['PORT','ISLE','AQUA','GRID','FERRY']
SITES={s:[(x['x'],x['y'],x['weight'],x['island'],x['name']) for x in case['companies'][s]['sites']] for s in PHYS}
isl_sites={}
for sym,ss in SITES.items():
    for x,y,w,i,n in ss: isl_sites.setdefault(i,[]).append((x,y))
def load(seasons):
    out=[]
    for s in seasons:
        feed=[json.loads(l) for l in open(root/'history'/s['dir']/'feed.jsonl')]
        season=[]
        for st in s['storms']:
            obs=np.array([[m['age'],m['x'],m['y'],m['radius'],m['intensity']] for m in feed if m['round']==st['round'] and m['type']=='storm'])
            imp={m['island']:m['age'] for m in feed if m['round']==st['round'] and m['type']=='impact'}
            season.append(dict(obs=obs,imp=imp,dmg=st['damage_pct'],pattern=st['pattern']))
        out.append(season)
    return out
train=load(man['seasons'][:300]); test=load(man['seasons'][300:])
# --- 1. threshold/k from impacts: minimize cv of I*exp(-k d/r) at the midpoint between pre-impact and impact obs
def impact_stats(k, data):
    v=[]
    for season in data:
        for st in season:
            o=st['obs']
            for isl,age in st['imp'].items():
                j=np.searchsorted(o[:,0],age)
                if j>=len(o) or o[j,0]!=age or j==0: continue
                for row in (o[j],o[j-1]):
                    d=min(np.hypot(row[1]-x,row[2]-y) for x,y in isl_sites[isl]); v.append(row[4]*np.exp(-k*d/row[3]))
    v=np.array(v).reshape(-1,2); mid=v.mean(1); return mid
res=minimize_scalar(lambda k: (lambda m: m.std()/m.mean())(impact_stats(k,train)), bounds=(0.5,5), method='bounded')
K=res.x; THR=impact_stats(K,train).mean(); print(f'wind field: I*exp(-{K:.3f} d/r); closure threshold {THR:.4f} (cv {res.fun:.3f})')
# --- 2. per-site exposure features given k, for a grid of p and thr candidates
def site_exposure(obs, x, y, k, thr, p):
    d=np.hypot(obs[:,1]-x, obs[:,2]-y); w=obs[:,4]*np.exp(-k*d/obs[:,3])
    return np.sum(np.clip(w-thr,0,None)**p)*2.0
def closure_secs(obs,x,y,k,thr):
    d=np.hypot(obs[:,1]-x, obs[:,2]-y); w=obs[:,4]*np.exp(-k*d/obs[:,3]); return 2.0*np.sum(w>thr)
# model: season-level, track per-site remaining = 100 - cum; new site dmg = remaining*(1-exp(-c*E)); company dmg = sum w*sitedmg
def predict(params, data, k, thr, p, return_all=False):
    c={s:params[i] for i,s in enumerate(PHYS)}
    preds=[]; actual=[]
    for season in data:
        state={s:[0.0]*len(SITES[s]) for s in PHYS}
        for st in season:
            for s in PHYS:
                tot=0
                for j,(x,y,w,isl,n) in enumerate(SITES[s]):
                    E=site_exposure(st['obs'],x,y,k,thr,p)
                    new=(100-state[s][j])*(1-np.exp(-c[s]*E)); state[s][j]+=new; tot+=w*new
                preds.append(tot); actual.append(st['dmg'][s])
    return np.array(preds), np.array(actual)
best=None
for p in [1.0,1.5,2.0]:
    for thr in [0.0, THR/2, THR]:
        r=least_squares(lambda prm: predict(prm,train[:120],K,thr,p)[0]-predict(prm,train[:120],K,thr,p)[1], x0=[0.01]*5, bounds=(0,10))
        pr,ac=predict(r.x,train[:120],K,thr,p); r2=1-((pr-ac)**2).sum()/((ac-ac.mean())**2).sum()
        print(f'p={p} thr={thr:.3f}: R2 {r2:.3f} c={np.round(r.x,4)}')
        if best is None or r2>best[0]: best=(r2,p,thr,r.x)
r2,p,thr,c=best
print('\nbest', best)
pr,ac=predict(c,test,K,thr,p)
print('holdout R2 overall', 1-((pr-ac)**2).sum()/((ac-ac.mean())**2).sum())
pr=pr.reshape(-1,5); ac=ac.reshape(-1,5)
for i,s in enumerate(PHYS):
    r2s=1-((pr[:,i]-ac[:,i])**2).sum()/((ac[:,i]-ac[:,i].mean())**2).sum()
    print(f'  {s}: holdout R2 {r2s:.3f}  rmse {np.sqrt(((pr[:,i]-ac[:,i])**2).mean()):.2f} pts  mean actual {ac[:,i].mean():.1f}')
json.dump(dict(k=float(K),thr_close=float(THR),p=p,thr_dmg=float(thr),c={s:float(v) for s,v in zip(PHYS,c)}), open('ctc/damage_params.json','w'), indent=1)
