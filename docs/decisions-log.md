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
**Status:** superseded (see 2026-05-29 entry "Bolus sources merged across all dates - no cutover")
**Decision:** Bolus events from 2026-01-31 onwards are sourced from Glooko's CSV export of NovoPen 6 data, parsed by `scripts/novopen_loader.py`. Clarity CSV remains the source pre-cutover. Combined events flow through `dexcom_loader.load_bolus_combined()` with cutover constant `NOVOPEN_CUTOVER = 2026-01-31`. Glooko export is currently manual (download from web app); automation deferred.
**Why:** Dexcom Clarity raw CSV exports are hard-filtered to G7-app-source events only - confirmed by inspecting every insulin row across all historical exports (100% `Kildeenheds id = "android G7"`, zero NovoPen rows). NovoPen data reaches Clarity reports via a separate partner pipeline but never enters the raw CSV. Glooko is the same partner channel Dexcom uses internally; pulling from there is the only viable path short of building a custom NFC reader. Manual export accepted as the v1 friction cost; Playwright automation planned as a follow-up.

## 2026-05-29 — Glooko Prime Detection rule implemented in novopen_loader.py
**Status:** accepted
**Decision:** `scripts/novopen_loader.py` filters NovoPen events using Glooko's documented Prime Detection rule: an event is a PRIME iff (amount <= 2u) AND (another insulin event follows within 6 minutes). Otherwise it is an INJECTION. Constants `PRIME_MAX_U = 2.0` and `PRIME_WINDOW = timedelta(minutes=6)` reflect the published rule verbatim.
**Why:** Thomas enabled Prime Detection in Glooko on setup but has not run the per-event manual classification UI, so `bolus_data_1.csv` is empty and the raw event stream is in `insulin_data_1.csv`. Implementing Glooko's own rule client-side gives a deterministic, documented classification without requiring the manual UI step. Known limitation: a real 1-2u bolus immediately followed by another bolus within 6 min would be misclassified as a prime - acceptable because (a) Thomas rarely takes sub-2u boluses, and (b) the loader's purpose is slope disambiguation, not carb-counting precision. Rule lives in `novopen_loader.py:PRIME_MAX_U` / `PRIME_WINDOW`.

## 2026-05-29 — Bolus sources merged across all dates - no cutover
**Status:** accepted
**Decision:** `dexcom_loader.load_bolus_combined()` now concatenates Clarity Hurtig events and Glooko ACS* (smart-pen) events across all dates and sorts by timestamp. No cutover date, no dedup. The previous `NOVOPEN_CUTOVER = 2026-01-31` constant is removed. Supersedes the earlier "NovoPen 6 bolus source via Glooko export (R13)" entry from today.
**Why:** Thomas confirmed (2026-05-29) that he uses both a regular pen (manually logged in the Dexcom G7 app -> Clarity) and a smart NovoPen 6 (NFC -> Glooko) interchangeably going forward, with the smart pen most of the time. There is no single switch date. The two sources are disjoint by construction at the event level: Clarity Hurtig rows have `Kildeenheds id = "android G7"` (manual entries only - confirmed across every historical Clarity CSV), and `novopen_loader.load_glooko_bolus()` filters to ACS-prefix serials only (skipping the Dexcom-source rows that Glooko ingests). Therefore a naive concatenation gives the full picture without double-counting. Verified: only 1 calendar day (2026-03-05) ever had bolus events in both streams, and they were at non-overlapping times.

