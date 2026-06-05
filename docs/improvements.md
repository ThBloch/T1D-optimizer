# T1D Improvement Backlog

Format rules in `claude-setup/CLAUDE.md`. Status: `[ ]` open, `[x]` done, `[-]` blocked.

Read this before proposing new refactors.

---

## B. Code hardening

- [x] B9. Rename shadowed `TGT_LO` / `TGT_HI` - done as part of Phase 1 redesign (R5). Constants renamed to `TARGET_LO` / `TARGET_HI` (user goal, 5-8) and `CLINICAL_TIR_LO` / `CLINICAL_TIR_HI` (clinical TIR, 4-10), both centralised in `night_stats.py`.
- [ ] B10. Fix bolus dedup precision - exact `(datetime, units)` tuple, 1-second timestamp drift across exports double-counts. Round to minute or dedup by `(date, hour, units)`. (deferred: low value-for-effort)
- [ ] B11. Widen `whoop_api_fetch.py` retry net beyond 429 - handle 401 token-expired, 5xx server errors. Per-endpoint isolation so one failure doesn't kill the other three. (deferred: low value-for-effort)

---

## C. Privacy / publishing

- [ ] C1. Sanitize source files before public push.
  - Leak surface (6 locations): `CLAUDE.md` L3/35, `scripts/basal_analysis.py` L2/138, `scripts/ml_model.py` L2, `scripts/whoop_api_fetch.py` L13 (`DIAGNOSIS_START` constant), `docs/architecture.md` L43.
  - Contents leaked: full name "Thomas Bloch-Nielsen" + diagnosis date 2025-04-09.
  - Original entry mentioned "email" - false alarm, not in any tracked file. `data/` already gitignored so no medical data leaks.
  - Separate leak: git commit author identity (full name on every past commit). At public-migration time decide file-only sanitization (accept history names you) vs `git filter-repo` rewrite (anonymous public repo, destructive).
  - Approach: replace "Thomas Bloch-Nielsen" with generic "T1D Basal Optimizer" framing in script headers / docstrings / CLAUDE.md; parameterize `DIAGNOSIS_START` as env var or local `config.json` (gitignored); same for any other personal constants.
  - Not blocking current work. Blocks public path of E2 only.

---

## E. Pending work

- [x] E1. Refine strain-based rule - 6-tier encoding shipped 2026-06-05 (STRAIN_T1..T5 in rules.py; 6 new test cases; decisions-log entry). Boundaries are data-anchored from Phase A binning but carry uncertainty; plan to calibrate from live performance.
  - Wanted: granular `+3, +2, +1, 0, -1, -2`. Define s1 thresholds per level.
  - Clinical direction: low strain -> higher insulin resistance (+adj), high strain -> higher insulin sensitivity (-adj). Confirm with Thomas before encoding.
  - Approach: bin historical nights by s1, look at TIR / fasting outcomes per dose, infer thresholds, encode in `rules.py`, add ~6 unittest cases, document in `decisions-log.md`.
  - Status 2026-05-27: Phase A + A2 analysis done (scripts/strain_binning_analysis.py, scripts/strain_regression_analysis.py). Threshold table proposed; encoding gated on Thomas sign-off. See session-log.md 2026-05-27 entry.
  - Hard requirement (Thomas, 2026-05-27): strain MUST be part of every dose suggestion. The current rule silently skips the strain block when `s1 is None`; this is unacceptable. -> see E1b, now elevated.
