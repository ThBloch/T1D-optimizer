"""Thomas's basal dosing rules.

Single source of truth. Imported by dexcom_fetch.py (nightly suggestion) and
rules_model.py (backtest + ML threshold learning).
"""

FASTING_LO   = 10.0
FASTING_MID  = 12.0
FASTING_HI   = 14.0
ACTIVITY_THR = 12.0

# Slope-based tier (mmol/L/h, second-half overnight slope from night_stats).
# Symmetric direction; asymmetric magnitude (down side capped at -2).
SLOPE_FLAT   = 0.3
SLOPE_MID    = 0.7
SLOPE_HI     = 1.2

DOSE_MIN = 15
DOSE_MAX = 29


def thomas_rules(yesterday_dose, fasting, hypo_events, s1, new_pen=False,
                 sh_slope=None,
                 slope_flat=SLOPE_FLAT, slope_mid=SLOPE_MID, slope_hi=SLOPE_HI,
                 fasting_lo=FASTING_LO, fasting_mid=FASTING_MID, fasting_hi=FASTING_HI,
                 activity_threshold=ACTIVITY_THR):
    """Return (suggested_dose, reasoning_lines).

    Priority: hypo events override everything. Otherwise the second-half
    overnight slope drives the glucose tier; when slope is unavailable
    the rule falls back to wake-time fasting. Activity (s1) and new-pen
    adjustments stack on top of the glucose tier. Result clamped to
    [DOSE_MIN, DOSE_MAX]. Thresholds parameterised for ML alternatives.
    """
    if yesterday_dose is None:
        return None, ['No anchor dose - cannot suggest']

    adj_glucose = 0
    adj_activity = 0
    adj_pen = 0
    reasoning = []

    if hypo_events >= 2:
        adj_glucose = -2
        reasoning.append(f'Multiple hypos ({hypo_events}) -> -2u')
    elif hypo_events == 1:
        adj_glucose = -1
        reasoning.append('One hypo -> -1u')
    elif sh_slope is not None:
        if sh_slope > slope_hi:
            adj_glucose = +3
            reasoning.append(f'Slope {sh_slope:+.2f} > {slope_hi} -> +3u')
        elif sh_slope > slope_mid:
            adj_glucose = +2
            reasoning.append(f'Slope {sh_slope:+.2f} > {slope_mid} -> +2u')
        elif sh_slope > slope_flat:
            adj_glucose = +1
            reasoning.append(f'Slope {sh_slope:+.2f} > {slope_flat} -> +1u')
        elif sh_slope < -slope_hi:
            adj_glucose = -2
            reasoning.append(f'Slope {sh_slope:+.2f} < {-slope_hi} -> -2u')
        elif sh_slope < -slope_flat:
            adj_glucose = -1
            reasoning.append(f'Slope {sh_slope:+.2f} < {-slope_flat} -> -1u')
        else:
            reasoning.append(f'Slope {sh_slope:+.2f} in flat band -> no adjustment')
    elif fasting is not None:
        if fasting > fasting_hi:
            adj_glucose = +3
            reasoning.append(f'No slope; fasting {fasting} > {fasting_hi} -> +3u (fallback)')
        elif fasting > fasting_mid:
            adj_glucose = +2
            reasoning.append(f'No slope; fasting {fasting} > {fasting_mid} -> +2u (fallback)')
        elif fasting > fasting_lo:
            adj_glucose = +1
            reasoning.append(f'No slope; fasting {fasting} > {fasting_lo} -> +1u (fallback)')
        else:
            reasoning.append(f'No slope; fasting {fasting} in range -> no adjustment (fallback)')

    if s1 is not None and s1 >= activity_threshold:
        adj_activity = -2
        reasoning.append(f's1={s1:.1f} >= {activity_threshold} -> -2u')

    if new_pen:
        adj_pen = -1
        reasoning.append('New pen -> -1u')

    raw = yesterday_dose + adj_glucose + adj_activity + adj_pen
    dose = max(DOSE_MIN, min(DOSE_MAX, round(raw)))
    if dose != raw:
        reasoning.append(f'Clamped {raw:.0f}u -> {dose}u')

    return dose, reasoning
