"""
Bolus noise analysis:
1. How much variance does total daily bolus explain in overnight TIR?
2. Does bolus in the 4-6h window before injection (proxy for IOB) add signal?
3. Does adding bolus improve the model BEYOND what inj_g already captures?
   (partial correlation / residual analysis)
4. Is the bolus effect mediated through inj_g, or independent of it?
"""
import csv, glob, os, math
from datetime import datetime, timedelta, date
from collections import defaultdict

BASE = 'D:/claude/t1d/data'
DIAGNOSIS = date(2025, 4, 9)
TGT_LO, TGT_HI = 5.0, 8.0
HYPO_THR = 4.0

def load_dexcom():
    files = sorted(glob.glob(os.path.join(BASE, 'Clarity_*.csv')))
    glucose, basal_ts, bolus_events = {}, {}, []
    for path in files:
        with open(path, 'r', encoding='utf-8') as f:
            for row in csv.reader(f, delimiter=';'):
                if len(row) < 9: continue
                ts=row[1].strip().strip('"'); etype=row[2].strip().strip('"')
                esub=row[3].strip().strip('"'); gval=row[7].strip().strip('"')
                ival=row[8].strip().strip('"')
                if not ts or 'T' not in ts: continue
                try: dt=datetime.strptime(ts,'%Y-%m-%dT%H:%M:%S')
                except: continue
                if dt.date()<DIAGNOSIS: continue
                if etype=='Estimeret glukoseværdi' and gval:
                    try: glucose[dt]=float(gval.replace(',','.'))
                    except: pass
                if etype=='Insulin' and ival:
                    try: u=float(ival.replace(',','.'))
                    except: continue
                    if 'Lang' in esub:
                        if dt not in basal_ts: basal_ts[dt]=u
                    elif 'Hurtig' in esub:
                        bolus_events.append((dt, u))

    basal_by_date={}
    for dt,u in sorted(basal_ts.items()):
        d=dt.date()
        if d not in basal_by_date: basal_by_date[d]=[dt,u]
        else: basal_by_date[d][1]+=u

    # Deduplicate bolus events by exact timestamp
    bolus_dedup = {}
    for dt, u in bolus_events:
        if dt not in bolus_dedup:
            bolus_dedup[dt] = u

    bolus_by_date = defaultdict(float)
    for dt, u in bolus_dedup.items():
        bolus_by_date[dt.date()] += u

    return (sorted(glucose.items()),
            sorted([(v[0],d,v[1]) for d,v in basal_by_date.items()]),
            bolus_by_date, sorted(bolus_dedup.items()))

def overnight_stats(inj_dt, glucose_list):
    end = datetime.combine(inj_dt.date()+timedelta(days=1),
                           datetime.min.time().replace(hour=7))
    rdgs = [(dt,v) for dt,v in glucose_list if inj_dt<=dt<=end]
    if len(rdgs)<6: return None
    vals=[v for _,v in rdgs]; n=len(vals)
    hypo_idx = next((i for i,v in enumerate(vals) if v<HYPO_THR), None)
    hypo_corr = hypo_idx is not None and max(vals[hypo_idx:])>7.0
    return {
        'tir':      round(sum(1 for v in vals if TGT_LO<=v<=TGT_HI)/n*100,1),
        'hypo_pct': round(sum(1 for v in vals if v<HYPO_THR)/n*100,1),
        'fasting':  round(vals[-1],1),
        'mean':     round(sum(vals)/n,1),
        'inj_g':    round(vals[0],1),
        'hypo_correction': hypo_corr,
    }

glucose_list, basal_list, bolus_by_date, bolus_events = load_dexcom()