- [ ] E1b. Always provide a usable s1 at dose time. **Elevated 2026-05-27; design corrected 2026-05-28.**
  - Problem: `scripts/whoop_loader.py:18-23` indexes the in-progress cycle under its start date, so `whoop.get(today)` returns `None` at evening dose-suggestion time. `dexcom_fetch.py:177-182` then silently skips the strain branch. Thomas does not see a strain reasoning line, and the dose has no activity adjustment.
  - **Generalized scope (2026-05-28):** The same bug class affects `/dose` step 1 - it asks for yesterday's dose upfront, but `dexcom_fetch.py` already auto-resolves yesterday's dose from Clarity CSV then diary on most nights. Fix both in one pass: the script signals what it could not auto-resolve via structured stdout lines; the slash command asks only for the missing items.
  - **Strain resolution - exactly two valid paths:**
    1. Today's WHOOP strain from cache (`whoop_loader.load_whoop()`; possibly augmented by live-fetch - see exploration sub-task below).
    2. Ask Thomas directly via documented manual-fallback prompts (see E1d).
  - **Yesterday's s1 is never a valid fallback.** Strain varies day-to-day; using yesterday's value produces a worse suggestion than asking the user. Memory: `feedback-strain-yesterday-invalid` (Thomas, 2026-05-28).
  - **Signaling mechanism (decided 2026-05-28):** Script emits structured stdout lines `NEEDS: <name>` (e.g. `NEEDS: dose`, `NEEDS: strain`) for inputs it cannot auto-resolve. `/dose` parses stdout, asks only for the listed items via prompts from E1d, then re-runs the script with the values passed as flags. Exit codes rejected: (a) cannot cleanly encode multiple missing items in one integer, (b) inconsistent with `/dose`'s existing stdout-parsing approach (hypo re-run is the model, step 5), (c) less human-readable when running the script manually.
  - **Sub-task (exploration, does not block):** Live-fetch the in-progress WHOOP cycle via `whoop-sdk` at dose-suggestion time. Investigate: does the SDK return the in-progress cycle? Is `score.strain` populated mid-day before the cycle closes? If viable -> slot in between cache lookup and manual prompt. If not -> manual prompt is the only fallback for cache-miss days.
  - **Sub-task (gates implementation):** E1d below - document manual-fallback prompt steps. Implementation cannot start until E1d is resolved.
  - **Implementation outline (after E1d lands):**
    1. `dexcom_fetch.py`: replace the Priority-3 `input()` dose prompt (lines ~162-174) with `print("NEEDS: dose")` + return. Replace the silent strain-None path (lines ~181-182) with `print("NEEDS: strain")` + return (strain is non-negotiable per the 2026-05-27 entry; final behavior depends on the "skip" decision in E1d).
    2. `dexcom_fetch.py`: add `--strain N` flag, mirror of `--dose N`. Flag overrides the cache lookup.
    3. `.claude/commands/dose.md`: remove step 1 (upfront dose question). New flow: run script with no flags -> parse stdout for `NEEDS:` lines -> ask only for those using prompts from E1d -> re-run with `--dose N` / `--strain N` flags.
  - **Acceptance:** `/dose` only asks for inputs the script cannot resolve. `dexcom_fetch.py` never silently skips strain - emits `NEEDS: strain` when unavailable. Script never blocks on `input()` in non-interactive mode.
- [ ] E1d. Document the manual-fallback prompt steps for `/dose`. **Gates E1b implementation.**
  - When the script signals `NEEDS: <name>`, `/dose` must ask using a documented prompt. This item specifies those prompts.
  - Open questions to resolve before writing the spec:
    - **Wording:** e.g. "What was today's WHOOP strain (0-21)?" - or alternative framing? Include hint about expected range?
    - **Validation:** accept floats (strain is e.g. 12.4)? Reject if outside 0-21? Reject negative or non-numeric input?
    - **"I don't know" path:** is "skip" an acceptable answer for strain? If yes - run without strain (contradicts the 2026-05-27 non-negotiable), use a documented default, or refuse to suggest a dose at all? Thomas must decide; this shapes the whole flow.
    - **Order of asks:** if both dose AND strain are missing in the same run (rare - first install with no Clarity CSV, no diary, no WHOOP), ask dose first or strain first? Suggestion: dose first (script cannot suggest without it).
    - **Re-run safety:** after collecting inputs, `/dose` re-invokes the script with the appropriate flags. Cap re-runs (max two passes or per-item retry) so invalid input does not infinite-loop.
    - **Output medium:** prompts inline in `.claude/commands/dose.md`, or in a separate doc like `docs/dose-manual-prompts.md`? Inline is simpler; separate is more reusable when E6 (Telegram bot) replicates the same prompts.
  - Output: a "Manual fallback prompts" section in `dose.md` (or referenced doc) with exact prompt strings, validation rules, and order of operations.
