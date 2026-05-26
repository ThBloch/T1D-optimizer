---
description: Show terse 4-line status snapshot of the T1D optimizer state
---

# /t1d-status

Print a 4-line status snapshot. Read-only - no fetches, no writes.

## Execute

Run this from the project root (`D:\claude\t1d`):

```bash
py -X utf8 -c "
import csv, re
from pathlib import Path
from datetime import datetime, date

root = Path('.').resolve()
today = date.today()

def fmt_missing(label, msg='<missing>'):
    return f'{label:<13} {msg}'

# 1. Last Dexcom fetch = mtime of data/doses.csv
doses = root / 'data' / 'doses.csv'
if doses.exists():
    mtime = datetime.fromtimestamp(doses.stat().st_mtime)
    line1 = f'dexcom_fetch  {mtime:%Y-%m-%d %H:%M}'
else:
    line1 = fmt_missing('dexcom_fetch')

# 2. Latest Clarity CSV - parse YYYY-MM-DD from filename
clarity_dir = root / 'data'
pat = re.compile(r'Clarity_.*_(\d{4}-\d{2}-\d{2})_\d{6}\.csv$')
clarity_files = list(clarity_dir.glob('Clarity_*.csv')) if clarity_dir.exists() else []
if clarity_files:
    latest = max(clarity_files, key=lambda p: p.stat().st_mtime)
    m = pat.search(latest.name)
    if m:
        line2 = f'clarity_csv   {m.group(1)}'
    else:
        mt = datetime.fromtimestamp(latest.stat().st_mtime).date()
        line2 = f'clarity_csv   {mt} (from mtime)'
else:
    line2 = fmt_missing('clarity_csv', '<none>')

# 3. Open backlog items in docs/improvements.md
imp = root / 'docs' / 'improvements.md'
if imp.exists():
    n = sum(1 for ln in imp.read_text(encoding='utf-8').splitlines() if ln.startswith('- [ ]'))
    line3 = f'backlog_open  {n}'
else:
    line3 = fmt_missing('backlog_open')

# 4. Days since last dose entry
if doses.exists():
    last_date = None
    with doses.open(encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    for row in reversed(rows):
        d = (row.get('date') or '').strip()
        if d:
            last_date = d
            break
    if last_date:
        try:
            ld = datetime.strptime(last_date, '%Y-%m-%d').date()
            delta = (today - ld).days
            line4 = f'last_dose     {delta}d ago ({last_date})'
        except ValueError:
            line4 = f'last_dose     {last_date}?'
    else:
        line4 = fmt_missing('last_dose', '<empty>')
else:
    line4 = fmt_missing('last_dose')

print(line1)
print(line2)
print(line3)
print(line4)
"
```

## Output

Four lines only. Do not add prose, headers, or commentary. The script's stdout IS the response.
