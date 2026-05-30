"""
Bolus noise analysis:
1. How much variance does total daily bolus explain in overnight TIR?
2. Does bolus in the 4-6h window before injection (proxy for IOB) add signal?
3. Does adding bolus improve the model BEYOND what inj_g already captures?
   (partial correlation / residual analysis)
4. Is the bolus effect mediated through inj_g, or independent of it?
"""
from collections import defaultdict
from datetime import timedelta
from dexcom_loader import load_dexcom, load_bolus_combined
from night_stats import overnight_window, night_stats
from stats_utils import spearman, linreg, residuals


def sig(p):
    if p is None: return '   '
    if p<0.001: return '***'
    if p<0.01:  return '** '
    if p<0.05:  return '*  '
    return '   '


def main():
    glucose_list, basal_list, _ = load_dexcom()
    bolus_events = load_bolus_combined()
    bolus_by_date = defaultdict(float)
    for dt, u in bolus_events:
        bolus_by_date[dt.date()] += u

    # Build nightly dataset with bolus detail
    nights = []
    for inj_dt, inj_date, dose in basal_list:
        if inj_dt.hour < 18: continue
        st = night_stats(overnight_window(inj_dt, glucose_list))
        if not st: continue

        # Total bolus that day
        bolus_total = bolus_by_date.get(inj_date, 0)

        # Bolus in 4h window before injection (proxy for active IOB)
        window_start = inj_dt - timedelta(hours=4)
        bolus_4h = sum(u for dt,u in bolus_events
                       if window_start <= dt <= inj_dt)

        # Bolus in 6h window
        bolus_6h = sum(u for dt,u in bolus_events
                       if (inj_dt - timedelta(hours=6)) <= dt <= inj_dt)

        nights.append({
            'date': inj_date, 'dose': dose,
            'bolus_total': bolus_total,
            'bolus_4h': bolus_4h,
            'bolus_6h': bolus_6h,
            **st
        })

    # Exclude hypo-correction nights
    clean = [n for n in nights if not n['hypo_correction']]
    print(f'Total nights: {len(nights)}  |  Clean (excl hypo-correction): {len(clean)}')
    print(f'Nights with any pre-injection bolus (4h): {sum(1 for n in clean if n["bolus_4h"]>0)} ({sum(1 for n in clean if n["bolus_4h"]>0)/len(clean)*100:.1f}%)')
    print(f'Nights with any pre-injection bolus (6h): {sum(1 for n in clean if n["bolus_6h"]>0)} ({sum(1 for n in clean if n["bolus_6h"]>0)/len(clean)*100:.1f}%)')

    # ── STATS ──────────────────────────────────────────────────────────────────────
    print()
    print('='*70)
    print('1. DIRECT CORRELATIONS WITH TIR%  (clean nights only)')
    print('='*70)
    for key, label in [('inj_g','Injection-time glucose'),('bolus_total','Total daily bolus'),
                       ('bolus_4h','Bolus in 4h before injection'),('bolus_6h','Bolus in 6h before injection')]:
        xs=[n[key] for n in clean]; ys=[n['tir'] for n in clean]
        r,p=spearman(xs,ys)
        print(f'  {label:<32}  r={r:>7}  p={p:>8}  {sig(p)}')

    print()
    print('='*70)
    print('2. DOES BOLUS ADD SIGNAL BEYOND inj_g?')
    print('   (Spearman of bolus vs TIR residuals after removing inj_g effect)')
    print('='*70)

    inj_g_vals = [n['inj_g'] for n in clean]
    tir_vals   = [n['tir']   for n in clean]
    tir_resid  = residuals(inj_g_vals, tir_vals)

    for key, label in [('bolus_total','Total daily bolus'),
                       ('bolus_4h','Bolus in 4h before injection'),
                       ('bolus_6h','Bolus in 6h before injection')]:
        xs = [n[key] for n in clean]
        r, p = spearman(xs, tir_resid)
        print(f'  {label:<32}  r={r:>7}  p={p:>8}  {sig(p)}')

    print()
    print('='*70)
    print('3. IS BOLUS EFFECT MEDIATED THROUGH inj_g?')
    print('   (Spearman of bolus vs inj_g - if high, bolus is already captured)')
    print('='*70)
    for key, label in [('bolus_total','Total daily bolus'),
                       ('bolus_4h','Bolus in 4h before injection'),
                       ('bolus_6h','Bolus in 6h before injection')]:
        xs=[n[key] for n in clean]; ys=[n['inj_g'] for n in clean]
        r,p=spearman(xs,ys)
        print(f'  {label:<32}  r={r:>7}  p={p:>8}  {sig(p)}')

    print()
    print('='*70)
    print('4. VARIANCE EXPLAINED: inj_g alone vs inj_g + bolus_4h')
    print('='*70)

    # R² of inj_g alone
    _,_,r2_inj,_,_ = linreg(inj_g_vals, tir_vals)
    print(f'  inj_g alone:          R²={r2_inj:.4f}')

    # Multiple R² approximation: add bolus_4h
    # Use R² of [inj_g, bolus_4h] via correlation matrix approach
    b4h = [n['bolus_4h'] for n in clean]
    r_ib, _ = spearman(inj_g_vals, b4h)   # correlation between predictors
    r_it, _ = spearman(inj_g_vals, tir_vals)
    r_bt, _ = spearman(b4h, tir_vals)
    if r_ib is not None and r_it is not None and r_bt is not None and abs(r_ib) < 1.0:
        r2_multi = (r_it**2 + r_bt**2 - 2*r_it*r_bt*r_ib) / (1 - r_ib**2)
        print(f'  inj_g + bolus_4h:     R²~{round(r2_multi,4)} (rank-based approx)')
        print(f'  Incremental gain:     +{round(r2_multi - r2_inj, 4)}')

    print()
    print('='*70)
    print('5. BOLUS DISTRIBUTION - how often and how much before injection?')
    print('='*70)
    b4h_nonzero = [n['bolus_4h'] for n in clean if n['bolus_4h']>0]
    if b4h_nonzero:
        print(f'  Nights with bolus in 4h window: {len(b4h_nonzero)} ({len(b4h_nonzero)/len(clean)*100:.1f}%)')
        print(f'  When present - mean: {round(sum(b4h_nonzero)/len(b4h_nonzero),1)}u  '
              f'median: {sorted(b4h_nonzero)[len(b4h_nonzero)//2]}u  '
              f'max: {max(b4h_nonzero)}u')
        # TIR with vs without pre-injection bolus
        with_bolus    = [n['tir'] for n in clean if n['bolus_4h']>0]
        without_bolus = [n['tir'] for n in clean if n['bolus_4h']==0]
        print(f'  Mean TIR with pre-inj bolus:    {round(sum(with_bolus)/len(with_bolus),1)}%  (n={len(with_bolus)})')
        print(f'  Mean TIR without pre-inj bolus: {round(sum(without_bolus)/len(without_bolus),1)}%  (n={len(without_bolus)})')
        # Compare inj_g between groups
        inj_with    = [n['inj_g'] for n in clean if n['bolus_4h']>0]
        inj_without = [n['inj_g'] for n in clean if n['bolus_4h']==0]
        print(f'  Mean inj_g with pre-inj bolus:  {round(sum(inj_with)/len(inj_with),1)} mmol/L')
        print(f'  Mean inj_g without:             {round(sum(inj_without)/len(inj_without),1)} mmol/L')


if __name__ == '__main__':
    main()
