"""
Predictor significance test — which variables predict overnight TIR%?
Spearman correlation + Mann-Whitney median split A/B test on all candidates.
"""
import csv, glob, os, math
from datetime import datetime, timedelta, date
from collections import defaultdict
from whoop_loader import load_whoop
from dexcom_loader import load_dexcom

BASE      = 'D:/claude/t1d/data'
DIAGNOSIS = date(2025, 4, 9)
TGT_LO, TGT_HI = 5.0, 8.0
HYPO_THR, HYPER_THR = 4.0, 10.0

def rolling_avg(d, n, idx):
    v = [idx[d - timedelta(days=i)]['strain']
         for i in range(n)
         if (d - timedelta(days=i)) in idx
         and idx[d - timedelta(days=i)]['strain'] is not None]
    return round(sum(v) / len(v), 2) if v else None

def overnight_stats(inj_dt, glucose_list):
    end = datetime.combine(inj_dt.date() + timedelta(days=1),
                           datetime.min.time().replace(hour=7))
    rdgs = [(dt, v) for dt, v in glucose_list if inj_dt <= dt <= end]
    if len(rdgs) < 6:
        return None
    vals = [v for _, v in rdgs]
    n = len(vals)
    return {
        'tir':     round(sum(1 for v in vals if TGT_LO <= v <= TGT_HI) / n * 100, 1),
        'tir_full':round(sum(1 for v in vals if HYPO_THR <= v <= HYPER_THR) / n * 100, 1),
        'hypo':    round(sum(1 for v in vals if v < HYPO_THR) / n * 100, 1),
        'hyper':   round(sum(1 for v in vals if v > HYPER_THR) / n * 100, 1),
        'fasting': round(vals[-1], 1),
        'mean':    round(sum(vals) / n, 1),
        'inj_g':   round(vals[0], 1),
    }

# ── build dataset ──────────────────────────────────────────────────────────────
glucose_list, basal_list, bolus = load_dexcom()
strain_idx = load_whoop()

nights = []
for inj_dt, inj_date, dose in basal_list:
    if inj_dt.hour < 18:
        continue
    st = overnight_stats(inj_dt, glucose_list)
    if not st:
        continue
    s1  = strain_idx.get(inj_date, {}).get('strain')
    s7  = rolling_avg(inj_date, 7, strain_idx)
    hrv = strain_idx.get(inj_date, {}).get('hrv')
    rec = strain_idx.get(inj_date, {}).get('recovery')
    rhr = strain_idx.get(inj_date, {}).get('rhr')
    s1_dev = round(s1 - s7, 2) if s1 is not None and s7 is not None else None
    nights.append({
        'date': inj_date, 'dose': dose,
        's1': s1, 's7': s7, 's1_dev': s1_dev,
        'hrv': hrv, 'recovery': rec, 'rhr': rhr,
        'bolus': bolus.get(inj_date, 0),
        **st
    })

print(f'Total nights in dataset: {len(nights)}')

# ── stat helpers ───────────────────────────────────────────────────────────────
def spearman(x, y):
    n = len(x)
    if n < 5:
        return None, None
    rx = sorted(range(n), key=lambda i: x[i])
    ry = sorted(range(n), key=lambda i: y[i])
    rankx = [0] * n
    ranky = [0] * n
    for r, i in enumerate(rx): rankx[i] = r + 1
    for r, i in enumerate(ry): ranky[i] = r + 1
    d2 = sum((rankx[i] - ranky[i]) ** 2 for i in range(n))
    rs = 1 - 6 * d2 / (n * (n ** 2 - 1))
    if abs(rs) >= 1.0:
        return round(rs, 3), 0.0
    t = rs * math.sqrt(n - 2) / math.sqrt(1 - rs ** 2)
    p = 2 * (1 / (1 + math.exp(1.7 * abs(t) * math.sqrt(n) / math.sqrt(n - 1))))
    return round(rs, 3), round(p, 4)

def mannwhitney_z(a, b):
    na, nb = len(a), len(b)
    if na < 3 or nb < 3:
        return None, None
    combined = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    ranks = list(range(1, na + nb + 1))
    # tie correction
    i = 0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]:
            j += 1
        avg = sum(range(i + 1, j + 1)) / (j - i)
        for k in range(i, j):
            ranks[k] = avg
        i = j
    ra = sum(ranks[i] for i, (v, g) in enumerate(combined) if g == 0)
    u  = ra - na * (na + 1) / 2
    mu = na * nb / 2
    su = math.sqrt(na * nb * (na + nb + 1) / 12)
    z  = (u - mu) / su if su > 0 else 0
    p  = 2 * (1 / (1 + math.exp(1.7 * abs(z))))
    return round(z, 3), round(p, 4)

