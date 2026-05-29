# Code Conventions

Principles that determine where code, constants, rules, and tests live
in this project. For doc-scope policy (where each kind of *document*
lives), see `architecture.md` "Doc map" or the decisions-log entry
2026-05-29 "Doc-scope policy + architecture.md rewrite".

These principles emerged from the 2026-05-28 audit (archived at
`archive/docs_pre_redesign/t1d-redesign.md` §7). They are durable; this
file supersedes the audit's P1-P12 list as the canonical home. Update
by appending a decisions-log entry, then editing here.

---

## P1. One source of truth per concept

Every concept gets one place:

- Production rule: `scripts/rules.py`.
- Overnight statistics + their constants: `scripts/night_stats.py`.
- Hypo-correction detection: same module (operates on the same data).
- Stats helpers (Spearman, linreg, residuals): `scripts/stats_utils.py`.
- Constants live with the concept. Rule-decision thresholds in
  `rules.py`; window/stat thresholds in `night_stats.py`; diagnosis
  date in `scripts/config.py`.

Documentation references the source of truth instead of restating
values. `architecture.md` points at `rules.py:7-19` and never duplicates
a number that lives in code.

## P2. Production path is named and stable

`dexcom_fetch.py -> rules.thomas_rules() -> dose_diary.upsert_row()` is
the production path. Every other script under `scripts/` is research
and must label itself as such (in its docstring and in `CLAUDE.md`
Quick Start).

## P3. One nightly suggestion

Only the production path emits "tonight's suggestion". Backtest /
analysis scripts emit analysis output and never claim to be a
tonight's-dose source. Enforce with grep:
`grep -i "tonight" scripts/*.py` returns matches only for
`dexcom_fetch.py`.

## P4. Rules are pure functions

`thomas_rules()` is pure: no I/O, deterministic, thresholds
parameterised. Any new rule logic lands as additional pure functions
in `rules.py` with full coverage in `tests/test_rules.py`. Side effects
belong outside the rule layer.

## P5. Data layer is loader-only

`dexcom_loader.py`, `novopen_loader.py`, `whoop_loader.py`, and
`dose_diary.py` only do I/O and parsing. They do not compute outcomes
or apply rules. Per-night statistics belong in `night_stats.py`, not in
loaders.

## P6. Drop dead weight

Fields loaded but never used by any rule or model are removed from the
loader. If they are later needed, they are added back at that moment.
Same for derived features: when a decisions-log entry retires a signal,
the computation is removed from active scripts.

## P7. Slope is a first-class signal

`sh_slope` is stored per night in the dose diary, exposed by
`night_stats.second_half_trend()`, and consumed by `thomas_rules()`. It
is not recomputed inside individual analysis scripts.

## P8. Bolus is a required input for slope disambiguation

Bolus is not a model feature for predicting TIR (decisions-log
2026-04-15) but IS required to interpret the slope signal: a falling
slope can be "basal too high" or "I corrected mid-night". Both
streams - Clarity manual G7 bolus, Glooko NovoPen 6 bolus - flow
through `dexcom_loader.load_bolus_combined()`.

## P9. Test the production rule, not the analysis scripts

`tests/test_rules.py` is the gate (38 cases). New rule branches land
with tests in the same file. Backtest / analysis scripts produce
reports; they do not block releases. `night_stats.py` is production-
path code; if it grows non-trivial logic beyond pure pass-through
stats, it earns its own test file.

## P10. Decisions-log gates non-trivial changes

Any change to a `rules.py` threshold, an exclusion criterion, a
model-feature set, or an outcome metric requires a decisions-log
entry. The `.claude/hookify.decisions-log-reminder.local.md` rule
fires at session end whenever `scripts/*.py` was edited.

## P11. Architecture doc is the map, not the registry

`docs/architecture.md` describes WHAT components exist, HOW data flows,
and WHO depends on WHO. It does not duplicate any number that lives in
code. When a value changes, the architecture doc does not change unless
the architecture itself changed.

## P12. Purpose invariants are visible

Five invariants - stated in `architecture.md` "Purpose" section and
mirrored here. Drift away from any of these is a red flag.

1. Dose decisions are user-initiated. Never scheduled, never pushed.
2. Strain MUST inform every suggestion. `dexcom_fetch.py` emits
   `NEEDS: strain` and refuses to compute a suggestion when today's
   WHOOP strain is unavailable (decisions-log 2026-05-29). User-side
   wiring of `/dose` to ask the user via documented prompts is the
   remaining E1b/E1d work.
3. Night-quality outcome metric is second-half slope, not endpoint
   fasting.
4. Bolus history is required for slope disambiguation.
5. Production path is `dexcom_fetch.py -> rules.py -> dose_diary.py`.

---

## How to use this file

- Before adding a new script, function, or constant: pick the right
  home using P1-P5.
- Before deleting something: P6 is permission to clean.
- Before changing a threshold or outcome metric: P10 - write the
  decisions-log entry first.
- When reading the architecture doc: trust P11 - if you want the
  current value, read the code.
- When sparring on direction: P12 is the answer to "does this fit?".
