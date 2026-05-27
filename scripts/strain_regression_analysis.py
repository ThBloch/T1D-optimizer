"""Strain regression analysis (E1, Phase A2).

Fits a linear regression of second-half overnight glucose slope on
(dose, strain, dose*strain interaction, prev_fasting, prev_hypos), then
solves for dose_optimal(s1) and maps strain ranges to integer adjustments.

Reuses build_nights + apply_filters from strain_binning_analysis.py.
Output: stdout + output/strain_regression.txt.

Run: py -X utf8 scripts/strain_regression_analysis.py
"""

import sys
from pathlib import Path
from statistics import mean

import numpy as np
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'scripts'))

from dexcom_loader import load_dexcom
from whoop_loader import load_whoop
from strain_binning_analysis import build_nights, apply_filters

OUT_DIR  = PROJECT_ROOT / 'output'
OUT_DIR.mkdir(exist_ok=True)
OUT_FILE = OUT_DIR / 'strain_regression.txt'

ADJ_LEVELS  = [+3, +2, +1, 0, -1, -2]
STRAIN_GRID = np.arange(4.0, 19.01, 0.25)


def fit_ols(X, y):
    n, k = X.shape
    XtX = X.T @ X
    XtX_inv = np.linalg.inv(XtX)
    beta = XtX_inv @ X.T @ y
    yhat = X @ beta
    resid = y - yhat
    df = n - k
    sigma2 = (resid @ resid) / df
    var_beta = sigma2 * XtX_inv
    se = np.sqrt(np.diag(var_beta))
    t = beta / se
    p = 2.0 * (1.0 - stats.t.cdf(np.abs(t), df))
    ss_tot = ((y - y.mean()) ** 2).sum()
    r2 = 1.0 - (resid @ resid) / ss_tot
    return beta, se, t, p, r2, n, k


