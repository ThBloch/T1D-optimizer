# Architecture

What the T1D basal optimizer is, how its parts fit together, and where each
signal comes from. For *why* a particular threshold or rule exists, read
`decisions-log.md`. For *open work*, read `improvements.md`. For the
principles that decide where each kind of code/constant/rule lives, see
`code-conventions.md`. This doc does not restate values that live in
code - it points at the file and line.

---

## Purpose

Five invariants. Everything else is implementation detail.

1. **User-initiated only.** A dose suggestion is produced when Thomas asks
   for one (`/dose`, manual script run, or - future - a remote Telegram
   request). The system never silently triggers, never pushes on a
   schedule, never decides on Thomas's behalf.

2. **Strain is non-negotiable.** Every dose suggestion must consider
   today's WHOOP strain. The current production path will silently skip
   the activity branch when `s1 is None`; this is a known invariant
   violation - see `improvements.md` E1b for the remediation plan
   (`NEEDS:`-line protocol).

3. **Outcome metric is the second-half overnight slope.** Down = dose too
   high; up = too low; flat = correct. TIR and fasting are secondary
   diagnostics, not the optimization target. See
   `night_stats.second_half_trend()`.

4. **Bolus history is required for slope disambiguation.** A falling
   second-half slope can be "basal too high" *or* "I corrected with a
   bolus mid-night". Without bolus events the rule cannot tell. NovoPen 6
   bolus reaches the dataset via Glooko (`novopen_loader.py`); manual G7
   bolus reaches it via Clarity. Both streams are merged in
   `dexcom_loader.load_bolus_combined()`.

5. **The production path is named.** Production = `dexcom_fetch.py` ->
   `rules.thomas_rules()` -> `dose_diary.upsert_row()`. Every other
   script under `scripts/` is research and may not emit a tonight's
   suggestion.

---

## Doc map

Where to read which kind of content. The split is enforced by writing
discipline; do not duplicate across files.

| File | Scope |
|---|---|
| `docs/architecture.md` (this file) | WHAT the components are and HOW they connect |
| `docs/code-conventions.md` | P1-P12: where each kind of code, constant, rule, or test lives |
| `docs/decisions-log.md` | WHY a decision was made. Immutable history; new decisions append. |
| `docs/improvements.md` | Backlog of open work. Status `[ ]` / `[x]` / `[-]`. |
| `docs/session-log.md` | Per-session log of changes, decisions, blockers, next steps |
| `docs/progress.md` | Milestone summary: Done / Next session / Open questions |
| `CLAUDE.md` | Quick reference for running the scripts; project conventions |
| Memory at `~/.claude/projects/D--claude-t1d/memory/` | Cross-session patterns (user, feedback, project, reference) |

If a number lives in code, it appears in code only. This doc names the
file and line.

---

## Components

### Production path

| Script | Role |
|---|---|
| `scripts/dexcom_fetch.py` | Live fetch + dose suggestion. The only script that prints "tonight's suggestion". |
| `scripts/rules.py` | `thomas_rules()` pure function. Single source of truth for the dosing rule. |
| `scripts/dose_diary.py` | `data/doses.csv` read + upsert. One row per dose-night. |

### Research scripts (read-only on production state)

| Script | Output |
|---|---|
| `scripts/basal_analysis.py` | Weekly pattern, comparable-night matching, regression appendix |
| `scripts/rules_model.py` | Rules backtest, agreement breakdown, decision-tree comparison |
| `scripts/inferential_predictor.py` | Best model spec, per-night inferred optimal dose, signal ranking |
| `scripts/predictor_test.py` | Direct outcome correlations |
| `scripts/ml_model.py` | sklearn TIR predictor (currently underperforms rules) |
| `scripts/bolus_noise_test.py` | Bolus-vs-outcome correlation |
| `scripts/strain_binning_analysis.py` | Strain-bin descriptive (Phase A) |
| `scripts/strain_regression_analysis.py` | Strain regression (Phase A2) |

### Shared modules