# Build nightly dataset with bolus detail
nights = []
for inj_dt, inj_date, dose in basal_list:
    if inj_dt.hour < 18: continue
    st = overnight_stats(inj_dt, glucose_list)
    if not st: continue

    # Total bolus that day
    bolus_total = bolus_by_date.get(inj_date, 0)

    # Bolus in 4h window before injection (proxy for active IOB)
    window_start = inj_dt - timedelta(hours=4)
    bolus_4h = sum(u for dt,u in bolus_events
                   if window_start <= dt <= inj_dt)

    # Bolus in 6h window
    bolus_6h = sum(u for dt,u in bolus_events
                   if (inj_dt - timedelta(hours=6)) <= dt <= inj_dt)

    nights.append({
        'date': inj_date, 'dose': dose,
        'bolus_total': bolus_total,
        'bolus_4h': bolus_4h,
        'bolus_6h': bolus_6h,
        **st
    })

# Exclude hypo-correction nights
clean = [n for n in nights if not n['hypo_correction']]
print(f'Total nights: {len(nights)}  |  Clean (excl hypo-correction): {len(clean)}')
print(f'Nights with any pre-injection bolus (4h): {sum(1 for n in clean if n["bolus_4h"]>0)} ({sum(1 for n in clean if n["bolus_4h"]>0)/len(clean)*100:.1f}%)')
print(f'Nights with any pre-injection bolus (6h): {sum(1 for n in clean if n["bolus_6h"]>0)} ({sum(1 for n in clean if n["bolus_6h"]>0)/len(clean)*100:.1f}%)')

# ── STATS ──────────────────────────────────────────────────────────────────────
def spearman(x, y):
    n=len(x)
    if n<5: return None,None
    rx=sorted(range(n),key=lambda i:x[i]); ry=sorted(range(n),key=lambda i:y[i])
    rankx=[0]*n; ranky=[0]*n
    for r,i in enumerate(rx): rankx[i]=r+1
    for r,i in enumerate(ry): ranky[i]=r+1
    d2=sum((rankx[i]-ranky[i])**2 for i in range(n))
    rs=1-6*d2/(n*(n**2-1))
    if abs(rs)>=1.0: return round(rs,3),0.0
    t=rs*math.sqrt(n-2)/math.sqrt(1-rs**2)
    p=2*(1/(1+math.exp(1.7*abs(t)*math.sqrt(n)/math.sqrt(n-1))))
    return round(rs,3),round(p,4)

def linreg(x, y):
    n=len(x); mx=sum(x)/n; my=sum(y)/n
    ssxx=sum((xi-mx)**2 for xi in x)
    ssxy=sum((xi-mx)*(yi-my) for xi,yi in zip(x,y))
    if ssxx==0: return None
    b1=ssxy/ssxx; b0=my-b1*mx
    yhat=[b0+b1*xi for xi in x]
    ssres=sum((yi-yhi)**2 for yi,yhi in zip(y,yhat))
    sstot=sum((yi-my)**2 for yi in y)
    r2=1-ssres/sstot if sstot>0 else 0
    return b0, b1, round(r2,4), [b0+b1*xi for xi in x], ssres

def residuals(x, y):
    result = linreg(x, y)
    if result is None: return None
    b0,b1,r2,yhat,_ = result
    return [yi-(b0+b1*xi) for xi,yi in zip(x,y)]

def sig(p):
    if p is None: return '   '
    if p<0.001: return '***'
    if p<0.01:  return '** '
    if p<0.05:  return '*  '
    return '   '

print()
print('='*70)
print('1. DIRECT CORRELATIONS WITH TIR%  (clean nights only)')
print('='*70)
for key, label in [('inj_g','Injection-time glucose'),('bolus_total','Total daily bolus'),
                   ('bolus_4h','Bolus in 4h before injection'),('bolus_6h','Bolus in 6h before injection')]:
    xs=[n[key] for n in clean]; ys=[n['tir'] for n in clean]
    r,p=spearman(xs,ys)
    print(f'  {label:<32}  r={r:>7}  p={p:>8}  {sig(p)}')

print()
print('='*70)
print('2. DOES BOLUS ADD SIGNAL BEYOND inj_g?')
print('   (Spearman of bolus vs TIR residuals after removing inj_g effect)')
print('='*70)

inj_g_vals = [n['inj_g'] for n in clean]
tir_vals   = [n['tir']   for n in clean]
tir_resid  = residuals(inj_g_vals, tir_vals)