def main():
    print('Loading data...')
    glucose_list, basal_list, _ = load_dexcom()
    strain_idx = load_whoop()
    nights = build_nights(glucose_list, basal_list, strain_idx)
    usable, reasons = apply_filters(nights)

    if len(usable) < 50:
        print(f'Only {len(usable)} usable nights - aborting.')
        return

    doses  = np.array([n['dose']             for n in usable], dtype=float)
    s1s    = np.array([n['s1']               for n in usable], dtype=float)
    fasts  = np.array([n['prev_fasting']     for n in usable], dtype=float)
    hypos  = np.array([n['prev_hypo_events'] for n in usable], dtype=float)
    slopes = np.array([n['sh_slope']         for n in usable], dtype=float)

    # Two models: with and without dose*s1 interaction.
    # The interaction-model produces a singularity near s1 = -b_dose/b_interact
    # (denominator goes to zero), so we fit both and report side-by-side, then
    # use the no-interaction additive model for the threshold derivation.
    X_full = np.column_stack([
        np.ones(len(usable)),
        doses,
        s1s,
        doses * s1s,
        fasts,
        hypos,
    ])
    feat_full = ['intercept', 'dose', 's1', 'dose*s1', 'prev_fasting', 'prev_hypos']

    X = np.column_stack([
        np.ones(len(usable)),
        doses,
        s1s,
        fasts,
        hypos,
    ])
    feat = ['intercept', 'dose', 's1', 'prev_fasting', 'prev_hypos']

    beta_full, _, _, pval_full, r2_full, _, _ = fit_ols(X_full, slopes)
    beta, se, tval, pval, r2, n_obs, k = fit_ols(X, slopes)
    df = n_obs - k
    ci_factor = stats.t.ppf(0.975, df)
    ci_low  = beta - ci_factor * se
    ci_high = beta + ci_factor * se

    f_med  = float(np.median(fasts))
    h_med  = float(np.median(hypos))
    anchor = float(np.median([n['prev_dose'] for n in usable]))

    def dose_opt(s1):
        num = -(beta[0] + beta[2] * s1 + beta[3] * f_med + beta[4] * h_med)
        den = beta[1]
        if abs(den) < 1e-8:
            return None
        return num / den

    curve = []
    for s1 in STRAIN_GRID:
        d = dose_opt(s1)
        if d is None:
            curve.append((float(s1), None, None))
            continue
        adj_raw = d - anchor
        adj_int = max(min(int(round(adj_raw)), +3), -2)
        curve.append((float(s1), adj_raw, adj_int))

    ranges = {}
    for adj_target in ADJ_LEVELS:
        in_range = [s for s, raw, ai in curve if ai == adj_target]
        ranges[adj_target] = (min(in_range), max(in_range)) if in_range else None

    lines = []
    def w(s=''):
        lines.append(s)

    # Section 1
    w('=' * 78)
    w('SECTION 1 - REGRESSION FIT (no-interaction additive model)')
    w('=' * 78)
    w(f'Observations          : {n_obs}')
    w(f'Parameters            : {k}')
    w(f'Degrees of freedom    : {df}')
    w(f'R^2                   : {r2:.4f}')
    resid = slopes - X @ beta
    w(f'Residual std error    : {np.sqrt((resid @ resid) / df):.4f} mmol/L/h')
    w('')
    w(f'{"coef":<14} {"beta":>11} {"SE":>9} {"t":>7} {"p":>8} {"95% CI":>24}')
    for i, name in enumerate(feat):
        w(f'{name:<14} {beta[i]:>+11.5f} {se[i]:>9.5f} {tval[i]:>+7.2f} '
          f'{pval[i]:>8.4f}   [{ci_low[i]:>+7.4f}, {ci_high[i]:>+7.4f}]')
    w('')

    p_strain = pval[2]
    p_dose   = pval[1]
    w('Validation gates:')
    w(f'  beta_dose p-value      : {p_dose:.4f}    '
      f'{"PASS" if p_dose < 0.05 else "FAIL - dose effect not significant"}')
    w(f'  beta_strain p-value    : {p_strain:.4f}    '
      f'{"PASS" if p_strain < 0.05 else "FAIL - strain effect not significant"}')
    w(f'  R^2                    : {r2:.4f}    '
      f'{"OK" if r2 >= 0.05 else "LOW - slope mostly noise"}')
    w('')
    w('Reference: interaction-model fit (for comparison, NOT used for thresholds)')
    w(f'  R^2 with dose*s1       : {r2_full:.4f}  '
      f'(gain over no-interaction: {r2_full - r2:+.4f})')
    w(f'  beta_dose*s1 p-value   : {pval_full[3]:.4f}')
    w('  Note: interaction model produced a denominator singularity at moderate s1')
    w('  (b_dose + b_interact*s1 -> 0), making dose_optimal undefined there.')
    w('  Dropping it gives a stable, monotonic threshold curve.')
    w('')

    # Section 2
    w('=' * 78)
    w('SECTION 2 - DOSE_OPTIMAL(s1) CURVE')
    w('=' * 78)
    w(f'Anchor (median prev_dose)        : {anchor:.1f} u')
    w(f'Confounders held at medians      : prev_fasting={f_med:.1f}, '
      f'prev_hypos={h_med:.1f}')
    w(f'sh_slope at s1=X, dose=anchor    : the row marked "*"')
    w('')
    w(f'{"s1":>6} {"dose_opt":>10} {"adj_raw":>10} {"adj_int":>8}  {"pred slope at anchor":>22}')
    for s1, raw, ai in curve:
        if abs(s1 - round(s1)) > 0.01:
            continue
        if raw is None:
            w(f'{s1:>6.1f} {"undef":>10} {"":>10} {"":>8}  {"":>22}')
            continue
        pred_at_anchor = (beta[0] + beta[1]*anchor + beta[2]*s1
                          + beta[3]*f_med + beta[4]*h_med)
        w(f'{s1:>6.1f} {raw + anchor:>10.2f} {raw:>+10.2f} {ai:>+8d}  {pred_at_anchor:>+22.3f}')
    w('')

    # Section 3
    w('=' * 78)
    w('SECTION 3 - STRAIN RANGE PER ADJUSTMENT LEVEL')
    w('=' * 78)
    for adj in ADJ_LEVELS:
        r = ranges[adj]
        if r is None:
            w(f'  {adj:>+2d} u : (no s1 in 4.0-19.0 maps to this level)')
        else:
            w(f'  {adj:>+2d} u : s1 in [{r[0]:.2f}, {r[1]:.2f}]')
    w('')

    # Section 4
    w('=' * 78)
    w('SECTION 4 - PROPOSED CUT POINTS FOR rules.py')
    w('=' * 78)
    cuts = []
    prev_ai = None
    for s, raw, ai in curve:
        if ai != prev_ai:
            cuts.append((s, ai))
            prev_ai = ai
    if len(cuts) == 1:
        w(f'Curve flat at adj = {cuts[0][1]:+d} across the whole strain range.')
    else:
        w('Reading: "s1 in [lo, hi) -> adj = X" (last range is closed on the right).')
        for i in range(len(cuts) - 1):
            s_lo, ai = cuts[i]
            s_hi = cuts[i + 1][0]
            w(f'  s1 in [{s_lo:.2f}, {s_hi:.2f})  ->  adj = {ai:+d}')
        s_lo, ai = cuts[-1]
        w(f'  s1 in [{s_lo:.2f}, 19.00]    ->  adj = {ai:+d}')
    w('')

    # Section 5
    w('=' * 78)
    w('SECTION 5 - PREDICTED vs OBSERVED BIN MEANS (fit-quality check)')
    w('=' * 78)
    s1_sorted = sorted(usable, key=lambda n: n['s1'])
    n_bins = 6
    step = len(s1_sorted) // n_bins
    bins = []
    for i in range(n_bins):
        lo_i = i * step
        hi_i = (i + 1) * step if i < n_bins - 1 else len(s1_sorted)
        grp = s1_sorted[lo_i:hi_i]
        if grp:
            bins.append((f'Q{i+1}', grp))
    w(f'{"bin":<5} {"s1 range":>12} {"n":>4} {"obs slope":>11} {"pred slope":>11} {"diff":>9}')
    w('-' * 60)
    for label, grp in bins:
        obs   = mean(n['sh_slope'] for n in grp)
        d_m   = mean(n['dose'] for n in grp)
        s_m   = mean(n['s1'] for n in grp)
        f_m   = mean(n['prev_fasting'] for n in grp)
        h_m   = mean(n['prev_hypo_events'] for n in grp)
        pred  = (beta[0] + beta[1]*d_m + beta[2]*s_m
                 + beta[3]*f_m + beta[4]*h_m)
        diff  = obs - pred
        lo_s  = min(n['s1'] for n in grp)
        hi_s  = max(n['s1'] for n in grp)
        w(f'{label:<5} {lo_s:>5.1f}-{hi_s:>5.1f}  {len(grp):>4} '
          f'{obs:>+11.4f} {pred:>+11.4f} {diff:>+9.4f}')
    w('')

    # Section 6
    w('=' * 78)
    w('SECTION 6 - CAVEATS')
    w('=' * 78)
    w('- Linear regression assumes additive effects (with one interaction term).')
    w('  Non-linear shape -> Section 5 diffs grow; consider a quadratic strain term.')
    w('- Confounders held at medians for the curve. The thresholds shift slightly if')
    w('  the actual anchor / fasting / hypos differ. Treat ranges as rules of thumb.')
    w(f'- {reasons["s1_none"]} nights lacked s1; {reasons["hypo_correction"]} dropped '
      f'for hypo correction; {reasons["no_anchor"]} for missing anchor.')
    if p_strain >= 0.05:
        w('- beta_strain p >= 0.05: thresholds are suggestive only, not statistically backed.')
    if r2 < 0.05:
        w(f'- R^2 = {r2:.3f} is low; slope is dominated by factors not in the model.')
    w('')

    text = '\n'.join(lines) + '\n'
    OUT_FILE.write_text(text, encoding='utf-8')
    print(text)
    print(f'Report written to: {OUT_FILE}')


if __name__ == '__main__':
    main()
