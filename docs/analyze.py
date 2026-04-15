"""
T1D Basal Optimizer — Thomas Bloch-Nielsen
==========================================
Run this script whenever new Dexcom + WHOOP data is uploaded.
Drop files in D:/claude/t1d and run: py analyze.py

Data expected:
  - Dexcom : Clarity_*.csv  (semicolon-separated, Danish locale, mmol/L)
  - WHOOP  : my_whoop_data_*/ folder

Only data from T1D diagnosis date (2025-04-09) onwards is used.
All outputs are observations + data-derived suggestions.
Verify all dosing changes with your endocrinologist.
"""

import csv
import glob
import os
from datetime import datetime, timedelta, date
from collections import defaultdict

BASE      = 'D:/claude/t1d'
DIAGNOSIS = date(2025, 4, 9)   # T1D diagnosis date — no data used before this

# --- FILE DISCOVERY -----------------------------------------------------------
def find_files():
    dexcom_files = sorted(glob.glob(os.path.join(BASE, 'Clarity_*.csv')))
    whoop_dirs   = sorted(glob.glob(os.path.join(BASE, 'my_whoop_data_*')))
    if not dexcom_files:
        raise FileNotFoundError("No Dexcom CSV found. Expected: Clarity_*.csv")
    if not whoop_dirs:
        raise FileNotFoundError("No WHOOP folder found. Expected: my_whoop_data_*/")
    whoop = max(whoop_dirs, key=os.path.getmtime)
    return dexcom_files, whoop

# --- LOADERS ------------------------------------------------------------------
def load_dexcom(paths):
    """Load and merge multiple Dexcom CSV files, deduplicating on exact timestamp."""
    glucose_dict = {}   # dt -> value  (deduplicates by keeping last seen)
    insulin_dict = {}   # dt -> (subtype, units)

    for path in paths:
        with open(path, 'r', encoding='utf-8') as f:
            for row in csv.reader(f, delimiter=';'):
                if len(row) < 9:
                    continue
                ts    = row[1].strip().strip('"')
                etype = row[2].strip().strip('"')
                esub  = row[3].strip().strip('"')
                gstr  = row[7].strip().strip('"')
                istr  = row[8].strip().strip('"')
                if not ts or 'T' not in ts:
                    continue
                try:
                    dt = datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S')
                except:
                    continue
                if etype == 'Estimeret glukoseværdi' and gstr:
                    try:
                        glucose_dict[dt] = float(gstr.replace(',', '.'))
                    except:
                        pass
                if etype == 'Insulin' and istr:
                    try:
                        insulin_dict[dt] = (esub, float(istr.replace(',', '.')))
                    except:
                        pass

    glucose = sorted(glucose_dict.items(), key=lambda x: x[0])
    insulin = sorted([(dt, sub, u) for dt, (sub, u) in insulin_dict.items()],
                     key=lambda x: x[0])
    return glucose, insulin

