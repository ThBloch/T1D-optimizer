"""Shared overnight glucose statistics.

Single source of truth for overnight window slicing, per-night stats,
and second-half slope computation.

Constants exported: HYPO_THR, WAKE_HOUR, OVN_START,
                    CLINICAL_TIR_LO/HI (4-10), TARGET_LO/HI (5-8),
                    SECOND_HALF_FRACTION, SH_MIN_READINGS.
"""

from datetime import datetime, timedelta

HYPO_THR    = 4.0
WAKE_HOUR   = 7
OVN_START   = 22

CLINICAL_TIR_LO = 4.0
CLINICAL_TIR_HI = 10.0
TARGET_LO   = 5.0
TARGET_HI   = 8.0

HYPO_CORRECTION_THR = 10.0

SECOND_HALF_FRACTION = 0.5
SH_MIN_READINGS      = 10


def overnight_window(inj_dt, glucose_list):
    """Readings from inj_dt through WAKE_HOUR:00 next morning."""
    end = datetime.combine(
        inj_dt.date() + timedelta(days=1),
        datetime.min.time().replace(hour=WAKE_HOUR)
    )
    return [(dt, v) for dt, v in glucose_list if inj_dt <= dt <= end]


def night_stats(readings, min_readings=6):
    """Compute overnight stats from pre-windowed (datetime, mmol/L) pairs.

    Returns None if fewer than min_readings readings.
    Fields returned:
      n_readings, fasting, mean, min_g, max_g, inj_g
      tir       -- % time in TARGET range (5-8 mmol/L)
      tir_full  -- % time in CLINICAL range (4-10 mmol/L)
      hypo_pct, hyper_pct, hyper_adj
      hypo_events (multi-episode count), hypo_correction, correction_spike_above_10
    """
    if len(readings) < min_readings:
        return None

    vals = [v for _, v in readings]
    n = len(vals)

    hypo_events, in_hypo = 0, False
    for v in vals:
        if v < HYPO_THR and not in_hypo:
            hypo_events += 1
            in_hypo = True
        elif v >= HYPO_THR:
            in_hypo = False

    hypo_idx = next((i for i, v in enumerate(vals) if v < HYPO_THR), None)
    hypo_correction = False
    correction_spike_above_10 = False
    if hypo_idx is not None:
        post = vals[hypo_idx:]
        if max(post) > HYPO_CORRECTION_THR:
            hypo_correction = True
        if max(post) > CLINICAL_TIR_HI:
            correction_spike_above_10 = True

    hypo_pct  = round(sum(1 for v in vals if v < HYPO_THR) / n * 100, 1)
    hyper_pct = round(sum(1 for v in vals if v > CLINICAL_TIR_HI) / n * 100, 1)

    return {
        'n_readings':                n,
        'fasting':                   round(vals[-1], 1),
        'mean':                      round(sum(vals) / n, 1),
        'min_g':                     round(min(vals), 1),
        'max_g':                     round(max(vals), 1),
        'inj_g':                     round(vals[0], 1),
        'tir':                       round(sum(1 for v in vals if TARGET_LO <= v <= TARGET_HI) / n * 100, 1),
        'tir_full':                  round(sum(1 for v in vals if CLINICAL_TIR_LO <= v <= CLINICAL_TIR_HI) / n * 100, 1),
        'hypo_pct':                  hypo_pct,
        'hyper_pct':                 hyper_pct,
        'hyper_adj':                 0.0 if hypo_correction else hyper_pct,
        'hypo_events':               hypo_events,
        'hypo_correction':           hypo_correction,
        'correction_spike_above_10': correction_spike_above_10,
    }


def second_half_trend(readings):
    """Return (sh_slope_mmol_per_h, sh_delta_mmol, sh_n) for the second half of the night.

    sh_slope: linear regression slope over time (mmol/L per hour); positive = rising.
    sh_delta: last - first value in the second half.
    sh_n:     number of readings in the second half.
    Returns (None, None, sh_n) when sh_n < SH_MIN_READINGS.
    """
    if not readings:
        return None, None, 0
    split  = int(len(readings) * SECOND_HALF_FRACTION)
    second = readings[split:]
    sh_n   = len(second)
    if sh_n < SH_MIN_READINGS:
        return None, None, sh_n
    t0 = second[0][0]
    xs = [(dt - t0).total_seconds() / 3600.0 for dt, _ in second]
    ys = [v for _, v in second]
    mx = sum(xs) / sh_n
    my = sum(ys) / sh_n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None, None, sh_n
    slope = num / den
    return slope, ys[-1] - ys[0], sh_n