| Module | Provides |
|---|---|
| `scripts/night_stats.py` | `overnight_window()`, `night_stats()`, `second_half_trend()` + all overnight constants |
| `scripts/stats_utils.py` | `spearman()`, `linreg()`, `residuals()` |
| `scripts/config.py` | `DIAGNOSIS_START` |
| `scripts/dexcom_loader.py` | Clarity CSV parser - `load_dexcom()`, `load_bolus_events()`, `load_bolus_combined()` |
| `scripts/novopen_loader.py` | Glooko CSV parser with prime detection - `load_glooko_bolus()` |
| `scripts/whoop_loader.py` | WHOOP JSON cache reader - `load_whoop()` |

### Fetch / refresh scripts (entry points)

| Script | Role |
|---|---|
| `scripts/whoop_api_fetch.py` | Incremental WHOOP cache refresh via `whoop-sdk` (4 endpoints, 7-day overlap cursor) |

### External

| Service | Library | Auth |
|---|---|---|
| Dexcom Share API | `pydexcom` | `dexcom_creds.json` (plaintext, gitignored) |
| WHOOP Developer API | `whoop-sdk` | OAuth tokens at `~/.whoop_sdk/config.json` |
| Dexcom Clarity export | manual download | clarity.dexcom.com -> `data/Clarity_*.csv` |
| Glooko export | manual download | glooko.com -> `data/glooko/Insulin data/insulin_data_1.csv` |

---

## Data sources

| Source | Loader | Fields | Cadence | Notes |
|---|---|---|---|---|
| Dexcom Share API | `dexcom_fetch.fetch_readings()` | Glucose only, last 24h | Per `/dose` run | No insulin events. Live readings used for "current" glucose snapshot. |
| Dexcom Clarity CSV | `dexcom_loader.load_dexcom()` | Glucose, basal (Lang), manual G7-app bolus (Hurtig) | Manual export, weekly-ish | Semicolon-delimited, Danish locale, mmol/L with comma decimals. Skipped-row count logged at load. |
| Glooko CSV | `novopen_loader.load_glooko_bolus()` | NovoPen 6 smart-pen bolus events | Manual export | Prime detection applied: `<=PRIME_MAX_U` units AND another pen event within `+/- PRIME_WINDOW` = prime, dropped. |
| WHOOP cache | `whoop_loader.load_whoop()` | strain, recovery, hrv, rhr, sleep_perf, keyed by local date | Read per script run | In-progress cycle indexed under start date - returns `None` for `today` at evening dose time (E1b). |
| WHOOP API | `whoop_api_fetch.py` | Same fields as cache | Refresh via `--full` or incremental | 7-day overlap cursor, 429 backoff, dedup-merge by id/cycle_id. |
| Dose diary | `dose_diary.load_diary()` | date, dose_u, fasting, hypo_events, tir_pct, sh_slope, strain_s1, suggested_u, reasoning | Read+upsert per dose run | One row per dose-night. Append-only history; rows amended only to fill unknown fields. |

### Anchor priority for "yesterday's dose"

`dexcom_fetch.py` resolves the anchor in strict order:

1. Clarity CSV (authoritative when present).
2. Dose diary `dose_u` field.
3. `--dose N` flag.
4. Interactive `input()` prompt (last resort; guarded by `EOFError` so
   non-interactive runs do not crash).

### Bolus merger

`dexcom_loader.load_bolus_combined()` concatenates Clarity Hurtig rows
(manual G7-app entries from regular-pen days) and Glooko ACS\*-source rows
(NovoPen 6 NFC syncs). The two streams are disjoint by construction -
manual entries never reach Glooko's pen-source rows; smart-pen events
never reach Clarity's raw CSV. No cutover date; no dedup needed.

---

## Signal flow

### Production path (one `/dose` run)

```
Dexcom Share API  --[fetch_readings]-->  last 24h glucose
                                            |
                                            v
              [overnight_window(inj_dt)]----+----[night_stats()]----> fasting,
                                            |                         hypo_events,
                                            +----[second_half_trend()]> sh_slope, ...
                                                                        |
Clarity / diary / --dose flag  ---->  yesterday_dose                    |
WHOOP cache  ------------------------>  today_s1                         |
flags (--new-pen, --no-hypo)  ------>  modifiers                        |
                                            \                           /
                                             +----[thomas_rules()]------+
                                                       |
                                                       v
                                          (suggested_u, reasoning)
                                                       |
                                                       v
                                          dose_diary.upsert_row()
                                                       |
                                                       v
                                          data/doses.csv
```

