# Decisions Log

Durable record of choices that shape this project and the reasoning behind them.

Format and rules: `claude-setup/docs/decisions-log-conventions.md`.

Quick rules:
- Append entries chronologically. Never reorder.
- Once written, an entry's content is immutable. Only the `Status` line can change (when superseded).
- Read this file before proposing non-trivial changes to `thomas_rules`, model parameters, data sources, or analysis approach.

Pre-existing entries below were written before the formal conventions were adopted on 2026-05-23. They have been retrofit with `Status: accepted` lines; no other content was changed.

---

## 2026-04-15 — Dropped s7 as match variable
**Status:** accepted
**Decision:** Replace s7 (7-day rolling strain) with inj_g as primary match variable.
**Why:** A/B test (predictor_test.py) showed s7 r=0.078, p=0.19 — not predictive of TIR. inj_g r=-0.376, p<0.001 is the strongest signal in the dataset.

## 2026-04-15 — Exclude hypo-correction nights from matching pool
**Status:** accepted
**Decision:** Nights where Thomas had a nocturnal hypo and ate to correct are excluded from the matching pool (but shown in weekly summary).
**Why:** These nights show post-correction hyperglycemia that is an artefact of eating, not a basal signal. Including them corrupted the dose→outcome relationship. 58/297 nights (19.5%) affected.

## 2026-04-15 — Bolus not added as model feature
**Status:** accepted
**Decision:** Bolus dose data not used as a predictor, despite having reliable logs to 2026-01-30.
**Why:** Partial correlation of bolus_4h vs TIR residuals (after removing inj_g effect) = -0.023, p=0.78. Bolus effect is fully mediated through inj_g — the 22:00 glucose reading already encodes the outcome of any pre-injection bolusing.

## 2026-04-15 — Rules model preferred over ML for dose suggestion
**Status:** accepted
**Decision:** Thomas's rule-based titration is used for tonight's suggestion, not an ML model.
**Why:** Decision tree (learned from data) test MAE = 1.45u vs rules MAE = 1.32u. With n=239 clean nights and prev_dose explaining 95.6% of variance, ML has insufficient data to improve on well-designed rules.

## 2026-04-15 — Clean build (all prior scripts superseded)
**Status:** accepted
**Decision:** Rewrote analysis from scratch, superseding analyze.py, recalibrate.py, REFERENCE.md.
**Why:** Prior model used s7 as primary match variable (shown to be non-predictive) and did not account for hypo-correction nights. Thomas also explicitly requested a clean start.

## 2026-05-15 — New-pen adjustment (-1u)
**Status:** accepted
**Decision:** Add a new rule: starting a fresh basal pen applies -1u. Stacks with glucose and activity adjustments. Triggered via `--new-pen` CLI flag on `dexcom_fetch.py`.
**Why:** Thomas observed (empirical, lived) that the first night on a fresh pen tends to run higher than expected — likely a priming/needle/insulin-freshness effect. -1u absorbs the bias on the first night without altering the steady-state titration. Encoded in `rules.py:thomas_rules(..., new_pen=True)` and locked in by 3 new unit tests.

## 2026-05-15 — Hypo override flag (`--no-hypo`)
**Status:** accepted
**Decision:** Allow the operator to instruct `dexcom_fetch.py` to ignore CGM-detected hypos for the rule calculation when they are judged sensor noise. The diary still records the raw CGM count for historical accuracy; the override appears as the first line in the reasoning chain.
**Why:** Dexcom G7 occasionally reports a single sub-4.0 reading (e.g. 3.9) due to sensor noise at the boundary. When the operator can verify (subjectively or via parallel finger-stick) that no real hypo occurred, the rule's automatic -1u correction is unwarranted and would drive the dose downward incorrectly. The override is opt-in per run, not a default, so the conservative behavior is preserved.

