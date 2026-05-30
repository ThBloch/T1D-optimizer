"""
T1D Basal ML Model (research)
=============================
Predicts overnight TIR% given (inj_g, s1, dose). Compares pipeline models
against a naive-mean baseline. Reports feature importance and per-night
residuals. Not the production path; see dexcom_fetch.py for suggestion.

Approach:
  - Features: inj_g, s1 (imputed with median when missing), dose
  - Target: TIR% (5-8 mmol/L)
  - Time-based 80/20 train/test split (no leakage)
  - Models: Linear baseline, Random Forest, Gradient Boosting
"""

from whoop_loader import load_whoop
from dexcom_loader import load_dexcom
from night_stats import overnight_window, night_stats

import numpy as np
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.inspection import permutation_importance


def main():
    # ── DATA LOADING ───────────────────────────────────────────────────────────────
    glucose_list, basal_list, _ = load_dexcom()
    strain_idx = load_whoop()

    # ── BUILD DATASET ──────────────────────────────────────────────────────────────
    nights = []
    for inj_dt, inj_date, dose in basal_list:
        if inj_dt.hour < 18: continue
        st = night_stats(overnight_window(inj_dt, glucose_list))
        if not st or st['hypo_correction']: continue
        s1  = strain_idx.get(inj_date, {}).get('strain')
        hrv = strain_idx.get(inj_date, {}).get('hrv')
        rec = strain_idx.get(inj_date, {}).get('recovery')
        rhr = strain_idx.get(inj_date, {}).get('rhr')
        nights.append({
            'date':     inj_date,
            'dose':     dose,
            'inj_g':    st['inj_g'],
            's1':       s1,
            'hrv':      hrv,
            'recovery': rec,
            'rhr':      rhr,
            'tir':      st['tir'],
            'fasting':  st['fasting'],
            'mean_g':   st['mean'],
        })

    nights.sort(key=lambda x: x['date'])
    print(f'Clean nights for modelling: {len(nights)}')
    print(f'Date range: {nights[0]["date"]} -> {nights[-1]["date"]}')

    # ── FEATURES ───────────────────────────────────────────────────────────────────
    # Core features: inj_g, s1, dose
    # Extended: + hrv, recovery, rhr
    # s1 missing in ~5% of nights - imputed with median in pipeline

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

    print(f'\nTrain: {len(train_nights)} nights ({train_nights[0]["date"]} -> {train_nights[-1]["date"]})')
    print(f'Test:  {len(test_nights)} nights  ({test_nights[0]["date"]} -> {test_nights[-1]["date"]})')

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
    print('MODEL EVALUATION - TIR% PREDICTION')
    print('='*65)

    best_model = None
    best_mae   = float('inf')
    best_name  = ''

    for feat_label, features in [('Core features (inj_g, s1, dose)', FEATURES_CORE),
                                   ('Extended (+hrv, recovery, rhr)',   FEATURES_EXT)]:
        print(f'\n  Features: {feat_label}')
        print(f'  {"Model":<25} {"Train MAE":>10} {"Test MAE":>10} {"Test R²":>9}')
        print(f'  {"-"*55}')

        X_train, y_train, _ = build_matrix(train_nights, features)
        X_test,  y_test,  _ = build_matrix(test_nights,  features)

        for name, _ in models.items():
            # Fresh pipeline each time - avoid cross-feature contamination
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

            gap = test_mae - train_mae
            flag = ' [overfit?]' if gap > 8 else (' [train>test]' if gap < 0 else '')
            print(f'  {name:<25} {train_mae:>9.1f}  {test_mae:>9.1f}  {test_r2:>8.3f}{flag}')

    print(f'\n  Best model (core features): {best_name}  test MAE={best_mae:.1f}%')

    # ── RESIDUAL ANALYSIS ──────────────────────────────────────────────────────────
    print('\n' + '='*65)
    print('TEST SET RESIDUALS - Best model on core features')
    print('='*65)

    X_test_core, y_test_core, _ = build_matrix(test_nights, FEATURES_CORE)
    preds = best_model.predict(X_test_core)
    residuals = y_test_core - preds

    print(f'\n  Mean residual    : {np.mean(residuals):+.1f}% (bias)')
    print(f'  Std of residuals : {np.std(residuals):.1f}%')
    print(f'  Within +/-10% TIR  : {np.mean(np.abs(residuals)<=10)*100:.1f}% of nights')
    print(f'  Within +/-20% TIR  : {np.mean(np.abs(residuals)<=20)*100:.1f}% of nights')

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

    # ── BASELINE COMPARISON ────────────────────────────────────────────────────────
    print('\n' + '='*65)
    print('BASELINE COMPARISON: ML vs naive mean predictor')
    print('='*65)
    naive_pred = np.mean(y_train)
    naive_mae  = mean_absolute_error(y_test_core, np.full_like(y_test_core, naive_pred))
    print(f'  Naive (always predict mean={naive_pred:.1f}%)  MAE={naive_mae:.1f}%')
    print(f'  {best_name:<30}               MAE={best_mae:.1f}%')
    print(f'  Improvement over naive: {naive_mae - best_mae:.1f}% MAE reduction')


if __name__ == '__main__':
    main()