- [ ] E1c. Rule audit and skip toggles - review every rule in `scripts/rules.py` with Thomas, line by line.
  - Reason: Thomas does not recognise the current thresholds (FASTING_LO=10.5, FASTING_MID=12.0, FASTING_HI=14.0, ACTIVITY_THR=12.0, DOSE_MIN=15, DOSE_MAX=29) as ones he personally set. They were inherited from earlier work or defaulted. He needs to own each one.
  - Approach:
    1. Enumerate every threshold + every conditional branch in `thomas_rules` (fasting tiers, hypo priority, strain block, new-pen, clamp).
    2. For each, surface to Thomas: current value, where it came from (`docs/decisions-log.md` cross-reference if any), and the historical effect on dose suggestions (count of nights it would have fired, or actually fired).
    3. Thomas accepts, modifies, or marks the rule "skippable".
    4. Add per-rule skip toggle: either a CLI flag on `dexcom_fetch.py` (e.g. `--skip strain,fasting`) or a config block at the top of `rules.py` (`ENABLED_RULES = {"fasting": True, "strain": True, ...}`).
    5. Document the audited rule set in a new `docs/rules-spec.md` so the rule contract is explicit and reviewable.
  - Not blocked; can start in any session.
- [ ] E2. GitHub publish - private backup done 2026-05-21; public migration deferred until "share-ready" AND C1 done.
  - Decision 2026-05-21: eventual aim is public, to help other T1D patients/builders. Not a priority now. "Better first" - improve model + automation before going public.
  - Informal quality bar: E1 (strain rule), E10 (nighttime objective validated), at least E5 (Phase 1 automation) done so it's not a single-user manual tool.
  - Status of the three migration paths:
    1. [x] Private push for backup - done 2026-05-21. Repo at https://github.com/ThBloch/T1D-optimizer (private). Origin tracked, GCM credential cached.
    2. [ ] Public, real name in history - requires C1 + flip visibility in GitHub Settings -> Danger Zone -> Change visibility. Standard for personal-portfolio repos.
    3. [ ] Public, fully anonymous - requires C1 + `git filter-repo` rewrite of past commit authors. Destructive, only if anonymity matters more than convenience.
- [x] E3. `/dose` slash command - thin orchestration wrapper around `dexcom_fetch.py`. Lives at `.claude/commands/dose.md`. (blocked by: E5)
  - Flow: ask new-pen + unmodeled factors (alcohol / late meal / illness / activity-not-in-WHOOP) -> run script -> if hypos detected, ask sensor-noise -> output terse `Tonight: Nu` + reasoning bullets + off-rules flags.
  - Format per global memory: `feedback_dose_recommendation`, `feedback_dose_unmodeled_factors`.
  - Why blocked: dose.md should consume `--dose N` flag and a non-interactive script. First draft rolled back - hit conflicts because it added interactivity that E5 is removing.
  - After E5, dose.md becomes ~20 lines (pure orchestration, no anchor-prompt handling). History in `decisions-log.md`.
- [x] E4. `/t1d-status` slash command - quick snapshot.
  - Shows: last Dexcom fetch timestamp, latest Clarity CSV date in `data/`, count of unchecked items in `docs/improvements.md`, days since last dose entry in `data/doses.csv`.
  - Path: `.claude/commands/t1d-status.md`. Effort ~15 min. Not blocked - good warmup task.
