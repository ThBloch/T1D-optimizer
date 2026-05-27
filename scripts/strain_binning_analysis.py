"""Strain binning analysis (E1) - one-off analysis script.

Bins historical dose-nights by WHOOP strain (s1) and reports per-bin outcomes,
with second-half glucose slope as the primary signal for whether the dose was
correct: down = dose too high, up = dose too low, flat = correct.

Reuses load_dexcom, load_whoop, and the overnight-window logic from
rules_model.overnight_stats. Output: stdout + output/strain_binning.txt.

Run: py -X utf8 scripts/strain_binning_analysis.py
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, median

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'scripts'))

from dexcom_loader import load_dexcom
from whoop_loader import load_whoop

SECOND_HALF_FRACTION = 0.5
SH_MIN_READINGS      = 10
FLAT_BAND            = 0.3
WAKE_HOUR            = 7
HYPO_THR             = 4.0
TGT_LO, TGT_HI       = 4.0, 10.0
MIN_USABLE_FULL_BINS = 80
MIN_USABLE_REDUCED   = 50

OUT_DIR  = PROJECT_ROOT / 'output'
OUT_DIR.mkdir(exist_ok=True)
OUT_FILE = OUT_DIR / 'strain_binning.txt'


def overnight_window(inj_dt, glucose_list):
    end = datetime.combine(inj_dt.date() + timedelta(days=1),
                           datetime.min.time().replace(hour=WAKE_HOUR))
    return [(dt, v) for dt, v in glucose_list if inj_dt <= dt <= end]


def night_outcome(rdgs):
    if len(rdgs) < 6:
        return None
    vals = [v for _, v in rdgs]
    n = len(vals)
    hypo_events = 0
    in_hypo = False
    for v in vals:
        if v < HYPO_THR and not in_hypo:
            hypo_events += 1
            in_hypo = True
        elif v >= HYPO_THR:
            in_hypo = False
    hypo_idx = next((i for i, v in enumerate(vals) if v < HYPO_THR), None)
    hypo_correction = hypo_idx is not None and max(vals[hypo_idx:]) > 7.0
    return {
        'tir':              sum(1 for v in vals if TGT_LO <= v <= TGT_HI) / n * 100,
        'fasting':          vals[-1],
        'mean':             sum(vals) / n,
        'inj_g':            vals[0],
        'min_g':            min(vals),
        'hypo_events':      hypo_events,
        'hypo_correction':  hypo_correction,
    }


def second_half_trend(rdgs):
    """Return (sh_slope_mmol_per_h, sh_delta_mmol, sh_n)."""
    if not rdgs:
        return None, None, 0
    split = int(len(rdgs) * SECOND_HALF_FRACTION)
    second = rdgs[split:]
    sh_n = len(second)
    if sh_n < SH_MIN_READINGS:
        return None, None, sh_n
    t0 = second[0][0]
    xs = [(dt - t0).total_seconds() / 3600.0 for dt, _ in second]
    ys = [v for _, v in second]
    mx = sum(xs) / sh_n
    my = sum(ys) / sh_n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    slope = num / den if den > 0 else 0.0
    delta = ys[-1] - ys[0]
    return slope, delta, sh_n


def classify_trend(slope):
    if slope is None:
        return None
    if slope < -FLAT_BAND:
        return 'down'
    if slope > FLAT_BAND:
        return 'up'
    return 'flat'


def quantile(sorted_vals, q):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * q
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def build_nights(glucose_list, basal_list, strain_idx):
    nights = []
    for inj_dt, inj_date, dose in basal_list:
        if inj_dt.hour < 18:
            continue
        rdgs = overnight_window(inj_dt, glucose_list)
        st = night_outcome(rdgs)
        if not st:
            continue
        slope, delta, sh_n = second_half_trend(rdgs)
        s1 = strain_idx.get(inj_date, {}).get('strain')
        nights.append({
            'date':          inj_date,
            'dose':          dose,
            's1':            s1,
            'sh_slope':      slope,
            'sh_delta':      delta,
            'sh_n':          sh_n,
            'trend_class':   classify_trend(slope),
            **st,
        })
    nights.sort(key=lambda n: n['date'])
    for i, n in enumerate(nights):
        if i == 0:
            n['prev_dose'] = None
            n['prev_fasting'] = None
            n['prev_hypo_events'] = None
            n['delta_dose'] = None
        else:
            p = nights[i - 1]
            n['prev_dose'] = p['dose']
            n['prev_fasting'] = p['fasting']
            n['prev_hypo_events'] = p['hypo_events']
            n['delta_dose'] = n['dose'] - p['dose']
    return nights


def apply_filters(nights):
    reasons = {'s1_none': 0, 'hypo_correction': 0, 'no_anchor': 0, 'sh_n_low': 0}
    usable = []
    for n in nights:
        if n['s1'] is None:
            reasons['s1_none'] += 1
            continue
        if n['hypo_correction']:
            reasons['hypo_correction'] += 1
            continue
        if n['prev_dose'] is None:
            reasons['no_anchor'] += 1
            continue
        if n['sh_n'] < SH_MIN_READINGS or n['sh_slope'] is None:
            reasons['sh_n_low'] += 1
            continue
        usable.append(n)
    return usable, reasons


def bin_summary(nights, edges, labels):
    out = []
    for i, label in enumerate(labels):
        lo, hi = edges[i], edges[i + 1]
        if i == len(labels) - 1:
            grp = [n for n in nights if lo <= n['s1'] <= hi]
        else:
            grp = [n for n in nights if lo <= n['s1'] < hi]
        if not grp:
            out.append({'label': label, 'lo': lo, 'hi': hi, 'n': 0})
            continue
        down = sum(1 for n in grp if n['trend_class'] == 'down')
        flat = sum(1 for n in grp if n['trend_class'] == 'flat')
        up   = sum(1 for n in grp if n['trend_class'] == 'up')
        hypo_nights = sum(1 for n in grp if n['hypo_events'] >= 1)
        hyper_nights = sum(1 for n in grp if n['mean'] > 10)
        out.append({
            'label':           label,
            'lo':              lo,
            'hi':              hi,
            'n':               len(grp),
            'med_dose':        median(n['dose'] for n in grp),
            'med_prev_dose':   median(n['prev_dose'] for n in grp),
            'mean_delta_dose': mean(n['delta_dose'] for n in grp),
            'mean_sh_slope':   mean(n['sh_slope'] for n in grp),
            'pct_down':        down / len(grp) * 100,
            'pct_flat':        flat / len(grp) * 100,
            'pct_up':          up / len(grp) * 100,
            'mean_tir':        mean(n['tir'] for n in grp),
            'mean_fasting':    mean(n['fasting'] for n in grp),
            'hypo_rate':       hypo_nights / len(grp) * 100,
            'hyper_rate':      hyper_nights / len(grp) * 100,
        })
    return out


def fmt_bin_table(bins):
    lines = []
    header = (f'{"bin":<7} {"range":>11} {"n":>4} {"medD":>5} {"deltD":>6} '
              f'{"slope":>7} {"%down":>6} {"%flat":>6} {"%up":>5} '
              f'{"TIR":>6} {"fast":>6} {"hypo%":>6} {"hyper%":>7}')
    lines.append(header)
    lines.append('-' * len(header))
    for b in bins:
        if b['n'] == 0:
            lines.append(f'{b["label"]:<7} {b["lo"]:>4.1f}-{b["hi"]:>4.1f}  '
                         f'{0:>4}  (empty)')
            continue
        lines.append(
            f'{b["label"]:<7} {b["lo"]:>4.1f}-{b["hi"]:>4.1f} '
            f'{b["n"]:>4} {b["med_dose"]:>5.1f} '
            f'{b["mean_delta_dose"]:>+6.2f} {b["mean_sh_slope"]:>+7.3f} '
            f'{b["pct_down"]:>6.1f} {b["pct_flat"]:>6.1f} {b["pct_up"]:>5.1f} '
            f'{b["mean_tir"]:>6.1f} {b["mean_fasting"]:>6.1f} '
            f'{b["hypo_rate"]:>6.1f} {b["hyper_rate"]:>7.1f}'
        )
    return '\n'.join(lines)


def suggest_thresholds(bins):
    valid = [b for b in bins if b['n'] > 0]
    if len(valid) < 4:
        return ['Not enough non-empty bins to suggest thresholds.']
    lines = ['Adjacent-bin slope comparison (look for sign flips):']
    for i in range(len(valid) - 1):
        a, b = valid[i], valid[i + 1]
        flip = ((a['mean_sh_slope'] >= 0) > (b['mean_sh_slope'] >= 0)) or \
               ((a['mean_sh_slope'] >= 0) < (b['mean_sh_slope'] >= 0))
        marker = '  <-- slope sign flip' if flip else ''
        lines.append(
            f'  {a["label"]:<6} (mean {a["mean_sh_slope"]:+.3f}) -> '
            f'{b["label"]:<6} (mean {b["mean_sh_slope"]:+.3f}){marker}'
        )
    return lines


def histogram(values, lo, hi, n_buckets):
    step = (hi - lo) / n_buckets
    counts = [0] * n_buckets
    below = sum(1 for v in values if v < lo)
    above = sum(1 for v in values if v >= hi)
    for v in values:
        if lo <= v < hi:
            idx = min(int((v - lo) / step), n_buckets - 1)
            counts[idx] += 1
    peak = max(counts) if counts else 1
    out = []
    if below:
        out.append(f'  < {lo:+.2f}        : {below}')
    for i, c in enumerate(counts):
        bar = '#' * int(c / peak * 40) if peak > 0 else ''
        out.append(f'  {lo + i*step:+.2f} to {lo + (i+1)*step:+.2f}: {c:4d}  {bar}')
    if above:
        out.append(f'  >= {hi:+.2f}       : {above}')
    return '\n'.join(out)


def main():
    print('Loading data...')
    glucose_list, basal_list, _ = load_dexcom()
    strain_idx = load_whoop()
    nights = build_nights(glucose_list, basal_list, strain_idx)
    usable, reasons = apply_filters(nights)

    lines = []
    def w(s=''):
        lines.append(s)

    # Section 1
    w('=' * 78)
    w('SECTION 1 - DATA ADEQUACY')
    w('=' * 78)
    if basal_list:
        d_min = min(b[1] for b in basal_list)
        d_max = max(b[1] for b in basal_list)
        w(f'Dose-night date range       : {d_min} -> {d_max} '
          f'({(d_max - d_min).days + 1} days span)')
    w(f'Total evening-injection nights: {len(nights)}')
    w(f'  Dropped (no s1)             : {reasons["s1_none"]}')
    w(f'  Dropped (hypo correction)   : {reasons["hypo_correction"]}')
    w(f'  Dropped (no prev-dose anchor): {reasons["no_anchor"]}')
    w(f'  Dropped (second half too short): {reasons["sh_n_low"]}')
    w(f'Usable nights                 : {len(usable)}')
    use_full_bins = len(usable) >= MIN_USABLE_FULL_BINS
    if len(usable) < MIN_USABLE_REDUCED:
        w('')
        w(f'!! Less than {MIN_USABLE_REDUCED} usable nights - results unreliable.')
    elif not use_full_bins:
        w('')
        w(f'-- Less than {MIN_USABLE_FULL_BINS} usable nights - using 4 bins instead of 6.')
    w('')

    if not usable:
        w('No usable nights - aborting.')
        OUT_FILE.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        print('\n'.join(lines))
        return

    # Section 2
    w('=' * 78)
    w('SECTION 2 - STRAIN DISTRIBUTION (s1, WHOOP day strain)')
    w('=' * 78)
    strains = sorted(n['s1'] for n in usable)
    w(f'min  : {strains[0]:.2f}')
    for q in (0.10, 0.25, 0.50, 0.75, 0.90):
        w(f'p{int(q * 100):02d}  : {quantile(strains, q):.2f}')
    w(f'max  : {strains[-1]:.2f}')
    w(f'mean : {mean(strains):.2f}')
    w('')

    # Section 3
    w('=' * 78)
    w('SECTION 3 - SECOND-HALF SLOPE DISTRIBUTION (mmol/L per hour)')
    w('=' * 78)
    slopes = sorted(n['sh_slope'] for n in usable)
    w(f'min  : {slopes[0]:+.3f}')
    for q in (0.10, 0.25, 0.50, 0.75, 0.90):
        w(f'p{int(q * 100):02d}  : {quantile(slopes, q):+.3f}')
    w(f'max  : {slopes[-1]:+.3f}')
    w(f'mean : {mean(slopes):+.3f}')
    w('')
    w('Histogram (capped at +/-2 mmol/L/h):')
    w(histogram([n['sh_slope'] for n in usable], -2.0, 2.0, 20))
    w('')
    tot = len(usable)
    down = sum(1 for n in usable if n['trend_class'] == 'down')
    flat = sum(1 for n in usable if n['trend_class'] == 'flat')
    up   = sum(1 for n in usable if n['trend_class'] == 'up')
    w(f'Trend bands at +/-{FLAT_BAND} mmol/L/h (overall):')
    w(f'  down : {down:4d} ({down/tot*100:5.1f}%) -- dose too high')
    w(f'  flat : {flat:4d} ({flat/tot*100:5.1f}%) -- dose correct')
    w(f'  up   : {up:4d}  ({up/tot*100:5.1f}%) -- dose too low')
    w('')

    n_bins = 6 if use_full_bins else 4

    # Section 4
    q_edges = [strains[0]]
    for i in range(1, n_bins):
        q_edges.append(quantile(strains, i / n_bins))
    q_edges.append(strains[-1])
    q_labels = [f'Q{i+1}' for i in range(n_bins)]
    q_bins = bin_summary(usable, q_edges, q_labels)
    w('=' * 78)
    w(f'SECTION 4 - QUANTILE BINS ({n_bins} bins, equal-count)')
    w('=' * 78)
    w(fmt_bin_table(q_bins))
    w('')

    # Section 5
    if n_bins == 6:
        f_edges = [0, 6, 10, 13, 16, 18, 21]
        f_labels = ['rest', 'light', 'mod', 'vigor', 'peak', 'max']
    else:
        f_edges = [0, 8, 12, 16, 21]
        f_labels = ['rest', 'mod', 'vigor', 'peak']
    f_bins = bin_summary(usable, f_edges, f_labels)
    w('=' * 78)
    w(f'SECTION 5 - FIXED CLINICAL BINS ({n_bins} bins)')
    w('=' * 78)
    w(fmt_bin_table(f_bins))
    w('')

    # Section 6
    w('=' * 78)
    w('SECTION 6 - CANDIDATE THRESHOLDS')
    w('=' * 78)
    w('Quantile bins:')
    for ln in suggest_thresholds(q_bins):
        w('  ' + ln)
    w('')
    w('Fixed clinical bins:')
    for ln in suggest_thresholds(f_bins):
        w('  ' + ln)
    w('')
    w('Reading these:')
    w('  - Bins where mean slope is < 0 -> Thomas typically over-doses there -> assign -adj.')
    w('  - Bins where mean slope is > 0 -> Thomas typically under-doses there -> assign +adj.')
    w('  - Sign-flip boundary is a natural threshold candidate.')
    w('')

    # Section 7
    w('=' * 78)
    w('SECTION 7 - TREND vs TIR/FASTING CONFLICTS')
    w('=' * 78)
    conflicts = 0
    for b in q_bins + f_bins:
        if b['n'] == 0:
            continue
        slope_sign = ('down' if b['mean_sh_slope'] < -0.05
                      else 'up' if b['mean_sh_slope'] > 0.05
                      else 'flat')
        tir_ok     = b['mean_tir'] >= 70
        fasting_ok = TGT_LO <= b['mean_fasting'] <= TGT_HI
        if slope_sign != 'flat' and tir_ok and fasting_ok:
            conflicts += 1
            w(f'  {b["label"]:<6}: slope={slope_sign} ({b["mean_sh_slope"]:+.3f}), '
              f'TIR={b["mean_tir"]:.1f}%, fasting={b["mean_fasting"]:.1f} '
              f'(TIR+fasting say OK but slope disagrees)')
    if conflicts == 0:
        w('No conflicts - trend signal and TIR/fasting agree across all bins.')
    w('')

    # Section 8
    w('=' * 78)
    w('SECTION 8 - CAVEATS')
    w('=' * 78)
    small_q = [b['label'] for b in q_bins if 0 < b['n'] < 10]
    small_f = [b['label'] for b in f_bins if 0 < b['n'] < 10]
    if small_q:
        w(f'Quantile bins with n<10 (low reliability): {", ".join(small_q)}')
    if small_f:
        w(f'Fixed bins    with n<10 (low reliability): {", ".join(small_f)}')
    sign_disagree = sum(
        1 for n in usable
        if abs(n['sh_slope']) > 0.1 and abs(n['sh_delta']) > 0.5
        and ((n['sh_slope'] > 0) != (n['sh_delta'] > 0))
    )
    w(f'Nights where sh_slope and sh_delta disagree in sign: {sign_disagree}')
    if reasons['s1_none'] > 0:
        w(f'Missing strain coverage: {reasons["s1_none"]} nights lacked s1 (WHOOP gap '
          f'or in-progress cycle).')
    w('')
    w(f'Direction: down = dose too HIGH, up = dose too LOW.')
    w(f'Trend band: flat = |slope| <= {FLAT_BAND} mmol/L/h.')
    w(f'Second-half split: last {int(SECOND_HALF_FRACTION*100)}% of CGM readings '
      f'between injection and {WAKE_HOUR}:00 wake.')

    text = '\n'.join(lines) + '\n'
    OUT_FILE.write_text(text, encoding='utf-8')
    print(text)
    print(f'Report written to: {OUT_FILE}')


if __name__ == '__main__':
    main()
