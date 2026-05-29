"""Dose diary - CSV of nightly basal doses + overnight outcomes.

One row per dose-event (night). Today's row is created when dexcom_fetch
computes a suggestion; yesterday's row is backfilled with the overnight
outcome (fasting, hypo, TIR, sh_slope) by the next run.

The 'append-only' label in the backlog refers to history: rows are never
deleted. Existing rows may be amended only to fill in fields that were
unknown when the row was first written.
"""
import csv
from pathlib import Path

DIARY_PATH = Path(__file__).resolve().parent.parent / 'data' / 'doses.csv'
COLUMNS    = ['date', 'dose_u', 'fasting', 'hypo_events', 'tir_pct',
              'sh_slope', 'strain_s1', 'suggested_u', 'reasoning']


def load_diary():
    if not DIARY_PATH.exists():
        return []
    with open(DIARY_PATH, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def save_diary(rows):
    DIARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DIARY_PATH, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for row in sorted(rows, key=lambda r: r['date']):
            w.writerow({k: row.get(k, '') for k in COLUMNS})


def find_row(diary, target_date):
    target = str(target_date)
    return next((r for r in diary if r['date'] == target), None)


def upsert_row(diary, row):
    """Merge row into diary by date: amend existing or append."""
    existing = find_row(diary, row['date'])
    if existing:
        for k, v in row.items():
            if v != '' and v is not None:
                existing[k] = v
    else:
        diary.append(row)
    return diary


def parse_dose(s):
    s = str(s or '').strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


if __name__ == '__main__':
    from datetime import date
    from dexcom_loader import load_dexcom
    from night_stats import overnight_window, second_half_trend

    diary = load_diary()
    glucose_list, basal_list, _ = load_dexcom()

    # Build injection-datetime lookup (first evening injection per date)
    basal_by_date = {}
    for inj_dt, inj_date, _ in basal_list:
        if inj_dt.hour >= 18 and inj_date not in basal_by_date:
            basal_by_date[inj_date] = inj_dt

    updated = 0
    for row in diary:
        if row.get('sh_slope'):
            continue
        try:
            d = date.fromisoformat(row['date'])
        except (ValueError, TypeError):
            continue
        inj_dt = basal_by_date.get(d)
        if inj_dt is None:
            continue
        window = overnight_window(inj_dt, glucose_list)
        slope, _, _ = second_half_trend(window)
        if slope is not None:
            row['sh_slope'] = round(slope, 3)
            updated += 1

    if updated:
        save_diary(diary)
        print(f'Backfilled sh_slope for {updated} diary rows.')
    else:
        print('No rows needed backfilling.')
