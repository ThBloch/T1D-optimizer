"""Dexcom Developer API v3 cache loader.

Reads data/dexcom_api/events.json and egvs.json (written by dexcom_events_fetch.py)
and returns structures compatible with existing consumers (mirrors dexcom_loader shapes).

Public API:
  load_api_basal()          -> [(inj_dt, date, units), ...] one entry per local date
  load_api_bolus()          -> [(dt, units), ...]  fastActing events
  load_api_glucose(s, e)    -> [(dt, mmol_l), ...]  EGVs in window [s, e]
"""

import json
import re
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / 'data' / 'dexcom_api'

MG_DL_TO_MMOL = 1 / 18.0182


# ── INTERNAL HELPERS ──────────────────────────────────────────────────────────

def _to_naive_local(s):
    """Strip tz offset from displayTime string -> naive local datetime.

    Handles: '2026-06-21T08:16:54.484+02:00', '2025-04-26T06:30:00.358+01:59:59',
    '2026-06-20T01:00+02:00' (no seconds).
    """
    s = re.sub(r'Z$|[+-]\d{2}:\d{2}(:\d{2})?$', '', s)
    for fmt in ('%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f'Cannot parse displayTime: {s!r}')


def _load_events_cache():
    path = DATA_DIR / 'events.json'
    if not path.exists():
        return []
    with open(path, encoding='utf-8') as f:
        return json.load(f).get('records', [])


def _load_egvs_cache():
    path = DATA_DIR / 'egvs.json'
    if not path.exists():
        return []
    with open(path, encoding='utf-8') as f:
        return json.load(f).get('records', [])


# ── PUBLIC API ────────────────────────────────────────────────────────────────

def load_api_basal():
    """Return sorted [(inj_dt, date, units), ...] longActing events, one per local date.

    Skips deleted records. Same-day events are summed (mirrors load_dexcom basal
    aggregation). inj_dt is the earliest injection datetime for that date.
    """
    records = _load_events_cache()
    by_date = {}  # date -> [first_dt, total_units]
    for r in records:
        if r.get('eventStatus') == 'deleted':
            continue
        if r.get('eventSubType') != 'longActing':
            continue
        dt = _to_naive_local(r['displayTime'])
        d = dt.date()
        units = float(r['value'])
        if d not in by_date:
            by_date[d] = [dt, units]
        else:
            if dt < by_date[d][0]:
                by_date[d][0] = dt
            by_date[d][1] += units
    return sorted([(v[0], d, v[1]) for d, v in by_date.items()])


def load_api_bolus():
    """Return sorted [(dt, units), ...] fastActing events.

    Skips deleted records.
    """
    records = _load_events_cache()
    events = {}  # dt -> units, last-seen wins (recordId dedup already in cache)
    for r in records:
        if r.get('eventStatus') == 'deleted':
            continue
        if r.get('eventSubType') != 'fastActing':
            continue
        dt = _to_naive_local(r['displayTime'])
        events[dt] = float(r['value'])
    return sorted(events.items())


def load_api_glucose(start, end):
    """Return sorted [(dt, mmol_l), ...] EGV readings in the window [start, end].

    start, end: naive local datetimes (same convention as night_stats callers).
    Values converted from mg/dL to mmol/L, rounded to 1 decimal.
    """
    records = _load_egvs_cache()
    result = []
    for r in records:
        dt = _to_naive_local(r['displayTime'])
        if dt < start or dt > end:
            continue
        mmol = round(int(r['value']) * MG_DL_TO_MMOL, 1)
        result.append((dt, mmol))
    result.sort(key=lambda x: x[0])
    return result