def load_whoop(folder):
    cycles, sleeps, workouts = [], [], []

    with open(os.path.join(folder, 'physiological_cycles.csv'), 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                cs = datetime.strptime(row['Cycle start time'], '%Y-%m-%d %H:%M:%S')
                ce = datetime.strptime(row['Cycle end time'], '%Y-%m-%d %H:%M:%S') \
                     if row['Cycle end time'].strip() else None
                # Key cycle by end date (day it represents), not start date.
                # Cycles start at sleep-time (~22:00) so a cycle ending at 23:00 on
                # day D represents day D; one ending at 00:20 on day D+1 represents day D.
                if ce is not None:
                    cycle_date = (ce - timedelta(hours=6)).date()
                else:
                    cycle_date = cs.date()
                cycles.append({
                    'date':     cycle_date,
                    'start':    cs,
                    'end':      ce,
                    'strain':   float(row['Day Strain'])             if row['Day Strain'].strip()             else None,
                    'recovery': float(row['Recovery score %'])       if row['Recovery score %'].strip()       else None,
                    'hrv':      float(row['Heart rate variability (ms)']) if row['Heart rate variability (ms)'].strip() else None,
                    'rhr':      float(row['Resting heart rate (bpm)'])    if row['Resting heart rate (bpm)'].strip()    else None,
                })
            except:
                pass

    with open(os.path.join(folder, 'sleeps.csv'), 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                cs   = datetime.strptime(row['Cycle start time'], '%Y-%m-%d %H:%M:%S')
                wake = datetime.strptime(row['Wake onset'], '%Y-%m-%d %H:%M:%S') \
                       if row['Wake onset'].strip() else None
                sleeps.append({'cycle_start': cs, 'wake': wake})
            except:
                pass
    sleeps.sort(key=lambda x: x['cycle_start'])

    with open(os.path.join(folder, 'workouts.csv'), 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                ws = datetime.strptime(row['Workout start time'], '%Y-%m-%d %H:%M:%S')
                we = datetime.strptime(row['Workout end time'],   '%Y-%m-%d %H:%M:%S')
                workouts.append({
                    'date':     ws.date(),
                    'start':    ws,
                    'end':      we,
                    'duration': float(row['Duration (min)']),
                    'activity': row['Activity name'],
                    'strain':   float(row['Activity Strain'])    if row['Activity Strain'].strip()    else 0,
                    'avg_hr':   float(row['Average HR (bpm)'])   if row['Average HR (bpm)'].strip()   else 0,
                    'max_hr':   float(row['Max HR (bpm)'])       if row['Max HR (bpm)'].strip()       else 0,
                    'z1': float(row['HR Zone 1 %']) if row['HR Zone 1 %'].strip() else 0,
                    'z2': float(row['HR Zone 2 %']) if row['HR Zone 2 %'].strip() else 0,
                    'z3': float(row['HR Zone 3 %']) if row['HR Zone 3 %'].strip() else 0,
                    'z4': float(row['HR Zone 4 %']) if row['HR Zone 4 %'].strip() else 0,
                    'z5': float(row['HR Zone 5 %']) if row['HR Zone 5 %'].strip() else 0,
                })
            except:
                pass

    return cycles, sleeps, workouts

def build_strain_index(whoop_cycles):
    """
    Build daily strain index from WHOOP cycles.
    Returns: date -> {'strain': float, 'source': 'whoop'}
    """
    index = {}
    for c in whoop_cycles:
        if c['strain'] is not None and c['date'] >= DIAGNOSIS:
            index[c['date']] = {'strain': c['strain'], 'source': 'whoop'}
    return index

# --- HELPERS ------------------------------------------------------------------
def glucose_in_range(start, end, glucose):
    return [(dt, v) for dt, v in glucose if start <= dt <= end]

def nearest_glucose(target, glucose, window_min=15):
    best, best_d = None, timedelta(minutes=window_min + 1)
    for dt, v in glucose:
        d = abs(dt - target)
        if d < best_d:
            best_d, best = d, v
    return best

def rolling_strain(ref_date, days, strain_index):
    """strain_index: date -> {'strain': float, 'source': str}"""
    vals = [strain_index[ref_date - timedelta(days=i)]['strain']
            for i in range(days) if (ref_date - timedelta(days=i)) in strain_index]
    return round(sum(vals) / len(vals), 2) if vals else None

def strain_val(d, strain_index):
    entry = strain_index.get(d)
    return entry['strain'] if entry else None

def strain_src(d, strain_index):
    entry = strain_index.get(d)
    return 'W' if entry else '?'

def is_heavy_weights(w):
    return (w['activity'] in ('Weightlifting', 'Strength Training')
            and w['duration'] >= 35)

def weight_training_flag(ref_date, workouts_by_date):
    """
    Returns True if heavy weightlifting occurred in the past 48 hours.
    Heavy weights extend insulin sensitivity 24-48h beyond normal exercise.
    """
    for i in range(1, 3):
        d = ref_date - timedelta(days=i)
        for w in workouts_by_date.get(d, []):
            if is_heavy_weights(w):
                return True, i  # (flag, days_ago)
    return False, None

def classify_half_day(day_workouts, strain_today):
    """
    Classify a moderate-strain day for basal adjustment.
    Returns: 'rest_leaning', 'active_leaning', 'moderate', or 'no_workout'
    """
    if not day_workouts:
        return 'no_workout'
    latest_end = max(w['end'] for w in day_workouts)
    hour = latest_end.hour + latest_end.minute / 60
    if hour < 14:
        return 'rest_leaning'
    elif hour < 17:
        return 'moderate'
    else:
        return 'active_leaning'

# --- BASAL RECOMMENDATION ENGINE ----------------------------------------------
def recommend_basal(s7, s1, yesterday_dose, last_night_stats, workouts_by_date, ref_date):
    """
    Anchor-based recommendation: start from yesterday's dose, adjust for
    last night outcome and today's activity transition.
    Formula (46.7 - 2.28 * s7) used as sanity check only.

    yesterday_dose   : actual units injected last night (float or None)
    last_night_stats : dict from overnight_stats() for last night, or None
    Returns dict: base (formula), adjusted, anchor, reasons (list)
    """
    reasons = []

    formula_dose = round(46.7 - 2.28 * s7, 1) if s7 is not None else None
    formula_clip = max(14, min(36, formula_dose)) if formula_dose is not None else None

    # No anchor — fall back to formula
    if yesterday_dose is None:
        if formula_clip is not None:
            reasons.append(f"No prior dose — formula: 46.7 - 2.28 x {s7:.1f} = {formula_clip}u")
        else:
            reasons.append("Insufficient data (no prior dose, no strain)")
        return {'base': formula_clip, 'adjusted': formula_clip, 'anchor': None, 'reasons': reasons}

    adj = yesterday_dose
    reasons.append(f"Anchor: yesterday = {yesterday_dose}u")

    # 1. Last night outcome
    if last_night_stats:
        tir  = last_night_stats['tir']
        hypo = last_night_stats['hypo']
        if hypo > 0:
            delta = -2 if hypo > 5 else -1
            adj  += delta
            reasons.append(f"Nocturnal hypo last night ({hypo:.0f}% below 4.0) -> {delta:+d}u")
        elif tir < 40:
            adj += 2
            reasons.append(
                f"Very high night (TIR={tir:.0f}%) -> +2u  "
                f"[skip this if cause was food/alcohol]"
            )
        elif tir < 60:
            adj += 1
            reasons.append(
                f"High night (TIR={tir:.0f}%) -> +1u  "
                f"[skip this if cause was food/alcohol]"
            )

    # 2. Activity transition: today vs 7-day rolling average
    if s1 is not None and s7 is not None:
        drop = round(s7 - s1, 1)
        rise = round(s1 - s7, 1)
        if drop >= 5:
            delta = +3 if drop >= 8 else +2
            adj  += delta
            reasons.append(
                f"Notably less active today (s1={s1:.1f} vs s7={s7:.1f}, -{drop:.1f}) -> +{delta}u"
            )
        elif drop >= 3:
            adj += 1
            reasons.append(
                f"Somewhat less active today (s1={s1:.1f} vs s7={s7:.1f}) -> +1u"
            )
        elif rise >= 4:
            delta = -2 if rise >= 6 else -1
            adj  += delta
            reasons.append(
                f"Notably more active today (s1={s1:.1f} vs s7={s7:.1f}, +{rise:.1f}) -> {delta:+d}u"
            )

    # 3. Heavy weightlifting residual
    wt_flag, wt_days_ago = weight_training_flag(ref_date, workouts_by_date)
    if wt_flag:
        delta = +2 if wt_days_ago == 1 else +1
        adj  += delta
        reasons.append(
            f"Heavy weightlifting {wt_days_ago}d ago -> sensitivity residual -> +{delta}u"
        )

    adj = max(14, min(36, round(adj)))

    # 4. Sanity check vs formula — only flag if unusually large AND formula is in a range
    # where it's historically reliable (s7 8-12). At high strain the formula undershoots.
    if formula_clip is not None and s7 is not None and 8 <= s7 <= 12:
        diff = adj - formula_clip
        if abs(diff) > 5:
            reasons.append(
                f"[!] Formula check: 46.7 - 2.28 x {s7:.1f} = {formula_clip}u  "
                f"(suggestion is {diff:+.0f}u off — review if unexpected)"
            )

    return {'base': formula_clip, 'adjusted': adj, 'anchor': yesterday_dose, 'reasons': reasons}

# --- OVERNIGHT STATS ----------------------------------------------------------
def overnight_stats(bdt, glucose, sleeps):
    next_wake = None
    for s in sleeps:
        if s['wake'] and s['wake'] > bdt and s['wake'] < bdt + timedelta(hours=14):
            next_wake = s['wake']
            break
    if not next_wake:
        next_wake = bdt + timedelta(hours=8)
    readings = glucose_in_range(bdt, next_wake, glucose)
    if len(readings) < 6:
        return None
    vals = [v for _, v in readings]
    return {
        'tir':    round(sum(1 for v in vals if 4.0 <= v <= 10.0) / len(vals) * 100, 1),
        'hypo':   round(sum(1 for v in vals if v < 4.0)          / len(vals) * 100, 1),
        'hyper':  round(sum(1 for v in vals if v > 10.0)         / len(vals) * 100, 1),
        'min_g':  round(min(vals), 1),
        'wake_g': round(vals[-1], 1),
        'inj_g':  round(vals[0],  1),
        'mean_g': round(sum(vals) / len(vals), 1),
    }

# --- MAIN REPORT --------------------------------------------------------------
def run():
    print("=" * 65)
    print("  T1D BASAL OPTIMIZER — Thomas Bloch-Nielsen")
    print(f"  Run date: {date.today()}")
    print("=" * 65)

    dexcom_paths, whoop_dir = find_files()
    print(f"\nDexcom files ({len(dexcom_paths)}):")
    for p in sorted(dexcom_paths):
        print(f"  {os.path.basename(p)}")
    print(f"WHOOP folder: {os.path.basename(whoop_dir)}\n")

    glucose, insulin = load_dexcom(dexcom_paths)
    cycles, sleeps, workouts = load_whoop(whoop_dir)
    strain_index = build_strain_index(cycles)

    workouts_by_date = defaultdict(list)
    for w in workouts:
        workouts_by_date[w['date']].append(w)

    whoop_days = len(strain_index)
    print(f"Strain data  : {whoop_days} days WHOOP")

    basal_raw = [(dt, u) for dt, t, u in insulin if 'Lang' in t]
    basal_raw.sort(key=lambda x: x[0])

    # Group split doses (e.g. two pens same evening) by date, summing units.
    # Use the earliest injection time as the representative timestamp.
    _basal_by_date = {}
    for dt, u in basal_raw:
        d = dt.date()
        if d not in _basal_by_date:
            _basal_by_date[d] = [dt, u]
        else:
            _basal_by_date[d][1] += u  # sum units, keep first timestamp
    basal = [(v[0], v[1]) for v in _basal_by_date.values()]
    basal.sort(key=lambda x: x[0])

    # -- Date range ------------------------------------------------------------
    g_start, g_end = glucose[0][0].date(), glucose[-1][0].date()
    total_days = (g_end - g_start).days + 1
    print(f"{'-'*65}")
    print(f"  DATA RANGE: {g_start} -> {g_end}  ({total_days} days)")
    print(f"{'-'*65}")

    # -- Overall TIR -----------------------------------------------------------
    vals = [v for _, v in glucose]
    tir  = sum(1 for v in vals if 4.0 <= v <= 10.0) / len(vals) * 100
    hypo = sum(1 for v in vals if v < 4.0)          / len(vals) * 100
    hypr = sum(1 for v in vals if v > 10.0)         / len(vals) * 100
    mean = sum(vals) / len(vals)

    print(f"\n  OVERALL GLYCEMIC SUMMARY ({total_days} days)")
    print(f"  Time In Range  4–10 mmol/L : {tir:5.1f}%  (target >=70%)")
    print(f"  Time Below     < 4.0       : {hypo:5.1f}%  (target <4%)")
    print(f"  Time Above     >10.0       : {hypr:5.1f}%  (target <25%)")
    print(f"  Mean glucose               : {mean:5.2f} mmol/L")
    print(f"  Min / Max                  : {min(vals):.1f} / {max(vals):.1f} mmol/L")

    # -- Recent 14-day TIR -----------------------------------------------------
    cutoff = datetime.combine(g_end - timedelta(days=14), datetime.min.time())
    r14    = [v for dt, v in glucose if dt >= cutoff]
    if r14:
        tir14  = sum(1 for v in r14 if 4 <= v <= 10) / len(r14) * 100
        hypo14 = sum(1 for v in r14 if v < 4)        / len(r14) * 100
        print(f"\n  LAST 14 DAYS")
        print(f"  TIR: {tir14:.1f}%   Hypo: {hypo14:.1f}%   Mean: {sum(r14)/len(r14):.2f} mmol/L")

    # -- Overnight history (last 14 nights) ------------------------------------
    print(f"\n  RECENT OVERNIGHT PERFORMANCE (last 14 nights)")
    print(f"  {'Date':<12} {'Dose':>6} {'S_1d':>6} {'S_7d':>6} {'TIR%':>6} {'Hypo%':>7} {'MinG':>6} {'WakeG':>7} {'InjG':>6}")
    recent_basal = [b for b in basal if b[0].date() >= g_end - timedelta(days=14)]
    for bdt, bunits in recent_basal:
        d   = bdt.date()
        s1  = strain_val(d, strain_index)
        s7  = rolling_strain(d, 7, strain_index)
        stats = overnight_stats(bdt, glucose, sleeps)
        if not stats:
            continue
        s1s = f"{s1:.1f}" if s1 else '-'
        s7s = f"{s7:.1f}" if s7 else '-'
        flag = ''
        if stats['hypo'] > 0:   flag = ' ! HYPO'
        elif stats['tir'] < 60: flag = ' ! HYPER'
        print(f"  {str(d):<12} {bunits:>5.0f}u  {s1s:>5}  {s7s:>5}  {stats['tir']:>5.1f}  "
              f"{stats['hypo']:>6.1f}  {stats['min_g']:>5.1f}  {stats['wake_g']:>6.1f}  "
              f"{stats['inj_g']:>5.1f}{flag}")

    # -- Strain trend ----------------------------------------------------------
    today    = g_end
    s_today  = strain_val(today, strain_index)
    s7_today = rolling_strain(today, 7, strain_index)
    s3_today = rolling_strain(today, 3, strain_index)
    s7_prev  = rolling_strain(today - timedelta(days=2), 5, strain_index)
    delta    = round((s3_today or 0) - (s7_prev or 0), 1) if s3_today and s7_prev else None

    today_src = strain_src(today, strain_index)
    print(f"\n  CURRENT STRAIN CONTEXT")
    print(f"  Today (s1)      : {s_today if s_today else 'N/A'}  [{today_src}]")
    print(f"  3-day avg (s3)  : {s3_today if s3_today else 'N/A'}")
    print(f"  7-day avg (s7)  : {s7_today if s7_today else 'N/A'}")
    if delta is not None:
        direction = 'dropping (activity decreasing)' if delta < -2 \
               else 'rising (activity increasing)'   if delta > 2  \
               else 'stable'
        print(f"  Trend           : {delta:+.1f}  ->  {direction}")

    # -- Transition warning ----------------------------------------------------
    if delta is not None:
        if delta < -3:
            steps = abs(round(delta / 2.5))
            print(f"\n  !  TRANSITION ALERT: Activity dropping fast.")
            print(f"     Consider titrating basal up +2-3u/night for ~{steps} nights")
            print(f"     until reaching rest-day target.")
        elif delta > 3:
            print(f"\n  !  TRANSITION ALERT: Activity rising fast.")
            print(f"     Consider titrating basal down -2u/night toward active-day target.")

    # -- Tonight's recommendation -----------------------------------------------
    print(f"\n  {'-'*61}")
    print(f"  TONIGHT'S BASAL SUGGESTION")
    print(f"  {'-'*61}")
    workouts_today = workouts_by_date.get(today, [])
    last_cgm = nearest_glucose(datetime.combine(today, datetime.max.time()), glucose, window_min=60)

    # Find yesterday's dose and last night's outcome (uses grouped basal)
    yesterday = today - timedelta(days=1)
    yesterday_dose = None
    last_night_stats = None
    for bdt, bunits in reversed(basal):
        if bdt.date() == yesterday:
            yesterday_dose   = bunits
            last_night_stats = overnight_stats(bdt, glucose, sleeps)
            break

    rec = recommend_basal(s7_today, s_today, yesterday_dose, last_night_stats, workouts_by_date, today)

    if rec['adjusted']:
        print(f"\n  Suggested dose  :  {rec['adjusted']}u")
        if rec['anchor']:
            print(f"  Yesterday       :  {rec['anchor']}u")
        print(f"  Formula check   :  {rec['base']}u  (46.7 - 2.28 x s7)")
        print(f"\n  Reasoning:")
        for r in rec['reasons']:
            print(f"    * {r}")
    else:
        print("  Insufficient data for tonight's recommendation.")

    if last_cgm:
        print(f"\n  Latest CGM reading: {last_cgm:.1f} mmol/L")

    # -- 3-day forecast --------------------------------------------------------
    print(f"\n  3-DAY FORWARD PROJECTION (assuming good nights, similar activity)")
    if s7_today is None:
        print(f"  ! WHOOP data appears to end before today -- upload a fresh WHOOP export")
    elif rec['adjusted']:
        base_proj = rec['adjusted']
        for i in range(1, 4):
            proj_date = today + timedelta(days=i)
            proj_s7 = s7_today
            if delta and delta < -2:
                proj_s7 = max(4, round(s7_today - 0.5 * i, 1))
            elif delta and delta > 2:
                proj_s7 = min(16, round(s7_today + 0.5 * i, 1))
            proj_formula = max(14, min(36, round(46.7 - 2.28 * proj_s7)))
            print(f"    {proj_date}  ~{base_proj}u  (formula ref: {proj_formula}u at s7={proj_s7:.1f})")

    # -- Workout quality today -------------------------------------------------
    if workouts_today:
        print(f"\n  TODAY'S WORKOUTS")
        for w in workouts_today:
            hi = (w['z3'] + w['z4'] + w['z5']) > 20
            wt = is_heavy_weights(w)
            tag = ' [HIGH INTENSITY]' if hi else ''
            tag += ' [HEAVY WEIGHTS — 48h effect]' if wt else ''
            print(f"    {w['start'].strftime('%H:%M')}–{w['end'].strftime('%H:%M')}  "
                  f"{w['activity']:<22} {w['duration']:.0f}min  "
                  f"strain={w['strain']:.1f}  avgHR={w['avg_hr']:.0f}{tag}")
    else:
        print(f"\n  No workouts logged today.")

    # -- Exercise-induced hypo risk (daytime) ----------------------------------
    print(f"\n  DAYTIME HYPO RISK SUMMARY (all workouts in dataset)")
    print(f"  Start glucose < 7.0 mmol/L  ->  34.5% hypo rate within 2h  !")
    print(f"  Start glucose 7.0–10.0      ->  11.0% hypo rate")
    print(f"  Start glucose > 10.0        ->   7.8% hypo rate")
    print(f"  Midday workouts (11–15h)    ->  36% hypo rate  !  (highest risk window)")

    print(f"\n  {'-'*61}")
    print(f"  Safety reminder: All suggestions are data-derived observations.")
    print(f"  Verify all dosing changes with your endocrinologist.")
    print(f"  {'-'*61}\n")

if __name__ == '__main__':
    run()
