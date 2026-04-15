# T1D Basal Optimization Reference
**Patient**: Thomas Bloch-Nielsen  
**Device**: Dexcom G7 (Android) + WHOOP  
**Insulin regimen**: MDI — long-acting basal once daily ~22:00, fast-acting bolus for meals  
**Target range**: 4.0–10.0 mmol/L  
**Analysis baseline**: 90 days (Jan 9 – Apr 8, 2026), ~25,600 CGM readings, 221 workouts  

---

## Glycemic Performance

**Full year (Apr 2025 – Apr 2026, 364 days)**:

| Metric | Value | Target |
|---|---|---|
| Time In Range (4–10) | 54.3% | ≥70% |
| Time Below (<4.0) | 1.0% | <4% ✓ |
| Time Above (>10.0) | 44.7% | <25% |
| Mean glucose | 10.13 mmol/L | — |

**Last 14 days (Apr 2026)**:

| Metric | Value |
|---|---|
| TIR | 76.2% |
| Hypo | 1.8% |
| Mean glucose | 8.25 mmol/L |

Primary problem is **hyperglycemia**, not hypoglycemia. Main drivers: (1) high injection-time glucose — 50% of nights injected at >10 mmol/L, and (2) post-diagnosis learning curve in early months.

---

## The Core Basal Model

### Formula
```
Base dose  =  45.8 − (2.18 × 7-day rolling WHOOP strain)
```
*Recalibrated Apr 2026 on Q4 Jan–Apr 2026 good nights (n=32, R²=0.64).*  
*Previous formula was 35 − 1.3×s7, valid for 90-day baseline but now superseded.*

| 7-day avg strain | Suggested base dose |
|---|---|
| 13–14 (very active week) | ~15–17u |
| 10–12 (active week) | ~19–23u |
| 7–9 (moderate week) | ~26–29u |
| 4–6 (inactive / vacation) | ~32–35u |

**The 7-day average is the primary input — not today's strain alone.**  
The body's insulin sensitivity shifts over multiple days, not overnight.

### Temporal drift note

Insulin requirements have been rising steadily quarter over quarter (Q1: avg 17u → Q4: avg 20.6u), consistent with the T1D honeymoon phase ending and beta cell output declining. Expect the formula to need re-calibration periodically — run recalibrate.py annually or after any major change in requirements.

### Adjustments on top of base dose

