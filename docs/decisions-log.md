# Decisions Log

Durable record of choices that shape this project and the reasoning behind them.

Format and rules: `claude-setup/docs/decisions-log-conventions.md`.

Quick rules:
- Append entries chronologically. Never reorder.
- Once written, an entry's content is immutable. Only the `Status` line can change (when superseded).
- Read this file before proposing non-trivial changes to `thomas_rules`, model parameters, data sources, or analysis approach.

Pre-existing entries below were written before the formal conventions were adopted on 2026-05-23. They have been retrofit with `Status: accepted` lines; no other content was changed.

---

## 2026-04-15 - Dropped s7 as match variable
**Status:** accepted
**Decision:** Replace s7 (7-day rolling strain) with inj_g as primary match variable.
**Why:** A/B test (predictor_test.py) showed s7 r=0.078, p=0.19 - not predictive of TIR. inj_g r=-0.376, p<0.001 is the strongest signal in the dataset.

## 2026-04-15 - Exclude hypo-correction nights from matching pool
**Status:** accepted
**Decision:** Nights where Thomas had a nocturnal hypo and ate to correct are excluded from the matching pool (but shown in weekly summary).
**Why:** These nights show post-correction hyperglycemia that is an artefact of eating, not a basal signal. Including them corrupted the dose->outcome relationship. 58/297 nights (19.5%) affected.

## 2026-04-15 - Bolus not added as model feature
**Status:** accepted
**Decision:** Bolus dose data not used as a predictor, despite having reliable logs to 2026-01-30.
**Why:** Partial correlation of bolus_4h vs TIR residuals (after removing inj_g effect) = -0.023, p=0.78. Bolus effect is fully mediated through inj_g - the 22:00 glucose reading already encodes the outcome of any pre-injection bolusing.

## 2026-04-15 - Rules model preferred over ML for dose suggestion
**Status:** accepted
**Decision:** Thomas's rule-based titration is used for tonight's suggestion, not an ML model.
**Why:** Decision tree (learned from data) test MAE = 1.45u vs rules MAE = 1.32u. With n=239 clean nights and prev_dose explaining 95.6% of variance, ML has insufficient data to improve on well-designed rules.

## 2026-04-15 - Clean build (all prior scripts superseded)
**Status:** accepted
**Decision:** Rewrote analysis from scratch, superseding analyze.py, recalibrate.py, REFERENCE.md.
**Why:** Prior model used s7 as primary match variable (shown to be non-predictive) and did not account for hypo-correction nights. Thomas also explicitly requested a clean start.

## 2026-05-15 - New-pen adjustment (-1u)
**Status:** accepted
**Decision:** Add a new rule: starting a fresh basal pen applies -1u. Stacks with glucose and activity adjustments. Triggered via `--new-pen` CLI flag on `dexcom_fetch.py`.
**Why:** Thomas observed (empirical, lived) that the first night on a fresh pen tends to run higher than expected - likely a priming/needle/insulin-freshness effect. -1u absorbs the bias on the first night without altering the steady-state titration. Encoded in `rules.py:thomas_rules(..., new_pen=True)` and locked in by 3 new unit tests.

## 2026-05-15 - Hypo override flag (`--no-hypo`)
**Status:** accepted
**Decision:** Allow the operator to instruct `dexcom_fetch.py` to ignore CGM-detected hypos for the rule calculation when they are judged sensor noise. The diary still records the raw CGM count for historical accuracy; the override appears as the first line in the reasoning chain.
**Why:** Dexcom G7 occasionally reports a single sub-4.0 reading (e.g. 3.9) due to sensor noise at the boundary. When the operator can verify (subjectively or via parallel finger-stick) that no real hypo occurred, the rule's automatic -1u correction is unwarranted and would drive the dose downward incorrectly. The override is opt-in per run, not a default, so the conservative behavior is preserved.

## 2026-05-18 - Rolled back first `/dose` slash command draft
**Status:** accepted
**Decision:** Deleted the first `D:/claude/t1d/.claude/commands/dose.md` draft. `/dose` rebuild deferred until Phase 1 of the automation roadmap lands (`--dose N` flag on `dexcom_fetch.py`, removal of `input()` prompts).
**Why:** The draft added an interactive orchestration layer (AskUserQuestion for new-pen, factors, sensor-noise) directly on top of the current interactive script. Phase 1 is removing script interactivity to make scripts cron-friendly for the Telegram path. Building `/dose` on the pre-Phase-1 script meant near-certain rewrite once Phase 1 ships. Cleaner to do Phase 1 first; `/dose` then becomes a ~20-line wrapper around a non-interactive `--dose N` invocation. Backlog entry moved here from `claude-setup/improvements.md` D1 to enforce the rule that project-specific work lives in the project's own backlog.

## 2026-05-21 - GitHub strategy: defer public push until project is "share-ready"
**Status:** accepted
**Decision:** Repo stays local for now (no remote yet). Eventual aim is public, to help other T1D patients/builders. Gated on an informal quality bar - E1 (strain rule refinement), E10 (nighttime objective validation), at least E5 (Phase 1 automation) - plus C1 sanitization. Three migration paths logged in E2 for the eventual flip.
**Why:** Thomas wants the tool shareable if it can help others, but the current state is a single-user manual workflow with a coarse strain rule and an outcome metric (TIR(5-8)) that may be reshaped by E10. Going public now would lock in shape decisions still in flux. Defer until the model + automation make this a real tool, not a notebook.

## 2026-05-21 - C1 leak surface scoped accurately
**Status:** accepted
**Decision:** Rewrote C1 in `improvements.md` to list the actual 6 leak locations (CLAUDE.md L3/35, basal_analysis.py L2/138, ml_model.py L2, whoop_api_fetch.py L13, architecture.md L43) and dropped the "email" claim (not in any tracked file). Added a note that git commit author identity is a separate leak with its own file-only-vs-history-rewrite decision at public-migration time.
**Why:** The original C1 entry said "CLAUDE.md ... email" - underscoped (missed scripts + architecture.md + the `DIAGNOSIS_START` constant) and inaccurate (no email anywhere in tree). Made it concrete so a future implementation pass knows exactly what to touch.

