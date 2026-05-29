"""Inferential predictor analysis (E1 Phase 5 / R8).

Question: of the signals available at dose time, which carry independent
information about whether the dose was correct (second-half slope == 0)?

Method: three convergent measurements per candidate signal -
  1. Direct Spearman vs sh_slope.
  2. Partial Spearman vs sh_slope after removing controls (s1, prev_dose, inj_g).
  3. Spearman vs inferred_optimal_dose (the dose that, per the regression model,
     would have landed at flat slope holding the night's other signals fixed).

The inferred-dose path follows the original Phase A2 plan but uses a
data-supported model spec (chosen via the model-comparison section) rather
than the linear-additive default if a stronger spec is supported.

Promotion is HIGH iff >=2 of 3 metrics agree at p<0.05 with consistent sign.

Run: py -X utf8 scripts/inferential_predictor.py
"""

import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'scripts'))

from dexcom_loader import load_dexcom, load_bolus_combined
from whoop_loader import load_whoop
from strain_binning_analysis import build_nights, apply_filters
from strain_regression_analysis import fit_ols

OUT_DIR  = PROJECT_ROOT / 'output'
OUT_DIR.mkdir(exist_ok=True)
OUT_FILE = OUT_DIR / 'inferential_predictor.txt'


def spearman_np(x, y):
    if len(x) < 5:
        return None, None
    r, p = stats.spearmanr(x, y)
    return float(r), float(p)


def multi_residuals(X, y):
    """OLS residuals of y regressed on X (X already includes intercept column)."""
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return y - X @ beta


def f_test_nested(rss_small, rss_big, df_small, df_big, k_added):
    """F-test for nested models. Returns (F, p)."""
    f = ((rss_small - rss_big) / k_added) / (rss_big / df_big)
    p = 1.0 - stats.f.cdf(f, k_added, df_big)
    return float(f), float(p)


