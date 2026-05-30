"""
T1D Basal Analysis - Thomas Bloch-Nielsen
Clean build: loads raw Dexcom + WHOOP, no prior assumptions.
Run: py basal_analysis.py
"""

import math
from datetime import timedelta, date
from whoop_loader import load_whoop
from dexcom_loader import load_dexcom
from night_stats import overnight_window, night_stats, TARGET_LO, TARGET_HI

# ── HELPERS ───────────────────────────────────────────────────────────────────
def spearman_r(x, y):
    n = len(x)
    if n < 3:
        return None, None
    rx = sorted(range(n), key=lambda i: x[i])
    ry = sorted(range(n), key=lambda i: y[i])
    rank_x = [0] * n
    rank_y = [0] * n
    for r, i in enumerate(rx): rank_x[i] = r + 1
    for r, i in enumerate(ry): rank_y[i] = r + 1
    d2 = sum((rank_x[i] - rank_y[i]) ** 2 for i in range(n))
    rs = 1 - 6 * d2 / (n * (n**2 - 1))
    # approximate t-test
    if abs(rs) == 1.0:
        return round(rs, 3), 0.0
    t = rs * math.sqrt(n - 2) / math.sqrt(1 - rs**2)
    # rough two-tailed p via normal approximation (adequate for display)
    z  = abs(t) * math.sqrt(n) / math.sqrt(n - 1)
    p  = 2 * (1 / (1 + math.exp(1.7 * z)))   # logistic approximation
    return round(rs, 3), round(p, 4)

def linreg(x, y):
    n = len(x)
    if n < 3:
        return None
    mx, my = sum(x)/n, sum(y)/n
    ss_xx = sum((xi - mx)**2 for xi in x)
    ss_xy = sum((xi - mx)*(yi - my) for xi, yi in zip(x, y))
    if ss_xx == 0:
        return None
    b1 = ss_xy / ss_xx
    b0 = my - b1 * mx
    y_hat = [b0 + b1 * xi for xi in x]
    ss_res = sum((yi - yhi)**2 for yi, yhi in zip(y, y_hat))
    ss_tot = sum((yi - my)**2 for yi in y)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    # SE of slope
    if n > 2 and ss_xx > 0:
        se = math.sqrt(ss_res / (n - 2) / ss_xx)
        ci95 = 1.96 * se
    else:
        se, ci95 = None, None
    return {'b0': round(b0, 3), 'b1': round(b1, 3), 'r2': round(r2, 3),
            'ci95': round(ci95, 3) if ci95 else None}

