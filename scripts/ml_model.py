"""
T1D Basal ML Model — Thomas Bloch-Nielsen
==========================================
Predicts overnight TIR% given (inj_g, s1, dose).
Optimizes over dose at recommendation time to suggest tonight's dose.

Approach:
  - Features: inj_g, s1 (imputed with median when missing), dose
  - Target: TIR% (5–8 mmol/L)
  - Time-based 80/20 train/test split (no leakage)
  - Models: Linear baseline, Random Forest, Gradient Boosting
  - Recommendation: predict TIR for dose 14–30u given tonight's profile
"""

import csv, glob, os, math
from datetime import datetime, timedelta, date
from collections import defaultdict
from whoop_loader import load_whoop
from dexcom_loader import load_dexcom

import numpy as np
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.inspection import permutation_importance

TGT_LO, TGT_HI = 5.0, 8.0
HYPO_THR  = 4.0

# ── DATA LOADING ───────────────────────────────────────────────────────────────
def rolling_avg(d, n, idx):
    v=[idx[d-timedelta(days=i)]['strain'] for i in range(n)
       if (d-timedelta(days=i)) in idx and idx[d-timedelta(days=i)]['strain'] is not None]
    return round(sum(v)/len(v),2) if v else None

def overnight_stats(inj_dt, glucose_list):
    end=datetime.combine(inj_dt.date()+timedelta(days=1),datetime.min.time().replace(hour=7))
    rdgs=[(dt,v) for dt,v in glucose_list if inj_dt<=dt<=end]
    if len(rdgs)<6: return None
    vals=[v for _,v in rdgs]; n=len(vals)
    hypo_idx=next((i for i,v in enumerate(vals) if v<HYPO_THR),None)
    hypo_corr=hypo_idx is not None and max(vals[hypo_idx:])>7.0
    return {
        'tir':     round(sum(1 for v in vals if TGT_LO<=v<=TGT_HI)/n*100,1),
        'fasting': round(vals[-1],1),
        'mean':    round(sum(vals)/n,1),
        'inj_g':   round(vals[0],1),
        'hypo_correction': hypo_corr,
    }

# ── BUILD DATASET ──────────────────────────────────────────────────────────────
glucose_list, basal_list, bolus = load_dexcom()
strain_idx = load_whoop()

nights = []
for inj_dt, inj_date, dose in basal_list:
    if inj_dt.hour < 18: continue
    st = overnight_stats(inj_dt, glucose_list)
    if not st or st['hypo_correction']: continue
    s1  = strain_idx.get(inj_date, {}).get('strain')
    hrv = strain_idx.get(inj_date, {}).get('hrv')
    rec = strain_idx.get(inj_date, {}).get('recovery')
    rhr = strain_idx.get(inj_date, {}).get('rhr')
    s7  = rolling_avg(inj_date, 7, strain_idx)
    nights.append({
        'date':     inj_date,
        'dose':     dose,
        'inj_g':    st['inj_g'],
        's1':       s1,
        's7':       s7,
        'hrv':      hrv,
        'recovery': rec,
        'rhr':      rhr,
        'tir':      st['tir'],
        'fasting':  st['fasting'],
        'mean_g':   st['mean'],
    })

nights.sort(key=lambda x: x['date'])
print(f'Clean nights for modelling: {len(nights)}')
print(f'Date range: {nights[0]["date"]} → {nights[-1]["date"]}')

# ── FEATURES ───────────────────────────────────────────────────────────────────
# Core features: inj_g, s1, dose
# Extended: + hrv, recovery, rhr, s7
# s1 missing in ~5% of nights — imputed with median in pipeline

FEATURES_CORE = ['inj_g', 's1', 'dose']
FEATURES_EXT  = ['inj_g', 's1', 'dose', 'hrv', 'recovery', 'rhr']

def build_matrix(nights, features):
    X = np.array([[n.get(f) for f in features] for n in nights], dtype=float)
    y_tir     = np.array([n['tir']     for n in nights], dtype=float)
    y_fasting = np.array([n['fasting'] for n in nights], dtype=float)
    return X, y_tir, y_fasting