## 2026-05-18 — Rolled back first `/dose` slash command draft
**Status:** accepted
**Decision:** Deleted the first `D:/claude/t1d/.claude/commands/dose.md` draft. `/dose` rebuild deferred until Phase 1 of the automation roadmap lands (`--dose N` flag on `dexcom_fetch.py`, removal of `input()` prompts).
**Why:** The draft added an interactive orchestration layer (AskUserQuestion for new-pen, factors, sensor-noise) directly on top of the current interactive script. Phase 1 is removing script interactivity to make scripts cron-friendly for the Telegram path. Building `/dose` on the pre-Phase-1 script meant near-certain rewrite once Phase 1 ships. Cleaner to do Phase 1 first; `/dose` then becomes a ~20-line wrapper around a non-interactive `--dose N` invocation. Backlog entry moved here from `claude-setup/improvements.md` D1 to enforce the rule that project-specific work lives in the project's own backlog.

## 2026-05-21 — GitHub strategy: defer public push until project is "share-ready"
**Status:** accepted
**Decision:** Repo stays local for now (no remote yet). Eventual aim is public, to help other T1D patients/builders. Gated on an informal quality bar - E1 (strain rule refinement), E10 (nighttime objective validation), at least E5 (Phase 1 automation) - plus C1 sanitization. Three migration paths logged in E2 for the eventual flip.
**Why:** Thomas wants the tool shareable if it can help others, but the current state is a single-user manual workflow with a coarse strain rule and an outcome metric (TIR(5-8)) that may be reshaped by E10. Going public now would lock in shape decisions still in flux. Defer until the model + automation make this a real tool, not a notebook.

## 2026-05-21 — C1 leak surface scoped accurately
**Status:** accepted
**Decision:** Rewrote C1 in `improvements.md` to list the actual 6 leak locations (CLAUDE.md L3/35, basal_analysis.py L2/138, ml_model.py L2, whoop_api_fetch.py L13, architecture.md L43) and dropped the "email" claim (not in any tracked file). Added a note that git commit author identity is a separate leak with its own file-only-vs-history-rewrite decision at public-migration time.
**Why:** The original C1 entry said "CLAUDE.md ... email" - underscoped (missed scripts + architecture.md + the `DIAGNOSIS_START` constant) and inaccurate (no email anywhere in tree). Made it concrete so a future implementation pass knows exactly what to touch.

## 2026-05-21 — Private GitHub backup pushed; line-ending policy locked
**Status:** accepted
**Decision:** Pushed local `master` (23 commits) to a private GitHub repo at https://github.com/ThBloch/T1D-optimizer - satisfies E2 path 1. Added `.gitattributes` with `* text=auto` to enforce LF in the repo regardless of any contributor's local Git config. Set `core.autocrlf=false` locally to silence the cosmetic LF/CRLF warnings now that `.gitattributes` makes the per-user setting irrelevant for normalization.
**Why:** Backup + portability were the only immediate needs; public migration stays gated by quality bar + C1 sanitization (see prior 2026-05-21 entry). `.gitattributes` is the right layer for line-ending policy because it travels with the repo - the local `core.autocrlf` change only affects this machine and would be overridden by `.gitattributes` anyway on a fresh clone. Repo URL also captured in auto-memory `reference_github_repo.md` so future sessions don't have to grep `git remote -v`.

## 2026-05-29 — Hypo-correction threshold raised from 7.0 to 10.0
**Status:** accepted
**Decision:** `night_stats.HYPO_CORRECTION_THR` raised from 7.0 to 10.0. A night is now only flagged as hypo-correction if glucose drops below 4.0 AND the subsequent peak exceeds 10.0 (not 7.0).
**Why:** The 7.0 threshold was too sensitive - any mild rebound after a hypo triggered the flag, pulling nights from the clean pool even when the post-hypo glucose stayed well within range. 10.0 matches the clinical hyper threshold used throughout the codebase and aligns hypo-correction flagging with the nights that genuinely show a large artefact spike. Consequence: fewer nights excluded from the matching pool; count to be verified on next backtest run.

## 2026-05-29 — Fasting +1u threshold lowered from 10.5 to 10.0
**Status:** accepted
**Decision:** `rules.FASTING_LO` lowered from 10.5 to 10.0. The +1u basal upward adjustment now triggers when fasting glucose is > 10.0 mmol/L instead of > 10.5 mmol/L.
**Why:** The original 10.5 threshold was set conservatively during early data collection. With a year of data, the pattern is clear that fasting in the 10.0-10.5 range consistently trends upward over subsequent nights without a dose increase. Lowering to 10.0 catches these nights earlier and is consistent with the clinical hyperglycaemia threshold used in `tir_full`. Unit test `test_fasting_at_lo_boundary_no_change` updated to reflect new boundary.