## 2026-05-21 - Private GitHub backup pushed; line-ending policy locked
**Status:** accepted
**Decision:** Pushed local `master` (23 commits) to a private GitHub repo at https://github.com/ThBloch/T1D-optimizer - satisfies E2 path 1. Added `.gitattributes` with `* text=auto` to enforce LF in the repo regardless of any contributor's local Git config. Set `core.autocrlf=false` locally to silence the cosmetic LF/CRLF warnings now that `.gitattributes` makes the per-user setting irrelevant for normalization.
**Why:** Backup + portability were the only immediate needs; public migration stays gated by quality bar + C1 sanitization (see prior 2026-05-21 entry). `.gitattributes` is the right layer for line-ending policy because it travels with the repo - the local `core.autocrlf` change only affects this machine and would be overridden by `.gitattributes` anyway on a fresh clone. Repo URL also captured in auto-memory `reference_github_repo.md` so future sessions don't have to grep `git remote -v`.

## 2026-05-29 - Hypo-correction threshold raised from 7.0 to 10.0
**Status:** accepted
**Decision:** `night_stats.HYPO_CORRECTION_THR` raised from 7.0 to 10.0. A night is now only flagged as hypo-correction if glucose drops below 4.0 AND the subsequent peak exceeds 10.0 (not 7.0).
**Why:** The 7.0 threshold was too sensitive - any mild rebound after a hypo triggered the flag, pulling nights from the clean pool even when the post-hypo glucose stayed well within range. 10.0 matches the clinical hyper threshold used throughout the codebase and aligns hypo-correction flagging with the nights that genuinely show a large artefact spike. Consequence: fewer nights excluded from the matching pool; count to be verified on next backtest run.

## 2026-05-29 - Fasting +1u threshold lowered from 10.5 to 10.0
**Status:** accepted
**Decision:** `rules.FASTING_LO` lowered from 10.5 to 10.0. The +1u basal upward adjustment now triggers when fasting glucose is > 10.0 mmol/L instead of > 10.5 mmol/L.
**Why:** The original 10.5 threshold was set conservatively during early data collection. With a year of data, the pattern is clear that fasting in the 10.0-10.5 range consistently trends upward over subsequent nights without a dose increase. Lowering to 10.0 catches these nights earlier and is consistent with the clinical hyperglycaemia threshold used in `tir_full`. Unit test `test_fasting_at_lo_boundary_no_change` updated to reflect new boundary.

## 2026-05-29 - Bolus IQR exclusion removed from basal_analysis.py
**Status:** accepted
**Decision:** Removed the `iqr_bolus_outlier()` exclusion from `basal_analysis.py`. High-bolus nights are no longer excluded from the matching pool; only hypo-correction nights remain excluded.
**Why:** The IQR exclusion was designed for the pre-NovoPen period when Clarity reliably logged all boluses. From 2026-01-31 the NovoPen 6 data is missing from Clarity, so the bolus data is incomplete and the IQR threshold is computed from a biased sample. Excluding based on an unreliable signal is worse than not excluding at all. The `[bolus]` annotation in the weekly summary is also removed. The `bolus` field is still loaded and stored per-night for future use once NovoPen data is integrated (Phase 4).

## 2026-05-29 - Bolus framing change: slope disambiguation, not predictor
**Status:** accepted
**Decision:** Bolus data is reframed in the codebase from "potential model feature" to "required signal for disambiguating the second-half slope". It is not - and per the 2026-04-15 decision still is not - used as a TIR predictor. Its role is to answer "did Thomas correct mid-night?" when interpreting a rising or falling second-half glucose slope.
**Why:** The slope-based fasting rule (decided 2026-05-28) cannot distinguish "basal too low" from "missed correction bolus" without bolus event timestamps. The 2026-04-15 evidence that bolus's predictive signal is fully mediated through `inj_g` still holds; bolus_noise_test.py confirms r drops from -0.24 (***)  direct to -0.07 (ns) after removing inj_g effect. Both facts coexist: not a predictor, but a load-bearing input for the slope rule's interpretation step. Documented here so no future session re-litigates "should we add bolus as a feature".

## 2026-05-29 - NovoPen 6 bolus source via Glooko export (R13)
**Status:** superseded (see 2026-05-29 entry "Bolus sources merged across all dates - no cutover")
**Decision:** Bolus events from 2026-01-31 onwards are sourced from Glooko's CSV export of NovoPen 6 data, parsed by `scripts/novopen_loader.py`. Clarity CSV remains the source pre-cutover. Combined events flow through `dexcom_loader.load_bolus_combined()` with cutover constant `NOVOPEN_CUTOVER = 2026-01-31`. Glooko export is currently manual (download from web app); automation deferred.
**Why:** Dexcom Clarity raw CSV exports are hard-filtered to G7-app-source events only - confirmed by inspecting every insulin row across all historical exports (100% `Kildeenheds id = "android G7"`, zero NovoPen rows). NovoPen data reaches Clarity reports via a separate partner pipeline but never enters the raw CSV. Glooko is the same partner channel Dexcom uses internally; pulling from there is the only viable path short of building a custom NFC reader. Manual export accepted as the v1 friction cost; Playwright automation planned as a follow-up.

## 2026-05-29 - Glooko Prime Detection rule implemented in novopen_loader.py
**Status:** accepted
**Decision:** `scripts/novopen_loader.py` filters NovoPen events using Glooko's documented Prime Detection rule: an event is a PRIME iff (amount <= 2u) AND (another insulin event follows within 6 minutes). Otherwise it is an INJECTION. Constants `PRIME_MAX_U = 2.0` and `PRIME_WINDOW = timedelta(minutes=6)` reflect the published rule verbatim.
**Why:** Thomas enabled Prime Detection in Glooko on setup but has not run the per-event manual classification UI, so `bolus_data_1.csv` is empty and the raw event stream is in `insulin_data_1.csv`. Implementing Glooko's own rule client-side gives a deterministic, documented classification without requiring the manual UI step. Known limitation: a real 1-2u bolus immediately followed by another bolus within 6 min would be misclassified as a prime - acceptable because (a) Thomas rarely takes sub-2u boluses, and (b) the loader's purpose is slope disambiguation, not carb-counting precision. Rule lives in `novopen_loader.py:PRIME_MAX_U` / `PRIME_WINDOW`.