# ── MAIN ──────────────────────────────────────────────────────────────────────
def run():
    print("=" * 65)
    print("  T1D BASAL ANALYSIS - Thomas Bloch-Nielsen")
    print(f"  Run date: {date.today()}")
    print("=" * 65)

    # ── STEP 1: Load data ──────────────────────────────────────────────────
    glucose_list, basal_list, bolus = load_dexcom()
    strain_by_date = load_whoop()

    g_dates = [dt.date() for dt, _ in glucose_list]
    g_start, g_end = min(g_dates), max(g_dates)
    b_dates = [d for _, d, _ in basal_list]

    print(f"\n  DATA LOADED")
    print(f"  CGM          : {len(glucose_list):,} readings | {g_start} -> {g_end}")
    print(f"  Basal doses  : {len(basal_list)} injections | {min(b_dates)} -> {max(b_dates)}")
    print(f"  Bolus days   : {len([v for v in bolus.values() if v > 0])} days with bolus logged")
    print(f"  WHOOP days   : {len(strain_by_date)} days with strain data")

    # ── STEP 2: Build nightly paired dataset ──────────────────────────────
    nights = []  # list of dicts per injection night
    for inj_dt, inj_date, dose in basal_list:
        if inj_dt.hour < 18:   # skip daytime basal - expect ~22:00
            continue
        readings = overnight_window(inj_dt, glucose_list)
        stats    = night_stats(readings)
        if stats is None:
            continue
        s1  = strain_by_date.get(inj_date, {}).get('strain')
        hrv = strain_by_date.get(inj_date, {}).get('hrv')
        rec = strain_by_date.get(inj_date, {}).get('recovery')
        rhr = strain_by_date.get(inj_date, {}).get('rhr')
        slp = strain_by_date.get(inj_date, {}).get('sleep_perf')
        nights.append({
            'date':    inj_date,
            'inj_dt':  inj_dt,
            'dose':    dose,
            's1':      s1,
            'hrv':     hrv,
            'recovery': rec,
            'rhr':     rhr,
            'sleep_perf': slp,
            'bolus':   bolus.get(inj_date, 0),
            **stats,
        })

    nights.sort(key=lambda x: x['date'])

    print(f"\n  Overnight nights with sufficient CGM data: {len(nights)}")

    # ── STEP 3: Exclude confounders ───────────────────────────────────────
    # Exclude hypo-correction nights: dose was clearly too high - using these
    # in the matching pool would bias the dose range downward incorrectly.
    # They ARE kept in the weekly summary for visibility.
    hypo_corr_dates = {n['date'] for n in nights if n['hypo_correction']}
    clean = [n for n in nights if n['date'] not in hypo_corr_dates]

    print(f"  Hypo-correction nights excl: {len(hypo_corr_dates)}  (dose-too-high signal, not used in matching)")
    print(f"  Clean nights for modeling  : {len(clean)}")

    # ── STEP 4: Current profile ───────────────────────────────────────────
    today = g_end
    today_s1  = strain_by_date.get(today, {}).get('strain')
    today_hrv = strain_by_date.get(today, {}).get('hrv')
    today_rec = strain_by_date.get(today, {}).get('recovery')

    # Find yesterday's dose and current injection-time glucose (latest CGM reading)
    yesterday = today - timedelta(days=1)
    yesterday_dose = next((n['dose'] for n in reversed(nights) if n['date'] == yesterday), None)

    # Latest CGM reading used as injection-time glucose proxy
    current_inj_g = None
    for dt, v in reversed(glucose_list):
        if dt.date() == today:
            current_inj_g = v
            break

    # ── STEP 5: Match comparable nights ───────────────────────────────────
    # Validated predictors (from predictor_test.py):
    #   inj_g  r=-0.36 ***  (strongest)
    #   s1     r=0.245 **
    #   s7     r=0.078 ns  - dropped from matching
    #
    # Match on: inj_g +/-2.5 mmol/L  AND  s1 +/-3.0 (if today s1 available)
    INJ_WINDOW = 2.5
    S1_WINDOW  = 3.0

    comparable = []

    if current_inj_g is not None:
        for n in clean:
            if abs(n['inj_g'] - current_inj_g) > INJ_WINDOW:
                continue
            if today_s1 is not None and n['s1'] is not None:
                if abs(n['s1'] - today_s1) > S1_WINDOW:
                    continue
            if n['date'] != today:
                comparable.append(n)
    elif today_s1 is not None:
        comparable = [n for n in clean
                      if n['s1'] is not None
                      and abs(n['s1'] - today_s1) <= S1_WINDOW
                      and n['date'] != today]

    n_comp = len(comparable)

    # ── STEP 6: Statistics ─────────────────────────────────────────────────
    # Outcomes: fasting, mean overnight, tir (5-8 range as per prompt)
    def outcome_stats(subset):
        if not subset:
            return {}
        doses    = [n['dose']   for n in subset]
        fastings = [n['fasting']for n in subset]
        means    = [n['mean']   for n in subset]
        tirs     = [n['tir']    for n in subset]
        hypos    = [n for n in subset if n['hypo_pct'] > 0]
        hypers   = [n for n in subset if n['hyper_pct'] > 0]
        fasting_in_range = [n for n in subset if TARGET_LO <= n['fasting'] <= TARGET_HI]
        mean_in_range    = [n for n in subset if TARGET_LO <= n['mean']    <= TARGET_HI]

        best_tir = max(subset, key=lambda n: n['tir'])

        return {
            'doses':     doses,
            'dose_min':  min(doses),
            'dose_max':  max(doses),
            'fasting_in_range_pct': round(len(fasting_in_range)/len(subset)*100, 1),
            'mean_in_range_pct':    round(len(mean_in_range)/len(subset)*100, 1),
            'tir_mean':             round(sum(tirs)/len(tirs), 1),
            'hypo_nights_pct':      round(len(hypos)/len(subset)*100, 1),
            'hyper_nights_pct':     round(len(hypers)/len(subset)*100, 1),
            'best_dose':            best_tir['dose'],
            'best_tir':             best_tir['tir'],
            'spearman_fasting':     spearman_r(doses, fastings),
            'spearman_mean':        spearman_r(doses, means),
            'spearman_tir':         spearman_r(doses, tirs),
            'reg_fasting':          linreg(doses, fastings),
            'reg_mean':             linreg(doses, means),
            'reg_tir':              linreg(doses, tirs),
        }

    # ── BLOCK 2 ───────────────────────────────────────────────────────────
    last7 = [n for n in nights if n['date'] >= today - timedelta(days=7)]
    print(f"\n{'='*65}")
    print(f"  WEEKLY PATTERN (last 7 nights, {today-timedelta(days=6)} -> {today})")
    print(f"{'='*65}")
    print(f"\n  {'Date':<12} {'Dose':>5}  {'S1':>5}  {'Fasting':>8}  {'Mean':>6}  {'TIR%':>6}  {'Hypo%':>6}  {'Note'}")
    print(f"  {'-'*78}")

    best_nights  = []
    worst_nights = []

    for n in last7:
        exc = ' [hypo+correction]' if n['hypo_correction'] else ''
        flag = ''
        if n['hypo_correction']:
            flag = 'DOSE>HIGH'
        elif n['hypo_pct'] > 0:
            flag = 'HYPO'
        elif n['hyper_adj'] > 50:
            flag = 'HYPER'
        elif TARGET_LO <= n['fasting'] <= TARGET_HI and n['tir'] >= 70:
            flag = 'GOOD'
            best_nights.append(n)
        else:
            worst_nights.append(n)
        s1s = f"{n['s1']:.1f}" if n['s1'] else '-'
        print(f"  {str(n['date']):<12} {n['dose']:>4.0f}u  {s1s:>5}  "
              f"{n['fasting']:>7.1f}  {n['mean']:>5.1f}  {n['tir']:>5.1f}  "
              f"{n['hypo_pct']:>5.1f}  {flag}{exc}")

    # Trend
    doses_7 = [n['dose'] for n in last7]
    if len(doses_7) >= 3:
        trend_delta = doses_7[-1] - doses_7[0]
        if trend_delta >= 3:
            trend_str = f"titrating up (+{trend_delta:.0f}u over 7 nights)"
        elif trend_delta <= -3:
            trend_str = f"titrating down ({trend_delta:.0f}u over 7 nights)"
        else:
            trend_str = "stable"
        print(f"\n  Doses used: {sorted(set(doses_7))}")
        print(f"  Trend: {trend_str}")

    if best_nights:
        b = max(best_nights, key=lambda n: n['tir'])
        print(f"  Best night:  {b['date']}  {b['dose']:.0f}u  fasting={b['fasting']} mean={b['mean']} TIR={b['tir']}%")
    if worst_nights:
        w = min(worst_nights, key=lambda n: n['tir'])
        exc_note = " [hypo+correction]" if w['hypo_correction'] else ""
        print(f"  Worst night: {w['date']}  {w['dose']:.0f}u  fasting={w['fasting']} mean={w['mean']} TIR={w['tir']}%{exc_note}")

    print(f"  Hypo-correction nights in window: {sum(1 for n in last7 if n['hypo_correction'])}")

    # ── APPENDIX ──────────────────────────────────────────────────────────
    inj_g_str = f"{current_inj_g:.1f} mmol/L" if current_inj_g else "unknown"
    print(f"\n{'='*65}")
    print(f"  APPENDIX - STATISTICAL DETAIL  (n={n_comp} comparable nights)")
    print(f"{'='*65}")

    if n_comp >= 5:
        stats = outcome_stats(comparable)
        print(f"\n  Spearman correlation: dose vs outcomes")
        print(f"  {'Outcome':<25} {'r':>7}  {'p':>8}")
        print(f"  {'-'*42}")
        for label, key in [('Fasting glucose','spearman_fasting'),
                            ('Mean overnight','spearman_mean'),
                            ('TIR% (5-8)','spearman_tir')]:
            r, p = stats[key]
            if r is not None:
                sig = '*' if p < 0.05 else ''
                print(f"  {label:<25} {r:>7.3f}  {p:>8.4f} {sig}")

        print(f"\n  Linear regression: dose -> outcomes")
        print(f"  {'Outcome':<25} {'coef':>7}  {'R²':>6}  {'95% CI':>10}")
        print(f"  {'-'*52}")
        for label, key in [('Fasting glucose','reg_fasting'),
                            ('Mean overnight','reg_mean'),
                            ('TIR% (5-8)','reg_tir')]:
            reg = stats[key]
            if reg:
                ci_str = f"+/-{reg['ci95']}" if reg['ci95'] else 'N/A'
                print(f"  {label:<25} {reg['b1']:>7.3f}  {reg['r2']:>6.3f}  {ci_str:>10}")

        print(f"\n  Per-night detail (comparable nights, sorted by dose):")
        print(f"  {'Date':<12} {'Dose':>5}  {'Fasting':>8}  {'Mean':>6}  {'TIR%':>6}  {'Hypo%':>6}")
        print(f"  {'-'*54}")
        for n in sorted(comparable, key=lambda x: x['dose']):
            print(f"  {str(n['date']):<12} {n['dose']:>4.0f}u  "
                  f"{n['fasting']:>7.1f}  {n['mean']:>5.1f}  {n['tir']:>5.1f}  {n['hypo_pct']:>5.1f}")
    else:
        print(f"\n  n={n_comp} - insufficient for statistics. Need ≥5 comparable nights.")

    print(f"\n  Current context:")
    print(f"    Inj-time glucose = {inj_g_str}")
    print(f"    Today s1         = {today_s1}")
    print(f"    HRV              = {today_hrv}")
    print(f"    Recovery         = {today_rec}%")
    print(f"    Yesterday dose   = {yesterday_dose}u")

    print(f"\n  {'-'*61}")
    print(f"  All outputs are observations from your own data only.")
    print(f"  Verify all dosing decisions with your endocrinologist.")
    print(f"  {'-'*61}\n")

if __name__ == '__main__':
    run()