## 2026-05-29 — Bolus IQR exclusion removed from basal_analysis.py
**Status:** accepted
**Decision:** Removed the `iqr_bolus_outlier()` exclusion from `basal_analysis.py`. High-bolus nights are no longer excluded from the matching pool; only hypo-correction nights remain excluded.
**Why:** The IQR exclusion was designed for the pre-NovoPen period when Clarity reliably logged all boluses. From 2026-01-31 the NovoPen 6 data is missing from Clarity, so the bolus data is incomplete and the IQR threshold is computed from a biased sample. Excluding based on an unreliable signal is worse than not excluding at all. The `[bolus]` annotation in the weekly summary is also removed. The `bolus` field is still loaded and stored per-night for future use once NovoPen data is integrated (Phase 4).

## 2026-05-29 — Bolus framing change: slope disambiguation, not predictor
**Status:** accepted
**Decision:** Bolus data is reframed in the codebase from "potential model feature" to "required signal for disambiguating the second-half slope". It is not - and per the 2026-04-15 decision still is not - used as a TIR predictor. Its role is to answer "did Thomas correct mid-night?" when interpreting a rising or falling second-half glucose slope.
**Why:** The slope-based fasting rule (decided 2026-05-28) cannot distinguish "basal too low" from "missed correction bolus" without bolus event timestamps. The 2026-04-15 evidence that bolus's predictive signal is fully mediated through `inj_g` still holds; bolus_noise_test.py confirms r drops from -0.24 (***)  direct to -0.07 (ns) after removing inj_g effect. Both facts coexist: not a predictor, but a load-bearing input for the slope rule's interpretation step. Documented here so no future session re-litigates "should we add bolus as a feature".

## 2026-05-29 — NovoPen 6 bolus source via Glooko export (R13)
**Status:** accepted
**Decision:** Bolus events from 2026-01-31 onwards are sourced from Glooko's CSV export of NovoPen 6 data, parsed by `scripts/novopen_loader.py`. Clarity CSV remains the source pre-cutover. Combined events flow through `dexcom_loader.load_bolus_combined()` with cutover constant `NOVOPEN_CUTOVER = 2026-01-31`. Glooko export is currently manual (download from web app); automation deferred.
**Why:** Dexcom Clarity raw CSV exports are hard-filtered to G7-app-source events only - confirmed by inspecting every insulin row across all historical exports (100% `Kildeenheds id = "android G7"`, zero NovoPen rows). NovoPen data reaches Clarity reports via a separate partner pipeline but never enters the raw CSV. Glooko is the same partner channel Dexcom uses internally; pulling from there is the only viable path short of building a custom NFC reader. Manual export accepted as the v1 friction cost; Playwright automation planned as a follow-up.

## 2026-05-29 — Glooko Prime Detection rule implemented in novopen_loader.py
**Status:** accepted
**Decision:** `scripts/novopen_loader.py` filters NovoPen events using Glooko's documented Prime Detection rule: an event is a PRIME iff (amount <= 2u) AND (another insulin event follows within 6 minutes). Otherwise it is an INJECTION. Constants `PRIME_MAX_U = 2.0` and `PRIME_WINDOW = timedelta(minutes=6)` reflect the published rule verbatim.
**Why:** Thomas enabled Prime Detection in Glooko on setup but has not run the per-event manual classification UI, so `bolus_data_1.csv` is empty and the raw event stream is in `insulin_data_1.csv`. Implementing Glooko's own rule client-side gives a deterministic, documented classification without requiring the manual UI step. Known limitation: a real 1-2u bolus immediately followed by another bolus within 6 min would be misclassified as a prime - acceptable because (a) Thomas rarely takes sub-2u boluses, and (b) the loader's purpose is slope disambiguation, not carb-counting precision. Rule lives in `novopen_loader.py:PRIME_MAX_U` / `PRIME_WINDOW`.