## 2026-05-29 - Bolus sources merged across all dates - no cutover
**Status:** accepted
**Decision:** `dexcom_loader.load_bolus_combined()` now concatenates Clarity Hurtig events and Glooko ACS* (smart-pen) events across all dates and sorts by timestamp. No cutover date, no dedup. The previous `NOVOPEN_CUTOVER = 2026-01-31` constant is removed. Supersedes the earlier "NovoPen 6 bolus source via Glooko export (R13)" entry from today.
**Why:** Thomas confirmed (2026-05-29) that he uses both a regular pen (manually logged in the Dexcom G7 app -> Clarity) and a smart NovoPen 6 (NFC -> Glooko) interchangeably going forward, with the smart pen most of the time. There is no single switch date. The two sources are disjoint by construction at the event level: Clarity Hurtig rows have `Kildeenheds id = "android G7"` (manual entries only - confirmed across every historical Clarity CSV), and `novopen_loader.load_glooko_bolus()` filters to ACS-prefix serials only (skipping the Dexcom-source rows that Glooko ingests). Therefore a naive concatenation gives the full picture without double-counting. Verified: only 1 calendar day (2026-03-05) ever had bolus events in both streams, and they were at non-overlapping times.

## 2026-05-29 - Phase 5 inferential predictor: M3 (dose*s1) chosen as best-supported spec
**Status:** accepted
**Decision:** `scripts/inferential_predictor.py` compares four nested model specs (M1 linear additive baseline, M2 + s1^2, M3 + dose*s1 interaction, M4 + both) and selects via F-test against the next-simpler nested model with the constraint that `beta_dose` retains p<0.10. M3 selected on current 288-night sample: R^2 = 0.064 (vs M1's 0.048), F-test M3 vs M1 p=0.029, beta_dose p=0.020, beta_(dose*s1) p=0.029. M2 (s1^2 alone) and M4 (both terms) failed their F-tests.
**Why:** The Phase A2 baseline (M1) has beta_dose p=0.42, which makes the inferred-optimal-dose computation unreliable. Adding the dose*s1 interaction makes dose significant and lifts R^2 by ~33% relatively, with a passing F-test. The biological story is that dose's effect on second-half slope is moderated by strain: at high strain, the same dose has a different relationship to overnight slope (consistent with the existing activity rule). M3 is now the model used to invert sh_slope=0 for "what dose would have flattened tonight". Re-run when sample grows materially; if a future dataset breaks M3's F-test or beta_dose significance, the script will fall back automatically.

## 2026-05-29 - Phase 5 signal ranking: 7 signals promoted to Phase 6 rule design
**Status:** accepted
**Decision:** Convergent ranking from `inferential_predictor.py` (direct Spearman vs sh_slope; partial Spearman after removing s1, prev_dose, inj_g; Spearman vs M3 inferred optimal dose). Promotion tiers on 288 usable nights:
- **HIGH (>=2/3 metrics p<0.05 same direction):** `s1` (strain), `recovery`, `hrv`, `rhr`, `inj_g`, `bolus_4h_pre`, `bolus_during_night`.
- **MED (1/3):** `sleep_perf`, `prev_dose`, `prev_fasting`.
- **LOW (0/3):** `prev_hypos`, `hypo_events_tonight`.

Phase 6 rule design works from the HIGH list. MED signals are watched but not encoded in the first rule iteration. LOW signals are dropped from the candidate set.
**Why:** Same-direction agreement across three independent measurement angles is stronger evidence than any single test, given the chosen-model R^2 is still only 0.064 (most slope variance is unexplained). Notable findings: (a) bolus_4h_pre AND bolus_during_night both clear HIGH - the slope rule's framing (bolus needed for disambiguation) is empirically supported; (b) inj_g passes via direct + inferential despite partial r ~ 0 (it IS one of the controls so partial is ~0 by construction - not a refutation); (c) prev_hypos / hypo_events_tonight are too rare to carry signal in this sample - revisit if hypo frequency rises.

## 2026-05-29 - WHOOP stress endpoint not exposed by whoop-sdk 0.3.1 (R21 closed for now)
**Status:** accepted
**Decision:** WHOOP stress not added as a Phase 5 candidate. `whoop-sdk` v0.3.1 exposes only cycles, recovery, sleep, workouts, body measurements, and profile - no stress endpoint. Path 2 fallback (derive a "stress proxy" from HRV) declined: HRV is already a candidate signal in its own right; relabeling it as "stress" would mislead more than inform.
**Why:** WHOOP's mobile app has a Stress Monitor feature but it is not exposed in the public Developer API as of the installed SDK version. Building a custom auth/scraping path against the mobile app is out of scope for Phase 5 and not warranted unless HRV alone proves insufficient in Phase 6 rule testing. Revisit when whoop-sdk publishes a stress endpoint, or if Phase 6 evidence demands a separate stress channel.

## 2026-05-29 - Slope-based fasting rule v1 encoded in thomas_rules()
**Status:** accepted
**Decision:** The fasting-glucose tier in `thomas_rules()` is replaced by a slope-based tier driven by second-half overnight slope (`sh_slope`, mmol/L/h). Priority: hypo events still override everything (Q4); when `sh_slope` is provided it drives the glucose tier; when unavailable the rule falls back to wake-time fasting via the same tier structure. Resolutions of the four open questions parked on 2026-05-28:
- **Q1 (down-direction symmetry):** Symmetric direction - falling slope WITHOUT a hypo triggers -u. Magnitudes asymmetric: 3-tier up (+1/+2/+3), 2-tier down (-1/-2). Down capped at -2 for safety.
- **Q2 (slope thresholds):** `SLOPE_FLAT = 0.3`, `SLOPE_MID = 0.7`, `SLOPE_HI = 1.2`. Derived from the actual slope distribution (flat band matches existing `FLAT_BAND` from strain_binning; mid/hi map to ~p75 and ~p90 of the absolute-slope distribution).
- **Q3 (adjustment scale):** 3-tier up, 2-tier down. Matches existing 3-tier fasting structure; asymmetry reflects clinical risk.
- **Q4 (hypo priority):** Hypo override KEPT. `hypo_events >= 2 -> -2u`; `hypo_events == 1 -> -1u`; both bypass slope. Same priority structure as the prior fasting rule.

Signature: `thomas_rules(yesterday_dose, fasting, hypo_events, s1, new_pen=False, sh_slope=None, slope_flat=0.3, slope_mid=0.7, slope_hi=1.2, ...)`. `sh_slope` defaults to None so existing callers / tests work unchanged; 17 new slope tests added in `tests/test_rules.py` (38/38 total green). `dexcom_fetch.py` and `rules_model.py` pass `sh_slope` (live and per-night respectively).
**Why:** Slope captures the trajectory the dose produced - a flat second half means the basal held; a rising one means it ran out; a falling one means too much. Endpoint fasting only sees the result, not the path, and is gameable by a late-night correction bolus (Phase 5 confirmed bolus_4h_pre and bolus_during_night are both HIGH-tier slope predictors, supporting the disambiguation framing). Backtest on 340 nights: slope-rule MAE 1.35u (within margin of the prior fasting-rule baseline 1.32u) with 63.8% within +/-1u of actual doses. Mean diff +0.79u (actual > suggested) is consistent with Phase 5's "Thomas systemically under-dosing relative to inferred optimum" finding. Thresholds parameterised so a future R8-style backtest can re-tune without code change.

## 2026-05-29 - Doc-scope policy + architecture.md rewrite (R20 / R16-R18)
**Status:** accepted
**Decision:** Adopt an explicit scope split across the project's docs and rewrite `docs/architecture.md` against it. Scope split:
- `docs/architecture.md` = WHAT the components are and HOW they connect. No values restated from code.
- `docs/decisions-log.md` = WHY a choice was made. Immutable history.
- `docs/improvements.md` = backlog (`[ ]` / `[x]` / `[-]`).
- `docs/session-log.md` = per-session log (changes / decisions / blockers / next).
- `CLAUDE.md` = quick reference (run commands, paths, conventions).
- Auto-memory at `~/.claude/projects/D--claude-t1d/memory/` = cross-session patterns.

Architecture doc rewritten with five invariants in the Purpose section (R18: user-initiated only; strain non-negotiable; second-half slope is the outcome; bolus required for slope disambiguation; production path named). Data-flow tables for sources + signal flow added (R17). All threshold values point at `scripts/rules.py:7-19` and `scripts/night_stats.py:13-25`; the doc itself contains zero numeric restates of code constants (R16). Verified via grep: `\b(10\.0|12\.0|14\.0|15|29|0\.3|0\.7|1\.2|4\.0|5\.0|8\.0|0\.5)\b` returns no hits in `docs/architecture.md`.
**Why:** Pre-rewrite, the architecture doc duplicated thresholds and code paths, drifted from current behavior (matching model framed as primary; slope rule not mentioned), and overlapped scope with `improvements.md` and the session-log. Single-source-of-truth in code prevents drift; one place per kind of question prevents readers from triangulating across three files. R20 makes that policy explicit so future contributions stay aligned without re-deriving the rule each time.

## 2026-05-29 - Phase 9 close-out: durable home for code-side principles + leftover cleanup
**Status:** accepted
**Decision:** Audit after Phase 8 found four gaps. Resolved here as a "Phase 9 close-out":
- **Code conventions (P1-P12) lifted to `docs/code-conventions.md`** as the durable home. Previously the 12 principles only lived inside the 2026-05-28 audit doc (`t1d-redesign.md` §7), which is a snapshot and not authoritative. The doc-scope policy from the previous entry covers documents; this new file covers code. CLAUDE.md "Working preferences" now points at it; `architecture.md` "Doc map" lists it; `t1d-redesign.md` §7 notes it as superseded.
- **R9 finished.** `rolling_avg()` + `s7` (and `s1_dev`) removed from `scripts/ml_model.py` and `scripts/predictor_test.py` (the only two remaining sites). The 2026-04-15 decision to drop s7 is now reflected in code everywhere; previously two analysis scripts still computed it.
- **R14 finished.** `scripts/ml_model.py` "TONIGHT'S DOSE RECOMMENDATION" block removed; only `dexcom_fetch.py` now emits a tonight's-dose suggestion (P3 enforced). The Phase 7 grep was scoped to three files and missed `ml_model.py`.
- **B9 marked done** in `improvements.md`. Phase 1 had already renamed `TGT_LO/HI` to `TARGET_LO/HI` (user goal) + `CLINICAL_TIR_LO/HI` (clinical TIR); the backlog item just wasn't checked off.
- **Architecture doc cleanup.** `scripts/whoop_api_fetch.py` reclassified from "Shared modules" (it's a CLI fetch script, not a loader) to a new "Fetch / refresh scripts (entry points)" subsection. Stale `docs/progress.md` (last meaningfully edited 2026-04-15, content over a year out of date) moved to `archive/docs_pre_redesign/` and removed from the doc map.
- **Unused import removed:** `os` in `scripts/dexcom_loader.py`.

**Why:** The redesign claimed completion at Phase 8, but the post-hoc audit surfaced that P3 ("one nightly suggestion") was violated by `ml_model.py`, P6 ("drop dead weight") was violated by `rolling_avg`/`s7` persistence, and the principles themselves had no durable home. Closing here keeps the principles enforceable rather than aspirational, and removes the dead surface that would otherwise re-grow under any future contributor's `grep -r "s7"` or `grep -r "tonight"`.

## 2026-05-29 - Phase 9 correction: progress.md restored (was not stale)
**Status:** accepted
**Decision:** Restored `docs/progress.md` to git and re-added it to the `architecture.md` doc map. The previous Phase 9 entry's claim that the file's "content over a year out of date" was incorrect; the doc was last meaningfully edited 2026-04-15, ~6 weeks before today (2026-05-29). The "Next session" notes in the doc had been executed since but the document itself is a milestone summary, not a session log, and is still in active use by Thomas. Architecture.md doc map row reworded from "legacy; lightly maintained" to "Milestone summary: Done / Next session / Open questions".
**Why:** I miscounted the time elapsed and unilaterally archived a doc that was not in fact stale. Thomas's own correction surfaces the principle for the close-out itself: when in doubt about deleting an artefact, ask. The 2026-04-15 date stays as the last edit; future updates are owned by Thomas, not by a redesign cleanup pass.

## 2026-05-29 - Redesign audit doc archived (R-series + P-series fully migrated)
**Status:** accepted
**Decision:** `docs/t1d-redesign.md` moved to `archive/docs_pre_redesign/`. The audit's actionable content is now fully migrated: R1-R21 done across Phases 1-9; R22 broken out as `improvements.md` E18 (last un-shipped item, gated on E10's fixed-vs-relative wake-anchor decision); P1-P12 lifted to `docs/code-conventions.md` (Phase 9). Sections 1-6 of the audit (component map, data sources, rules, inconsistencies, modularity assessment) were informational and fed the R-series.
- `architecture.md` doc map row removed.
- `code-conventions.md` "principles emerged from..." sentence updated to point at the archived path.
- Decisions-log entries referencing the audit doc by its old `docs/` path are immutable and remain as-is (historical context); future references should use the archive path.
**Why:** The audit was a snapshot with a defined purpose - extract inconsistencies and propose principles. Both are now durably homed (`improvements.md`, `code-conventions.md`, and the 9 phase commits). Keeping the audit in `docs/` would imply ongoing relevance it no longer has. Archiving preserves the historical record (gitignored locally, recoverable via git history at the old path) without it occupying the active doc tree.

## 2026-05-29 - E12 resolved: strain-non-negotiable invariant enforced in code (Path A)
**Status:** accepted
**Decision:** `dexcom_fetch.py` now refuses to compute a suggestion when today's WHOOP strain is unavailable. When `args.strain` is not passed and `load_whoop().get(today)` returns no `strain`, the script:
- emits `NEEDS: strain` on stdout (machine-readable, for future `/dose` parsing),
- prints a courtesy hint ("Today's WHOOP strain not yet on file (in-progress cycle). Re-run with `--strain N` or wait for the cycle to close."),
- saves the diary (preserving yesterday's outcome backfill),
- returns without calling `thomas_rules()`.

New `--strain N` CLI flag mirrors `--dose N`: when present it overrides the cache lookup entirely. P12 invariant #2 ("strain MUST inform every suggestion") is now real in code on the production path.

Scope intentionally minimal (Path A from the E12 spar): no changes to `.claude/commands/dose.md`. Users of `/dose` hit a hard wall on strain-missing days and re-run the script manually with `--strain N`. The friendly `/dose` side - parse `NEEDS:` lines and ask via documented prompt wording - remains tracked at `improvements.md` E1b / E1d.

Doc updates: `CLAUDE.md` Quick Start + dexcom_fetch.py description list the new `--strain N` flag and the refusal behaviour; `code-conventions.md` P12 #2 reworded to reflect the new state; `architecture.md` "Purpose" #2 and "Limits" updated.

**Why:** The invariant was asserted in two prose locations (`architecture.md` Purpose and `code-conventions.md` P12) while the code silently no-opped the activity branch when `s1 is None`. That contradicted the 2026-05-27 "strain non-negotiable" decision and the `feedback-strain-yesterday-invalid` memory. Path A is the smallest code change that makes the invariant true: it accepts a worse `/dose` UX today (raw wall instead of friendly prompt) in exchange for the protocol being honest. The friendly UX layer (E1b/E1d) lands separately when E1d's open prompt-wording questions are resolved. The alternative (Path C - downgrade the invariant wording) was rejected because it walks back a stated load-bearing preference.

## 2026-05-29 - Memory vs decisions-log policy (E16)
**Status:** accepted
**Decision:** Two persistent stores hold project knowledge: `docs/decisions-log.md` (append-only, immutable, in git) and Claude auto-memory at `~/.claude/projects/D--claude-t1d/memory/` (per-Claude-instance, loaded at session start, not in git). They serve different purposes - decisions-log is the *record* (full WHY), memory is a *recall aid* (short behavioural shortcut). They are not duplicates.

When they disagree, the **decisions-log wins**. Memory is updated to match; the decisions-log entry is never edited (P10 immutability).

**Cross-reference convention:** any memory whose content corresponds to a decisions-log entry ends with a plain-text line of the form `Recorded in docs/decisions-log.md YYYY-MM-DD: <short slug>.` Plain text, not a wiki-link (`[[name]]` syntax is reserved for inter-memory links). Pure collaboration-pattern memories (e.g. `feedback_token_saving_priority`, `feedback_plan_before_implement`) are exempt - they describe how to work with Thomas, not project decisions.

**Drift discipline:** when a project-level rule changes, write the decisions-log entry first (P10), then update or create the memory and add the cross-reference. Never update a memory that states a project-level rule without a matching decisions-log entry.

This policy is codified in `docs/code-conventions.md` under "Knowledge stores: memory and decisions-log". Applied to the four overlapping memory files today: `feedback_night_quality_slope`, `feedback_rule_parameter_ownership`, `feedback_strain_yesterday_invalid`, `project_glooko_prime_detection`. The latter previously gestured at a decisions-log entry via a broken wiki-link (`[[decisions-log-glooko-prime-rule]]`); replaced with the plain-text reference.

**Why:** Without a policy, future sessions could update memory independently of decisions-log, producing silently divergent guidance that a future Claude has no protocol for resolving. Memory drift is the more likely direction because memory edits are session-local and not surfaced in `git status`. The cross-reference makes the link traceable both ways: a memory's authority can be checked, and a decisions-log entry's behavioural implication can be located.

## 2026-05-29 - night_stats degenerate-slope refuses + direct tests (E17)
**Status:** accepted
**Decision:** `night_stats.second_half_trend()` now returns `(None, None, sh_n)` when the regression denominator is 0 (mathematically: all timestamps in the second half are equal). Previously it returned `slope = 0.0` in that case, which flowed into `thomas_rules()` and triggered the slope-tier "flat band -> no adjustment" branch. The new contract matches the existing insufficient-readings branch (`sh_n < SH_MIN_READINGS`): both signal "no measurable slope" and let the fasting fallback in `rules.py` take over.

Production impact is essentially zero - Dexcom emits at 5-minute intervals, so distinct timestamps are the norm and the degenerate path was never exercised in real data. The change is honesty: refuse to claim "flat" when we have no signal at all.

New test file `tests/test_night_stats.py` adds 24 direct unit cases:
- `second_half_trend()`: empty input, insufficient second half, rising/falling/flat slopes with hand-computable magnitudes, degenerate identical-timestamps, narrow-window per-hour scaling, first-half-does-not-affect-slope.
- `night_stats()`: empty input, below `min_readings`, normal field math, hypo-event counting (zero / single dip / two separate / sustained one-episode / boundary at HYPO_THR=4.0), hypo-correction (trigger / boundary-not-trigger at HYPO_CORRECTION_THR=10.0 / no-hypo-no-trigger), `hyper_adj` zero-when-correction / equals-hyper_pct-otherwise, TIR target range, TIR clinical range, constants-imported sanity check.

Test count totals: `test_rules.py` 38/38 + `test_night_stats.py` 24/24 = 62 green.

**Why:** `scripts/night_stats.py` was the most heavily-consumed production-path module without direct tests (consumed by `dexcom_fetch.py`, `rules_model.py`, `basal_analysis.py`, `inferential_predictor.py`, `dose_diary.py` backfill block, `bolus_noise_test.py`, both strain analysis scripts). A bug in any of its fields would surface only as a misclassified night somewhere downstream. Direct tests close that gap. The degenerate-slope fix is small but matches the honesty principle E12 just enforced for strain: refuse rather than silently no-op.

## 2026-05-29 - code-conventions P5-P10 polish + P5 refactor (E11)
**Status:** accepted
**Decision:** Four sub-decisions resolved on the principle wording in `docs/code-conventions.md`:

- **P5 (option b refactor; principle body extended).** Two in-loader domain-logic blocks moved out so P5 stays as-stated. (a) `_parse_offset`, `_parse_iso`, and `_cycle_date` migrated from `whoop_loader.py` to new `scripts/whoop_cycles.py`; loader imports `cycle_date_for`. (b) Glooko Prime Detection rule (`PRIME_MAX_U`, `PRIME_WINDOW`, bidirectional lookahead) migrated from `novopen_loader.py` to new `scripts/bolus_classification.py`; loader imports `filter_primes`. P5 body extended to list the dedicated modules (matching the P7+P8 hybrid form).

- **P7 + P8 (option c hybrid + strict P8).** Both principles rewritten with generalised header + listed current instances. P7: "Production-path signals are first-class - stored per-night, exposed by a shared module, consumed by `rules.py` directly. Current production signals: sh_slope, s1, fasting, hypo_events." P8: "Confoundable signals require their disambiguator. Current cases: sh_slope <- bolus." Strict P8 creates a new invariant-vs-code mismatch on bolus (parallel to E12's strain fix), tracked as new backlog item `E19`.

- **P9 (option d hybrid + strict on inferential_predictor).** P9 reworded with required-test-files list: `test_rules.py`, `test_night_stats.py`, `test_inferential_predictor.py` (the last not yet written). Opt-in test list explicitly names the research scripts that are exempt. Strict reading creates new backlog item `E20` for the missing test file (~half-day effort).

- **P10 (option c title rename).** Title changes from "Decisions-log gates non-trivial changes" to "Decisions-log gates rule and model changes." Body unchanged. The four triggers in the body (rules.py thresholds, exclusion criteria, model-feature sets, outcome metrics) all fit the new title cleanly; "non-trivial" was vague.

Refactor verification: `novopen_loader.py` `__main__` block produces byte-identical output to pre-refactor snapshot (342 injections, 2026-03 96/497u, 2026-04 131/704u, 2026-05 115/626u). `whoop_loader.load_whoop()` returns same dict size (364 dates). New `tests/test_bolus_classification.py` adds 8 cases (boundaries at `PRIME_MAX_U` and `PRIME_WINDOW`, bidirectional lookahead, empty input).

Test totals: `test_rules.py` 38 + `test_night_stats.py` 24 + `test_bolus_classification.py` 8 = 70 green.

**Why:** Without the wording polish, code-conventions had two structural mismatches (P5 violated; P9 empirically wrong after E17 landed) and two soft principles (P7+P8 as decision-snapshots; P10's vague title). The refactor under P5 keeps the principle crisp at the cost of two small new modules - the alternative ("tighten the wording") would have hedged P5 in a way future loader authors could lean on. P7+P8 in hybrid form (generalised principle + listed instances) gives both durability and grepability, matching the same style now also adopted for P5 and P9. Strict P8 and P9 readings intentionally surface follow-on work (E19, E20) rather than absorbing them into E11 - they are real code work, not wording fixes. Total session-internal time on E11: ~1 hour sparring + ~30 min implementation.

## 2026-05-29 - Bolus stream disjointness sanity check at merge (E15)
**Status:** accepted
**Decision:** `dexcom_loader.load_bolus_combined()` now scans for events with same `(minute, units)` appearing in both Clarity Hurtig and Glooko ACS streams. When any match: emits one `[dexcom_loader] WARNING:` line listing the overlapping `(datetime, units)` tuples (up to 5, then "... and N more"). Both events stay in the merged output - the check is log-warn, not filter or hard-fail.

Detection helper `find_minute_unit_overlaps(events_a, events_b)` lives in `scripts/bolus_classification.py` (per P5: bolus-classification logic in dedicated module, loader stays I/O-only). Granularity is minute-resolution + units, chosen to catch near-duplicates from clock-skew between Clarity (second-resolution) and Glooko (minute-resolution) timestamps. Stricter alternatives (exact-second) miss near-dupes; looser alternatives (+/- 5 min) risk false positives on legitimate close-spaced micro-doses.

7 new unit tests in `tests/test_bolus_classification.py` cover empty inputs, exact matches, unit/minute mismatches, second-level skew within same minute, and minute-boundary semantics. Current dataset produces zero overlaps - the warning never fires today, which matches the 2026-05-29 empirical baseline (`load_bolus_combined()` returns 1907 events; no warning printed).

Test totals: `test_rules.py` 38 + `test_night_stats.py` 24 + `test_bolus_classification.py` 15 = 77 green.

**Why:** The "disjoint by construction" assumption holds for today's vendor integrations but is not an invariant. If Glooko ever ingests G7-app data via a Dexcom partnership (hinted at in Glooko's roadmap), the same bolus event lands in both streams and `load_bolus_combined()` silently double-counts. Downstream consumers (`inferential_predictor.py`, `bolus_noise_test.py`, the future E19 bolus-into-rules work) would operate on doubled bolus history with no alarm. Log-warn was chosen over hard-fail because the check runs in every call to `load_bolus_combined()` including research scripts - a hard fail would crash analysis runs the moment the assumption breaks, before the user has a chance to investigate. The warning is loud enough to be noticed without disrupting in-flight work.

## 2026-05-29 - /session-done slash command (E5b)
**Status:** accepted
**Decision:** New slash command at `.claude/commands/session-done.md` automates the end-of-session sequence Thomas ran four times today: scan `git status` + `git log origin/master..HEAD` + tail of session-log; draft a continuation-format session-log entry from conversation context + git state; show the draft and ask `Approve / Edit / Cancel` via `AskUserQuestion`; on approval append to `docs/session-log.md`; run all three test suites (`test_rules.py` + `test_night_stats.py` + `test_bolus_classification.py`) and refuse to commit if any fail; explicit `git add docs/session-log.md` + optional confirmation for other tracked modifications (NEVER `-A`, NEVER `.`, NEVER untracked); commit with a generated message (subject + 2-3 body lines mirroring the entry's `Changed:` bullets + standard `Co-Authored-By`); `git push` to `origin/master` (no force, no hook skipping); final three-line report (entry size, commit hash + subject, push confirmation).

Sub-decisions baked in: approval gate before write (don't trust auto-summarisation of conversation context blindly); always push (matches current workflow); tests-must-pass before commit (all three suites run <0.01s); refuse on empty diff (no empty entries); explicit-files-only staging (defensive against any future `git add -f`).

**Why:** Repeating the same five-step manual sequence is a drift surface - small format inconsistencies creep into session-log entries each time. Automating with an approval gate gets the benefit (consistent format, free test gate) while keeping Thomas in the loop on what gets written to git history. The hard rules around `git add` scope and force-push exist to keep the command boring and predictable - the rule of thumb is "never let `/session-done` do anything the user didn't explicitly approve in the draft step." First-use smoke test note in the command file flags the spot-check responsibility the first time it runs.

## 2026-05-30 - Clarity out-of-range glucose clamped; parse-warning made truthful
**Status:** accepted
**Decision:** `dexcom_loader.load_dexcom()` now clamps Dexcom out-of-range glucose sentinels into the series instead of dropping them: `Høj` -> `GLUCOSE_HIGH_CLAMP = 22.2`, `Lav` -> `GLUCOSE_LOW_CLAMP = 2.2` mmol/L (the G7 measurable limits, 40-400 mg/dL). The per-file Clarity header row (`Tidsstempel ...`) is now skipped explicitly instead of hitting the timestamp-parse `except`. The `skipped_parse` counter and its warning now increment/fire only on genuinely unparseable values; the message changed from "(check Clarity export locale/format)" to "(genuine malformed data - inspect export)". Constants live at `dexcom_loader.py` module top (P1: constant with the concept; P5: parsing, not domain logic). `load_bolus_events()` untouched - it parses only Hurtig insulin and already skipped headers silently.
**Why:** The recurring `[dexcom_loader] skipped 690 rows due to parse errors` warning was investigated (2026-05-30) and found to be a false alarm - zero genuine format/locale problems. Breakdown of the 690: 671 `Høj` (glucose > 22.2), 8 `Lav` (glucose < 2.2), 11 export header rows (one per Clarity file). Dropping `Høj`/`Lav` silently biased every research/backtest consumer of `glucose_list`: TIR was inflated (671 highs removed vs 8 lows), and Clarity-based hypo analysis was blind to the 8 severe lows. Production path is unaffected - `dexcom_fetch.py` uses `_, basal_list, _ = load_dexcom()` and pulls the overnight glucose window from the live Dexcom Share API, not Clarity; tonight's suggestion never saw `glucose_list`. Impact confined to `basal_analysis.py`, `rules_model.py`, `inferential_predictor.py`, `dose_diary.py` backfill, `ml_model.py`, `predictor_test.py`, `bolus_noise_test.py`, and the two strain analyses.

Clamp boundary choice: 22.2 / 2.2 mmol/L are the G7 hardware limits and what Clarity itself uses for its own statistics. The alternative (2.1 / 22.3 to mark "strictly beyond range") was declined in favour of the standard boundary values. Consequence: clamping the 8 `Lav` to 2.2 makes them count as `<4.0` hypos in research `night_stats`, which can move a few nights into the hypo-correction exclusion pool.

Verification: backtest (`rules_model.py`) before -> after: nights evaluated 340 -> 340, within +/-1u 217 (63.8%) -> 218 (64.1%), MAE 1.35u -> 1.34u. Small favourable shift, consistent with a handful of previously-incomplete nights now resolving. All three required suites green (38 + 24 + 15 = 77). `dexcom_fetch.py` base run no longer prints the skipped-rows warning.

## 2026-05-30 - Global ASCII rule enforced repo-wide; one-time unicode normalization pass
**Status:** accepted
**Decision:** One-time conversion pass applied to all committed files: em-dash -> hyphen, en-dash -> hyphen, curly quotes -> straight quotes, ellipsis -> ..., bullet -> hyphen, non-breaking space -> regular space, Unicode arrow -> ->, plusminus -> +/-. Scope: docs (decisions-log.md, progress.md, session-log.md, .claude/commands/*.md), code comments/docstrings (basal_analysis.py, bolus_noise_test.py, dexcom_fetch.py, ml_model.py, rules_model.py, whoop_loader.py). Exception: Danish data strings that match CSV column names and sentinel values (Høj, Lav, Estimeret glukoseværdi, Insulin, etc.) were never touched - they must preserve exact spelling for Clarity CSV parsing.

Forward policy: Global ASCII rule (C:\Users\thblo\.claude\CLAUDE.md section 3) now explicitly applies to all files in this repo - no exceptions for "matching the file's prior style". Project CLAUDE.md "Working preferences" section updated with a one-line rule. Decisions-log-conventions.md (in claude-setup/) already requires ASCII in decisions-log entries; no change needed there.
**Why:** Thomas prefers uniform ASCII punctuation across all repos to avoid context-switching between style rules. The prior situation (repo's docs using em-dashes because "match existing") created a conflict with the global rule, which I handled inconsistently. One-time pass removes the surface that could regrow. The immutability of decisions-log.md entries was respected by treating punctuation normalization as a formatting pass (parallel to the 2026-05-23 bulk Status-line retrofit) rather than content editing. No entries were altered in substance - only punctuation marks replaced. Test suites unaffected: 77/77 green (38 + 24 + 15).

## 2026-06-04 - Wake anchor fixed at 06:20; WAKE_HOUR int -> WAKE_TIME value (E18)
**Status:** accepted
**Decision:** The overnight window now ends at a fixed **06:20** (Thomas's weekday alarm), not 07:00 and not a WHOOP-derived variable wake time. The design choice (fixed clock time vs wake-relative) was reached 2026-06-02 - see session-log `e10-wake-anchor-decision`; this entry records it and ships the code change (E18, the last item from the 2026-05-28 redesign audit, originally R22).

The bare-int constant `WAKE_HOUR = 7` in `scripts/night_stats.py` is replaced by a single `datetime.time` value `WAKE_TIME = time(6, 20)`, referenced at every site that needs the wake boundary. Datetime construction uses `datetime.combine(date, WAKE_TIME)`; display uses `WAKE_TIME.strftime('%H:%M')`. This removes a hardcoded `"07:00"` literal in `dexcom_fetch.py` (the fasting label, which bypassed the constant entirely) and two display strings that hardcoded `:00`. No `wake_end()` helper was added - `datetime.combine` is self-documenting and only has two call sites (P1: the value lives with its concept; over-engineering avoided).

Incidental fix: rewriting `dexcom_fetch.py`'s end-of-window construction from `datetime(yesterday.year, yesterday.month, yesterday.day + 1, WAKE_HOUR)` to `datetime.combine(yesterday + timedelta(days=1), WAKE_TIME)` also fixes a latent month-end overflow (`day + 1` raised `ValueError` on the last day of any month).

**Why:** The dawn phenomenon (early-morning glucose rise from circadian hormone release) fires at a roughly fixed clock time regardless of when Thomas actually wakes. A wake-relative window would extend into the post-dawn rise on sleep-in weekends, inflating the second-half slope and making weekend nights non-comparable to weekday nights. A fixed cutoff keeps cross-night slope comparisons consistent, which is the whole point of the second-half-slope outcome metric (decisions 2026-05-27 / 2026-05-28). 06:20 matches the actual weekday wake, so the fasting reading (= last reading in the window) reflects real wake glucose.

Impact: the change lives in `overnight_window()`, so it propagates to every historical-analysis consumer (`basal_analysis.py`, `rules_model.py`, both strain scripts, `inferential_predictor.py`, `dose_diary.py` backfill, etc.) and the production path (`dexcom_fetch.py`) uniformly. All nights now slice to 06:20; `fasting` moves ~40 min earlier. `overnight_window()` previously had no direct tests; this change adds 5 boundary cases to `tests/test_night_stats.py` (24 -> 29: 06:20 inclusivity, post-wake exclusion, pre-injection exclusion, full-span filtering, month-end crossing). All three suites green: 38 + 29 + 15 = 82.

## 2026-06-05 - E8 pivot: Playwright Clarity export dropped; Dexcom Developer API v3 adopted for insulin events
**Status:** accepted
**Decision:** The Playwright browser-automation approach for Clarity CSV export (E8, original plan) is abandoned. New direction: the official Dexcom Developer API v3 `/events` endpoint over OAuth 2.0 (app registered at developer.dexcom.com). This is a different API from the Share API (`pydexcom`, glucose-only) already in use. The Developer API carries insulin events logged in the G7 app (`longActing` = basal, `fastActing` = bolus) - the same source as Clarity's Hurtig rows. Implementation plan: probe script first (validation gate with sandbox then production data), then `dexcom_events_fetch.py` + `dexcom_events_loader.py` once the probe confirms G7 event history depth and the long/short-acting field split. API is the authoritative source for dates it serves; Clarity CSVs become the fallback for older history it may not reach. `clarity_coverage.py` is kept as a glucose-gap utility and semi-manual fallback driver. Token storage mirrors WHOOP: `~/.dexcom_api/`. `requests` (no SDK). EU host: `api.dexcom.eu` (confirm at app registration). Limited Access tier (up to 5 users, requires Dexcom DLA signature + approval) gates production access - sandbox-first development while the application is in review. E8b (Glooko bolus automation) parked until the probe clarifies what the API actually serves.
**Why:** Clarity sits behind Akamai-grade bot protection (TLS fingerprinting, injected JS challenges, CDP detection) that standard Playwright/Selenium cannot reliably bypass - confirmed 2026-06-05. The stealth-patch ecosystem is unmaintainable. The sanctioned Developer API is the correct long-term path: same data source (G7-app-logged insulin), OAuth-based (mirrors the WHOOP pattern already in place), no ToS exposure, no fragile DOM selectors. The medical data context makes reliability a hard requirement, not a nice-to-have.

## 2026-06-05 - 6-tier strain adjustment replaces 2-tier activity rule (E1 Phase B)
**Status:** accepted
**Decision:** The coarse 2-tier strain rule (`s1 >= 12 -> -2u`, else `0u`) is replaced with a 6-tier chain. Boundaries and adjustments:

| adj | s1 range     |
|-----|--------------|
| +3  | s1 < 6       |
| +2  | 6 <= s1 < 9  |
| +1  | 9 <= s1 < 11 |
|  0  | 11 <= s1 < 13|
| -1  | 13 <= s1 < 15|
| -2  | s1 >= 15     |

`ACTIVITY_THR` constant removed; replaced by `STRAIN_T1..T5` (cutoffs 6, 9, 11, 13, 15). The `activity_threshold` function parameter removed from `thomas_rules()` signature (no callers used it). The variable previously named `adj_activity` retains its name (stacks with glucose adj and new-pen adj as before).

**Why:** The 2-tier rule was a placeholder. Phase A binning analysis (`strain_binning_analysis.py`, 2026-05-27) ran on 256 historical nights and measured second-half glucose slope per strain bin. Results: low strain bins show rising slopes (under-dose signal), high strain bins show falling slopes (over-dose signal). Phase A2 OLS regression confirmed direction: b_strain = -0.054 mmol/L/h per strain unit, p=0.001. The 6-tier table is anchored to observed slope transitions in the binning output. Known limitations: (a) s1 < 6 bin has n=12 nights (thin evidence); (b) dose coefficient is weak (p=0.43) due to narrow historical dose range (mostly 17-19u), so +1/+2/+3 magnitudes carry uncertainty; (c) the 13-15 bin (-1u) showed a flat slope in the data rather than sensitivity - adopted as a granularity improvement over the old -2u at s1 >= 12. Threshold boundaries are judgment-anchored, not statistically optimized. Plan: treat as a starting point and calibrate from live performance.
