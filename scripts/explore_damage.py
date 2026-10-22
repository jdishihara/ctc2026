import json, numpy as np, sys
from pathlib import Path
root=Path('data')
case=json.load(open(root/'case.json'))
man=json.load(open(root/'history/manifest.json'))
sites={s:[(x['x'],x['y'],x['weight'],x['island']) for x in c['sites']] for s,c in case['companies'].items() if c['sites']}
isl_sites={}
for sym,ss in sites.items():
    for x,y,w,i in ss: isl_sites.setdefault(i,[]).append((x,y,sym))
# load storms
storms=[]  # dict: pattern, obs array (age,x,y,r,I), impacts {island:age}, damage
for s in man['seasons'][:300]:
    feed=[json.loads(l) for l in open(root/'history'/s['dir']/'feed.jsonl')]
    for st in s['storms']:
        obs=np.array([[m['age'],m['x'],m['y'],m['radius'],m['intensity']] for m in feed if m['round']==st['round'] and m['type']=='storm'])
        imp={m['island']:m['age'] for m in feed if m['round']==st['round'] and m['type']=='impact'}
        storms.append(dict(pattern=st['pattern'],obs=obs,imp=imp,dmg=st['damage_pct'],loss=st['industry_loss_musd']))
print(len(storms),'storms; obs per storm', np.mean([len(s['obs']) for s in storms]))
# 1. impact boundary: for each impact, (d/r, intensity) of closest site at impact age and one step before
pts=[]; prev=[]
for s in storms:
    for isl,age in s['imp'].items():
        o=s['obs']; k=np.searchsorted(o[:,0],age)
        if k>=len(o) or o[k,0]!=age: continue
        for row,lst in ((o[k],pts),(o[k-1],prev) if k>0 else (None,None)):
            if row is None: continue
            d=min(np.hypot(row[1]-x,row[2]-y) for x,y,_ in isl_sites[isl])
            lst.append((d/row[3], row[4], d, row[3]))
pts=np.array(pts); prev=np.array(prev)
print('impacts',len(pts))
for lo,hi in [(0.5,0.7),(0.7,0.8),(0.8,0.9),(0.9,1.0),(1.0,1.2)]:
    m=(pts[:,1]>=lo)&(pts[:,1]<hi)
    if m.sum(): print(f'I in [{lo},{hi}): n={m.sum()} d/r at impact: mean {pts[m,0].mean():.3f} min {pts[m,0].min():.3f} max {pts[m,0].max():.3f}; prev step d/r mean {prev[m,0].mean():.3f}')
# does product I*(1-d/r) look constant at impact?
for name,f in [('I*(1-d/r)',lambda p:p[:,1]*(1-p[:,0])),('I*exp(-d/r)',lambda p:p[:,1]*np.exp(-p[:,0])),('I*exp(-(d/r)^2)',lambda p:p[:,1]*np.exp(-p[:,0]**2)),('I/(1+(d/r)^2)',lambda p:p[:,1]/(1+p[:,0]**2)),('I*exp(-2 d/r)',lambda p:p[:,1]*np.exp(-2*p[:,0])),('I*(1-d/r)^2',lambda p:p[:,1]*np.clip(1-p[:,0],0,None)**2)]:
    v=f(pts); print(f'{name}: at impact mean {v.mean():.4f} sd {v.std():.4f} cv {v.std()/v.mean():.3f}')
# also: impacts only happen when d/r < 1?
print('max d/r at impact', pts[:,0].max())