### Per-night pipeline (historical analysis)

For every basal injection in Clarity (evening hour filter):

1. `overnight_window(inj_dt, glucose_list)` -> readings from injection
   through `WAKE_HOUR:00` next day.
2. `night_stats(readings)` -> `{n_readings, fasting, mean, min_g, max_g,
   inj_g, tir, tir_full, hypo_pct, hyper_pct, hyper_adj, hypo_events,
   hypo_correction, correction_spike_above_10}`.
3. `second_half_trend(readings)` -> `(sh_slope, sh_delta, sh_n)`.
4. WHOOP fields joined by `inj_date`: `strain`, `recovery`, `hrv`,
   `rhr`, `sleep_perf`.
5. Bolus events joined via `load_bolus_combined()` when the analysis
   needs sub-day timing (e.g. `inferential_predictor.py`'s `bolus_4h_pre`
   and `bolus_during_night` features).

Field names returned by `night_stats()` are stable across all consumers -
do not redefine locally.

---

## Outcome metric

Per-night quality is measured by the second-half overnight slope
(`night_stats.second_half_trend()`), computed as a linear regression of
glucose vs hours over the last `SECOND_HALF_FRACTION` of the overnight
window. Direction encodes dose error:

- `sh_slope < 0` -> overnight glucose fell -> dose too high
- `sh_slope > 0` -> overnight glucose rose -> dose too low
- `sh_slope ~ 0` -> flat -> correct

Two TIR fields are retained in `night_stats()` as secondary
diagnostics: `tir` uses the user-target band (`TARGET_LO/HI`), `tir_full`
uses the clinical band (`CLINICAL_TIR_LO/HI`). The headline ranking
inside `inferential_predictor.py` and the slope-tier branch in
`thomas_rules()` both use `sh_slope` directly.

---

## Rules

All thresholds and clamps live in code. This section describes the
*structure* only; read the values at the source.

- `scripts/rules.py:7-19` - rule constants (slope tiers, fasting tiers,
  activity threshold, dose clamp).
- `scripts/night_stats.py:13-25` - overnight-window constants and
  per-night stat thresholds (hypo, hypo-correction, TIR ranges,
  second-half fraction, minimum reading counts).

### `thomas_rules()` priority order

Implemented in `scripts/rules.py` as a pure function. Branch precedence:

1. **Hypo override.** If overnight `hypo_events >= 1`, glucose-tier
   branches are skipped. One hypo -> small reduction; two or more ->
   larger reduction.
2. **Slope tier.** If `sh_slope is not None`, compare against the
   `SLOPE_*` constants. Positive slopes adjust upward through three
   tiers; negative slopes adjust downward through two tiers (asymmetric
   magnitudes - see `decisions-log.md` 2026-05-29).
3. **Fasting fallback.** Only when `sh_slope is None` (insufficient CGM
   data for the second half), fall back to wake-time fasting tiers.
   Reasoning lines are tagged `(fallback)`.

### Stacked modifiers

- **Activity.** When `s1 >= ACTIVITY_THR`, apply a fixed reduction. Coarse
  by design; the 6-tier replacement is gated on the Phase 5 R8 ranking
  re-run (see `improvements.md` E1).
- **New pen.** When `--new-pen` is set, apply a fixed reduction.

### Clamp

Final result clamped to `[DOSE_MIN, DOSE_MAX]`. A clamp event appends a
reasoning line so the user can see when the rule wanted to step beyond
the safe band.

### Tests

`tests/test_rules.py` covers every branch and boundary (38 cases):
hypo override, fasting tiers and boundary equality, activity stacking,
clamp, slope tiers in both directions, slope-vs-fasting precedence,
slope-vs-hypo precedence, custom-threshold parameterization. Run:
`py -X utf8 tests/test_rules.py`.

