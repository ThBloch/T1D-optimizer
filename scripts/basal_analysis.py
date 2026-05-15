"""
T1D Basal Analysis — Thomas Bloch-Nielsen
Clean build: loads raw Dexcom + WHOOP, no prior assumptions.
Run: py basal_analysis.py
"""

import csv, glob, os, math
from datetime import datetime, timedelta, date
from collections import defaultdict
from whoop_loader import load_whoop
from dexcom_loader import load_dexcom

BASE      = 'D:/claude/t1d/data'
DIAGNOSIS = date(2025, 4, 9)
OVN_START = 22   # overnight window start hour
OVN_END   = 7    # overnight window end hour (next day)
HYPO_THR  = 4.0
HYPER_THR = 10.0
TGT_LO    = 5.0
TGT_HI    = 8.0

# ── HELPERS ───────────────────────────────────────────────────────────────────
def rolling_avg(d, n, index, key='strain'):
    vals = [index[d - timedelta(days=i)][key]
            for i in range(n)
            if (d - timedelta(days=i)) in index and index[d - timedelta(days=i)][key] is not None]
    return round(sum(vals) / len(vals), 2) if vals else None

def overnight_glucose(inj_dt, glucose_list):
    """Return readings from inj_dt through next 07:00."""
    next_morning = datetime.combine(inj_dt.date() + timedelta(days=1),
                                    datetime.min.time().replace(hour=OVN_END))
    return [(dt, v) for dt, v in glucose_list if inj_dt <= dt <= next_morning]

def compute_night_stats(readings):
    if len(readings) < 6:
        return None
    vals = [v for _, v in readings]
    n    = len(vals)

    # Detect hypo-correction pattern:
    # If glucose drops below 4.0 and then rises above 7.0, the post-hypo
    # hyperglycemia is a correction artefact — dose-too-high signal, not
    # a sign of insufficient basal.
    hypo_idx = next((i for i, v in enumerate(vals) if v < HYPO_THR), None)
    hypo_correction = False
    correction_spike_above_10 = False
    if hypo_idx is not None:
        post = vals[hypo_idx:]
        if max(post) > 7.0:
            hypo_correction = True
        if max(post) > HYPER_THR:
            correction_spike_above_10 = True

    tir      = round(sum(1 for v in vals if TGT_LO <= v <= TGT_HI) / n * 100, 1)
    tir_full = round(sum(1 for v in vals if HYPO_THR <= v <= HYPER_THR) / n * 100, 1)
    hypo_pct = round(sum(1 for v in vals if v < HYPO_THR) / n * 100, 1)
    hyper_pct= round(sum(1 for v in vals if v > HYPER_THR) / n * 100, 1)

    # Adjusted hyper: only count hyper% that is NOT a post-hypo correction spike
    # These nights are dose-too-high, treating their hyper as a separate signal is wrong
    hyper_adj = 0.0 if hypo_correction else hyper_pct

    return {
        'n_readings':           n,
        'fasting':              round(vals[-1], 1),
        'mean':                 round(sum(vals) / n, 1),
        'min':                  round(min(vals), 1),
        'max':                  round(max(vals), 1),
        'tir':                  tir,
        'tir_full':             tir_full,
        'hypo_pct':             hypo_pct,
        'hyper_pct':            hyper_pct,
        'hyper_adj':            hyper_adj,        # hyper excluding correction spikes
        'hypo_correction':      hypo_correction,  # True = dose was too high
        'correction_spike_above_10': correction_spike_above_10,
        'inj_g':                round(vals[0], 1),
    }

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

