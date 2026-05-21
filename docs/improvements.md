# T1D Improvement Backlog

Format rules in `claude-setup/CLAUDE.md`. Status: `[ ]` open, `[x]` done, `[-]` blocked.

Read this before proposing new refactors.

---

## B. Code hardening

- [ ] B9. Rename shadowed `TGT_LO` / `TGT_HI` - value 5/8 in `basal_analysis.py` (user goal) vs 4/10 in `rules_model.py` + `dexcom_fetch.py` (clinical TIR). Different intent, same name. (deferred: low value-for-effort)
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

- [ ] E1. Refine strain-based rule - currently coarse (`s1 >= 12.0 -> -2u`, else 0u; two of six possible levels).
  - Wanted: granular `+3, +2, +1, 0, -1, -2`. Define s1 thresholds per level.
  - Clinical direction: low strain -> higher insulin resistance (+adj), high strain -> higher insulin sensitivity (-adj). Confirm with Thomas before encoding.
  - Approach: bin historical nights by s1, look at TIR / fasting outcomes per dose, infer thresholds, encode in `rules.py`, add ~6 unittest cases, document in `decisions-log.md`.
  - Also: handle in-progress-cycle indexing quirk so today's strain is found at dose time (currently indexed under cycle start date, often yesterday).
- [ ] E2. GitHub publish - deferred until project is "share-ready" AND C1 done.
  - Decision 2026-05-21: eventual aim is public, to help other T1D patients/builders. Not a priority now. "Better first" - improve model + automation before going public.
  - Informal quality bar: E1 (strain rule), E10 (nighttime objective validated), at least E5 (Phase 1 automation) done so it's not a single-user manual tool.
  - When ready, three paths:
    1. Private push for backup only - skip C1, repo not discoverable. Cheap if backup is the main goal.
    2. Public, real name in history - C1 + push. Standard for personal-portfolio repos.
    3. Public, fully anonymous - C1 + `git filter-repo` to rewrite all past commit authors. Destructive, only if anonymity matters.
  - Mechanics: `gh` CLI not installed -> create repo via web UI -> `git remote add origin <url>` -> `git push -u origin master`.
- [-] E3. `/dose` slash command - thin orchestration wrapper around `dexcom_fetch.py`. Lives at `.claude/commands/dose.md`. (blocked by: E5)
  - Flow: ask new-pen + unmodeled factors (alcohol / late meal / illness / activity-not-in-WHOOP) -> run script -> if hypos detected, ask sensor-noise -> output terse `Tonight: Nu` + reasoning bullets + off-rules flags.
  - Format per global memory: `feedback_dose_recommendation`, `feedback_dose_unmodeled_factors`.
  - Why blocked: dose.md should consume `--dose N` flag and a non-interactive script. First draft rolled back - hit conflicts because it added interactivity that E5 is removing.
  - After E5, dose.md becomes ~20 lines (pure orchestration, no anchor-prompt handling). History in `decisions-log.md`.
- [ ] E4. `/t1d-status` slash command - quick snapshot.
  - Shows: last Dexcom fetch timestamp, latest Clarity CSV date in `data/`, count of unchecked items in `docs/improvements.md`, days since last dose entry in `data/doses.csv`.
  - Path: `.claude/commands/t1d-status.md`. Effort ~15 min. Not blocked - good warmup task.
- [ ] E5. Phase 1: cron-friendly scripts (~1h) - `--dose N` CLI flag on `dexcom_fetch`, remove remaining `input()` prompts. (blocks: E3, E6)
- [ ] E6. Phase 2: Telegram bot (~3-4h) - `python-telegram-bot` on Hetzner Frankfurt (EU/GDPR) or Raspberry Pi. Commands: `/today`, `/took N`, `/stats`. (blocked by: E5) (blocks: E7)
- [ ] E7. Phase 3: nightly proactive push (~30m) - cron 21:30 -> bot DMs tonight's suggestion. (blocked by: E6)
  - Soft dep: needs fresh Clarity data. Either E8 or manual re-export.
- [ ] E8. Phase 4 (optional): Playwright Clarity CSV export (~2-4h) - gnarly; cached `storage_state`, monthly MFA refresh. Solves the manual-export blocker for true end-to-end.
- [ ] E9. Phase 5 (optional): web dashboard for history graphs.

End goal: phone-triggered nightly suggestion. Hard blocker for true end-to-end: Dexcom Share API has no insulin events; Clarity export is manual. E8 solves it via browser automation OR user accepts periodic manual re-export.

Risks across E5-E9: MFA on Clarity, Dexcom ToS on automated access, UI brittleness, server uptime, Telegram chat-id whitelist.

- [ ] E10. Nighttime objective spec: flat curve, weighted toward wake-up (logged 2026-05-21, not yet scoped to a phase)
  - Goal hierarchy (priority order):
    1. Wake-up glucose in target (5-8 mmol/L).
    2. Minimize abs(wake - bedtime).
    3. Minimize variability across the night (flat curve).
  - Weighting: second half of night > first half. Optimize for stability and on-target landing in the hours before wake, even at the cost of more deviation earlier in the night.
  - Open definitions (resolve with Thomas before encoding):
    - "Bedtime" = injection-time glucose (`vals[0]` in `compute_night_stats`)? Or first CGM reading after sleep-onset?
    - "Wake-up" = current `fasting` (`vals[-1]`)? Or last reading before alarm time?
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
