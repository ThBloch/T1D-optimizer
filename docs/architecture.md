# Architecture

## Model approach

### What we predict
Not the optimal dose directly — we don't have ground truth labels. Instead:
1. **Matching model** (`basal_analysis.py`): find historical nights similar to tonight, show outcomes by dose - This is incorrect. Goal was to do ML or similar to predict based on math and statistics. Not based on matching days.
2. **Rules model** (`rules_model.py`): encode Thomas's titration rules, backtest, suggest tonight's dose
3. **Math model** - predicting the correct dose based on a machine learning model splitting the data into two groups. Training and testing.

### Validated predictors (from predictor_test.py)
| Variable | Spearman r | p | Status |
|---|---|---|---|
| inj_g (injection-time glucose) | -0.376 | <0.001 | Primary match variable |
| s1 (today's WHOOP strain) | 0.245 | 0.001 | Secondary match variable |
| bolus_4h | -0.023 (partial) | 0.78 | Dropped — fully mediated by inj_g |
| s7 (7-day rolling strain) | 0.078 | 0.19 | Dropped — not predictive |

### Exclusion rules
1. **Hypo-correction nights**: Thomas eats fast carbs to correct nocturnal hypos → glucose spikes after hypo. These nights show inflated hyper% that is a correction artefact, not a basal signal. Detected as: hypo event (val <4.0) followed by recovery above 7.0 mmol/L. 58/297 nights (19.5%). Excluded from matching, shown as DOSE>HIGH in weekly summary.
2. **High-bolus outlier nights**: IQR method. Bolus confounder.

### Thomas's titration rules
Anchor = yesterday's dose, then:
- Hypo takes priority over fasting adjustment
- 1 hypo event → -1u | ≥2 hypo events → -2u
- Fasting ~11 → +1u | fasting 12–14 → +2u | fasting >14 → +3u
- s1 ≥ 12 → -2u (very active day)
- New pen day → -1u (no data available)
- Clamp: 15–29u

Rules MAE = 1.32u vs anchor-only 1.53u. Decision tree (learned) = 1.45u — rules outperform ML at current n.

### Why ML underperforms
- prev_dose explains 95.6% of variance in actual dose decisions (feature importance)
- Outcome prediction (TIR%) has R² ≈ -0.10 on test set — model is worse than mean predictor
- Missing variable is likely meal/carb data, not activity (activity is captured via s1 and inj_g)
- ML will become more viable when NovoPen bolus data is integrated

## Data pipeline
- Multiple Dexcom CSV exports overlap — deduplicated by exact timestamp
- WHOOP cycle date assigned as (cycle_end - 6h).date() to handle midnight-spanning cycles
- Overnight window: injection time → next 07:00
- Bolus logging reliable: 2025-04-09 → 2026-01-30. Gap thereafter (NovoPen switch).
