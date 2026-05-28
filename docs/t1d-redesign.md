# T1D Redesign - audit and proposal

Audit done 2026-05-28 by Claude (Sonnet 4.6). No code changed; this document is the deliverable.

Scope per Thomas's brief:
1. Find inconsistencies across the whole solution.
2. Assess whether the overarching design is good and whether parts play well together.
3. Assess modularity vs cascade risk.
4. Describe each component and how it connects to the others.
5. Map data sources (Dexcom, basal, bolus, WHOOP) and where each is used.
6. Map rules and where they apply.
7. Propose principles to keep the solution from drifting.
8. List concrete to-do items in a format extractable into `docs/improvements.md` (prefixed `R1`, `R2`, ... for "redesign").

---

## 1. Executive summary

The codebase has good bones (clean `rules.py`, dedicated `dexcom_loader.py`, `whoop_loader.py`, `dose_diary.py`) but suffers from significant duplication in the analysis layer. The same logic - overnight statistics, hypo-correction detection, Spearman / linear regression, basic data loading - is reimplemented in five to seven places. A single small change (e.g. "raise the hypo-correction threshold from 7 to 10") touches five files instead of one. This is the cascade pattern Thomas wants to avoid.

The production path (the one `/dose` exercises) is `dexcom_fetch.py -> rules.py -> dose_diary.py`. The other modeling scripts (`basal_analysis.py`, `rules_model.py`, `ml_model.py`, `predictor_test.py`, `bolus_noise_test.py`, `strain_binning_analysis.py`, `strain_regression_analysis.py`) are research / backtest tools that share many concepts but each carries its own copies. Documentation (`docs/architecture.md`) is partially stale because rule thresholds and exclusion rules are documented there in addition to being implemented in `rules.py` / `basal_analysis.py`; the two drift.

The biggest immediate risk is that today's decisions (hypo-correction threshold 7 -> 10; remove bolus IQR exclusion; fasting +1u threshold 10.5 -> 10; slope-based fasting rule) will land in some files but not others. A consolidation pass (see Section 7) is the right pre-work before applying any of those code changes.

---

## 2. Component map - what the system is made of

### 2.1 Data ingestion layer

| Component | File | Purpose | External dep |
|---|---|---|---|
| Dexcom historical (CSV) | `scripts/dexcom_loader.py` | Read `data/Clarity_*.csv` exports (semicolon, Danish locale). Returns glucose + basal + bolus(only manually logged - no Novopen doses). | Manual Clarity export. |
| Dexcom live (Share API) | `scripts/dexcom_fetch.py:44-50` | Pull last 24h of glucose from Dexcom Share via `pydexcom`. No insulin events. | `dexcom_creds.json` (gitignored). |
| WHOOP API fetch | `scripts/whoop_api_fetch.py` | Incremental fetch from WHOOP Developer API via `whoop-sdk`. 4 endpoints: cycles, recovery, sleep, workouts. Cursor-based with 7-day overlap. | `~/.whoop_sdk/` OAuth config. |
| WHOOP loader | `scripts/whoop_loader.py` | Read `data/whoop_api/*.json`, join cycles + recovery + sleep on `cycle_id`, return dict keyed by local date. | None (reads cache). |
| Dose diary | `scripts/dose_diary.py` | Read / upsert / save `data/doses.csv` (one row per dose-night). | None. |

***Manual addition by Thomas*** The stress level should be added to whoop extract - this seems to be a major factor when high.

### 2.2 Rule and modeling layer

| Component | File | Role | Used by `/dose`? |
|---|---|---|---|
| `thomas_rules()` | `scripts/rules.py` | Single source of truth for the production decision rule. Pure function, no I/O. | YES (via `dexcom_fetch.py`). |
| Live fetch + diary anchor + rule call | `scripts/dexcom_fetch.py` | Production path. Fetches live CGM, looks up anchor dose (Clarity -> diary -> flag/prompt), looks up today's strain, calls `thomas_rules()`, writes diary. | YES. |
| Rules backtest | `scripts/rules_model.py` | Replays `thomas_rules()` over the full history; computes MAE vs actual; trains a Decision Tree as a comparison baseline. Includes its own "tonight's suggestion" block. | NO (research). |
| Matching model | `scripts/basal_analysis.py` | Finds historical nights similar to tonight on `(inj_g, s1)`; reports outcome distribution by dose. Also prints a weekly pattern. | NO (research). |
| ML model | `scripts/ml_model.py` | sklearn pipeline (Ridge, RF, GBM); predicts overnight TIR% per candidate dose; recommends the dose maximising predicted TIR. | NO (research). |

### 2.3 One-off analysis scripts (research / validation)

| Script | Purpose |
|---|---|
| `scripts/predictor_test.py` | Spearman + Mann-Whitney significance test for every candidate predictor (inj_g, s1, s7, bolus, hrv, recovery, rhr, dose) against outcomes (TIR, fasting, mean). |
| `scripts/bolus_noise_test.py` | Does bolus add signal beyond inj_g? Partial correlation analysis. Answer (per `decisions-log.md` 2026-04-15): no, fully mediated by inj_g. |
| `scripts/strain_binning_analysis.py` | Phase A of E1: bin nights by strain, report per-bin second-half slope, suggest threshold candidates. |
| `scripts/strain_regression_analysis.py` | Phase A2 of E1: OLS regression of slope on (dose, strain, prev_fasting, prev_hypos); derives dose_optimal(s1) curve and proposed cut points. |

