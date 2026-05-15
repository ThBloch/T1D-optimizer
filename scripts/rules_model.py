"""
Thomas's Rules — backtest + ML optimization
============================================
1. Encode the rules exactly as described
2. Backtest on full dataset: what dose would the rules have suggested each night?
3. Compare rule-suggested dose to actual dose, and outcomes of each
4. Use a Decision Tree to learn optimized thresholds from data
5. Compare: user rules vs ML-optimized rules vs actual decisions
"""

import csv, glob, os, math
from datetime import datetime, timedelta, date
from collections import defaultdict
import numpy as np
from sklearn.tree import DecisionTreeRegressor, export_text
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error
from whoop_loader import load_whoop
from dexcom_loader import load_dexcom
from rules import thomas_rules

HYPO_THR  = 4.0
TGT_LO, TGT_HI = 4.0, 10.0   # user's TIR range

def overnight_stats(inj_dt, glucose_list):
    end=datetime.combine(inj_dt.date()+timedelta(days=1),datetime.min.time().replace(hour=7))
    rdgs=[(dt,v) for dt,v in glucose_list if inj_dt<=dt<=end]
    if len(rdgs)<6: return None
    vals=[v for _,v in rdgs]; n=len(vals)

    # Count distinct hypo events (separate episodes below 4.0)
    hypo_events = 0
    in_hypo = False
    for v in vals:
        if v < HYPO_THR and not in_hypo:
            hypo_events += 1
            in_hypo = True
        elif v >= HYPO_THR:
            in_hypo = False

    return {
        'tir':        round(sum(1 for v in vals if TGT_LO<=v<=TGT_HI)/n*100, 1),
        'fasting':    round(vals[-1], 1),
        'mean':       round(sum(vals)/n, 1),
        'inj_g':      round(vals[0], 1),
        'min_g':      round(min(vals), 1),
        'hypo_events': hypo_events,
        'hypo_correction': hypo_events > 0 and max(vals[next(i for i,v in enumerate(vals) if v<HYPO_THR):]) > 7.0,
    }

# ── BUILD NIGHTLY DATASET ──────────────────────────────────────────────────────
glucose_list, basal_list, _ = load_dexcom()
strain_idx = load_whoop()

nights = []
for inj_dt, inj_date, dose in basal_list:
    if inj_dt.hour < 18: continue
    st = overnight_stats(inj_dt, glucose_list)
    if not st: continue
    s1 = strain_idx.get(inj_date, {}).get('strain')
    nights.append({'date': inj_date, 'dose': dose, 's1': s1, **st})

nights.sort(key=lambda x: x['date'])

# ── BACKTEST THOMAS'S RULES ────────────────────────────────────────────────────
print('='*70)
print('THOMAS\'S RULES — BACKTEST')
print('='*70)

results = []
for i, n in enumerate(nights):
    if i == 0: continue
    prev = nights[i-1]

    suggested, reasoning = thomas_rules(
        yesterday_dose = prev['dose'],
        fasting        = prev['fasting'],
        hypo_events    = prev['hypo_events'],
        s1             = n['s1'],
    )
    if suggested is None: continue

    actual = n['dose']
    diff   = actual - suggested

    results.append({
        'date':      n['date'],
        'actual':    actual,
        'suggested': suggested,
        'diff':      diff,
        'tir':       n['tir'],
        'fasting':   n['fasting'],
        'hypo_events': n['hypo_events'],
        's1':        n['s1'],
        'prev_fasting': prev['fasting'],
        'prev_hypo':    prev['hypo_events'],
    })

n_total    = len(results)
n_agree    = sum(1 for r in results if r['diff'] == 0)
n_close    = sum(1 for r in results if abs(r['diff']) <= 1)
mean_diff  = round(sum(r['diff'] for r in results) / n_total, 2)
mae_diff   = round(sum(abs(r['diff']) for r in results) / n_total, 2)

print(f'\n  Nights evaluated   : {n_total}')
print(f'  Exact agreement    : {n_agree} ({n_agree/n_total*100:.1f}%)')
print(f'  Within ±1u         : {n_close} ({n_close/n_total*100:.1f}%)')
print(f'  Mean diff (actual-suggested): {mean_diff:+.2f}u')
print(f'  MAE (dose units)   : {mae_diff:.2f}u')