- [x] E5. Phase 1: cron-friendly scripts (~1h) - `--dose N` CLI flag on `dexcom_fetch`, remove remaining `input()` prompts. (blocks: E3, E6)
- [x] E5b. `/session-done` slash command - one command to log session, commit, and push. Resolved 2026-05-29: `.claude/commands/session-done.md` implements the 10-step flow with an approval gate before the commit, mandatory test pass (`test_rules.py` + `test_night_stats.py` + `test_bolus_classification.py`) before staging, explicit `git add docs/session-log.md` (no `-A`, no `.`, no untracked files), and a fixed three-line final report. First-use smoke test note included in the command file. See decisions-log 2026-05-29.
- [ ] E6. Phase 2: Telegram bot (~3-4h) - `python-telegram-bot` on Hetzner Frankfurt (EU/GDPR) or Raspberry Pi. Commands: `/today`, `/took N`, `/stats`. (blocked by: E5) (blocks: E7)
- [ ] E7. Phase 3: nightly proactive push (~30m) - cron 21:30 -> bot DMs tonight's suggestion. (blocked by: E6)
  - Soft dep: needs fresh Clarity data. Either E8 or manual re-export.
- [ ] E8. Phase 4: Dexcom Developer API v3 for insulin events - OAuth app (developer.dexcom.com), `/events` endpoint (longActing=basal, fastActing=bolus), incremental fetch to `data/dexcom_api/events.json`. Replaces manual Clarity CSV export as the authoritative insulin source; Clarity CSVs become historical fallback for older dates the API may not reach. Gate: probe script (`scripts/dexcom_api_probe.py`) must confirm G7 event history depth + long/short-acting field split vs Clarity on overlapping dates. Limited Access DLA (Dexcom approval required, unknown review time) gates production data. Token storage at `~/.dexcom_api/`. See decisions-log 2026-06-05.
  - Note: Playwright approach abandoned 2026-06-05 (Akamai bot protection - see decisions-log).
  - `scripts/clarity_coverage.py` kept as glucose-gap utility + semi-manual fallback driver.
- [-] E8b. Phase 4b: Playwright Glooko bolus export - parked. Revisit after E8 probe determines what the Dexcom Developer API actually serves; may be redundant or may reveal a gap.

End goal: phone-triggered nightly suggestion. Hard blocker for true end-to-end: Dexcom Share API has no insulin events. E8 solves it via the official Developer API (preferred) or semi-manual Clarity re-export (fallback).

Risks across E5-E8: Dexcom Limited Access approval time, DLA terms, API data retention depth, Telegram chat-id whitelist.

