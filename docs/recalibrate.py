"""
Recalibrate the basal formula on the full year of data.
Finds: optimal_dose = intercept - slope * 7d_strain
using only nights where the outcome was good (TIR >= 80%, no hypo).
"""

import csv, glob, os
from datetime import datetime, timedelta, date
from collections import defaultdict

BASE       = 'D:/claude/t1d'
FITBIT_DIR = os.path.join(BASE, 'Fitbit')
DIAGNOSIS  = date(2025, 4, 9)

# ---- paste loaders inline to keep this script self-contained ----
def load_dexcom(paths):
    glucose_dict, insulin_dict = {}, {}
    for path in paths:
        with open(path, 'r', encoding='utf-8') as f:
            for row in csv.reader(f, delimiter=';'):
                if len(row) < 9: continue
                ts    = row[1].strip().strip('"')
                etype = row[2].strip().strip('"')
                esub  = row[3].strip().strip('"')
                gstr  = row[7].strip().strip('"')
                istr  = row[8].strip().strip('"')
                if not ts or 'T' not in ts: continue
                try: dt = datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S')
                except: continue
                if etype == 'Estimeret glukoseværdi' and gstr:
                    try: glucose_dict[dt] = float(gstr.replace(',','.'))
                    except: pass
                if etype == 'Insulin' and istr:
                    try: insulin_dict[dt] = (esub, float(istr.replace(',','.')))
                    except: pass
    glucose = sorted(glucose_dict.items())
    insulin = sorted([(dt,s,u) for dt,(s,u) in insulin_dict.items()])
    return glucose, insulin

