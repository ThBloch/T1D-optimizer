# Progress

## Done
- Clean data pipeline: Dexcom (multi-file, deduplicated) + WHOOP loader
- Predictor significance testing — validated inj_g and s1 as match variables, dropped s7
- Hypo-correction night detection and exclusion
- Bolus noise analysis — confirmed bolus adds no independent signal beyond inj_g
- Matching model (basal_analysis.py): inj_g ±2.5, s1 ±3.0
- Thomas's rules encoded and backtested (MAE 1.32u)
- ML model attempted — underperforms rules at current n, documented why
- Project restructured: data/, scripts/, docs/, output/

## Next session
- Tonight (2026-04-15): get wake glucose, hypo count, s1 when WHOOP closes → run rules_model.py for suggestion
- When NovoPen data arrives: integrate bolus loader, re-run bolus_noise_test.py on full dataset
- Consider: add carb logging field to nightly dataset when data becomes available

## Open questions
- New pen adjustment (-1u): Thomas has the rule but data isn't in Dexcom. Flag pen-switch dates manually?
- Activity threshold for -2u adjustment: data suggests s1 ≥ 12 (matches Thomas's rule). Worth testing s1 ≥ 11 as alternative.