### 2.4 Tests

| Test | What it gates |
|---|---|
| `tests/test_rules.py` | 21 unittest cases for `thomas_rules()`. The only test gate in the project. |

### 2.5 Commands (slash commands for Claude Code)

| Command | File | Calls |
|---|---|---|
| `/dose` | `.claude/commands/dose.md` | `dexcom_fetch.py` (with `--dose N`, optional `--new-pen`, `--no-hypo`). |
| `/t1d-status` | `.claude/commands/t1d-status.md` | Inline Python; no script calls. Prints 4-line snapshot from filesystem state. |

### 2.6 Documentation

| File | Purpose |
|---|---|
| `CLAUDE.md` (project) | Quick reference + working preferences + session protocol. |
| `docs/architecture.md` | Model approach + validated predictors + exclusion rules + titration rules + data pipeline. |
| `docs/decisions-log.md` | Durable record of major decisions with rationale. Protocol: never edit content, only `Status`. |
| `docs/improvements.md` | Backlog of `[ ]` open / `[x]` done / `[-]` blocked items. |
| `docs/session-log.md` | Per-session changes / decisions / blockers / next steps. |
| `docs/t1d-redesign.md` | This file. |

---

## 3. Data sources - how each is fetched and where it is used

### 3.1 Dexcom glucose (CGM)

Two fetch paths:

| Path | What | When |
|---|---|---|
| Live Share API | Last 24h, glucose only | Every `/dose` run (`dexcom_fetch.py:44-50`). |
| Clarity CSV export | Full history, glucose + basal + bolus | Manual export from clarity.dexcom.com to `data/Clarity_*.csv` whenever Thomas re-exports. Loaded by `dexcom_loader.py`. |

Where the CGM data is used:
- Production: `dexcom_fetch.py` computes the overnight window (22:00 last night to 07:00 this morning), summarises fasting + hypo events + TIR (4-10) + mean + min.
- Backtest: all research scripts iterate `basal_list` from `dexcom_loader.py`, pair each evening injection with the next-morning window.
- The "tonight's injection-time glucose" reading (`inj_g`) is the strongest predictor of next-morning TIR (r=-0.376, p<0.001 per `decisions-log.md` 2026-04-15). Currently used as the primary match variable in the matching model and as a feature in the ML model.

### 3.2 Basal insulin

| Source | How |
|---|---|
| Clarity CSV | Rows where `etype='Insulin' AND esub` contains 'Lang' (long-acting). Aggregated by day in `dexcom_loader.py:71-77`. |
| Dose diary | `data/doses.csv` `dose_u` column. Backfilled from Clarity when present; otherwise filled by `/dose --dose N` or interactive prompt. |
| Live anchor priority | In `dexcom_fetch.py:136-174`: (1) Clarity, (2) diary, (3) --dose N flag, (4) interactive prompt. |

Used by: the `yesterday_dose` argument to `thomas_rules()`. All backtest scripts also read it for anchor + outcome pairing.

### 3.3 Bolus insulin

| Source | How |
|---|---|
| Clarity CSV | Rows where `etype='Insulin' AND esub` contains 'Hurtig' (fast-acting). Aggregated by day in `dexcom_loader.py:79-81`. |
| NovoPen 6 (since 2026-01-31) | NOT YET INTEGRATED. The pen logs digitally but the data has not been pulled into the project. |

Reliability (Thomas, 2026-05-28): pre-2026-01-31 Clarity bolus is trustworthy - Thomas manually logged each dose. Post-2026-01-31 (NovoPen 6 era) there is no Clarity bolus at all. The historical signal in `bolus_noise_test.py` and the decisions-log conclusions can be relied on for the pre-NovoPen window.

Status of bolus across the codebase:
- `decisions-log.md` 2026-04-15: bolus dropped as a model feature (partial correlation ~0; fully mediated by inj_g).
- `basal_analysis.py:123-133` and `:189-205`: bolus IQR outlier exclusion. **To be removed per today's decision.**
- `bolus_noise_test.py`: research script that validated the "drop bolus" decision.
- New slope-based fasting rule (decided today): **requires bolus data** to disambiguate "basal too low" from "I corrected mid-night". This elevates NovoPen 6 integration from "known gap" to a hard dependency.

Bolus is in a confused state. The codebase says "we don't use it" while one script uses it as an exclusion gate, while a planned future rule requires it.

### 3.4 WHOOP

Fetched by `whoop_api_fetch.py`; cached as JSON. Loaded by `whoop_loader.py`. Fields available per cycle date:

| Field | Loaded? | Used by any rule or model? |
|---|---|---|
| `strain` (s1) | Yes | Yes - `rules.py` activity threshold + matching model + ML model + all analysis scripts. |
| `recovery` | Yes | No. Loaded into the nightly dict in `basal_analysis.py:168` but never read by any rule. Displayed in `basal_analysis.py:451` only. |
| `hrv` | Yes | No. Same pattern as recovery. |
| `rhr` | Yes | No. Same. |
| `sleep_perf` | Yes | No. Same. |
| `stress` | NOT YET FETCHED | Pending (Thomas, 2026-05-28): check whether `whoop-sdk` exposes the WHOOP Stress Monitor endpoint (added by WHOOP in 2024). If yes, fetch it. If absent or hard to integrate, use `hrv` as the derived stress proxy (low HRV = high autonomic stress). See R21. |