def main():
    print('Loading data...')
    glucose_list, basal_list, _ = load_dexcom()
    strain_idx    = load_whoop()
    bolus_events  = load_bolus_combined()
    nights        = build_nights(glucose_list, basal_list, strain_idx)

    # Re-walk basal_list to attach inj_dt and bolus context to each night
    basal_by_date = {}
    for inj_dt, d, _ in basal_list:
        if inj_dt.hour >= 18 and d not in basal_by_date:
            basal_by_date[d] = inj_dt

    for n in nights:
        inj_dt = basal_by_date.get(n['date'])
        n['inj_dt']        = inj_dt
        n['bolus_4h_pre']  = sum(u for dt, u in bolus_events
                                  if inj_dt is not None
                                  and inj_dt - timedelta(hours=4) <= dt <= inj_dt)
        n['bolus_during']  = sum(u for dt, u in bolus_events
                                  if inj_dt is not None
                                  and inj_dt < dt <= inj_dt + timedelta(hours=9))
        # Recovery/HRV/RHR/sleep_perf from strain index
        wd = strain_idx.get(n['date'], {})
        n['recovery']   = wd.get('recovery')
        n['hrv']        = wd.get('hrv')
        n['rhr']        = wd.get('rhr')
        n['sleep_perf'] = wd.get('sleep_perf')

    usable, reasons = apply_filters(nights)
    print(f'Usable nights: {len(usable)} '
          f'(drops: {reasons})')

    if len(usable) < 50:
        print('Not enough nights. Aborting.')
        return

    # ── DATA MATRICES ─────────────────────────────────────────────────────────
    dose   = np.array([n['dose']             for n in usable], dtype=float)
    s1     = np.array([n['s1']               for n in usable], dtype=float)
    pfast  = np.array([n['prev_fasting']     for n in usable], dtype=float)
    phypos = np.array([n['prev_hypo_events'] for n in usable], dtype=float)
    inj_g  = np.array([n['inj_g']            for n in usable], dtype=float)
    slope  = np.array([n['sh_slope']         for n in usable], dtype=float)
    n_obs  = len(usable)

    lines = []
    def w(s=''):
        lines.append(s)
        print(s)

    # ── SECTION 1: MODEL DIAGNOSTICS ──────────────────────────────────────────
    w('=' * 78)
    w('SECTION 1 - MODEL DIAGNOSTICS (choose the spec for inferred dose)')
    w('=' * 78)

    ones = np.ones(n_obs)
    X_m1 = np.column_stack([ones, dose, s1, pfast, phypos])
    X_m2 = np.column_stack([ones, dose, s1, s1**2, pfast, phypos])
    X_m3 = np.column_stack([ones, dose, s1, dose * s1, pfast, phypos])
    X_m4 = np.column_stack([ones, dose, s1, dose * s1, s1**2, pfast, phypos])

    specs = [
        ('M1 baseline (linear additive)',           X_m1, ['intercept','dose','s1','prev_fasting','prev_hypos']),
        ('M2 + quadratic strain (s1^2)',            X_m2, ['intercept','dose','s1','s1^2','prev_fasting','prev_hypos']),
        ('M3 + dose*s1 interaction',                X_m3, ['intercept','dose','s1','dose*s1','prev_fasting','prev_hypos']),
        ('M4 + interaction + quadratic',            X_m4, ['intercept','dose','s1','dose*s1','s1^2','prev_fasting','prev_hypos']),
    ]

    fits = []
    for label, X, names in specs:
        beta, se, t, p, r2, n, k = fit_ols(X, slope)
        rss = float(((slope - X @ beta) ** 2).sum())
        df  = n - k
        fits.append({'label': label, 'X': X, 'names': names, 'beta': beta, 'se': se,
                     't': t, 'p': p, 'r2': r2, 'rss': rss, 'df': df, 'k': k})

    w(f'{"Spec":<46} {"R^2":>7} {"adjR^2":>8} {"k":>3} {"df":>4}')
    for f in fits:
        adj_r2 = 1 - (1 - f['r2']) * (n_obs - 1) / f['df']
        w(f'  {f["label"]:<44} {f["r2"]:>6.4f}  {adj_r2:>7.4f}  {f["k"]:>3} {f["df"]:>4}')
    w('')

    # Nested F-tests: M2 vs M1, M3 vs M1, M4 vs M3
    fM1, fM2, fM3, fM4 = fits
    w('Nested F-tests (does the added term improve fit?):')
    for big, small, label in [(fM2, fM1, 'M2 over M1 (s1^2)'),
                               (fM3, fM1, 'M3 over M1 (dose*s1)'),
                               (fM4, fM3, 'M4 over M3 (s1^2 added)')]:
        F, p = f_test_nested(small['rss'], big['rss'], small['df'], big['df'],
                              big['k'] - small['k'])
        w(f'  {label:<28} F={F:>6.2f}  p={p:>7.4f}  {"PASS" if p<0.05 else "ns"}')
    w('')

    # Selection rule: prefer the most complex spec that passes its F-test
    # against the next-simpler nested model, and where beta_dose stays significant
    chosen = fM1
    chosen_label = 'M1 (baseline)'
    _, p_m2 = f_test_nested(fM1['rss'], fM2['rss'], fM1['df'], fM2['df'], 1)
    _, p_m3 = f_test_nested(fM1['rss'], fM3['rss'], fM1['df'], fM3['df'], 1)
    if p_m2 < 0.05 and fM2['p'][1] < 0.10:  # dose stays at least marginal
        chosen, chosen_label = fM2, 'M2 (+ s1^2)'
    if p_m3 < 0.05 and fM3['p'][1] < 0.10:
        chosen, chosen_label = fM3, 'M3 (+ dose*s1)'
    # M4 only if it adds significantly over M3
    _, p_m4 = f_test_nested(fM3['rss'], fM4['rss'], fM3['df'], fM4['df'], 1)
    if p_m4 < 0.05 and chosen is fM3:
        chosen, chosen_label = fM4, 'M4 (+ s1^2 + dose*s1)'

    w(f'Chosen spec for inferred-dose computation: {chosen_label}')
    w(f'  Chosen R^2          : {chosen["r2"]:.4f}')
    w(f'  beta_dose p-value   : {chosen["p"][1]:.4f}  '
      f'{"(usable for inversion)" if chosen["p"][1]<0.10 else "(WEAK - inferred dose unreliable)"}')
    w('')
    w('Coefficients (chosen model):')
    w(f'  {"name":<14} {"beta":>11} {"SE":>9} {"t":>7} {"p":>8}')
    for i, name in enumerate(chosen['names']):
        w(f'  {name:<14} {chosen["beta"][i]:>+11.5f} {chosen["se"][i]:>9.5f} '
          f'{chosen["t"][i]:>+7.2f} {chosen["p"][i]:>8.4f}')
    w('')

    # ── SECTION 2: INFERRED OPTIMAL DOSE (per night) ──────────────────────────
    w('=' * 78)
    w('SECTION 2 - INFERRED OPTIMAL DOSE PER NIGHT (chosen spec)')
    w('=' * 78)

    # Solve sh_slope = 0 for dose, holding other terms fixed.
    # Each spec has a different inverse formula:
    beta_c = chosen['beta']
    names  = chosen['names']
    inferred = np.full(n_obs, np.nan)

    for i in range(n_obs):
        if chosen is fM1:
            # 0 = b0 + b_dose*d + b_s1*s1 + b_pf*pfast + b_ph*phypos
            num = -(beta_c[0] + beta_c[2]*s1[i] + beta_c[3]*pfast[i] + beta_c[4]*phypos[i])
            den = beta_c[1]
        elif chosen is fM2:
            # adds s1^2 term
            num = -(beta_c[0] + beta_c[2]*s1[i] + beta_c[3]*s1[i]**2
                    + beta_c[4]*pfast[i] + beta_c[5]*phypos[i])
            den = beta_c[1]
        elif chosen is fM3:
            # 0 = b0 + (b_dose + b_int*s1)*dose + b_s1*s1 + ...
            num = -(beta_c[0] + beta_c[2]*s1[i] + beta_c[4]*pfast[i] + beta_c[5]*phypos[i])
            den = beta_c[1] + beta_c[3]*s1[i]
        else:  # M4
            num = -(beta_c[0] + beta_c[2]*s1[i] + beta_c[4]*s1[i]**2
                    + beta_c[5]*pfast[i] + beta_c[6]*phypos[i])
            den = beta_c[1] + beta_c[3]*s1[i]
        inferred[i] = num / den if abs(den) > 1e-6 else np.nan

    # Mask absurd values (outside [5, 50] u) to avoid corrupting the rank tests
    mask = np.isfinite(inferred) & (inferred >= 5) & (inferred <= 50)
    w(f'Inferred-dose valid range mask: {int(mask.sum())} / {n_obs} nights '
      f'(masked: extrapolation outside 5-50u or undefined denominator)')
    w(f'Inferred dose quantiles (valid): '
      f'p10={np.quantile(inferred[mask], 0.10):.1f} '
      f'p50={np.quantile(inferred[mask], 0.50):.1f} '
      f'p90={np.quantile(inferred[mask], 0.90):.1f}')
    w(f'Actual dose quantiles:           '
      f'p10={np.quantile(dose, 0.10):.1f} '
      f'p50={np.quantile(dose, 0.50):.1f} '
      f'p90={np.quantile(dose, 0.90):.1f}')
    w('')

    # Partial-residuals controls: s1, prev_dose, inj_g.
    # NB: when a candidate IS one of these controls, the partial r is ~0 by
    # construction; tiering still works because direct + inferential remain.
    prev_dose = np.array([n['prev_dose'] if n['prev_dose'] is not None else np.nan
                          for n in usable])
    X_ctrl = np.column_stack([ones, s1,
                              np.nan_to_num(prev_dose, nan=float(np.nanmean(prev_dose))),
                              inj_g])
    slope_resid = multi_residuals(X_ctrl, slope)

    # ── SECTION 3: CANDIDATE SIGNAL RANKING ───────────────────────────────────
    w('=' * 78)
    w('SECTION 3 - CANDIDATE SIGNAL RANKING')
    w('=' * 78)

    candidates = [
        ('s1',           's1 (today strain)'),
        ('recovery',     'recovery'),
        ('hrv',          'hrv'),
        ('rhr',          'rhr'),
        ('sleep_perf',   'sleep_perf'),
        ('prev_dose',    'prev_dose'),
        ('prev_fasting', 'prev_fasting'),
        ('prev_hypo_events', 'prev_hypos'),
        ('inj_g',        'inj_g (injection-time glucose)'),
        ('bolus_4h_pre', 'bolus_4h_pre'),
        ('bolus_during', 'bolus_during_night'),
        ('hypo_events',  'hypo_events (tonight)'),
    ]

    w(f'{"Signal":<32} {"DirectR":>9} {"Direct p":>10} {"PartialR":>10} '
      f'{"Partial p":>11} {"InfR":>7} {"Inf p":>9}  {"Tier":>6}')
    w('-' * 105)

    results = []
    for key, label in candidates:
        vals = np.array([n.get(key) if n.get(key) is not None else np.nan
                          for n in usable], dtype=float)
        v_mask = np.isfinite(vals)
        if v_mask.sum() < 30:
            w(f'  {label:<30}  (n<30, skipped)')
            continue

        r_dir, p_dir = spearman_np(vals[v_mask], slope[v_mask])
        r_par, p_par = spearman_np(vals[v_mask], slope_resid[v_mask])
        inf_mask = v_mask & mask
        if inf_mask.sum() >= 30:
            r_inf, p_inf = spearman_np(vals[inf_mask], inferred[inf_mask])
        else:
            r_inf, p_inf = None, None

        # Convergence: count metrics with p<0.05; check sign consistency
        signed = [(r, p) for r, p in [(r_dir, p_dir), (r_par, p_par), (r_inf, p_inf)]
                   if r is not None and p is not None]
        sig = [(r, p) for r, p in signed if p < 0.05]
        if len(sig) >= 2:
            signs = {1 if r > 0 else -1 for r, _ in sig}
            tier = 'HIGH' if len(signs) == 1 else 'MIXED'
        elif len(sig) == 1:
            tier = 'MED'
        else:
            tier = 'LOW'

        fmt = lambda x: f'{x:+.3f}' if x is not None else '   n/a '
        fmtp = lambda x: f'{x:.4f}' if x is not None else '  n/a  '
        w(f'  {label:<30} {fmt(r_dir):>9} {fmtp(p_dir):>10} {fmt(r_par):>10} '
          f'{fmtp(p_par):>11} {fmt(r_inf):>7} {fmtp(p_inf):>9}  {tier:>6}')
        results.append({'key': key, 'label': label, 'tier': tier,
                        'r_dir': r_dir, 'p_dir': p_dir,
                        'r_par': r_par, 'p_par': p_par,
                        'r_inf': r_inf, 'p_inf': p_inf})

    w('')
    w('Tier rules:')
    w('  HIGH   - >=2/3 metrics significant (p<0.05) and same direction')
    w('  MIXED  - >=2/3 significant but directions disagree (signal noisy)')
    w('  MED    - 1/3 metrics significant')
    w('  LOW    - 0/3 significant')
    w('')
    w('Controls used in PartialR: s1, prev_dose, inj_g.')
    w('Inferred dose computed per Section 2 using the chosen spec.')
    w(f'beta_dose p in chosen spec = {chosen["p"][1]:.4f}; '
      f'{"inferential column is usable" if chosen["p"][1]<0.10 else "inferential column should be treated as exploratory only"}')
    w('')

    # ── SECTION 5: PROMOTION RECOMMENDATION ───────────────────────────────────
    w('=' * 78)
    w('SECTION 4 - PROMOTION RECOMMENDATION FOR PHASE 6 RULE DESIGN')
    w('=' * 78)
    high = [r for r in results if r['tier'] == 'HIGH']
    med  = [r for r in results if r['tier'] == 'MED']
    mixed = [r for r in results if r['tier'] == 'MIXED']
    low  = [r for r in results if r['tier'] == 'LOW']

    w(f'HIGH  (promote to rule)            : {", ".join(r["label"] for r in high) or "(none)"}')
    w(f'MED   (consider, watch reliability): {", ".join(r["label"] for r in med) or "(none)"}')
    w(f'MIXED (noisy direction)            : {", ".join(r["label"] for r in mixed) or "(none)"}')
    w(f'LOW   (drop from candidate list)   : {", ".join(r["label"] for r in low) or "(none)"}')
    w('')
    w('CAVEATS')
    w(f'  Chosen R^2 = {chosen["r2"]:.4f}. Most slope variance is unexplained;')
    w(f'  promotion tiers reflect rank consistency, not absolute predictive power.')
    if chosen["p"][1] >= 0.10:
        w(f'  beta_dose is NOT significant (p={chosen["p"][1]:.3f}); the inferred-dose')
        w(f'  column is exploratory. Tier was decided by direct + partial metrics.')

    text = '\n'.join(lines) + '\n'
    OUT_FILE.write_text(text, encoding='utf-8')
    print(f'\nReport written to: {OUT_FILE}')


if __name__ == '__main__':
    main()
