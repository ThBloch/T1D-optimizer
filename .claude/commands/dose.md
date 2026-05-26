---
description: Get tonight's basal dose suggestion from live Dexcom data
---

# /dose

Gather inputs, run dexcom_fetch.py non-interactively, output terse suggestion.

## Steps

1. Ask the user: "What dose did you take last night? (units)"
   Store the answer as DOSE.

2. Ask the user: "New pen cartridge tonight? (y/n)"
   If y, set NEW_PEN_FLAG to `--new-pen`, otherwise empty string.

3. Ask the user: "Any unmodeled factors? (alcohol / late meal / illness / activity not in WHOOP — or 'none')"
   Store as FACTORS.

4. Run from project root `D:\claude\t1d`:
   ```bash
   cd "D:/claude/t1d/scripts" && py -X utf8 dexcom_fetch.py --dose DOSE NEW_PEN_FLAG
   ```
   Capture full stdout as OUTPUT.

5. Check OUTPUT for hypo events:
   - Find the line matching `Hypo events.*: [1-9]`
   - If found, ask: "CGM detected N hypo(s) last night. Sensor noise? (y/n)"
   - If y: re-run the same command with `--no-hypo` added, replace OUTPUT with new stdout.

6. Extract from OUTPUT:
   - Suggested dose: find line matching `Suggested dose\s*:\s*(\S+)` -> SUGGESTION
   - Reasoning: collect all lines starting with `    * ` -> REASONS

7. Print:
   ```
   Tonight: SUGGESTION
   * reason 1
   * reason 2
   ...
   ```
   If FACTORS is non-empty and not "none":
   ```
   Off-rules: FACTORS (not modeled)
   ```

Print nothing else. No prose, no headers, no commentary beyond the lines above.