def group_means(nights, key, outcome):
    vals = [n[key] for n in nights if n[key] is not None]
    if not vals:
        return None, None, None
    med = sorted(vals)[len(vals) // 2]
    lo  = [n[outcome] for n in nights if n[key] is not None and n[key] <= med]
    hi  = [n[outcome] for n in nights if n[key] is not None and n[key] > med]
    lom = round(sum(lo) / len(lo), 1) if lo else None
    him = round(sum(hi) / len(hi), 1) if hi else None
    return lo, hi, med, lom, him

def sig_stars(p):
    if p is None:   return '   '
    if p < 0.001:   return '***'
    if p < 0.01:    return '** '
    if p < 0.05:    return '*  '
    return '   '

# ── MAIN TEST ──────────────────────────────────────────────────────────────────
candidates = [
    ('inj_g',    'Injection-time glucose'),
    ('s7',       '7-day avg strain'),
    ('s1',       'Today strain (s1)'),
    ('s1_dev',   'Today vs 7d (s1-s7)'),
    ('bolus',    'Bolus units that day'),
    ('hrv',      'HRV (ms)'),
    ('recovery', 'Recovery score %'),
    ('rhr',      'Resting HR (bpm)'),
    ('dose',     'Basal dose'),
]

outcomes = ['tir', 'fasting', 'mean']

for outcome in outcomes:
    print()
    print('=' * 90)
    print(f'OUTCOME: {outcome.upper()}  (n={len(nights)} nights)')
    print('=' * 90)
    print(f'{"Variable":<28} {"r":>6}  {"p":>8}  {"sig":>3}  {"MW z":>7}  {"p":>8}  {"sig":>3}  '
          f'{"lo_mean":>8}  {"hi_mean":>8}  {"median split"}')
    print('-' * 90)

    for key, label in candidates:
        xs = [n[key] for n in nights if n[key] is not None]
        ys = [n[outcome] for n in nights if n[key] is not None]
        rs, ps = spearman(xs, ys)
        result = group_means(nights, key, outcome)
        if result[0] is None:
            continue
        lo, hi, med, lom, him = result
        z, pm = mannwhitney_z(lo, hi)
        print(f'{label:<28} {str(rs):>6}  {str(ps):>8}  {sig_stars(ps):>3}  '
              f'{str(z):>7}  {str(pm):>8}  {sig_stars(pm):>3}  '
              f'{str(lom):>8}  {str(him):>8}  (split at {med})')

# ── INTERACTION TEST: inj_g x s7 ──────────────────────────────────────────────
print()
print('=' * 60)
print('INTERACTION: inj_g + s7 combined vs TIR')
print('=' * 60)

# Quadrant split: low/high inj_g x low/high s7
med_inj = sorted(n['inj_g'] for n in nights)[len(nights) // 2]
med_s7  = sorted(n['s7']  for n in nights if n['s7'] is not None)[len([n for n in nights if n['s7'] is not None]) // 2]

groups = {
    'low_inj + low_s7':  [n['tir'] for n in nights if n['inj_g'] <= med_inj and n['s7'] is not None and n['s7'] <= med_s7],
    'low_inj + high_s7': [n['tir'] for n in nights if n['inj_g'] <= med_inj and n['s7'] is not None and n['s7'] > med_s7],
    'high_inj + low_s7': [n['tir'] for n in nights if n['inj_g'] > med_inj  and n['s7'] is not None and n['s7'] <= med_s7],
    'high_inj + high_s7':[n['tir'] for n in nights if n['inj_g'] > med_inj  and n['s7'] is not None and n['s7'] > med_s7],
}
print(f'Median inj_g = {med_inj}  |  Median s7 = {med_s7}')
print()
for label, vals in groups.items():
    if vals:
        m = round(sum(vals)/len(vals), 1)
        print(f'  {label:<22}  n={len(vals):>3}  mean TIR={m}%')

# Compare low_inj vs high_inj within each s7 half
print()
for s7_label, s7_cond in [('low_s7', lambda n: n['s7'] is not None and n['s7'] <= med_s7),
                            ('high_s7', lambda n: n['s7'] is not None and n['s7'] > med_s7)]:
    sub = [n for n in nights if s7_cond(n)]
    lo  = [n['tir'] for n in sub if n['inj_g'] <= med_inj]
    hi  = [n['tir'] for n in sub if n['inj_g'] > med_inj]
    z, p = mannwhitney_z(lo, hi)
    print(f'  inj_g effect within {s7_label}: MW z={z}  p={p}  {sig_stars(p)}  '
          f'(low_inj mean={round(sum(lo)/len(lo),1) if lo else None}, '
          f'high_inj mean={round(sum(hi)/len(hi),1) if hi else None})')
