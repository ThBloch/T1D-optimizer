# Decisions Log

## 2026-04-15 — Dropped s7 as match variable
**Decision:** Replace s7 (7-day rolling strain) with inj_g as primary match variable.
**Why:** A/B test (predictor_test.py) showed s7 r=0.078, p=0.19 — not predictive of TIR. inj_g r=-0.376, p<0.001 is the strongest signal in the dataset.

## 2026-04-15 — Exclude hypo-correction nights from matching pool
**Decision:** Nights where Thomas had a nocturnal hypo and ate to correct are excluded from the matching pool (but shown in weekly summary).
**Why:** These nights show post-correction hyperglycemia that is an artefact of eating, not a basal signal. Including them corrupted the dose→outcome relationship. 58/297 nights (19.5%) affected.

## 2026-04-15 — Bolus not added as model feature
**Decision:** Bolus dose data not used as a predictor, despite having reliable logs to 2026-01-30.
**Why:** Partial correlation of bolus_4h vs TIR residuals (after removing inj_g effect) = -0.023, p=0.78. Bolus effect is fully mediated through inj_g — the 22:00 glucose reading already encodes the outcome of any pre-injection bolusing.

## 2026-04-15 — Rules model preferred over ML for dose suggestion
**Decision:** Thomas's rule-based titration is used for tonight's suggestion, not an ML model.
**Why:** Decision tree (learned from data) test MAE = 1.45u vs rules MAE = 1.32u. With n=239 clean nights and prev_dose explaining 95.6% of variance, ML has insufficient data to improve on well-designed rules.

## 2026-04-15 — Clean build (all prior scripts superseded)
**Decision:** Rewrote analysis from scratch, superseding analyze.py, recalibrate.py, REFERENCE.md.
**Why:** Prior model used s7 as primary match variable (shown to be non-predictive) and did not account for hypo-correction nights. Thomas also explicitly requested a clean start.