`s7` (7-day rolling strain) is computed by `rolling_avg()` in `basal_analysis.py:21-25` and `ml_model.py:34-37`. Decisions-log 2026-04-15 dropped it as a match variable (r=0.078, p=0.19). But the function still gets called every run.

The WHOOP in-progress-cycle date issue (the entire E1b problem): `whoop_loader.py:18-23` indexes the in-progress cycle under its start date. By evening of the same day, that cycle is "yesterday" in the index. `whoop.get(today)` returns None at dose time.

### 3.5 Dose diary

`data/doses.csv` - one row per dose-night. Columns: `date, dose_u, fasting, hypo_events, tir_pct, strain_s1, suggested_u, reasoning`.

Lifecycle of a row:
1. Tonight: `dexcom_fetch.py` writes today's row with `strain_s1`, `suggested_u`, `reasoning`. `dose_u` filled from --dose flag or prompt.
2. Tomorrow morning: `dexcom_fetch.py` next run backfills `fasting`, `hypo_events`, `tir_pct` for the previous night. Also backfills `dose_u` from Clarity if a fresh CSV is present.

Used by: `dexcom_fetch.py` as the anchor source (Priority 2 after Clarity). NOT used by any backtest script - all backtest scripts go through `dexcom_loader.py` (Clarity-only).

This is a coverage gap: nights after 2026-01-31 (NovoPen switch, no Clarity bolus) are in the diary but invisible to the backtest scripts unless the user has also re-exported Clarity. Backtest pipelines do not see recent nights.

---

## 4. Rules and where they apply

The actual decision rule lives in one place: `scripts/rules.py:thomas_rules()`. Pure function. No I/O.

Inputs: `yesterday_dose, fasting, hypo_events, s1, new_pen, [threshold overrides]`.
Outputs: `(dose, reasoning_lines)`.

Thresholds (`rules.py:7-13`):
- `FASTING_LO = 10.5` (planned change: 10.0)
- `FASTING_MID = 12.0`
- `FASTING_HI = 14.0`
- `ACTIVITY_THR = 12.0`
- `DOSE_MIN = 15`
- `DOSE_MAX = 29`

Rule branches:
1. **Anchor** (line 25-26): if `yesterday_dose is None`, return None.
2. **Hypo priority** (line 33-50): if `hypo_events >= 2 -> -2u`; if `== 1 -> -1u`; else evaluate fasting tier.
3. **Fasting tier** (line 39-50): `>14 -> +3u`; `>12 -> +2u`; `>10.5 -> +1u`; else 0. **Planned shift to slope-based.**
4. **Activity** (line 52-54): `s1 >= 12 -> -2u`. Single threshold, no gradient. Planned replacement: E1 6-tier scale.
5. **New pen** (line 56-58): `new_pen=True -> -1u`.
6. **Clamp** (line 61): `max(DOSE_MIN, min(DOSE_MAX, round(raw)))`.

Where these rules show up beyond `rules.py`:
- `tests/test_rules.py` exercises all branches.
- `docs/architecture.md:24-30` documents them (out of date - 10.5 in code, "~11" in doc).
- `docs/decisions-log.md` records WHY each branch exists (new-pen 2026-05-15; hypo override flag 2026-05-15).
- `scripts/rules_model.py` calls `thomas_rules()` per night for backtest.
- `scripts/dexcom_fetch.py` calls `thomas_rules()` for production.

Outside `thomas_rules()`, exclusion rules apply only to the matching model and the analysis scripts:
- Hypo-correction exclusion: implemented in five files (see Section 5).
- High-bolus IQR exclusion: only in `basal_analysis.py`; to be removed.

---

## 5. Inconsistencies found

### 5.1 Cascade: hypo-correction logic duplicated five times

Same logic in `basal_analysis.py:43-51`, `ml_model.py:44-45`, `rules_model.py:48`, `bolus_noise_test.py:70-71`, `strain_binning_analysis.py:57-58`. Each uses `HYPO_THR = 4.0` and `> 7.0` (the threshold Thomas wants to change to 10.0).

Today's decision (7 -> 10) touches five files. If the logic lived in one place, it would touch one.

`strain_regression_analysis.py` imports `build_nights` and `apply_filters` from `strain_binning_analysis.py` - reuses the logic correctly. The other scripts each carry their own copy.

### 5.2 Cascade: `overnight_stats` duplicated seven times

`basal_analysis.py:33-76` (compute_night_stats - most detailed), `rules_model.py:25-49`, `ml_model.py:39-52`, `dexcom_fetch.py:53-82` (tz-aware variant), `bolus_noise_test.py:64-79`, `predictor_test.py:21-37`, `strain_binning_analysis.py:38-67`.

