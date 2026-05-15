#!/usr/bin/env python3
import json
import os
import sys
import time
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from whoop_sdk import Whoop
from requests.exceptions import HTTPError

w = Whoop()

DIAGNOSIS_START = "2025-04-09T00:00:00.000Z"
OVERLAP_DAYS = 7  # re-fetch window to catch updated in-progress records

end_date = (date.today() + timedelta(days=1)).isoformat() + "T00:00:00.000Z"
fetched_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
output_dir = str(Path(__file__).resolve().parent.parent / 'data' / 'whoop_api')

force_full = "--full" in sys.argv

def load_cache(filename):
    path = os.path.join(output_dir, filename)
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f).get('records', [])

def cursor_from_records(records, time_field):
    if not records:
        return DIAGNOSIS_START
    vals = [r.get(time_field) for r in records if r.get(time_field)]
    if not vals:
        return DIAGNOSIS_START
    dt = datetime.fromisoformat(max(vals).replace('Z', '+00:00'))
    cursor = dt - timedelta(days=OVERLAP_DAYS)
    return cursor.strftime('%Y-%m-%dT%H:%M:%S.000Z')

def merge_records(existing, new, id_field, sort_field):
    by_id = {r[id_field]: r for r in existing}
    for r in new:
        by_id[r[id_field]] = r
    return sorted(by_id.values(), key=lambda r: r.get(sort_field) or '')

def fetch_with_retry(fetch_func, label, max_retries=5):
    for attempt in range(max_retries):
        try:
            result = fetch_func()
            return result.get('records', [])
        except HTTPError as e:
            if e.response.status_code == 429:
                wait_time = 2 ** attempt
                print(f"  Rate limited. Waiting {wait_time}s before retry {attempt+1}/{max_retries}...")
                time.sleep(wait_time)
            else:
                raise
    raise Exception(f"Failed to fetch {label} after {max_retries} retries")

ENDPOINTS = [
    ('cycles.json',   'cycles',   'id',       'start',      lambda s, e: w.get_cycles(start=s, end=e, limit=25, max_pages=None)),
    ('recovery.json', 'recovery', 'cycle_id', 'created_at', lambda s, e: w.get_recovery(start=s, end=e, limit=25, max_pages=None)),
    ('sleep.json',    'sleep',    'id',       'start',      lambda s, e: w.get_sleep(start=s, end=e, limit=25, max_pages=None)),
    ('workouts.json', 'workouts', 'id',       'start',      lambda s, e: w.get_workouts(start=s, end=e, limit=25, max_pages=None)),
]

print(f"Mode: {'FULL refresh' if force_full else 'INCREMENTAL'}")
print(f"Output: {output_dir}")
print()

results = {}
for filename, label, id_field, time_field, fetch_fn in ENDPOINTS:
    existing = [] if force_full else (load_cache(filename) or [])
    start = DIAGNOSIS_START if force_full or not existing else cursor_from_records(existing, time_field)
    print(f"Fetching {label} from {start[:10]} (cache has {len(existing)})...")
    new = fetch_with_retry(lambda fn=fetch_fn, s=start: fn(s, end_date), label)
    merged = merge_records(existing, new, id_field, time_field) if existing else new
    added = len(merged) - len(existing)
    print(f"  Fetched {len(new)} | merged {len(merged)} (+{added} new)")
    results[filename] = merged

print()

for filename, records in results.items():
    filepath = os.path.join(output_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump({'fetched_at': fetched_at, 'records': records}, f, indent=2)
    print(f"Saved {filename}: {os.path.getsize(filepath):,} bytes")

print()
print("SUMMARY")
print("=" * 50)
for filename, records in results.items():
    print(f"{filename:16} {len(records)}")

cycles = results.get('cycles.json', [])
if cycles:
    starts = sorted([c.get('start') for c in cycles if c.get('start')])
    print(f"Earliest cycle: {starts[0]}")
    print(f"Latest cycle:   {starts[-1]}")