def iqr_bolus_outlier(bolus_by_date, nights):
    """Flag dates where bolus units are outliers (> Q3 + 1.5*IQR)."""
    vals = sorted([bolus_by_date.get(d, 0) for d, _ in nights])
    n = len(vals)
    if n < 4:
        return set()
    q1 = vals[n // 4]
    q3 = vals[3 * n // 4]
    iqr = q3 - q1
    threshold = q3 + 1.5 * iqr
    return {d for d, _ in nights if bolus_by_date.get(d, 0) > threshold}

# ── MAIN ──────────────────────────────────────────────────────────────────────
def run():
    print("=" * 65)
    print("  T1D BASAL ANALYSIS — Thomas Bloch-Nielsen")
    print(f"  Run date: {date.today()}")
    print("=" * 65)

    # ── STEP 1: Load data ──────────────────────────────────────────────────
    glucose_list, basal_list, bolus = load_dexcom()
    strain_by_date = load_whoop()

    g_dates = [dt.date() for dt, _ in glucose_list]
    g_start, g_end = min(g_dates), max(g_dates)
    b_dates = [d for _, d, _ in basal_list]

    print(f"\n  DATA LOADED")
    print(f"  CGM          : {len(glucose_list):,} readings | {g_start} → {g_end}")
    print(f"  Basal doses  : {len(basal_list)} injections | {min(b_dates)} → {max(b_dates)}")
    print(f"  Bolus days   : {len([v for v in bolus.values() if v > 0])} days with bolus logged")
    print(f"  WHOOP days   : {len(strain_by_date)} days with strain data")

    # ── STEP 2: Build nightly paired dataset ──────────────────────────────
    nights = []  # list of dicts per injection night
    for inj_dt, inj_date, dose in basal_list:
        if inj_dt.hour < 18:   # skip daytime basal — expect ~22:00
            continue
        readings = overnight_glucose(inj_dt, glucose_list)
        stats    = compute_night_stats(readings)
        if stats is None:
            continue
        s1  = strain_by_date.get(inj_date, {}).get('strain')
        s7  = rolling_avg(inj_date, 7, strain_by_date)
        hrv = strain_by_date.get(inj_date, {}).get('hrv')
        rec = strain_by_date.get(inj_date, {}).get('recovery')
        rhr = strain_by_date.get(inj_date, {}).get('rhr')
        slp = strain_by_date.get(inj_date, {}).get('sleep_perf')
        nights.append({
            'date':    inj_date,
            'inj_dt':  inj_dt,
            'dose':    dose,
            's1':      s1,
            's7':      s7,
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
    # Two exclusion classes:
    # 1. High-bolus nights (bolus confounder, r=-0.29 p<0.001)
    # 2. Hypo-correction nights: dose was clearly too high — using these in
    #    the matching pool would bias the dose range downward incorrectly.
    #    They ARE kept in the weekly summary for visibility.
    bolus_outlier_dates = iqr_bolus_outlier(bolus, [(n['date'], n) for n in nights])
    hypo_corr_dates     = {n['date'] for n in nights if n['hypo_correction']}
    excluded_dates      = bolus_outlier_dates | hypo_corr_dates

    clean = [n for n in nights if n['date'] not in excluded_dates]

    bolus_excl_str = ', '.join(str(d) for d in sorted(bolus_outlier_dates)) or 'none'
    print(f"  High-bolus nights excluded : {bolus_excl_str}")
    print(f"  Hypo-correction nights excl: {len(hypo_corr_dates)}  (dose-too-high signal, not used in matching)")
    print(f"  Clean nights for modeling  : {len(clean)}")

    # ── STEP 4: Tonight's profile ─────────────────────────────────────────
    today = g_end
    today_s1  = strain_by_date.get(today, {}).get('strain')
    today_s7  = rolling_avg(today, 7, strain_by_date)
    today_hrv = strain_by_date.get(today, {}).get('hrv')
    today_rec = strain_by_date.get(today, {}).get('recovery')

    # Find yesterday's dose and tonight's injection-time glucose (latest CGM reading)
    yesterday = today - timedelta(days=1)
    yesterday_dose = next((n['dose'] for n in reversed(nights) if n['date'] == yesterday), None)

    # Best estimate of tonight's injection-time glucose: last CGM reading of the day
    tonight_inj_g = None
    for dt, v in reversed(glucose_list):
        if dt.date() == today:
            tonight_inj_g = v
            break

    # ── STEP 5: Match comparable nights ───────────────────────────────────
    # Validated predictors (from predictor_test.py):
    #   inj_g  r=-0.36 ***  (strongest)
    #   s1     r=0.245 **
    #   bolus  excluded above
    #   s7     r=0.078 ns  — dropped from matching
    #
    # Match on: inj_g ±2.5 mmol/L  AND  s1 ±3.0 (if today s1 available)
    INJ_WINDOW = 2.5
    S1_WINDOW  = 3.0

    comparable = []
    match_criteria = []

    if tonight_inj_g is not None:
        match_criteria.append(f"inj_g {tonight_inj_g:.1f} ±{INJ_WINDOW}")
        for n in clean:
            if abs(n['inj_g'] - tonight_inj_g) > INJ_WINDOW:
                continue
            if today_s1 is not None and n['s1'] is not None:
                if abs(n['s1'] - today_s1) > S1_WINDOW:
                    continue
            if n['date'] != today:
                comparable.append(n)
        if today_s1 is not None:
            match_criteria.append(f"s1 {today_s1:.1f} ±{S1_WINDOW}")
    elif today_s1 is not None:
        # fallback: s1 only
        match_criteria.append(f"s1 {today_s1:.1f} ±{S1_WINDOW}")
        comparable = [n for n in clean
                      if n['s1'] is not None
                      and abs(n['s1'] - today_s1) <= S1_WINDOW
                      and n['date'] != today]
    else:
        match_criteria.append('no match variables available')

    n_comp = len(comparable)

    # ── STEP 6: Statistics ─────────────────────────────────────────────────
    # Outcomes: fasting, mean overnight, tir (5–8 range as per prompt)
    def outcome_stats(subset):
        if not subset:
            return {}
        doses    = [n['dose']   for n in subset]
        fastings = [n['fasting']for n in subset]
        means    = [n['mean']   for n in subset]
        tirs     = [n['tir']    for n in subset]
        hypos    = [n for n in subset if n['hypo_pct'] > 0]
        hypers   = [n for n in subset if n['hyper_pct'] > 0]
        fasting_in_range = [n for n in subset if TGT_LO <= n['fasting'] <= TGT_HI]
        mean_in_range    = [n for n in subset if TGT_LO <= n['mean']    <= TGT_HI]

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

    # Confidence level
    def confidence(n, stats):
        if n < 5:
            return 'INSUFFICIENT'
        variance_penalty = False
        if stats:
            dose_spread = stats['dose_max'] - stats['dose_min']
            if dose_spread > 8:
                variance_penalty = True
        if n >= 10:
            level = 'HIGH' if not variance_penalty else 'MEDIUM'
        else:
            level = 'LOW'
        return level

    # ── BLOCK 1 ───────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  TONIGHT'S BASAL RANGE")
    print(f"{'='*65}")

    inj_g_str = f"{tonight_inj_g:.1f} mmol/L" if tonight_inj_g else "unknown"
    print(f"\n  Tonight's injection-time glucose: {inj_g_str}")
    print(f"  Tonight's s1 (strain): {today_s1 if today_s1 else 'not yet available'}")
    print(f"  Yesterday dose: {yesterday_dose}u" if yesterday_dose else "  Yesterday dose: unknown")

    if n_comp < 5:
        print(f"\n  INSUFFICIENT DATA — n={n_comp}")
        print(f"  Cannot produce a reliable dose range.")
        print(f"  Match criteria: {' | '.join(match_criteria)}")
        if tonight_inj_g is None:
            print(f"  ! Injection-time glucose unknown — check your CGM.")
    else:
        stats = outcome_stats(comparable)
        conf  = confidence(n_comp, stats)
        print(f"\n  Comparable nights (n={n_comp}) | Match: {' | '.join(match_criteria)}")
        print(f"  Dose range observed : {stats['dose_min']:.0f}–{stats['dose_max']:.0f}u")
        print(f"\n  Outcomes in comparable nights:")
        print(f"    Fasting glucose in target (5–8):   {stats['fasting_in_range_pct']}%")
        print(f"    Mean overnight in target (5–8):    {stats['mean_in_range_pct']}%")
        print(f"    Time-in-range overnight (5–8) avg: {stats['tir_mean']}%")
        print(f"    Hypo nights  (<4.0):               {stats['hypo_nights_pct']}%")
        print(f"    Hyper nights (>10.0):              {stats['hyper_nights_pct']}%")
        print(f"  Best performing dose: {stats['best_dose']:.0f}u  (TIR {stats['best_tir']}%)")
        print(f"  High-bolus excluded: {bolus_excl_str} | Hypo-correction nights excl: {len(hypo_corr_dates)}")
        conf_reason = f"n={n_comp}" + (", wide dose spread" if stats['dose_max']-stats['dose_min']>8 else "")
        print(f"  Confidence: {conf} — {conf_reason}")

        if stats['hypo_nights_pct'] > 10:
            print(f"  ⚠ Hypo risk: {stats['hypo_nights_pct']}% of comparable nights had nocturnal hypo")
        elif stats['hyper_nights_pct'] > 40:
            print(f"  ⚠ Hyper pattern: {stats['hyper_nights_pct']}% of comparable nights above 10 mmol/L")

    # ── BLOCK 2 ───────────────────────────────────────────────────────────
    last7 = [n for n in nights if n['date'] >= today - timedelta(days=7)]
    print(f"\n{'='*65}")
    print(f"  WEEKLY PATTERN (last 7 nights, {today-timedelta(days=6)} → {today})")
    print(f"{'='*65}")
    print(f"\n  {'Date':<12} {'Dose':>5}  {'S1':>5}  {'S7':>5}  {'Fasting':>8}  {'Mean':>6}  {'TIR%':>6}  {'Hypo%':>6}  {'Note'}")
    print(f"  {'-'*85}")

    best_nights  = []
    worst_nights = []

    for n in last7:
        exc = ''
        if n['date'] in bolus_outlier_dates:   exc = ' [bolus]'
        elif n['hypo_correction']:             exc = ' [hypo+correction]'
        flag = ''
        if n['hypo_correction']:
            flag = 'DOSE>HIGH'
        elif n['hypo_pct'] > 0:
            flag = 'HYPO'
        elif n['hyper_adj'] > 50:
            flag = 'HYPER'
        elif TGT_LO <= n['fasting'] <= TGT_HI and n['tir'] >= 70:
            flag = 'GOOD'
            best_nights.append(n)
        else:
            worst_nights.append(n)
        s1s = f"{n['s1']:.1f}" if n['s1'] else '-'
        s7s = f"{n['s7']:.1f}" if n['s7'] else '-'
        print(f"  {str(n['date']):<12} {n['dose']:>4.0f}u  {s1s:>5}  {s7s:>5}  "
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
        exc_note = " [bolus]" if w['date'] in bolus_outlier_dates else \
                   " [hypo+correction]" if w['hypo_correction'] else ""
        print(f"  Worst night: {w['date']}  {w['dose']:.0f}u  fasting={w['fasting']} mean={w['mean']} TIR={w['tir']}%{exc_note}")

    print(f"  High-bolus excluded: {bolus_excl_str}")
    print(f"  Hypo-correction nights in window: {sum(1 for n in last7 if n['hypo_correction'])}")

    # ── APPENDIX ──────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  APPENDIX — STATISTICAL DETAIL  (n={n_comp} comparable nights)")
    print(f"{'='*65}")

    if n_comp >= 5:
        stats = outcome_stats(comparable)
        print(f"\n  Spearman correlation: dose vs outcomes")
        print(f"  {'Outcome':<25} {'r':>7}  {'p':>8}")
        print(f"  {'-'*42}")
        for label, key in [('Fasting glucose','spearman_fasting'),
                            ('Mean overnight','spearman_mean'),
                            ('TIR% (5–8)','spearman_tir')]:
            r, p = stats[key]
            if r is not None:
                sig = '*' if p < 0.05 else ''
                print(f"  {label:<25} {r:>7.3f}  {p:>8.4f} {sig}")

        print(f"\n  Linear regression: dose → outcomes")
        print(f"  {'Outcome':<25} {'coef':>7}  {'R²':>6}  {'95% CI':>10}")
        print(f"  {'-'*52}")
        for label, key in [('Fasting glucose','reg_fasting'),
                            ('Mean overnight','reg_mean'),
                            ('TIR% (5–8)','reg_tir')]:
            reg = stats[key]
            if reg:
                ci_str = f"±{reg['ci95']}" if reg['ci95'] else 'N/A'
                print(f"  {label:<25} {reg['b1']:>7.3f}  {reg['r2']:>6.3f}  {ci_str:>10}")

        print(f"\n  Per-night detail (comparable nights, sorted by dose):")
        print(f"  {'Date':<12} {'Dose':>5}  {'S7':>5}  {'Fasting':>8}  {'Mean':>6}  {'TIR%':>6}  {'Hypo%':>6}")
        print(f"  {'-'*60}")
        for n in sorted(comparable, key=lambda x: x['dose']):
            s7s = f"{n['s7']:.1f}" if n['s7'] else '-'
            print(f"  {str(n['date']):<12} {n['dose']:>4.0f}u  {s7s:>5}  "
                  f"{n['fasting']:>7.1f}  {n['mean']:>5.1f}  {n['tir']:>5.1f}  {n['hypo_pct']:>5.1f}")
    else:
        print(f"\n  n={n_comp} — insufficient for statistics. Need ≥5 comparable nights.")

    print(f"\n  Current context:")
    print(f"    Inj-time glucose = {inj_g_str}")
    print(f"    Today s1         = {today_s1}")
    print(f"    Today s7         = {today_s7}  (not used for matching — not predictive)")
    print(f"    HRV              = {today_hrv}")
    print(f"    Recovery         = {today_rec}%")
    print(f"    Yesterday dose   = {yesterday_dose}u")

    print(f"\n  {'-'*61}")
    print(f"  All outputs are observations from your own data only.")
    print(f"  Verify all dosing decisions with your endocrinologist.")
    print(f"  {'-'*61}\n")

if __name__ == '__main__':
    run()
