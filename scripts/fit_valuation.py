"""Fit settlement values as functions of season damage, outage and insured losses. Writes ctc/valuation_params.json."""
import json, sys, numpy as np
from pathlib import Path
from scipy.optimize import least_squares
sys.path.insert(0, '.')
from ctc.wind import SiteState, PHYS
root=Path('data'); case=json.load(open(root/'case.json')); man=json.load(open(root/'history/manifest.json'))
START={'PORT':72.48,'ISLE':50.26,'AQUA':27.33,'GRID':36.41,'FERRY':17.91,'RECON':52.38,'MAT':35.81,'GEN':40.30,'HAVEN':39.55,'REIN':89.36}
rows=[]  # per season: cum dmg per company, weighted outage per company, season loss, settle
per_storm=[]  # (dmg vector, loss)
for s in man['seasons']:
    feed=[json.loads(l) for l in open(root/'history'/s['dir']/'feed.jsonl')]
    states={k:SiteState(case,k) for k in PHYS}
    for st in s['storms']:
        for k in PHYS: states[k].new_storm()
        for m in feed:
            if m['round']==st['round'] and m['type']=='storm':
                for k in PHYS: states[k].observe(m)
        per_storm.append(([st['damage_pct'][k] for k in PHYS], st['industry_loss_musd']))
    cum={k:sum(st['damage_pct'][k] for st in s['storms']) for k in PHYS}
    out={k:states[k].weighted_outage() for k in PHYS}
    sett=json.load(open(root/'history'/s['dir']/'settlement.json'))
    rows.append((cum,out,s['season_loss_musd'],sett))
n=len(rows); tr=slice(0,450); te=slice(450,n)
def r2(p,a): return 1-((p-a)**2).sum()/((a-a.mean())**2).sum()
P={}
print('-- island businesses: settle = base - a*cum - b*cum^2 - o*outage_secs --')
for k in PHYS:
    X=np.array([[1,r[0][k],r[0][k]**2,r[1][k]] for r in rows]); y=np.array([r[3][k] for r in rows])
    beta,*_=np.linalg.lstsq(X[tr],y[tr],rcond=None)
    print(f'{k}: base {beta[0]:.2f} a {beta[1]:.4f} b {beta[2]:.6f} outage {beta[3]:.5f}/s  train R2 {r2(X[tr]@beta,y[tr]):.3f} test R2 {r2(X[te]@beta,y[te]):.3f}')
    P[k]=dict(kind='island',beta=beta.tolist())
print('-- season loss per storm = sum l_k * dmg_k --')
X=np.array([d for d,_ in per_storm]); y=np.array([l for _,l in per_storm])
beta,*_=np.linalg.lstsq(X[:1350],y[:1350],rcond=None)
print('loss per damage pt:', dict(zip(PHYS,np.round(beta,2))), 'test R2', round(r2(X[1350:]@beta,y[1350:]),3))
P['loss']=dict(beta=beta.tolist())
print('-- rebuilders: settle = base + A*(1-exp(-D/s)) --')
feat={'RECON':lambda r: r[0]['PORT']+r[0]['GRID']+r[0]['FERRY'], 'MAT':lambda r: sum(r[0].values()), 'GEN':lambda r: r[0]['GRID']}
feat2={'GEN':lambda r: r[1]['GRID']}
for k in ['RECON','MAT','GEN']:
    D=np.array([feat[k](r) for r in rows]); O=np.array([feat2[k](r) if k in feat2 else 0 for r in rows]); y=np.array([r[3][k] for r in rows])
    f=lambda p,D,O: p[0]+p[1]*(1-np.exp(-D/p[2]))+p[3]*O
    res=least_squares(lambda p: f(p,D[tr],O[tr])-y[tr], x0=[30,20,50,0.0], bounds=([0,0,1,-1],[100,100,1000,1]))
    print(f'{k}: base {res.x[0]:.2f} A {res.x[1]:.2f} s {res.x[2]:.1f} outage {res.x[3]:.5f} train R2 {r2(f(res.x,D[tr],O[tr]),y[tr]):.3f} test R2 {r2(f(res.x,D[te],O[te]),y[te]):.3f}')
    P[k]=dict(kind='rebuild',params=res.x.tolist())
print('-- insurers: piecewise linear in season loss --')
L=np.array([r[2] for r in rows])
for k,top,floor in [('HAVEN',75,21),('REIN',90,None)]:
    y=np.array([r[3][k] for r in rows])
    if floor is not None:
        f=lambda p,L: top-(top-floor)*np.clip((L-p[0])/(p[1]-p[0]),0,1)
        res=least_squares(lambda p: f(p,L[tr])-y[tr], x0=[400,1300], bounds=([0,500],[1000,3000]))
    else:
        f=lambda p,L: top-p[1]*np.clip(L-p[0],0,None)
        res=least_squares(lambda p: f(p,L[tr])-y[tr], x0=[1300,0.03], bounds=([500,0],[3000,1]))
    print(f'{k}: params {np.round(res.x,3)} train R2 {r2(f(res.x,L[tr]),y[tr]):.3f} test R2 {r2(f(res.x,L[te]),y[te]):.3f} max abs err {np.abs(f(res.x,L[te])-y[te]).max():.2f}')
    P[k]=dict(kind='insurer',top=top,floor=floor,params=res.x.tolist())
# unconditional per-storm priors for remaining rounds
P['prior']=dict(dmg={k:float(np.mean([d[i] for d,_ in per_storm])) for i,k in enumerate(PHYS)}, loss=float(np.mean([l for _,l in per_storm])),
                outage={k:float(np.mean([r[1][k] for r in rows]))/3 for k in PHYS})
print('priors per storm', P['prior'])
json.dump(P, open('ctc/valuation_params.json','w'), indent=1)