# ── TIME-BASED SPLIT ───────────────────────────────────────────────────────────
split_idx = int(len(nights) * 0.80)
train_nights = nights[:split_idx]
test_nights  = nights[split_idx:]

print(f'\nTrain: {len(train_nights)} nights ({train_nights[0]["date"]} → {train_nights[-1]["date"]})')
print(f'Test:  {len(test_nights)} nights  ({test_nights[0]["date"]} → {test_nights[-1]["date"]})')

# ── MODELS ─────────────────────────────────────────────────────────────────────
def make_pipeline(model):
    return Pipeline([
        ('impute', SimpleImputer(strategy='median')),
        ('scale',  StandardScaler()),
        ('model',  model),
    ])

models = {
    'Linear (Ridge)':       make_pipeline(Ridge(alpha=1.0)),
    'Random Forest':        make_pipeline(RandomForestRegressor(
                                n_estimators=300, max_depth=4,
                                min_samples_leaf=8, random_state=42)),
    'Gradient Boosting':    make_pipeline(GradientBoostingRegressor(
                                n_estimators=200, max_depth=3,
                                learning_rate=0.05, min_samples_leaf=8,
                                subsample=0.8, random_state=42)),
}

print('\n' + '='*65)
print('MODEL EVALUATION — TIR% PREDICTION')
print('='*65)

best_model = None
best_mae   = float('inf')
best_name  = ''
best_feats = FEATURES_CORE

for feat_label, features in [('Core features (inj_g, s1, dose)', FEATURES_CORE),
                               ('Extended (+hrv, recovery, rhr)',   FEATURES_EXT)]:
    print(f'\n  Features: {feat_label}')
    print(f'  {"Model":<25} {"Train MAE":>10} {"Test MAE":>10} {"Test R²":>9}')
    print(f'  {"-"*55}')

    X_train, y_train, _ = build_matrix(train_nights, features)
    X_test,  y_test,  _ = build_matrix(test_nights,  features)

    for name, _ in models.items():
        # Fresh pipeline each time — avoid cross-feature contamination
        if 'Linear' in name:
            pipe = make_pipeline(Ridge(alpha=1.0))
        elif 'Forest' in name:
            pipe = make_pipeline(RandomForestRegressor(
                n_estimators=300, max_depth=4, min_samples_leaf=8, random_state=42))
        else:
            pipe = make_pipeline(GradientBoostingRegressor(
                n_estimators=200, max_depth=3, learning_rate=0.05,
                min_samples_leaf=8, subsample=0.8, random_state=42))

        pipe.fit(X_train, y_train)
        train_pred = pipe.predict(X_train)
        test_pred  = pipe.predict(X_test)
        train_mae  = mean_absolute_error(y_train, train_pred)
        test_mae   = mean_absolute_error(y_test,  test_pred)
        test_r2    = r2_score(y_test, test_pred)

        if feat_label.startswith('Core') and test_mae < best_mae:
            best_mae   = test_mae
            best_model = pipe
            best_name  = name
            best_feats = features

        gap = test_mae - train_mae
        flag = ' [overfit?]' if gap > 8 else (' [train>test]' if gap < 0 else '')
        print(f'  {name:<25} {train_mae:>9.1f}  {test_mae:>9.1f}  {test_r2:>8.3f}{flag}')

print(f'\n  Best model (core features): {best_name}  test MAE={best_mae:.1f}%')

# ── RESIDUAL ANALYSIS ──────────────────────────────────────────────────────────
print('\n' + '='*65)
print('TEST SET RESIDUALS — Best model on core features')
print('='*65)

X_test_core, y_test_core, _ = build_matrix(test_nights, FEATURES_CORE)
preds = best_model.predict(X_test_core)
residuals = y_test_core - preds

print(f'\n  Mean residual    : {np.mean(residuals):+.1f}% (bias)')
print(f'  Std of residuals : {np.std(residuals):.1f}%')
print(f'  Within ±10% TIR  : {np.mean(np.abs(residuals)<=10)*100:.1f}% of nights')
print(f'  Within ±20% TIR  : {np.mean(np.abs(residuals)<=20)*100:.1f}% of nights')