def load_whoop(folder):
    cycles, sleeps = [], []
    with open(os.path.join(folder,'physiological_cycles.csv'),'r',encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                cs = datetime.strptime(row['Cycle start time'],'%Y-%m-%d %H:%M:%S')
                ce = datetime.strptime(row['Cycle end time'],'%Y-%m-%d %H:%M:%S') \
                     if row['Cycle end time'].strip() else None
                if ce is not None:
                    cycle_date = (ce - timedelta(hours=6)).date()
                else:
                    cycle_date = cs.date()
                cycles.append({'date':cycle_date,'start':cs,'end':ce,
                    'strain': float(row['Day Strain']) if row['Day Strain'].strip() else None})
            except: pass
    with open(os.path.join(folder,'sleeps.csv'),'r',encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                cs   = datetime.strptime(row['Cycle start time'],'%Y-%m-%d %H:%M:%S')
                wake = datetime.strptime(row['Wake onset'],'%Y-%m-%d %H:%M:%S') \
                       if row['Wake onset'].strip() else None
                sleeps.append({'cycle_start':cs,'wake':wake})
            except: pass
    sleeps.sort(key=lambda x: x['cycle_start'])
    return cycles, sleeps

def load_fitbit_azm():
    azm_dir = os.path.join(FITBIT_DIR,'Active Zone Minutes (AZM)')
    if not os.path.isdir(azm_dir): return {}
    zone_weights = {'FAT_BURN':1,'CARDIO':2,'PEAK':3}
    daily = defaultdict(float)
    for f in sorted(glob.glob(os.path.join(azm_dir,'Active Zone Minutes - 20*.csv'))):
        with open(f,'r',encoding='utf-8') as fh:
            for row in csv.DictReader(fh):
                try:
                    d = datetime.strptime(row['date_time'].strip()[:10],'%Y-%m-%d').date()
                    if d < DIAGNOSIS: continue
                    daily[d] += float(row['total_minutes']) * zone_weights.get(row['heart_zone_id'].strip(),0)
                except: pass
    return dict(daily)

def build_strain_index(cycles, fitbit_azm):
    whoop_strain = {c['date']:c['strain'] for c in cycles
                    if c['strain'] is not None and c['date'] >= DIAGNOSIS}
    overlap_w, overlap_f = [], []
    for d,fs in fitbit_azm.items():
        if d in whoop_strain and fs > 0:
            overlap_w.append(whoop_strain[d])
            overlap_f.append(fs)
    scale = (sum(overlap_w)/len(overlap_w))/(sum(overlap_f)/len(overlap_f)) if overlap_f else 1.0
    index = {d:{'strain':s,'source':'whoop'} for d,s in whoop_strain.items()}
    for d,azm in fitbit_azm.items():
        if d not in index and d >= DIAGNOSIS:
            index[d] = {'strain':round(azm*scale,1),'source':'fitbit'}
    return index, scale

def rolling_strain(ref_date, days, index):
    vals = [index[ref_date-timedelta(days=i)]['strain']
            for i in range(days) if (ref_date-timedelta(days=i)) in index]
    return round(sum(vals)/len(vals),2) if vals else None

def overnight_stats(bdt, glucose, sleeps):
    next_wake = None
    for s in sleeps:
        if s['wake'] and s['wake'] > bdt and s['wake'] < bdt+timedelta(hours=14):
            next_wake = s['wake']; break
    if not next_wake: next_wake = bdt+timedelta(hours=8)
    vals = [v for dt,v in glucose if bdt <= dt <= next_wake]
    if len(vals) < 6: return None
    return {
        'tir':   sum(1 for v in vals if 4<=v<=10)/len(vals)*100,
        'hypo':  sum(1 for v in vals if v<4)/len(vals)*100,
        'min_g': min(vals), 'wake_g': vals[-1], 'inj_g': vals[0],
    }

# ---- Linear regression (no numpy needed) ----
def linreg(xs, ys):
    n = len(xs)
    if n < 3: return None, None, None
    mx, my = sum(xs)/n, sum(ys)/n
    ss_xx = sum((x-mx)**2 for x in xs)
    ss_xy = sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    slope  = ss_xy / ss_xx
    intercept = my - slope * mx
    # R-squared
    ss_res = sum((y - (intercept + slope*x))**2 for x,y in zip(xs,ys))
    ss_tot = sum((y - my)**2 for y in ys)
    r2 = 1 - ss_res/ss_tot if ss_tot > 0 else 0
    return round(slope,4), round(intercept,4), round(r2,3)

# ---- MAIN ----
dexcom_paths = sorted(glob.glob(os.path.join(BASE,'Clarity_*.csv')))
whoop_dir    = max(sorted(glob.glob(os.path.join(BASE,'my_whoop_data_*'))), key=os.path.getmtime)

glucose, insulin = load_dexcom(dexcom_paths)
cycles, sleeps   = load_whoop(whoop_dir)
fitbit_azm       = load_fitbit_azm()
strain_index, scale = build_strain_index(cycles, fitbit_azm)

basal = [(dt,u) for dt,t,u in insulin if 'Lang' in t]
basal.sort(key=lambda x: x[0])

# Build per-night records
records = []
for bdt, bunits in basal:
    d = bdt.date()
    if d < DIAGNOSIS: continue
    s7 = rolling_strain(d, 7, strain_index)
    s3 = rolling_strain(d, 3, strain_index)
    if s7 is None: continue
    stats = overnight_stats(bdt, glucose, sleeps)
    if not stats: continue
    records.append({
        'date': d, 'basal': bunits, 's7': s7, 's3': s3,
        **stats,
        'good': stats['tir'] >= 80 and stats['hypo'] == 0,
    })

print(f"Total nights: {len(records)}")
good = [r for r in records if r['good']]
print(f"Good nights (TIR>=80%, no hypo): {len(good)}")

# ---- Fit on good nights ----
xs = [r['s7'] for r in good]
ys = [r['basal'] for r in good]
slope, intercept, r2 = linreg(xs, ys)

print(f"\n=== RECALIBRATED FORMULA (full year, good nights only) ===")
print(f"  Basal = {intercept:.1f} + ({slope:.2f} x 7d_strain)")
print(f"  R-squared: {r2:.3f}")
print(f"\n  Old formula: Basal = 35 - (1.30 x 7d_strain)")
print(f"  New formula: Basal = {intercept:.1f} + ({slope:.2f} x 7d_strain)")

# Show what the new formula gives at key strain levels
print(f"\n  {'7d_strain':<12} {'Old':>6} {'New':>6}")
for s in [4, 6, 8, 10, 12, 14, 16]:
    old = round(35 - 1.3*s)
    new = round(intercept + slope*s)
    diff = new - old
    marker = ' <--' if abs(diff) > 3 else ''
    print(f"  {s:<12} {old:>6} {new:>6}  ({diff:+d}){marker}")

# ---- Temporal drift: has the relationship changed over the year? ----
print(f"\n=== TEMPORAL DRIFT: formula by quarter ===")
quarters = [
    ('Q1 Apr-Jun 2025', date(2025,4,9),  date(2025,6,30)),
    ('Q2 Jul-Sep 2025', date(2025,7,1),  date(2025,9,30)),
    ('Q3 Oct-Dec 2025', date(2025,10,1), date(2025,12,31)),
    ('Q4 Jan-Apr 2026', date(2026,1,1),  date(2026,4,13)),
]
for label, qstart, qend in quarters:
    qgood = [r for r in good if qstart <= r['date'] <= qend]
    if len(qgood) < 4:
        print(f"  {label}: too few good nights ({len(qgood)})")
        continue
    qs, qi, qr2 = linreg([r['s7'] for r in qgood], [r['basal'] for r in qgood])
    avg_dose = sum(r['basal'] for r in qgood)/len(qgood)
    avg_s7   = sum(r['s7'] for r in qgood)/len(qgood)
    print(f"  {label}: n={len(qgood):2d}  avg_dose={avg_dose:.1f}u  avg_s7={avg_s7:.1f}"
          f"  formula={qi:.1f}+({qs:.2f}*s7)  R2={qr2:.2f}")

# ---- Injection glucose effect ----
print(f"\n=== INJECTION GLUCOSE vs OVERNIGHT OUTCOME (all nights) ===")
inj_bands = [('<4',4,0,4),('4-6',2,4,6),('6-8',0,6,8),('8-10',0,8,10),('10-12',1,10,12),('>12',2,12,99)]
for label, adj, lo, hi in inj_bands:
    grp = [r for r in records if lo <= r['inj_g'] < hi]
    if not grp: continue
    avg_tir  = sum(r['tir'] for r in grp)/len(grp)
    hypo_n   = sum(1 for r in grp if r['hypo']>0)
    hyper_n  = sum(1 for r in grp if r['tir']<60)
    print(f"  InjG {label:<6}: n={len(grp):3d}  TIR={avg_tir:5.1f}%  hypos={hypo_n:2d}  hypers={hyper_n:2d}")

# ---- Half-day recalibration ----
print(f"\n=== HALF-DAY TIMING (last workout end) vs OVERNIGHT TIR ===")
print(f"  (Recalibrated on full year)")

# Load workouts for timing
workouts = []
with open(os.path.join(whoop_dir,'workouts.csv'),'r',encoding='utf-8') as f:
    for row in csv.DictReader(f):
        try:
            ws = datetime.strptime(row['Workout start time'],'%Y-%m-%d %H:%M:%S')
            we = datetime.strptime(row['Workout end time'],  '%Y-%m-%d %H:%M:%S')
            workouts.append({'date':ws.date(),'end':we,
                'strain':float(row['Activity Strain']) if row['Activity Strain'].strip() else 0})
        except: pass
wbd = defaultdict(list)
for w in workouts: wbd[w['date']].append(w)

half_records = [r for r in records if r['s7'] is not None and 6<=r['s7']<=12]  # actually use s1 concept
# For timing, use the actual day workouts
time_buckets = defaultdict(list)
for r in records:
    ws = wbd.get(r['date'],[])
    if not ws:
        time_buckets['no_workout'].append(r)
        continue
    latest_h = max(w['end'].hour + w['end'].minute/60 for w in ws)
    if latest_h < 14:   time_buckets['before_14h'].append(r)
    elif latest_h < 17: time_buckets['14-17h'].append(r)
    elif latest_h < 20: time_buckets['17-20h'].append(r)
    else:               time_buckets['after_20h'].append(r)

for label, key in [('No workout','no_workout'),('Last end <14:00','before_14h'),
                    ('Last end 14-17h','14-17h'),('Last end 17-20h','17-20h'),
                    ('Last end >20:00','after_20h')]:
    grp = time_buckets[key]
    if not grp: continue
    avg_tir = sum(r['tir'] for r in grp)/len(grp)
    hypos   = sum(1 for r in grp if r['hypo']>0)
    good_g  = [r for r in grp if r['good']]
    avg_good_dose = sum(r['basal'] for r in good_g)/len(good_g) if good_g else None
    dose_str = f"{avg_good_dose:.1f}u" if avg_good_dose else 'n/a'
    print(f"  {label:<20}: n={len(grp):3d}  TIR={avg_tir:5.1f}%  hypos={hypos:2d}  best_dose={dose_str}")

# ---- Summary of recommended formula update ----
print(f"\n=== SUMMARY ===")
print(f"  Old: 35 - (1.30 x s7)  [calibrated on 88 nights, Jan-Apr 2026]")
print(f"  New: {intercept:.1f} + ({slope:.2f} x s7)  [calibrated on {len(good)} good nights, full year]")
tonight_s7 = rolling_strain(date(2026,4,13), 7, strain_index)
if tonight_s7:
    old_dose = round(35 - 1.3*tonight_s7)
    new_dose = round(intercept + slope*tonight_s7)
    print(f"\n  Tonight s7={tonight_s7}: old formula -> {old_dose}u,  new formula -> {new_dose}u")
    print(f"  Recent actual doses: 23-29u")