- [ ] E10. Nighttime objective spec: flat curve, weighted toward wake-up (logged 2026-05-21, not yet scoped to a phase)
  - Goal hierarchy (priority order):
    1. Wake-up glucose in target (5-8 mmol/L).
    2. Minimize abs(wake - bedtime).
    3. Minimize variability across the night (flat curve).
  - Weighting: second half of night > first half. Optimize for stability and on-target landing in the hours before wake, even at the cost of more deviation earlier in the night.
  - Open definitions (resolve with Thomas before encoding):
    - "Bedtime" = injection-time glucose (`vals[0]` in `compute_night_stats`)? Or first CGM reading after sleep-onset?
    - "Wake-up" anchor: **fixed 06:20 daily** (decided 2026-06-02). Variable wake time from WHOOP sleep data is technically feasible (sleep record `end` field is available in cache for closed cycles) but was rejected for the slope window: dawn phenomenon is circadian, not wake-relative - the pre-dawn glucose rise fires at roughly the same clock time regardless of actual wake. A sleep-in weekend extends the window into the post-dawn climb, making slopes look steeper and incomparable to weekday windows. Fixed cutoff is more consistent for cross-night slope comparison. Note: WHOOP-derived wake time could still be useful for the fasting reading specifically (actual wake glucose vs fixed-cutoff proxy) - a separate future consideration.
    - "Flat" metric: SD, range, MAGE, or time outside +/-1.5 mmol/L band from bedtime? Pick one and justify.
    - "Second half" boundary: clock-based (e.g. 02:30) or fraction-based (last 50% of CGM points)?
    - Weighting function: hard split (e.g. 70/30) or gradient (linear ramp toward wake)?
  - Validation gate (must pass before any code change ships):
    - Compute new composite score on historical 200+ nights.
    - Rank nights under new metric and under current `tir(5-8)` metric.
    - If Spearman r > 0.95 the new metric is decoratively different - aborts the change, document and stop.
    - If r < 0.95 identify which "best doses" reorder, inspect ~5 hand-picked nights for face validity, then proceed.
  - Conflicts with existing code:
    - `basal_analysis.py:compute_night_stats` produces `tir(5-8)` as the headline metric - becomes secondary under new spec.
    - `outcome_stats` ranks `best_dose` by `tir` - needs to switch to composite score.
    - `rules_model.py` backtest evaluates rules by next-night `tir` - comparison surface changes; old MAE numbers (1.32u rules vs 1.45u DT) lose comparability.
    - `rules.py:thomas_rules` is a dose-titration rule, NOT an outcome optimizer. The new objective may only change evaluation, not the rule itself. Confirm before touching rules.
    - Hypo-correction exclusion (`hypo_correction` flag) still applies: a flat post-correction night at 10+ is still dose-too-high, not a "flat curve win".
    - Possible interaction with E1 (strain-rule refinement): if both land, retune in the right order so one doesn't mask the other's effect.
  - Approach when implementing:
    1. Extend (do not replace) `compute_night_stats` with: `wake_delta`, variability metric, late-night sub-window stats.
    2. Add composite score function with weight parameter exposed.
    3. Run the validation gate above on full history.
    4. If it passes: switch headline metric in `basal_analysis.py` BLOCK 1, update `rules_model.py` evaluation. Leave `rules.py` untouched unless validation surfaces a rule gap.
    5. Add unit tests for the metric (all-flat, sawtooth, post-hypo correction, second-half-only-flat).
    6. Log decision + r value + which "best doses" changed in `decisions-log.md`.

- [x] E11. Code-conventions principle wording polish (post-Phase-9 audit). Resolved 2026-05-29: P5 refactored (`_cycle_date` -> `whoop_cycles.cycle_date_for`; Prime Detection -> `bolus_classification.filter_primes`); P7+P8 hybrid form with listed instances and strict P8; P9 hybrid form with required test files listed; P10 title renamed to "rule and model changes". Two follow-on items added: E19 (bolus integration into thomas_rules per strict P8) and E20 (tests/test_inferential_predictor.py per strict P9). See decisions-log 2026-05-29.

- [x] E12. P12 invariant #2 ("strain MUST inform every suggestion") vs actual code enforcement. Resolved 2026-05-29 via Path A (minimal NEEDS-line enforcement). `dexcom_fetch.py` now emits `NEEDS: strain` and refuses to compute a suggestion when today's WHOOP strain is unavailable; new `--strain N` flag overrides cache lookup. The friendly `/dose` side (parse `NEEDS:`, ask via documented prompt) remains E1b/E1d work. See decisions-log 2026-05-29.

- [x] E13. Hookify reality-check. Resolved 2026-05-30: global standalone hooks in `D:\claude-config\.claude\settings.json` (`creds-commit-guard.py`, `session-end-checks.py`, `session-start-inject.py`) now fire for t1d scripts regardless of launch dir. Local hookify rules were cwd-bound and never fired from the workspace root; pre-existing bug found (`hookify.run-tests-reminder.local.md` had wrong `name:` field). All three local rules set to `enabled: false` (superseded by global hooks).

- [x] E14. Production-path smoke test (integration test for `dexcom_fetch.py` end-to-end). Shipped 2026-06-05: `tests/test_dexcom_fetch.py` (3 smoke tests); `run()` refactored to accept optional args list.
  - 38 unit tests cover `thomas_rules` (pure function). Zero integration tests cover the production path: Dexcom fetch -> `night_stats` -> rules -> diary upsert. Regression in any signature or import is undetected until `/dose` is run live.
  - Approach: fixture-based smoke under `tests/fixtures/` - synthetic CGM + WHOOP + Clarity snapshot (no real medical data) -> assert produced suggestion + diary delta. Stub Dexcom Share API or skip live fetch.
  - Effort: ~half a day to set up fixtures; ongoing cost low.