print(f'\n  {"Date":<12} {"Dose":>5}  {"inj_g":>6}  {"s1":>5}  {"Actual TIR":>10}  {"Pred TIR":>9}  {"Residual":>9}')
print(f'  {"-"*65}')
for i, n in enumerate(test_nights):
    s1s = f'{n["s1"]:.1f}' if n['s1'] else '-'
    resid = y_test_core[i] - preds[i]
    flag = ' !' if abs(resid) > 25 else ''
    print(f'  {str(n["date"]):<12} {n["dose"]:>4.0f}u  {n["inj_g"]:>5.1f}  {s1s:>5}  '
          f'{y_test_core[i]:>9.1f}%  {preds[i]:>8.1f}%  {resid:>+8.1f}%{flag}')

# ── FEATURE IMPORTANCE ─────────────────────────────────────────────────────────
print('\n' + '='*65)
print('FEATURE IMPORTANCE (permutation, test set)')
print('='*65)
perm = permutation_importance(best_model, X_test_core, y_test_core,
                               n_repeats=30, random_state=42)
for i, fname in enumerate(FEATURES_CORE):
    print(f'  {fname:<12}  mean decrease MAE: {perm.importances_mean[i]:+.2f}  '
          f'std: {perm.importances_std[i]:.2f}')

# ── TONIGHT'S RECOMMENDATION ───────────────────────────────────────────────────
print('\n' + '='*65)
print('TONIGHT\'S DOSE RECOMMENDATION')
print('='*65)

# Get tonight's profile from latest CGM
today = max(dt.date() for dt, _ in glucose_list)
tonight_inj_g = next((v for dt,v in reversed(glucose_list) if dt.date()==today), None)
today_s1 = strain_idx.get(today, {}).get('strain')

print(f'\n  Tonight inj_g : {tonight_inj_g:.1f} mmol/L' if tonight_inj_g else '\n  Tonight inj_g : unknown')
print(f'  Tonight s1    : {today_s1:.1f}' if today_s1 else '  Tonight s1    : not yet available (using median imputation)')

# Predict TIR for each candidate dose
candidate_doses = list(range(14, 31))
profile = [[tonight_inj_g if tonight_inj_g else 9.0,
            today_s1 if today_s1 else float('nan'),
            d] for d in candidate_doses]
X_pred = np.array(profile, dtype=float)
tir_preds = best_model.predict(X_pred)

print(f'\n  Predicted TIR% by dose ({best_name}):')
print(f'  {"Dose":>5}  {"Pred TIR%":>10}  {"Bar"}')
print(f'  {"-"*45}')
best_dose_idx = int(np.argmax(tir_preds))
for i, (d, t) in enumerate(zip(candidate_doses, tir_preds)):
    bar = '#' * max(0, int(t / 2))
    marker = ' <-- BEST' if i == best_dose_idx else ''
    print(f'  {d:>4}u  {t:>9.1f}%  {bar}{marker}')

print(f'\n  Model recommendation: {candidate_doses[best_dose_idx]}u  '
      f'(predicted TIR {tir_preds[best_dose_idx]:.1f}%)')

# Uncertainty: show ±1 dose range above 80% of peak prediction
peak = tir_preds[best_dose_idx]
threshold = peak * 0.90
good_doses = [d for d, t in zip(candidate_doses, tir_preds) if t >= threshold]
if len(good_doses) > 1:
    print(f'  Doses within 90% of peak TIR: {min(good_doses)}–{max(good_doses)}u')

# ── BASELINE COMPARISON ────────────────────────────────────────────────────────
print('\n' + '='*65)
print('BASELINE COMPARISON: ML vs naive mean predictor')
print('='*65)
naive_pred = np.mean(y_train)
naive_mae  = mean_absolute_error(y_test_core, np.full_like(y_test_core, naive_pred))
print(f'  Naive (always predict mean={naive_pred:.1f}%)  MAE={naive_mae:.1f}%')
print(f'  {best_name:<30}               MAE={best_mae:.1f}%')
print(f'  Improvement over naive: {naive_mae - best_mae:.1f}% MAE reduction')
