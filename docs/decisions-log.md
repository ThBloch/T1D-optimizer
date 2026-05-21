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

## 2026-05-15 — New-pen adjustment (-1u)
**Decision:** Add a new rule: starting a fresh basal pen applies -1u. Stacks with glucose and activity adjustments. Triggered via `--new-pen` CLI flag on `dexcom_fetch.py`.
**Why:** Thomas observed (empirical, lived) that the first night on a fresh pen tends to run higher than expected — likely a priming/needle/insulin-freshness effect. -1u absorbs the bias on the first night without altering the steady-state titration. Encoded in `rules.py:thomas_rules(..., new_pen=True)` and locked in by 3 new unit tests.

## 2026-05-15 — Hypo override flag (`--no-hypo`)
**Decision:** Allow the operator to instruct `dexcom_fetch.py` to ignore CGM-detected hypos for the rule calculation when they are judged sensor noise. The diary still records the raw CGM count for historical accuracy; the override appears as the first line in the reasoning chain.
**Why:** Dexcom G7 occasionally reports a single sub-4.0 reading (e.g. 3.9) due to sensor noise at the boundary. When the operator can verify (subjectively or via parallel finger-stick) that no real hypo occurred, the rule's automatic -1u correction is unwarranted and would drive the dose downward incorrectly. The override is opt-in per run, not a default, so the conservative behavior is preserved.

## 2026-05-18 — Rolled back first `/dose` slash command draft
**Decision:** Deleted the first `D:/claude/t1d/.claude/commands/dose.md` draft. `/dose` rebuild deferred until Phase 1 of the automation roadmap lands (`--dose N` flag on `dexcom_fetch.py`, removal of `input()` prompts).
**Why:** The draft added an interactive orchestration layer (AskUserQuestion for new-pen, factors, sensor-noise) directly on top of the current interactive script. Phase 1 is removing script interactivity to make scripts cron-friendly for the Telegram path. Building `/dose` on the pre-Phase-1 script meant near-certain rewrite once Phase 1 ships. Cleaner to do Phase 1 first; `/dose` then becomes a ~20-line wrapper around a non-interactive `--dose N` invocation. Backlog entry moved here from `claude-setup/improvements.md` D1 to enforce the rule that project-specific work lives in the project's own backlog.

## 2026-05-21 — GitHub strategy: defer public push until project is "share-ready"
**Decision:** Repo stays local for now (no remote yet). Eventual aim is public, to help other T1D patients/builders. Gated on an informal quality bar - E1 (strain rule refinement), E10 (nighttime objective validation), at least E5 (Phase 1 automation) - plus C1 sanitization. Three migration paths logged in E2 for the eventual flip.
**Why:** Thomas wants the tool shareable if it can help others, but the current state is a single-user manual workflow with a coarse strain rule and an outcome metric (TIR(5-8)) that may be reshaped by E10. Going public now would lock in shape decisions still in flux. Defer until the model + automation make this a real tool, not a notebook.

## 2026-05-21 — C1 leak surface scoped accurately
**Decision:** Rewrote C1 in `improvements.md` to list the actual 6 leak locations (CLAUDE.md L3/35, basal_analysis.py L2/138, ml_model.py L2, whoop_api_fetch.py L13, architecture.md L43) and dropped the "email" claim (not in any tracked file). Added a note that git commit author identity is a separate leak with its own file-only-vs-history-rewrite decision at public-migration time.
**Why:** The original C1 entry said "CLAUDE.md ... email" - underscoped (missed scripts + architecture.md + the `DIAGNOSIS_START` constant) and inaccurate (no email anywhere in tree). Made it concrete so a future implementation pass knows exactly what to touch.

## 2026-05-21 — Private GitHub backup pushed; line-ending policy locked
**Decision:** Pushed local `master` (23 commits) to a private GitHub repo at https://github.com/ThBloch/T1D-optimizer - satisfies E2 path 1. Added `.gitattributes` with `* text=auto` to enforce LF in the repo regardless of any contributor's local Git config. Set `core.autocrlf=false` locally to silence the cosmetic LF/CRLF warnings now that `.gitattributes` makes the per-user setting irrelevant for normalization.
**Why:** Backup + portability were the only immediate needs; public migration stays gated by quality bar + C1 sanitization (see prior 2026-05-21 entry). `.gitattributes` is the right layer for line-ending policy because it travels with the repo - the local `core.autocrlf` change only affects this machine and would be overridden by `.gitattributes` anyway on a fresh clone. Repo URL also captured in auto-memory `reference_github_repo.md` so future sessions don't have to grep `git remote -v`.