Each variant has subtly different field sets (some include `inj_g`, some don't; some include `hypo_events`, some only `hypo_pct`). A change to "what an overnight window summarises" cascades through all seven.

### 5.3 Cascade: stats helpers duplicated

Three copies of `spearman`: `basal_analysis.py:78`, `predictor_test.py:67`, `bolus_noise_test.py:117`. Three copies of `linreg`: same files. Each uses slightly different formulas (Spearman uses the logistic approximation for the p-value in all three but the normalisation differs).

### 5.4 `bolus_noise_test.py` has its own `load_dexcom`

`bolus_noise_test.py:19-62` does not import `dexcom_loader.py`; it has its own. The two diverge in their bolus deduplication and return-tuple shape (4-tuple vs 3-tuple). This is the original ancestor pattern from before `dexcom_loader.py` was extracted.

### 5.5 Constants scattered with conflicting values

`HYPO_THR = 4.0` is redeclared in seven files.

`TGT_LO / TGT_HI`:
- `4.0 / 10.0` in `dexcom_fetch.py`, `rules_model.py`, `predictor_test.py`, `strain_binning_analysis.py`.
- `5.0 / 8.0` in `basal_analysis.py`, `ml_model.py`, `bolus_noise_test.py`.

These are the same constant name with different meanings: 4-10 is the clinical TIR band; 5-8 is Thomas's preferred narrow band. Documented in `improvements.md` B9 as a known issue, currently deferred. The shadowing means anyone changing `TGT_*` has to know which file means which.

`DIAGNOSIS` / `DIAGNOSIS_START = 2025-04-09` declared in three places: `dexcom_loader.py`, `whoop_api_fetch.py`, `bolus_noise_test.py`.

Overnight window hours `(22, 7)` declared in every overnight_stats variant.
***Manual addition by Thomas*** The overnight window should be (22-6.20)


### 5.6 Rule documentation scattered

Rules are described in:
- `rules.py` (authoritative).
- `docs/architecture.md` Section 4 (descriptive, currently stale - "Fasting ~11 -> +1u" while code says 10.5).
- `docs/decisions-log.md` (rationale, per-decision).
- `docs/improvements.md` E1c (planned audit task).
- `docs/session-log.md` (in-flight discussion).
- `CLAUDE.md` (header summary).
- Memory `feedback-rule-parameter-ownership` (meta-rule).

The architecture doc and decisions-log can drift from the code because they re-state thresholds rather than pointing at them. Source-of-truth ambiguity.

### 5.7 Bolus is in a confused state

- Decisions-log says bolus is not a model feature.
- `bolus_noise_test.py` is the validation for that.
- `basal_analysis.py` uses bolus IQR as an exclusion criterion - inconsistent with "we don't use it".
- The planned slope-based fasting rule requires bolus.
- NovoPen 6 data (since 2026-01-31) is not in the project at all.

Three different framings of bolus's role co-exist.

### 5.8 Architecture section 2 ("Validated predictors") frames variables as match variables

`architecture.md:13-17` labels `inj_g` and `s1` as "Primary / Secondary match variable". This is matching-model framing, but matching is now planned to be tertiary (today's section-1 decision). The labels should describe what the variable IS (a validated predictor), not how one of the three models uses it.

### 5.9 WHOOP fields loaded but never tested against the right outcome

`whoop_loader.py:43-50` returns `strain, recovery, hrv, rhr, sleep_perf`. Only `strain` (and the dropped `s7` rolling average) is used by any rule or model.

The other four fields HAVE been tested. `predictor_test.py:134-138` runs Spearman + Mann-Whitney for hrv, recovery, rhr against TIR / fasting / mean. Two reasons it looks otherwise:
- The architecture doc's "Validated predictors" table only lists the four winners (inj_g, s1, s7, bolus_4h). The losers are invisible there, so it appears the WHOOP biometrics were never tested.
- They were tested against the WRONG outcome. The slope-based outcome metric was only decided 2026-05-27, after the predictor analysis had already been run. And the inferential framing ("what dose would have produced a flat second-half slope, given the night's signals?", Thomas 2026-05-28) has never been tested at all.

Correction (Thomas, 2026-05-28): the right action is not "drop dead weight". It is to re-run the analysis with the right outcome and the inferential framing. See R8 (rewritten).

***Manual addition by Thomas*** I would have expected this data to have been used, when looking for which parameters affected my basal insulin need, to see if there is a causation.

### 5.10 Top-level imperative scripts

`ml_model.py`, `rules_model.py`, `bolus_noise_test.py`, `predictor_test.py` all run on import (top-level code, no `def run() / if __name__ == '__main__':`).

`basal_analysis.py` and `dexcom_fetch.py` follow the function-and-main pattern.

Mixed style. The imperative scripts cannot be imported without triggering the whole pipeline, which complicates reuse.

### 5.11 Slope computation lives only in an analysis script

`strain_binning_analysis.py:70-88` defines `second_half_trend()`. Today's decision to make the fasting rule slope-based means this logic needs to move into the production path (`rules.py` or a shared module). Right now it exists only in a one-off analysis script.

### 5.12 Diary schema does not match the planned signal

`data/doses.csv` columns: `date, dose_u, fasting, hypo_events, tir_pct, strain_s1, suggested_u, reasoning`. No slope field. If the production rule shifts to slope-based, the diary needs to record the overnight slope per night for future backtesting.

### 5.13 Three "tonight's suggestion" outputs

`basal_analysis.py` Block 1 (matching-based), `rules_model.py` final block (rules-based), `dexcom_fetch.py` (rules-based, live CGM). All three can be run manually. They use different anchor priorities and could give different numbers. There is no single "what was tonight's suggestion?" surface.

### 5.14 CLAUDE.md Quick Start exposes all three as if equal

Lists `basal_analysis.py` first as "main analysis + tonight's suggestion", which implies it is the production tool. But `/dose` calls `dexcom_fetch.py`. The label has been wrong since the rules-primary framing was established.

### 5.15 The E1b problem - WHOOP in-progress cycle invisible

`whoop_loader.py:18-23` indexes the in-progress cycle under its start date; `whoop.get(today)` returns None at evening dose-suggestion time; `dexcom_fetch.py` then silently skips the strain branch in `thomas_rules()`. Already extensively documented in `improvements.md` E1b and today's session-log entry.

### 5.16 Two CGM fetch paths with implicit handoff

Live Share API (24h, glucose-only) and Clarity CSV (full history, insulin + glucose) co-exist. The handoff is implicit:
- Live is used for the "current glucose" reading inside `dexcom_fetch.py`.
- Clarity is used for "yesterday's dose" via the anchor priority chain.
The dependency is not documented anywhere obvious; it lives inside the priority chain in `dexcom_fetch.py:136-174`.

### 5.17 Docs overlap in concern

- Architecture.md describes rules (will go stale unless it points at rules.py instead of restating thresholds).
- E10 in improvements.md reads like architecture (it specifies the nighttime objective metric, which is design, not work).
- New `/dose` design lands in session-log first, then improvements.md, then eventually code.

No clear policy for what goes where.

---

## 6. Modularity assessment - cascade risk per planned change

For each pending or planned change (from `docs/improvements.md` and today's session-log decisions), how many files have to be touched?

| Change | Files touched today | Files if consolidated |
|---|---|---|
| Hypo-correction threshold 7 -> 10 | 5 scripts + architecture.md + decisions-log | 1 shared module + 1 doc |
| Bolus IQR exclusion removal | basal_analysis.py (3 sections) + architecture.md + decisions-log | Same (only one script uses it; consolidation does not help here) |
| Fasting +1u threshold 10.5 -> 10 | rules.py + test_rules.py + architecture.md + decisions-log | Same (rules already centralised) |
| Fasting tier -> slope-based | rules.py + new slope util + dexcom_fetch.py + test_rules.py + diary schema + bolus integration + architecture.md + decisions-log + improvements.md | Same (this is a real structural change, not consolidation-soluble) |
| E1 6-tier strain | rules.py + test_rules.py + architecture.md + decisions-log | Same (rules already centralised) |
| E1b NEEDS: protocol | dexcom_fetch.py + dose.md + new docs/dose-manual-prompts.md (or inline) | Same |
| `TGT_LO / TGT_HI` rename (B9) | 7 scripts + architecture.md | 1 shared module + 1 doc |

The biggest wins from consolidation are the hypo-correction threshold, `overnight_stats`, the stats helpers, and the constant scatter. These are the cascade hot-spots.

The slope-based fasting rule is a real structural change, not a duplication issue. It is the right time to introduce a `night_signals` module if we are going to add slope as a first-class signal anyway.

---

## 7. Proposed principles

### P1. One source of truth per concept

Every concept gets one place:
- Production rule: `rules.py`.
- Overnight statistics: a new shared module (call it `night_stats.py`).
- Hypo-correction detection: the same shared module.
- Stats helpers (Spearman, linreg, residuals): a single `stats_utils.py`.
- Constants: live with the concept. `HYPO_THR` next to `night_stats`. `TGT_LO/TGT_HI` renamed to disambiguate clinical (4-10) vs preferred (5-8). Diagnosis date in one config.

Documentation references the source of truth instead of restating values. `architecture.md` should say "thresholds are defined in `rules.py`" and not duplicate them.

### P2. Production path is named and stable

`dexcom_fetch.py -> rules.py -> dose_diary.py` is THE production path. Everything else is research / backtest. Documentation, CLAUDE.md, and any "tonight's suggestion" surface should make this explicit. Backtest scripts are labelled research and not exposed as user-facing suggestion tools.

### P3. One nightly suggestion

Only the production path emits "tonight's suggestion". Backtest scripts emit analysis output and never claim to be a tonight's-dose source. If `basal_analysis.py` or `rules_model.py` print a suggestion today, that should change.

### P4. Rules are pure functions

`thomas_rules()` is pure (no I/O, deterministic, thresholds parameterised). Any new rule logic (slope-based fasting, 6-tier strain) is added as additional pure functions in `rules.py`, with full test coverage in `test_rules.py`. Side effects belong outside the rule layer.

### P5. Data layer is loader-only

`dexcom_loader.py`, `whoop_loader.py`, `dose_diary.py` only do I/O and parsing. They do not compute outcomes or apply rules. Any analysis logic that has crept into them gets moved to a shared analysis module.

### P6. Drop dead weight

WHOOP fields loaded but never used by any rule or model are removed from the loader. If they are later needed, they are added back at that moment. Same for `s7` (rolling 7-day strain) - dropped per decisions-log but `rolling_avg()` still runs.

### P7. Slope is now a first-class signal

The slope-based fasting rule decision (today, section 4) means second-half slope joins the data layer as a stored, first-class signal. The dose diary records it per night. `night_stats.py` exposes it. `rules.py` consumes it. No more "the slope lives only in a one-off analysis script".

### P8. Bolus is now a first-class dependency

If the slope-based rule is to ship, bolus integration is no longer optional. NovoPen 6 data ingestion moves from "known gap" to an active prerequisite. Bolus's role across the codebase needs to be reconciled to one framing: not a model feature, but required to disambiguate slope signal.

### P9. Test the production rule; not the analysis scripts

`test_rules.py` is the gate. Backtest scripts produce reports; they do not block releases. New tests for slope-based rule additions land in `test_rules.py` (or a sibling `test_slope_rule.py` if it grows large).

### P10. Decisions-log gates non-trivial changes

Already protocol per CLAUDE.md. Strengthen it: any change to a `rules.py` threshold, an exclusion criterion, a model-feature set, or an outcome metric requires a decisions-log entry **before** the code change, not after. The pre-existing `decisions-log-reminder` hookify rule (still pending Thomas's manual fix per session-log 2026-05-26) should be wired correctly so this is enforced.

### P11. The architecture doc is the map, not the registry

`docs/architecture.md` describes WHAT components exist, HOW data flows, and WHO depends on WHO. It does not duplicate rule thresholds, exclusion threshold values, or any number that lives in code. When a value changes, the architecture doc does not change unless the architecture itself changed.

### P12. The "purpose" is fixed and visible

Memory captures it; the architecture doc should reference it:
- Dose decisions are always user-initiated active choices.
- The Telegram bot (future) is remote access, not scheduled push.
- The system supports the decision; it never triggers it.
- Night quality outcome metric is second-half slope, not endpoint fasting.
- Strain MUST inform every suggestion - never silently skipped.

Drift away from these is a red flag. The redesign doc, the architecture doc, and CLAUDE.md should all surface these explicitly so a future session cannot lose them.

---

## 8. To-do items (R-series, extractable to `docs/improvements.md`)

Each item is written in the same format as existing `improvements.md` entries so it can be copy-pasted across without rework. Prefix `R` for redesign.

- [ ] R1. Consolidate `overnight_stats` into one shared module (`scripts/night_stats.py`).
  - Today: 7 implementations (`basal_analysis.py:33-76`, `rules_model.py:25-49`, `ml_model.py:39-52`, `dexcom_fetch.py:53-82`, `bolus_noise_test.py:64-79`, `predictor_test.py:21-37`, `strain_binning_analysis.py:38-67`).
  - Define one function with a clear signature: `night_stats(readings) -> {tir, fasting, mean, min, inj_g, hypo_events, hypo_correction, second_half_slope, ...}`. Include the slope from the start - it becomes load-bearing.
  - Update all 7 call sites. The tz-aware variant in `dexcom_fetch.py` becomes one optional argument.
  - Acceptance: a future "change to overnight statistics" touches one file.

- [ ] R2. Consolidate hypo-correction detection into `night_stats.py`.
  - Today: 5 copies with threshold `> 7.0` (`basal_analysis.py`, `ml_model.py`, `rules_model.py`, `bolus_noise_test.py`, `strain_binning_analysis.py`).
  - Pre-requisite for the today's-decision change (7 -> 10): once consolidated, the threshold change is a one-file edit.
  - Acceptance: only `night_stats.py` defines the hypo-correction logic and threshold.

- [ ] R3. Consolidate stats helpers (`spearman`, `linreg`, `residuals`) into `scripts/stats_utils.py`.
  - Today: 3 copies of `spearman` and `linreg` in `basal_analysis.py`, `predictor_test.py`, `bolus_noise_test.py`.
  - Acceptance: research scripts import from `stats_utils`; no duplicate math.

- [ ] R4. Remove `bolus_noise_test.py`'s private `load_dexcom`; use the shared loader.
  - Today: `bolus_noise_test.py:19-62` is a pre-extraction copy that returns a different tuple shape and does its own bolus dedup.
  - If a 4-tuple shape is required, extend `dexcom_loader.py` to optionally return raw bolus events; do not duplicate the whole loader.

- [ ] R5. Resolve the `TGT_LO / TGT_HI` shadowing (improvements.md B9 already lists this; promote from deferred).
  - Today: name collision between clinical TIR (4-10) and Thomas's preferred range (5-8).
  - Rename to `CLINICAL_TIR_LO/HI` (4-10) and `TARGET_LO/HI` (5-8), or push both into `night_stats.py` constants with distinct names.
  - Touches all 7 scripts that import or declare them.

- [ ] R6. Move `HYPO_THR`, `WAKE_HOUR`, `OVN_START`, `DIAGNOSIS_START` into single-source-of-truth modules.
  - `HYPO_THR`, `WAKE_HOUR`, `OVN_START` -> `night_stats.py`.
  - `DIAGNOSIS_START` -> a small `config.py` (or env var per improvements.md C1).
  - Today: 7 declarations of `HYPO_THR`, 3 of `DIAGNOSIS_START`.

- [ ] R7. Make all modeling scripts function-and-main.
  - Today: `ml_model.py`, `rules_model.py`, `bolus_noise_test.py`, `predictor_test.py` are top-level imperative.
  - Wrap each in `def main(): ...` and `if __name__ == '__main__': main()`. Enables import without side-effects (needed for R1 and R2).

- [ ] R8. Re-run predictor analysis with the inferential framing.
  - Question to test: "given the night's signals (strain, recovery, hrv, rhr, sleep_perf, stress if available, prev_dose, prev_fasting, prev_hypos), what dose would have produced a flat second-half slope?"
  - This is the inferential framing (Thomas, 2026-05-28) - not "what correlates with TIR" but "what dose would have been correct given these signals".
  - Today: `predictor_test.py` runs the correlational framing against TIR / fasting / mean. The slope-based outcome (decided 2026-05-27) has never been tested. The dose-needed-to-land-flat framing has never been tested at all.
  - Approach:
    1. Extend `predictor_test.py` (or build a new script) to compute, for each historical night, the dose that would have produced a flat second-half slope - use the regression coefficients from `strain_regression_analysis.py` Phase A2 as the starting model.
    2. Test each candidate signal (strain, recovery, hrv, rhr, sleep_perf, stress, prev_dose, prev_fasting, prev_hypos) for predictive value against the inferred optimal dose.
    3. Decide which fields to keep / drop / promote into the rule based on results.
    4. Until this analysis completes, keep all WHOOP fields loaded - dropping them now would lose the option to test.
  - Replaces the original R8 framing ("drop dead weight"), which was wrong - the right action is to test, not to drop.

- [ ] R9. Drop `s7` (rolling 7-day strain) from active code paths.
  - Decisions-log 2026-04-15 dropped s7 as a match variable. But `rolling_avg(d, 7, ...)` is still computed by `basal_analysis.py:166` and `ml_model.py:67`.
  - Either delete the computation entirely or keep it behind a `--with-s7` flag for research purposes.

- [ ] R10. Add second-half slope to the dose diary schema.
  - Today: `data/doses.csv` columns do not include slope.
  - Add `sh_slope` (mmol/L/h, second half of overnight window). Backfill historical rows from existing Clarity data so backtests have full history.
  - Acceptance: every new diary row records the slope; backtests can validate the slope-based rule from `doses.csv`.

- [ ] R11. Move `second_half_trend()` from `strain_binning_analysis.py` into `night_stats.py`.
  - Promotes slope from "research script-only" to a first-class signal in the production path.
  - Today: only `strain_binning_analysis.py` and `strain_regression_analysis.py` (via import) compute it.

- [ ] R12. Reconcile bolus's role in the codebase.
  - Resolve the three-way tension: "not a model feature" (decisions-log) vs "used as an exclusion criterion" (basal_analysis.py) vs "required for slope-based rule" (today's decision).
  - Sub-tasks:
    - Remove the IQR bolus exclusion (today's decision; already in code touchpoints).
    - Promote NovoPen 6 bolus integration from "Background known gap" to an active backlog item.
    - Document the new role: "bolus is not a predictor of overnight TIR but IS required to disambiguate slope signal for basal titration".

- [ ] R13. Integrate NovoPen 6 bolus data (now load-bearing).
  - Today: gap since 2026-01-31. Slope-based fasting rule cannot ship without this.
  - Investigate NovoPen 6 export options (mobile app, USB, API?). Pick the lowest-friction.
  - Update `dexcom_loader.py` or add a `novopen_loader.py` to ingest. Decide whether to merge into the Clarity bolus stream or keep separate.

- [ ] R14. Remove the "tonight's suggestion" block from `basal_analysis.py` and `rules_model.py`.
  - Today: three scripts produce a "tonight's dose" output. Risk of drift.
  - Only `dexcom_fetch.py` (the production path) should claim to suggest tonight's dose.
  - `basal_analysis.py` becomes "weekly pattern + historical observation".
  - `rules_model.py` becomes "backtest report only".
  - Acceptance: `grep -i "tonight"` finds the phrase in `dexcom_fetch.py` and documentation, not in research scripts.

- [ ] R15. Update CLAUDE.md Quick Start to reflect the production path.
  - Today: `basal_analysis.py` labelled "main analysis + tonight's suggestion" - misleading.
  - Reword: `dexcom_fetch.py` is the production path (called by `/dose`); `basal_analysis.py` is "weekly historical pattern (research)"; `rules_model.py` is "rules backtest (research)".

- [ ] R16. Rewrite `docs/architecture.md` so it does not duplicate values that live in code.
  - Sections 2, 3, 4 currently restate thresholds, exclusion values, and predictor stats. Today's decisions already render some of these stale.
  - New principle (P11): the architecture doc describes WHAT exists and HOW it connects; not WHAT VALUE each threshold has.
  - For each value-restatement, replace with a pointer: e.g. "thresholds defined in `scripts/rules.py:7-13`".

- [ ] R17. Document the data-flow explicitly in the architecture doc.
  - Today: the architecture doc describes models but not data flow. The reader cannot easily trace "where does today's strain come from" or "what happens to a `/dose` invocation".
  - Add diagrams or tables that map: data sources -> loaders -> shared modules -> production path -> outputs.
  - Cover the two CGM fetch paths (Share live + Clarity historical) and their handoff explicitly.

- [ ] R18. Add the "purpose" preamble to the architecture doc.
  - Per Principle P12: the doc should state the load-bearing invariants up front:
    - User-initiated only (no scheduled push).
    - Strain non-negotiable.
    - Night quality = slope, not endpoint fasting.
    - Bolus required for slope disambiguation.
    - Single production path: `/dose` -> `dexcom_fetch.py` -> `rules.py` -> `dose_diary.py`.
  - These are the principles the system should not drift away from. Surfacing them in the doc makes the drift visible.

- [ ] R19. Wire the `decisions-log-reminder` hookify rule correctly.
  - Per session-log 2026-05-26: the rule's event/field is misconfigured and needs Thomas's manual fix.
  - Once fixed, P10 (decisions-log gates non-trivial changes) has a working enforcement mechanism.

- [ ] R20. Decide a doc-scope policy and apply it.
  - Today: overlap and drift between `architecture.md`, `decisions-log.md`, `improvements.md`, `session-log.md`, `CLAUDE.md`, memory.
  - Propose:
    - `architecture.md`: WHAT and HOW (components, data flow, principles).
    - `decisions-log.md`: WHY of each major decision (immutable history).
    - `improvements.md`: planned WORK (backlog).
    - `session-log.md`: WHAT happened this session.
    - `CLAUDE.md`: quick reference + session protocol.
    - Memory: cross-session behavioural patterns.
  - Audit existing content against the policy; move misplaced sections (e.g. E10's nighttime objective spec - it is design, not just a backlog item; should partly live in architecture.md once validated).

- [ ] R21. Add WHOOP stress signal to the data layer.
  - Thomas (2026-05-28): "stress level should be added to whoop extract - this seems to be a major factor when high."
  - Path 1: check whether the current `whoop-sdk` exposes WHOOP's Stress Monitor endpoint (added by WHOOP in 2024). If yes, extend `whoop_api_fetch.py` to fetch it and `whoop_loader.py` to surface it.
  - Path 2 (fallback): if no SDK support or hard to integrate, use `hrv` as the derived stress proxy. Low HRV = high autonomic stress. `hrv` is already loaded (see R8).
  - Acceptance: a stress signal (direct or HRV-derived) is available to the predictor analysis in R8 and to the slope-based rule if R8 finds it predictive.
  - Open (deferred until R8 results land): how stress enters the rule structure - its own adjustment branch, or input to the slope rule?

- [ ] R22. Change overnight window end from 07:00 to 06:20.
  - Today: `WAKE_HOUR = 7` (`OVN_END = 7`) hard-coded across all 7 overnight_stats variants (see R1).
  - New: 06:20 - Thomas's actual weekday alarm time. Goal is "actual wake glucose", not a fixed clinical fasting hour.
  - Touches: every overnight_stats implementation, all backtest output (every night recomputed with the new window), slope calculation (second-half window shifts), hypo counting / TIR / fasting reading.
  - Dependency: do R1 (consolidate overnight_stats) first so this becomes a one-file edit instead of seven.
  - Open (deferred to E10): fixed 06:20 daily vs wake-time-relative (variable by day for weekends, sick days, sleep-ins). See note added to `improvements.md` E10.

---

## 9. Reading order when resuming

If a future session picks this up cold:

1. Read `docs/architecture.md` for the component map. Now stale; updating it is R16-R18.
2. Read `docs/improvements.md` for current backlog.
3. Read this file (`docs/t1d-redesign.md`) for the consolidation + principles proposal.
4. Read `docs/session-log.md` for context on the most recent design discussions (E1b NEEDS-line protocol, architecture-doc walkthrough, slope-based fasting rule).
5. Read `docs/decisions-log.md` before proposing any change to a rule, exclusion criterion, or data source.

If implementing R-series items, the natural order is:
- R1 -> R2 -> R6 (consolidation foundations).
- R7 (refactor scripts to function-and-main so consolidated imports work).
- R3 -> R4 -> R5 (further consolidation).
- R8 -> R9 (drop dead weight).
- R10 -> R11 (slope as first-class signal - sets up the slope rule).
- R12 -> R13 (bolus reconciliation - unblocks the slope rule).
- Then today's deferred decisions (hypo threshold 7 -> 10, bolus IQR removal, fasting +1u 10.5 -> 10) become trivial single-file edits.
- R14 -> R15 (clean up the "tonight's suggestion" surface).
- R16 -> R17 -> R18 (architecture doc rewrite, last - by then the truth has settled).
- R19 -> R20 in parallel.

---

## 10. What is NOT in scope of this audit

- No code was changed.
- No new tests written.
- The slope-based rule itself (the four open questions in session-log) is not resolved here; this audit only catalogs the structural changes needed to support it.
- WHOOP live-fetch viability (exploration sub-task in `improvements.md` E1b) is not investigated.
- The "current vs target" model ranking decision (today's architecture walkthrough section 1) is reflected in R14-R16 but not separately re-litigated.

End of redesign audit.