- [x] E15. Bolus stream disjointness sanity check at merge time. Resolved 2026-05-29: `bolus_classification.find_minute_unit_overlaps()` added; `dexcom_loader.load_bolus_combined()` calls it after merging Clarity + Glooko streams. Emits a `[dexcom_loader] WARNING:` line listing overlapping `(datetime, units)` tuples when any match. Log-warn behaviour (option a) - both events kept in the merged output. 7 new tests in `tests/test_bolus_classification.py`. Current dataset produces zero overlaps. See decisions-log 2026-05-29.

- [x] E16. Memory vs decisions-log overlap policy. Resolved 2026-05-29: policy codified in `docs/code-conventions.md` under "Knowledge stores: memory and decisions-log". Decisions-log is canonical; memories carry plain-text `Recorded in docs/decisions-log.md YYYY-MM-DD` cross-references when their content corresponds to a decisions-log entry. Applied to the four overlapping memories today. See decisions-log 2026-05-29.

- [x] E17. `night_stats.second_half_trend()` edge-case behaviour + direct tests. Resolved 2026-05-29: `second_half_trend()` now returns `(None, None, sh_n)` when the regression denominator is 0 (previously returned `0.0` silently). New file `tests/test_night_stats.py` adds 24 direct unit cases covering slope direction/magnitude, degenerate inputs, hypo-event counting, hypo-correction boundaries, and TIR fields. See decisions-log 2026-05-29.