# Agreement breakdown by glucose category
print(f'\n  Agreement by last-night fasting glucose:')
cats = [
    ('Hypo ≥2',      lambda r: r['prev_hypo'] >= 2),
    ('Hypo 1',       lambda r: r['prev_hypo'] == 1 and r['prev_hypo'] < 2),
    ('Fasting >14',  lambda r: r['prev_hypo'] == 0 and r['prev_fasting'] > 14),
    ('Fasting 12-14',lambda r: r['prev_hypo'] == 0 and 12 < r['prev_fasting'] <= 14),
    ('Fasting 10.5-12',lambda r: r['prev_hypo'] == 0 and 10.5 < r['prev_fasting'] <= 12),
    ('Fasting ≤10.5',lambda r: r['prev_hypo'] == 0 and r['prev_fasting'] <= 10.5),
]
print(f'  {"Category":<22} {"n":>4}  {"Agree%":>7}  {"Mean diff":>10}  {"Avg TIR next night":>20}')
print(f'  {"-"*70}')
for label, fn in cats:
    sub = [r for r in results if fn(r)]
    if not sub: continue
    agree = sum(1 for r in sub if r['diff']==0)
    mdiff = round(sum(r['diff'] for r in sub)/len(sub), 2)
    mtir  = round(sum(r['tir'] for r in sub)/len(sub), 1)
    print(f'  {label:<22} {len(sub):>4}  {agree/len(sub)*100:>6.1f}%  {mdiff:>+9.2f}u  {mtir:>19.1f}%')

# Where rules and actual diverge most
print(f'\n  Largest disagreements (|diff| ≥ 3u):')
big = sorted([r for r in results if abs(r['diff']) >= 3], key=lambda r: abs(r['diff']), reverse=True)[:15]
if big:
    print(f'  {"Date":<12} {"Actual":>7} {"Suggest":>8} {"Diff":>6}  {"PrevFast":>9}  {"PrevHypo":>9}  {"s1":>5}  {"TIR":>6}')
    print(f'  {"-"*70}')
    for r in big:
        s1s = f'{r["s1"]:.1f}' if r['s1'] else '-'
        print(f'  {str(r["date"]):<12} {r["actual"]:>6.0f}u  {r["suggested"]:>7.0f}u  '
              f'{r["diff"]:>+5.0f}u  {r["prev_fasting"]:>8.1f}  {r["prev_hypo"]:>9}  '
              f'{s1s:>5}  {r["tir"]:>5.1f}%')

# ── OUTCOME COMPARISON: rules vs actual ───────────────────────────────────────
print(f'\n  Outcome comparison: nights where rules differ from actual')
over  = [r for r in results if r['diff'] > 1]   # actual dosed MORE than rules suggest
under = [r for r in results if r['diff'] < -1]  # actual dosed LESS than rules suggest
match = [r for r in results if abs(r['diff']) <= 1]

for label, grp in [('Rules ≈ actual (±1u)', match),
                   ('Actual > rules (+2u or more)', over),
                   ('Actual < rules (-2u or more)', under)]:
    if not grp: continue
    avg_tir     = round(sum(r['tir'] for r in grp)/len(grp), 1)
    avg_fasting = round(sum(r['fasting'] for r in grp)/len(grp), 1)
    hypo_nights = sum(1 for r in grp if r['hypo_events'] > 0)
    print(f'\n  {label}  (n={len(grp)})')
    print(f'    Next night avg TIR     : {avg_tir}%')
    print(f'    Next night avg fasting : {avg_fasting} mmol/L')
    print(f'    Next night hypo nights : {hypo_nights} ({hypo_nights/len(grp)*100:.1f}%)')

# ── ML: DECISION TREE TO LEARN OPTIMIZED THRESHOLDS ───────────────────────────
print(f'\n{"="*70}')
print('DECISION TREE — LEARNING THRESHOLDS FROM DATA')
print('Note: target = actual dose used (learns user behaviour)')
print('='*70)

# Features: prev_fasting, prev_hypo_events, s1 (today), yesterday_dose
# Target: today's actual dose
# Time-based split
split_idx = int(len(results) * 0.80)
train_r = results[:split_idx]
test_r  = results[split_idx:]

def build_Xy(rlist):
    X, y = [], []
    for r in rlist:
        s1 = r['s1'] if r['s1'] is not None else 10.0   # median impute
        X.append([r['prev_fasting'], r['prev_hypo'], s1, r['actual'] - r['diff']])  # anchor = actual - diff = suggested... actually use prev dose
        y.append(r['actual'])
    return np.array(X), np.array(y)