## 2026-05-29 — Phase 5 inferential predictor: M3 (dose*s1) chosen as best-supported spec
**Status:** accepted
**Decision:** `scripts/inferential_predictor.py` compares four nested model specs (M1 linear additive baseline, M2 + s1^2, M3 + dose*s1 interaction, M4 + both) and selects via F-test against the next-simpler nested model with the constraint that `beta_dose` retains p<0.10. M3 selected on current 288-night sample: R^2 = 0.064 (vs M1's 0.048), F-test M3 vs M1 p=0.029, beta_dose p=0.020, beta_(dose*s1) p=0.029. M2 (s1^2 alone) and M4 (both terms) failed their F-tests.
**Why:** The Phase A2 baseline (M1) has beta_dose p=0.42, which makes the inferred-optimal-dose computation unreliable. Adding the dose*s1 interaction makes dose significant and lifts R^2 by ~33% relatively, with a passing F-test. The biological story is that dose's effect on second-half slope is moderated by strain: at high strain, the same dose has a different relationship to overnight slope (consistent with the existing activity rule). M3 is now the model used to invert sh_slope=0 for "what dose would have flattened tonight". Re-run when sample grows materially; if a future dataset breaks M3's F-test or beta_dose significance, the script will fall back automatically.

## 2026-05-29 — Phase 5 signal ranking: 7 signals promoted to Phase 6 rule design
**Status:** accepted
**Decision:** Convergent ranking from `inferential_predictor.py` (direct Spearman vs sh_slope; partial Spearman after removing s1, prev_dose, inj_g; Spearman vs M3 inferred optimal dose). Promotion tiers on 288 usable nights:
- **HIGH (>=2/3 metrics p<0.05 same direction):** `s1` (strain), `recovery`, `hrv`, `rhr`, `inj_g`, `bolus_4h_pre`, `bolus_during_night`.
- **MED (1/3):** `sleep_perf`, `prev_dose`, `prev_fasting`.
- **LOW (0/3):** `prev_hypos`, `hypo_events_tonight`.

Phase 6 rule design works from the HIGH list. MED signals are watched but not encoded in the first rule iteration. LOW signals are dropped from the candidate set.
**Why:** Same-direction agreement across three independent measurement angles is stronger evidence than any single test, given the chosen-model R^2 is still only 0.064 (most slope variance is unexplained). Notable findings: (a) bolus_4h_pre AND bolus_during_night both clear HIGH - the slope rule's framing (bolus needed for disambiguation) is empirically supported; (b) inj_g passes via direct + inferential despite partial r ~ 0 (it IS one of the controls so partial is ~0 by construction - not a refutation); (c) prev_hypos / hypo_events_tonight are too rare to carry signal in this sample - revisit if hypo frequency rises.

## 2026-05-29 — WHOOP stress endpoint not exposed by whoop-sdk 0.3.1 (R21 closed for now)
**Status:** accepted
**Decision:** WHOOP stress not added as a Phase 5 candidate. `whoop-sdk` v0.3.1 exposes only cycles, recovery, sleep, workouts, body measurements, and profile - no stress endpoint. Path 2 fallback (derive a "stress proxy" from HRV) declined: HRV is already a candidate signal in its own right; relabeling it as "stress" would mislead more than inform.
**Why:** WHOOP's mobile app has a Stress Monitor feature but it is not exposed in the public Developer API as of the installed SDK version. Building a custom auth/scraping path against the mobile app is out of scope for Phase 5 and not warranted unless HRV alone proves insufficient in Phase 6 rule testing. Revisit when whoop-sdk publishes a stress endpoint, or if Phase 6 evidence demands a separate stress channel.

## 2026-05-29 — Slope-based fasting rule v1 encoded in thomas_rules()
**Status:** accepted
**Decision:** The fasting-glucose tier in `thomas_rules()` is replaced by a slope-based tier driven by second-half overnight slope (`sh_slope`, mmol/L/h). Priority: hypo events still override everything (Q4); when `sh_slope` is provided it drives the glucose tier; when unavailable the rule falls back to wake-time fasting via the same tier structure. Resolutions of the four open questions parked on 2026-05-28:
- **Q1 (down-direction symmetry):** Symmetric direction - falling slope WITHOUT a hypo triggers -u. Magnitudes asymmetric: 3-tier up (+1/+2/+3), 2-tier down (-1/-2). Down capped at -2 for safety.
- **Q2 (slope thresholds):** `SLOPE_FLAT = 0.3`, `SLOPE_MID = 0.7`, `SLOPE_HI = 1.2`. Derived from the actual slope distribution (flat band matches existing `FLAT_BAND` from strain_binning; mid/hi map to ~p75 and ~p90 of the absolute-slope distribution).
- **Q3 (adjustment scale):** 3-tier up, 2-tier down. Matches existing 3-tier fasting structure; asymmetry reflects clinical risk.
- **Q4 (hypo priority):** Hypo override KEPT. `hypo_events >= 2 -> -2u`; `hypo_events == 1 -> -1u`; both bypass slope. Same priority structure as the prior fasting rule.

Signature: `thomas_rules(yesterday_dose, fasting, hypo_events, s1, new_pen=False, sh_slope=None, slope_flat=0.3, slope_mid=0.7, slope_hi=1.2, ...)`. `sh_slope` defaults to None so existing callers / tests work unchanged; 17 new slope tests added in `tests/test_rules.py` (38/38 total green). `dexcom_fetch.py` and `rules_model.py` pass `sh_slope` (live and per-night respectively).
**Why:** Slope captures the trajectory the dose produced - a flat second half means the basal held; a rising one means it ran out; a falling one means too much. Endpoint fasting only sees the result, not the path, and is gameable by a late-night correction bolus (Phase 5 confirmed bolus_4h_pre and bolus_during_night are both HIGH-tier slope predictors, supporting the disambiguation framing). Backtest on 340 nights: slope-rule MAE 1.35u (within margin of the prior fasting-rule baseline 1.32u) with 63.8% within +/-1u of actual doses. Mean diff +0.79u (actual > suggested) is consistent with Phase 5's "Thomas systemically under-dosing relative to inferred optimum" finding. Thresholds parameterised so a future R8-style backtest can re-tune without code change.

## 2026-05-29 — Doc-scope policy + architecture.md rewrite (R20 / R16-R18)
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

## 2026-05-29 — Phase 9 close-out: durable home for code-side principles + leftover cleanup
**Status:** accepted
**Decision:** Audit after Phase 8 found four gaps. Resolved here as a "Phase 9 close-out":
- **Code conventions (P1-P12) lifted to `docs/code-conventions.md`** as the durable home. Previously the 12 principles only lived inside the 2026-05-28 audit doc (`t1d-redesign.md` §7), which is a snapshot and not authoritative. The doc-scope policy from the previous entry covers documents; this new file covers code. CLAUDE.md "Working preferences" now points at it; `architecture.md` "Doc map" lists it; `t1d-redesign.md` §7 notes it as superseded.
- **R9 finished.** `rolling_avg()` + `s7` (and `s1_dev`) removed from `scripts/ml_model.py` and `scripts/predictor_test.py` (the only two remaining sites). The 2026-04-15 decision to drop s7 is now reflected in code everywhere; previously two analysis scripts still computed it.
- **R14 finished.** `scripts/ml_model.py` "TONIGHT'S DOSE RECOMMENDATION" block removed; only `dexcom_fetch.py` now emits a tonight's-dose suggestion (P3 enforced). The Phase 7 grep was scoped to three files and missed `ml_model.py`.
- **B9 marked done** in `improvements.md`. Phase 1 had already renamed `TGT_LO/HI` to `TARGET_LO/HI` (user goal) + `CLINICAL_TIR_LO/HI` (clinical TIR); the backlog item just wasn't checked off.
- **Architecture doc cleanup.** `scripts/whoop_api_fetch.py` reclassified from "Shared modules" (it's a CLI fetch script, not a loader) to a new "Fetch / refresh scripts (entry points)" subsection. Stale `docs/progress.md` (last meaningfully edited 2026-04-15, content over a year out of date) moved to `archive/docs_pre_redesign/` and removed from the doc map.
- **Unused import removed:** `os` in `scripts/dexcom_loader.py`.

**Why:** The redesign claimed completion at Phase 8, but the post-hoc audit surfaced that P3 ("one nightly suggestion") was violated by `ml_model.py`, P6 ("drop dead weight") was violated by `rolling_avg`/`s7` persistence, and the principles themselves had no durable home. Closing here keeps the principles enforceable rather than aspirational, and removes the dead surface that would otherwise re-grow under any future contributor's `grep -r "s7"` or `grep -r "tonight"`.

## 2026-05-29 — Phase 9 correction: progress.md restored (was not stale)
**Status:** accepted
**Decision:** Restored `docs/progress.md` to git and re-added it to the `architecture.md` doc map. The previous Phase 9 entry's claim that the file's "content over a year out of date" was incorrect; the doc was last meaningfully edited 2026-04-15, ~6 weeks before today (2026-05-29). The "Next session" notes in the doc had been executed since but the document itself is a milestone summary, not a session log, and is still in active use by Thomas. Architecture.md doc map row reworded from "legacy; lightly maintained" to "Milestone summary: Done / Next session / Open questions".
**Why:** I miscounted the time elapsed and unilaterally archived a doc that was not in fact stale. Thomas's own correction surfaces the principle for the close-out itself: when in doubt about deleting an artefact, ask. The 2026-04-15 date stays as the last edit; future updates are owned by Thomas, not by a redesign cleanup pass.

## 2026-05-29 — Redesign audit doc archived (R-series + P-series fully migrated)
**Status:** accepted
**Decision:** `docs/t1d-redesign.md` moved to `archive/docs_pre_redesign/`. The audit's actionable content is now fully migrated: R1-R21 done across Phases 1-9; R22 broken out as `improvements.md` E18 (last un-shipped item, gated on E10's fixed-vs-relative wake-anchor decision); P1-P12 lifted to `docs/code-conventions.md` (Phase 9). Sections 1-6 of the audit (component map, data sources, rules, inconsistencies, modularity assessment) were informational and fed the R-series.
- `architecture.md` doc map row removed.
- `code-conventions.md` "principles emerged from..." sentence updated to point at the archived path.
- Decisions-log entries referencing the audit doc by its old `docs/` path are immutable and remain as-is (historical context); future references should use the archive path.
**Why:** The audit was a snapshot with a defined purpose - extract inconsistencies and propose principles. Both are now durably homed (`improvements.md`, `code-conventions.md`, and the 9 phase commits). Keeping the audit in `docs/` would imply ongoing relevance it no longer has. Archiving preserves the historical record (gitignored locally, recoverable via git history at the old path) without it occupying the active doc tree.

## 2026-05-29 — E12 resolved: strain-non-negotiable invariant enforced in code (Path A)
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