---

## Inferential predictor

`scripts/inferential_predictor.py` is the analytical input to the rule
design. It:

1. **Selects a model spec.** Fits four nested models (M1 dose-only, M2
   +s1, M3 dose x s1 interaction, M4 +bolus) of `sh_slope ~ ...`. Picks
   the best via F-test plus the requirement that `beta_dose` is
   significant (otherwise the model cannot be inverted to "what dose
   would have flattened the slope").
2. **Inverts.** For every historical night, solves for the dose that
   would have produced `sh_slope = 0` under the chosen spec.
3. **Ranks signals.** For each candidate (`s1`, `recovery`, `hrv`,
   `rhr`, `inj_g`, `bolus_4h_pre`, `bolus_during_night`, sleep, prev
   metrics) computes three Spearman metrics: direct vs `sh_slope`,
   partial controlling for `s1` + `prev_dose` + `inj_g`, and
   inferential vs M3 optimal dose. Convergence-based tiering: HIGH (>=2
   of 3 significant, same direction), MED (1 of 3), LOW (0 of 3).

Output: stdout + `output/inferential_predictor.txt`.

The slope-tier thresholds in `rules.py` are *not* derived from this
model directly - they were anchored on the empirical slope distribution
(quartiles) because model inversion is still noisy at the current `n`.
Richer rule encoding (bolus modifiers, inj_g floor for extreme highs)
is future work pending higher data volume; see `improvements.md`.

---

## Tests + hookify

| File | Purpose |
|---|---|
| `tests/test_rules.py` | 38 unittest cases for `thomas_rules()` |
| `.claude/hookify.run-tests-reminder.local.md` | Nudges at session end if `scripts/*.py` was edited but `test_rules.py` was not run |
| `.claude/hookify.decisions-log-reminder.local.md` | Nudges at session end if `scripts/*.py` was edited |
| `.claude/hookify.creds-commit-guard.local.md` | Blocks `git add`/`commit` commands referencing `creds`, `credential`, `secret`, `.env` |

Both reminder rules use `event: stop` + `field: transcript` +
`regex_match` against `scripts.*\.py`. They fire once per session at
the stop event.

---

## Limits and known gaps

- **WHOOP in-progress cycle.** The cycle covering "today" is indexed by
  its start date and lacks `score.strain` until the cycle closes (i.e.
  after Thomas's next sleep), so `load_whoop().get(today)` returns
  `None` at evening dose time. The strain-non-negotiable invariant is
  therefore not yet enforced in code - `dexcom_fetch.py` falls through
  to `thomas_rules(s1=None)`, which silently no-ops the activity
  branch. Remediation tracked at `improvements.md` E1b: emit
  `NEEDS: strain` on stdout, let `/dose` ask Thomas directly. Live-fetch
  of the in-progress cycle via `whoop-sdk` is an exploration sub-task.

- **Glooko export is manual.** No public Glooko API exposes NovoPen
  bolus today; weekly browser exports populate `data/glooko/`. Playwright
  automation is tracked as `improvements.md` E8.

- **Dexcom Share API has no insulin events.** Clarity CSV is the only
  source for historical basal + manual G7 bolus from G7-app days. The
  Share API is glucose-only and only spans 24h.

- **Bolus streams are source-segregated.** Manual G7-app bolus appears
  only in Clarity; smart-pen NovoPen 6 bolus appears only in Glooko.
  This is enforced by Dexcom and Glooko's respective ingest paths -
  there is no cutover date, but no source-overlap either.

- **Decision-tree underperforms rules.** `ml_model.py` and the
  `rules_model.py` DT comparison both produce higher MAE than
  `thomas_rules()`. `prev_dose` dominates feature importance (Thomas's
  own day-to-day persistence). Slope-based rule + bolus integration is
  the path to making a learned model viable.

- **Clamp band is informed, not data-derived.** `DOSE_MIN`/`DOSE_MAX` in
  `rules.py` reflect Thomas's working range; future titration outside
  that band requires explicit decisions-log entry + clamp update.