# Rebuild with explicit prev_dose
results2 = []
for i, n in enumerate(nights):
    if i == 0: continue
    prev = nights[i-1]
    suggested, _ = thomas_rules(prev['dose'], prev['fasting'], prev['hypo_events'], n['s1'])
    if suggested is None: continue
    results2.append({
        'date':         n['date'],
        'actual':       n['dose'],
        'prev_dose':    prev['dose'],
        'prev_fasting': prev['fasting'],
        'prev_hypo':    prev['hypo_events'],
        's1':           n['s1'] if n['s1'] is not None else 10.0,
        'tir':          n['tir'],
        'fasting':      n['fasting'],
        'hypo_events':  n['hypo_events'],
        'suggested':    suggested,
        'diff':         n['dose'] - suggested,
    })

split2 = int(len(results2)*0.80)
train2 = results2[:split2]
test2  = results2[split2:]

def to_Xy(rlist):
    X = np.array([[r['prev_fasting'], float(r['prev_hypo']),
                   r['s1'], r['prev_dose']] for r in rlist])
    y = np.array([r['actual'] for r in rlist])
    return X, y

X_train, y_train = to_Xy(train2)
X_test,  y_test  = to_Xy(test2)

# Decision tree — shallow for interpretability
dt = DecisionTreeRegressor(max_depth=4, min_samples_leaf=10, random_state=42)
dt.fit(X_train, y_train)
dt_train_mae = mean_absolute_error(y_train, dt.predict(X_train))
dt_test_mae  = mean_absolute_error(y_test,  dt.predict(X_test))

# Thomas's rules MAE on same split
rules_preds_test = [r['suggested'] for r in test2]
rules_test_mae   = mean_absolute_error(y_test, rules_preds_test)

# Anchor-only baseline (predict yesterday's dose unchanged)
anchor_preds_test = [r['prev_dose'] for r in test2]
anchor_test_mae   = mean_absolute_error(y_test, anchor_preds_test)

print(f'\n  Train: {len(train2)} nights | Test: {len(test2)} nights')
print(f'\n  {"Model":<35} {"Test MAE (dose units)":>22}')
print(f'  {"-"*58}')
print(f'  {"Anchor only (no adjustment)":<35} {anchor_test_mae:>21.2f}u')
print(f'  {"Thomas\'s rules":<35} {rules_test_mae:>21.2f}u')
print(f'  {"Decision Tree (learned)":<35} {dt_test_mae:>21.2f}u')

print(f'\n  Decision Tree structure (feature order: prev_fasting, prev_hypo, s1, prev_dose):')
print(export_text(dt, feature_names=['prev_fasting','prev_hypo','s1','prev_dose'], max_depth=4))

# Feature importance
print(f'  Feature importance (predicting actual dose used):')
for fname, imp in zip(['prev_fasting','prev_hypo','s1','prev_dose'], dt.feature_importances_):
    bar = '#' * int(imp * 40)
    print(f'    {fname:<15} {imp:.3f}  {bar}')

# ── TONIGHT'S SUGGESTION FROM RULES ───────────────────────────────────────────
print(f'\n{"="*70}')
print('TONIGHT\'S SUGGESTION — THOMAS\'S RULES')
print('='*70)

today = max(dt.date() for dt,_ in glucose_list)
yesterday = today - timedelta(days=1)

last_night = next((n for n in reversed(nights) if n['date'] == yesterday), None)
today_s1   = strain_idx.get(today, {}).get('strain')

if last_night:
    suggested, reasoning = thomas_rules(
        yesterday_dose = last_night['dose'],
        fasting        = last_night['fasting'],
        hypo_events    = last_night['hypo_events'],
        s1             = today_s1,
    )
    print(f'\n  Last night ({yesterday}):')
    print(f'    Dose injected : {last_night["dose"]:.0f}u')
    print(f'    Fasting (wake): {last_night["fasting"]} mmol/L')
    print(f'    Hypo events   : {last_night["hypo_events"]}')
    print(f'    TIR (4-10)    : {last_night["tir"]}%')
    print(f'\n  Today s1 (strain): {today_s1 if today_s1 else "not yet available"}')
    print(f'\n  Rule-based suggestion: {suggested}u')
    print(f'  Reasoning:')
    for r in reasoning:
        print(f'    * {r}')
else:
    print('  No data for yesterday — cannot produce suggestion.')