- [x] E19. Bolus disambiguator integration into the production rule (P8 strict follow-on, added 2026-05-29). Shipped 2026-06-05: `thomas_rules()` accepts `bolus_in_second_half`; falling slope suppressed (with warning) when bolus present in 2nd half; `dexcom_fetch.py` loads and filters bolus events; 4 new tests.
  - `dexcom_fetch.py` does not currently consult bolus events when interpreting `sh_slope`. A falling slope produces "basal too high" reasoning even when a mid-night correction bolus was taken; the rule cannot distinguish the two cases without the disambiguator.
  - Approach (E12-pattern): pull bolus events in the overnight window via `dexcom_loader.load_bolus_combined()`, pass them to `thomas_rules` (or a wrapper), and either refuse-to-suggest OR flag ambiguity in the reasoning line when `sh_slope < 0` AND bolus events overlap the second half. Decision on refuse-vs-flag deferred to implementation; lean: flag in reasoning (less invasive than E12's strain refusal because the data IS available, just contextually).
  - Tests: extend `tests/test_rules.py` with cases for bolus-in-window / bolus-out-of-window / no-bolus.
  - Effort ~2-3 hours.

- [x] E20. `tests/test_inferential_predictor.py` (P9 strict follow-on, added 2026-05-29). Resolved 2026-06-05: 11 tests covering spearman_np, multi_residuals, f_test_nested; main() excluded (loads real data).
  - `scripts/inferential_predictor.py` shaped the Phase 6 slope rule via M3 selection (decisions-log 2026-05-29). Per P9 it is a required test file but does not exist yet.
  - Coverage targets: nested-model F-test logic (`fit_ols`-based comparison + `beta_dose` significance gate), signal-ranking output (direct + partial + inferential Spearman, convergence tiering), inferred-optimal-dose computation per night for the selected M-spec.
  - Approach: synthetic nights with hand-computable expected M-spec selection (e.g. linear data favouring M1; interaction-driven data favouring M3); ranking output for known signal combinations.
  - Effort ~half day.

- [x] E18. WAKE_HOUR 7 -> 06:20 (R22 from the 2026-05-28 audit, the last un-shipped redesign item).
  - `scripts/night_stats.py:14` set `WAKE_HOUR = 7`. Thomas's weekday alarm is 06:20; both the slope rule's overnight window and the fasting fallback end at the wake boundary, so moving to 06:20 shifts both signals and can move suggestions.
  - Design question resolved 2026-06-02: fixed 06:20 (see E10 wake-up anchor note).
  - Resolved 2026-06-04: bare int `WAKE_HOUR` promoted to a single `WAKE_TIME = time(6, 20)` value referenced at all 5 derivation sites (consolidation per Thomas's "why scattered" pushback); removed a hardcoded `Fasting (07:00)` literal and fixed a latent month-end overflow in `dexcom_fetch.py`. decisions-log entry 2026-06-04. Added 5 `overnight_window()` boundary tests (test_night_stats 24 -> 29). Tests 82/82 green.

---

## Background

Generated from architecture critique 2026-05-15.

Known gaps (not bugs - by design or upstream limitation):
- Bolus log gap from 2026-01-31 (NovoPen 6 export pending).
- WHOOP `score.strain` only updates on app sync - `today_s1` often `None` at dose time.
- Dexcom historical backfill via Clarity CSV is manual (Share API limited to 24h).

B9/B10/B11 are deferred: low value-for-effort given the current single-user manual-nightly workflow.

---

## Done

- [x] A1. Add "Working preferences" section to CLAUDE.md - model rotation, no preamble, prefer Grep over Agent, no unsolicited suggestions, no trailing summaries.
- [x] A2. Tighten `.claude/settings.local.json` allowlist - replaced wildcard `py *` with four explicit script invocations. Skill found nothing universal to add.
- [x] A3. Default model: Sonnet 4.6. Downshift to Haiku for renames/format/lookup. Opus only for cross-file design or critique. Documented in CLAUDE.md.
- [x] A4. Keep CLAUDE.md under ~100 lines - currently ~60.
- [x] B1. Extract `scripts/dexcom_loader.py` - unifies the 4x duplicate `load_dexcom()`. ml_model's redundant dt-only bolus dedup dropped (set-based dedup sufficient).
- [x] B2. Extract `scripts/rules.py` - single source of truth for `thomas_rules()`. ASCII-only, parameterized thresholds preserved for ML.
- [x] B3. Add `tests/test_rules.py` - 18 unittest cases (fasting tiers + boundaries, hypo priority, activity stacking, clamp bounds, None inputs, threshold parameterization). Run: `py -X utf8 tests/test_rules.py`. stdlib unittest (pytest not installed).
- [x] B4. Persistent dose diary `data/doses.csv` - `scripts/dose_diary.py` module reads/upserts one row per dose-night. `dexcom_fetch` backfills yesterday's outcome, pulls today's WHOOP strain from cache, writes today's row with suggestion + reasoning.
- [x] B5. Anchor priority fixed (post-B4) - Clarity CSV is authoritative. `dexcom_fetch` tries Clarity first, falls through to diary, then prompts (EOFError-guarded) only as last resort. Clarity-derived dose backfills diary's `dose_u` when present.
- [x] B6. Portable paths - derive `DATA_DIR`/`API_DIR`/`PROJECT_ROOT` from `Path(__file__)` in 5 active path users. Deleted 4 dead `BASE`/`DIAGNOSIS` orphan declarations from extraction refactors.
- [x] B7. Replace silent `except: pass` in CSV parsing with skipped-row counter + load-time log. First run surfaces 677 skipped rows (~0.6%), likely Dexcom "Low"/"High" sentinels; root-cause deferred.
- [x] B8. Wrap `dexcom_fetch.py` `input()` in `try/except EOFError` so non-interactive runs don't crash.
- [x] B12. Fix cosmetic bug in `rules_model.py:164-165` - replaced literal `'="*70 + note...'` and `'="'*35` strings with proper note + divider.
- [x] B13. Removed `docs/analyze.py`, `docs/recalibrate.py`, `docs/REFERENCE.md` (superseded). Dropped "Do not use" pointer from CLAUDE.md.
