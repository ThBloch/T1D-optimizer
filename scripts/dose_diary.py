"""Dose diary - CSV of nightly basal doses + overnight outcomes.

One row per dose-event (night). Today's row is created when dexcom_fetch
computes a suggestion; yesterday's row is backfilled with the overnight
outcome (fasting, hypo, TIR) by the next run.

The 'append-only' label in the backlog refers to history: rows are never
deleted. Existing rows may be amended only to fill in fields that were
unknown when the row was first written.
"""
import csv
from pathlib import Path

DIARY_PATH = Path(__file__).resolve().parent.parent / 'data' / 'doses.csv'
COLUMNS    = ['date', 'dose_u', 'fasting', 'hypo_events', 'tir_pct',
              'strain_s1', 'suggested_u', 'reasoning']


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
