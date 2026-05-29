"""
Predictor significance test (research) - which variables predict overnight TIR%?
Spearman correlation + Mann-Whitney median split A/B test on all candidates.
"""
import math
from whoop_loader import load_whoop
from dexcom_loader import load_dexcom
from night_stats import overnight_window, night_stats
from stats_utils import spearman


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


def main():
    # ── build dataset ──────────────────────────────────────────────────────────────
    glucose_list, basal_list, bolus = load_dexcom()
    strain_idx = load_whoop()

    nights = []
    for inj_dt, inj_date, dose in basal_list:
        if inj_dt.hour < 18:
            continue
        st = night_stats(overnight_window(inj_dt, glucose_list))
        if not st:
            continue
        s1  = strain_idx.get(inj_date, {}).get('strain')
        hrv = strain_idx.get(inj_date, {}).get('hrv')
        rec = strain_idx.get(inj_date, {}).get('recovery')
        rhr = strain_idx.get(inj_date, {}).get('rhr')
        nights.append({
            'date': inj_date, 'dose': dose,
            's1': s1,
            'hrv': hrv, 'recovery': rec, 'rhr': rhr,
            'bolus': bolus.get(inj_date, 0),
            **st
        })

    print(f'Total nights in dataset: {len(nights)}')

    # ── MAIN TEST ──────────────────────────────────────────────────────────────────
    candidates = [
        ('inj_g',    'Injection-time glucose'),
        ('s1',       'Today strain (s1)'),
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

    # Richer interaction modelling (dose x s1, bolus effects) lives in
    # scripts/inferential_predictor.py (Phase 5 / R8).


if __name__ == '__main__':
    main()
