---
description: Log session, run tests, commit changed docs + tracked code, push to origin/master
---

# /session-done

Wrap up the session in one command: append a dated entry to
`docs/session-log.md`, run all test suites, commit changed docs +
tracked code, push to `origin/master`. Replaces the manual
five-step end-of-session sequence.

## Steps

1. **Read session state.** From project root (`D:\claude\t1d`):
   ```bash
   git status -s
   git log origin/master..HEAD --oneline
   ```
   Also tail the last `## ` header in `docs/session-log.md` to see
   whether today already has an entry.

2. **Refuse if nothing changed.** If `git status -s` is empty AND
   `git log origin/master..HEAD` is empty AND the last session-log
   entry already covers today's work, print exactly:
   ```
   Nothing to log; working tree clean and origin is up to date.
   ```
   and stop. Do not generate an empty entry.

3. **Draft a session-log entry.** Synthesise from:
   - the conversation context (what was worked on, decisions made, blockers),
   - `git log origin/master..HEAD` (commits already made this session),
   - `git status -s` (changes pending).

   The entry MUST match the existing convention. Template:
   ```
   ## YYYY-MM-DD [(continued)] <workstream-slug>
   **Changed:**
   - <bullet per script / data / doc area touched this session, with the relevant commit hash if applicable>

   **Decided:**
   - <bullet per non-obvious decision made this session>

   **Blocked:**
   - <bullet per current blocker; or "Nothing.">

   **Next (when Thomas resumes):**
   1. <recommended next item from the backlog>
   2. <alternates with effort estimates if helpful>

   **Commits this entry:** `<hash1>` <short summary> | `<hash2>` <short>.
   ```
   Rules:
   - `YYYY-MM-DD` is today's date. Use the system date, not anything from the conversation.
   - Include `(continued)` ONLY if `docs/session-log.md` already has an entry whose header starts with today's date.
   - `<workstream-slug>` is the conversation's `/rename` slug if one was set; otherwise infer a short kebab-case label from the work (e.g. `e15-bolus-disjointness`). If unclear, ask the user with `AskUserQuestion`.
   - The `**Commits this entry:**` line MUST list every hash returned by `git log origin/master..HEAD --oneline`, in commit order. The session-log commit itself is appended to this list AFTER step 8 (the commit hash is unknown at draft time; leave a placeholder like `<this-commit>` and substitute after committing - or just list the prior commits and add the new line later).

   Display the draft inline to the user, then go to step 4.

4. **Ask approval** via `AskUserQuestion`:
   - Question: "Approve the session-log entry, edit, or cancel?"
   - Options: "Approve", "Edit (paste replacement)", "Cancel".
   - On "Edit": ask the user to paste the replacement text.
   - On "Cancel": stop. Do not write any files. Do not commit.

5. **Append** the (possibly edited) entry to the end of
   `docs/session-log.md`. Preserve the existing trailing newline
   semantics - insert one blank line between the existing last
   entry and the new one.

6. **Run tests.** From project root:
   ```bash
   py -X utf8 tests/test_rules.py
   py -X utf8 tests/test_night_stats.py
   py -X utf8 tests/test_bolus_classification.py
   ```
   If ANY suite exits non-zero or reports failures: STOP. Print the
   failing-test output verbatim. Do not stage, commit, or push.
   The user investigates and re-invokes `/session-done` once tests
   are green.

7. **Stage selectively.** Run:
   ```bash
   git add docs/session-log.md
   ```
   If `git status -s` shows other modified (`M`) tracked files
   beyond `docs/session-log.md`, surface them via
   `AskUserQuestion`: "Also include these tracked changes in the
   commit?" with options "Yes (all)", "Pick a subset", "No, just
   the session-log entry."

   NEVER `git add -A`. NEVER `git add .`. NEVER stage files marked
   `??` (untracked) - if the user wants them in, they add them
   manually before re-invoking.

8. **Commit.** Generate a message:
   - Subject (first line, <70 chars): one short summary of the
     session-log entry's workstream.
   - Body: 2-3 lines mirroring the entry's `**Changed:**` bullets.
   - Footer: standard
     `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`
     (or the model the current session is using).
   Use a HEREDOC for the commit message to preserve formatting:
   ```bash
   git commit -m "$(cat <<'EOF'
   <subject>

   <body line 1>
   <body line 2>

   Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
   EOF
   )"
   ```

9. **Push.** Run `git push` (no `--force`, no `--no-verify`). If
   push fails (e.g. non-fast-forward), print the error and stop -
   the user investigates and resolves.

10. **Report.** Print exactly three lines:
    ```
    Session entry appended (NN lines)
    Commit: <hash> <subject>
    Pushed to origin/master
    ```

## Output

Show the entry draft, the approval question, the test output, and
the final three-line report. Do not add prose, headers, or
celebratory commentary. The final three-line report is the
end-of-turn message.

## Safety rails

- NEVER `git push --force`.
- NEVER skip hooks (`--no-verify`).
- NEVER `git add -A` or `git add .` - explicit file list only.
- NEVER stage untracked files (lines starting with `??` in
  `git status -s`).
- NEVER stage anything matching the project's `.gitignore` (the
  gitignore handles this, but be defensive against `git add -f`).
- If tests fail at step 6: STOP. Do not commit. Do not push.
- If `git push` fails at step 9: STOP. Print the error verbatim.
  Do not retry with force or hook-skipping.

## First-use smoke test

The first time you (the user) run `/session-done`:
1. Read the generated draft carefully before approving.
2. Spot-check the commit message against the session-log entry.
3. Verify `git log origin/master..HEAD` is empty after the push.
4. If anything looks off, cancel at step 4 and report what was
   wrong so this command file can be tightened.