**1. Half-day adjustment** (today's strain 6–12):

| Last workout ended | Adjustment |
|---|---|
| Before 14:00 | +4u (treat as rest day — sensitivity window has closed) |
| 14:00–17:00 | +2u (moderate sensitivity remaining) |
| After 17:00 | ±0u (sensitivity still active overnight) |
| No structured workout logged | +5u (treat as full rest day regardless of WHOOP strain) |

**2. Heavy weightlifting residual** (sessions ≥35 min):
- Extends insulin sensitivity **24–48 hours** beyond the session — longer than any other activity type
- Day after heavy weights: +2u to suggestion
- Two days after heavy weights: +1u to suggestion

**3. Injection-time glucose correction**:

| CGM at ~22:00 | Adjustment |
|---|---|
| > 12 mmol/L | +2u |
| 10–12 mmol/L | +1u |
| 6–10 mmol/L | No adjustment |
| < 6 mmol/L | −1u |
| < 4 mmol/L | −2u + treat hypo before injecting |

---

## The Transition Rule

When moving between activity states (e.g., active training → vacation, or vacation → back to training):

```
Titrate +2–3u per night when going MORE inactive
Titrate −2u per night when going MORE active
```

Do not jump to the target dose in one step. The body needs 3–5 days to recalibrate.

**Validated example**: March 29 – April 4, 2026  
20u → 23u → 26u → 29u over 3 nights = four consecutive 100% TIR nights.

**Failed example**: February 6–15, 2026  
Dose oscillated reactively (up when hyper, down when hypo) without a plan = 8 consecutive poor nights.

---

## The Skiing / Assumed Activity Trap

**Never plan basal based on activity type. Use measured WHOOP strain.**

Skiing with small children (Feb 2026):
- 90-minute sessions, avg HR 82–90 bpm, zero Zone 2
- Strain: 4.3–5.5 per session — equivalent to a slow walk
- Expected by patient: high activity → low basal
- Result: 4 consecutive hyperglycemic nights

**Rule**: If WHOOP strain on day 1 of a new activity context is below your expectation, start titrating up immediately. Do not wait to see if it improves.

---

## The Half-Day Problem

Half-days (WHOOP strain 6–12) are the hardest to manage. Average TIR: **61.3%** — the worst of all categories.

### Key insight: timing beats quantity

A morning-only workout followed by inactivity = rest day overnight.  
An evening workout = active day overnight.

This is because exercise-induced insulin sensitivity peaks 4–8 hours after exercise ends. A session finishing at 08:00 has no meaningful effect on sensitivity at 22:00.

**Red flags**:
- Morning-only activity: 100% hyperglycemia rate in dataset
- WHOOP strain 6–12 with no structured workout logged: 83% hyperglycemia rate

---

## Daytime Exercise Safety Rules

**Starting glucose predicts hypo risk more than anything else**:

| Glucose at workout start | Hypo rate within 2h |
|---|---|
| < 7.0 mmol/L | **34.5%** |
| 7.0–10.0 | 11.0% |
| > 10.0 | 7.8% |

→ **Target >7.0 mmol/L before any aerobic session**

**Highest-risk workout window**: Midday (11:00–15:00) = **36% hypo rate**  
Likely cause: post-breakfast bolus IOB still active.

**Highest-risk activity types** (by hypo rate during/within 2h):
- Manual Labor: 50% (small n)
- Spin class: 26%
- Cycling: 21%
- Walking: 11%
- Weightlifting: 9%
- Running: 8%

**IOB stacking risk** (confirmed April 8, 2026):  
Correction bolus given at ~13:00 for high glucose (16.2 mmol/L) → cycling at 15:24 → hypo at 3.7 mmol/L by 16:31. Classic active bolus + aerobic exercise stacking.

---

## Activity Profile Reference

Thomas is a highly active cyclist and spin class attendee. Resting HR 44–54 bpm, HRV 40–71ms.

| Activity | Typical strain | Zone profile | Overnight effect |
|---|---|---|---|
| Commute cycling (30 min) | 7–9 | Z1–Z2 | ~8h |
| Hard cycling / interval (30 min) | 9–12 | Z2–Z3 | ~12h |
| Spin class (60+ min) | 12–15 | Z2–Z4 sustained | ~18h |
| Running (30 min, hard) | 9–12 | Z3–Z4 | ~12h |
| Heavy weightlifting (40+ min) | 9–13 | Z1 HR but high load | **24–48h** |
| Skiing with children | 4–6 | Z1 only | ~4h |
| Walking | 3–5 | Z1 | minimal |

---

## How to Use This System

### When new data arrives

1. Drop the new Dexcom Clarity CSV and WHOOP folder in `D:/claude`
2. Run: `py analyze.py`
3. Review the overnight history and tonight's suggestion
4. Cross-reference suggestion with your own assessment
5. Verify any planned changes with your endocrinologist

### What to tell Claude when starting a new session

> "New data uploaded. Run the analysis and give me tonight's basal suggestion."

Or for a deeper review:

> "Run the analysis and focus on [the last 2 weeks / a specific date / an upcoming trip]."

### Data quality tips

- **Log all bolus doses in Dexcom** — the model is blind to IOB without this
- **Log carb intake if possible** — explains outlier nights
- **Keep WHOOP charged and worn** — gaps in strain data degrade the 7-day rolling average
- Export Dexcom from Clarity app: Menu → Export data → CSV
- Export WHOOP: Profile → App settings → Download my data

---

## Known Model Limitations

- Does not account for illness, stress, or hormonal variation
- Does not account for carbohydrate intake
- Bolus logging in dataset is incomplete (~1.9 boluses/day logged — likely under-reported)
- Heavy weightlifting effect is patient-reported and consistent with T1D literature but has limited n in this dataset
- Suggestions are based on Q4 2026 formula — re-run recalibrate.py when formula feels off
- **All suggestions must be verified with endocrinologist before acting**

---

*Last updated: 2026-04-13. Formula recalibrated on full year (Apr 2025 – Apr 2026). Q4 formula active.*