for key, label in [('bolus_total','Total daily bolus'),
                   ('bolus_4h','Bolus in 4h before injection'),
                   ('bolus_6h','Bolus in 6h before injection')]:
    xs = [n[key] for n in clean]
    r, p = spearman(xs, tir_resid)
    print(f'  {label:<32}  r={r:>7}  p={p:>8}  {sig(p)}')

print()
print('='*70)
print('3. IS BOLUS EFFECT MEDIATED THROUGH inj_g?')
print('   (Spearman of bolus vs inj_g — if high, bolus is already captured)')
print('='*70)
for key, label in [('bolus_total','Total daily bolus'),
                   ('bolus_4h','Bolus in 4h before injection'),
                   ('bolus_6h','Bolus in 6h before injection')]:
    xs=[n[key] for n in clean]; ys=[n['inj_g'] for n in clean]
    r,p=spearman(xs,ys)
    print(f'  {label:<32}  r={r:>7}  p={p:>8}  {sig(p)}')

print()
print('='*70)
print('4. VARIANCE EXPLAINED: inj_g alone vs inj_g + bolus_4h')
print('='*70)

# R² of inj_g alone
_,_,r2_inj,_,_ = linreg(inj_g_vals, tir_vals)
print(f'  inj_g alone:          R²={r2_inj:.4f}')

# Multiple R² approximation: add bolus_4h
# Use R² of [inj_g, bolus_4h] via correlation matrix approach
b4h = [n['bolus_4h'] for n in clean]
r_ib, _ = spearman(inj_g_vals, b4h)   # correlation between predictors
r_it, _ = spearman(inj_g_vals, tir_vals)
r_bt, _ = spearman(b4h, tir_vals)
if r_ib is not None and r_it is not None and r_bt is not None and abs(r_ib) < 1.0:
    r2_multi = (r_it**2 + r_bt**2 - 2*r_it*r_bt*r_ib) / (1 - r_ib**2)
    print(f'  inj_g + bolus_4h:     R²~{round(r2_multi,4)} (rank-based approx)')
    print(f'  Incremental gain:     +{round(r2_multi - r2_inj, 4)}')

print()
print('='*70)
print('5. BOLUS DISTRIBUTION — how often and how much before injection?')
print('='*70)
b4h_nonzero = [n['bolus_4h'] for n in clean if n['bolus_4h']>0]
b6h_nonzero = [n['bolus_6h'] for n in clean if n['bolus_6h']>0]
all_b4h = [n['bolus_4h'] for n in clean]
if b4h_nonzero:
    print(f'  Nights with bolus in 4h window: {len(b4h_nonzero)} ({len(b4h_nonzero)/len(clean)*100:.1f}%)')
    print(f'  When present — mean: {round(sum(b4h_nonzero)/len(b4h_nonzero),1)}u  '
          f'median: {sorted(b4h_nonzero)[len(b4h_nonzero)//2]}u  '
          f'max: {max(b4h_nonzero)}u')
    # TIR with vs without pre-injection bolus
    with_bolus    = [n['tir'] for n in clean if n['bolus_4h']>0]
    without_bolus = [n['tir'] for n in clean if n['bolus_4h']==0]
    print(f'  Mean TIR with pre-inj bolus:    {round(sum(with_bolus)/len(with_bolus),1)}%  (n={len(with_bolus)})')
    print(f'  Mean TIR without pre-inj bolus: {round(sum(without_bolus)/len(without_bolus),1)}%  (n={len(without_bolus)})')
    # Compare inj_g between groups
    inj_with    = [n['inj_g'] for n in clean if n['bolus_4h']>0]
    inj_without = [n['inj_g'] for n in clean if n['bolus_4h']==0]
    print(f'  Mean inj_g with pre-inj bolus:  {round(sum(inj_with)/len(inj_with),1)} mmol/L')
    print(f'  Mean inj_g without:             {round(sum(inj_without)/len(inj_without),1)} mmol/L')
