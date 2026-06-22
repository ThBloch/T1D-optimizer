"""
dexcom_events_fetch.py - Dexcom Developer API v3 incremental fetcher.
Pulls insulin events and EGV readings from api.dexcom.eu.
Run: py -X utf8 dexcom_events_fetch.py [--full]
"""

import argparse
import json
import re
import time
import urllib.error
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── PATHS ─────────────────────────────────────────────────────────────────────
CONFIG_FILE = Path.home() / '.dexcom_api' / 'config.json'
TOKENS_FILE = Path.home() / '.dexcom_api' / 'tokens.json'
DATA_DIR    = Path(__file__).resolve().parent.parent / 'data' / 'dexcom_api'

BASE_URL   = 'https://api.dexcom.eu'
TOKEN_URL  = f'{BASE_URL}/v2/oauth2/token'
DATA_URL   = f'{BASE_URL}/v3/users/self'

OVERLAP_DAYS     = 7    # re-fetch window to catch updated records
EGV_CHUNK_HOURS  = 6   # egvs truncate at ~100 records; 6h ~= 72 readings
EVT_CHUNK_DAYS   = 30  # events are sparse; API returns 400 above ~36 days
EGV_FULL_DAYS    = 30  # --full seeds this many days of egvs (NOT full history)

# Import diagnosis date so it is not re-hardcoded (C1 leak hygiene).
from dexcom_loader import DIAGNOSIS


# ── AUTH HELPERS ──────────────────────────────────────────────────────────────
def load_config():
    with open(CONFIG_FILE, encoding='utf-8') as f:
        return json.load(f)


def load_tokens():
    with open(TOKENS_FILE, encoding='utf-8') as f:
        return json.load(f)


def save_tokens(tokens):
    with open(TOKENS_FILE, 'w', encoding='utf-8') as f:
        json.dump(tokens, f, indent=2)


def _now_utc_ts():
    return datetime.now(timezone.utc).timestamp()


def refresh_access_token(config, tokens):
    """Exchange refresh_token for a new access_token. Persists rotated tokens."""
    data = urllib.parse.urlencode({
        'grant_type':    'refresh_token',
        'refresh_token': tokens['refresh_token'],
        'client_id':     config['client_id'],
        'client_secret': config['client_secret'],
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, method='POST')
    try:
        res = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')
        raise RuntimeError(f'Token refresh failed {e.code}: {body}') from e
    new_tokens = json.loads(res.read().decode())
    new_tokens['expires_at'] = _now_utc_ts() + new_tokens.get('expires_in', 7200) - 30
    save_tokens(new_tokens)
    return new_tokens


def get_access_token(config, tokens):
    """Return a valid access token, refreshing proactively or on 401."""
    expires_at = tokens.get('expires_at')
    if expires_at is None or _now_utc_ts() >= float(expires_at):
        tokens = refresh_access_token(config, tokens)
    return tokens['access_token'], tokens


def api_get(url, config, tokens):
    """GET url with Bearer auth; refreshes once on 401."""
    token, tokens = get_access_token(config, tokens)
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    try:
        res = urllib.request.urlopen(req)
        return json.loads(res.read().decode()), tokens
    except urllib.error.HTTPError as e:
        if e.code == 401:
            tokens = refresh_access_token(config, tokens)
            req = urllib.request.Request(
                url, headers={'Authorization': f'Bearer {tokens["access_token"]}'}
            )
            res = urllib.request.urlopen(req)
            return json.loads(res.read().decode()), tokens
        body = e.read().decode(errors='replace')
        raise RuntimeError(f'API GET {url} failed {e.code}: {body}') from e


# ── UTILITIES ─────────────────────────────────────────────────────────────────
def _dt_to_utc_str(dt):
    """datetime (naive UTC assumed) -> ISO string for API query."""
    return dt.strftime('%Y-%m-%dT%H:%M:%S')


def chunk_ranges(start_dt, end_dt, max_hours):
    """Yield (start_str, end_str) UTC pairs spanning at most max_hours."""
    delta = timedelta(hours=max_hours)
    cur = start_dt
    while cur < end_dt:
        nxt = min(cur + delta, end_dt)
        yield _dt_to_utc_str(cur), _dt_to_utc_str(nxt)
        cur = nxt


def merge_records(existing, new_recs, id_field, sort_field):
    """Dedup by id_field (new wins), return sorted by sort_field."""
    by_id = {r[id_field]: r for r in existing}
    for r in new_recs:
        by_id[r[id_field]] = r
    return sorted(by_id.values(), key=lambda r: r.get(sort_field) or '')


def to_naive_local(s):
    """Strip tz offset from displayTime string -> naive local datetime.

    Handles formats like '2026-06-21T08:16:54.484+02:00',
    '2026-06-21T08:16:54+01:59:59', '2026-06-20T01:00+02:00'.
    """
    s = re.sub(r'Z$|[+-]\d{2}:\d{2}(:\d{2})?$', '', s)
    for fmt in ('%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f'Cannot parse displayTime: {s!r}')


def _parse_utc_str(s):
    """Parse a UTC systemTime string ('2026-06-21T06:16:54.484Z') -> naive UTC datetime."""
    s = s.rstrip('Z')
    for fmt in ('%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f'Cannot parse systemTime: {s!r}')


def _max_time(records, *fields):
    """Max value across given fields across all records; returns naive UTC datetime or None."""
    times = []
    for r in records:
        for f in fields:
            v = r.get(f)
            if v:
                times.append(v)
    if not times:
        return None
    return _parse_utc_str(max(times))


# ── FETCH ─────────────────────────────────────────────────────────────────────
def _fetch_with_retry(url, config, tokens, max_retries=5):
    """api_get with exponential back-off on 429."""
    for attempt in range(max_retries):
        try:
            return api_get(url, config, tokens)
        except RuntimeError as e:
            if '429' in str(e) and attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f'  Rate limited; retrying in {wait}s...')
                time.sleep(wait)
            else:
                raise
    raise RuntimeError(f'Failed after {max_retries} retries: {url}')


def fetch_events(config, tokens, start_dt, end_dt):
    """Fetch all event records in [start_dt, end_dt] UTC, chunked by EVT_CHUNK_DAYS."""
    records = []
    chunks = list(chunk_ranges(start_dt, end_dt, max_hours=EVT_CHUNK_DAYS * 24))
    for i, (cs, ce) in enumerate(chunks, 1):
        params = urllib.parse.urlencode({'startDate': cs, 'endDate': ce})
        data, tokens = _fetch_with_retry(
            f'{DATA_URL}/events?{params}', config, tokens
        )
        batch = data.get('records', [])
        records.extend(batch)
        if len(chunks) > 1:
            print(f'  events chunk {i}/{len(chunks)}: {len(batch)} records')
    return records, tokens


def fetch_egvs(config, tokens, start_dt, end_dt):
    """Fetch EGV records in [start_dt, end_dt] UTC, chunked by EGV_CHUNK_HOURS."""
    records = []
    chunks = list(chunk_ranges(start_dt, end_dt, max_hours=EGV_CHUNK_HOURS))
    for i, (cs, ce) in enumerate(chunks, 1):
        params = urllib.parse.urlencode({'startDate': cs, 'endDate': ce})
        data, tokens = _fetch_with_retry(
            f'{DATA_URL}/egvs?{params}', config, tokens
        )
        batch = data.get('records', [])
        records.extend(batch)
        if len(chunks) > 1:
            print(f'  egvs chunk {i}/{len(chunks)}: {len(batch)} records')
    return records, tokens


def _load_cache(path):
    if not path.exists():
        return []
    with open(path, encoding='utf-8') as f:
        return json.load(f).get('records', [])


def _save_cache(path, records):
    fetched_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'fetched_at': fetched_at, 'records': records}, f, indent=2)


# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--full', action='store_true',
                        help='Full refresh: events from DIAGNOSIS, egvs last 30 days')
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config()
    tokens = load_tokens()

    now_utc  = datetime.now(timezone.utc).replace(tzinfo=None)
    diag_dt  = datetime(DIAGNOSIS.year, DIAGNOSIS.month, DIAGNOSIS.day)

    # ── EVENTS ────────────────────────────────────────────────────────────────
    events_path    = DATA_DIR / 'events.json'
    existing_evts  = _load_cache(events_path)

    if args.full or not existing_evts:
        evt_start = diag_dt
        mode_label = 'FULL'
    else:
        max_recorded = _max_time(existing_evts, 'recordedSystemTime', 'systemTime')
        evt_start = (max_recorded or diag_dt) - timedelta(days=OVERLAP_DAYS)
        mode_label = 'INCREMENTAL'

    print(f'Mode: {mode_label}')
    print(f'Fetching events from {_dt_to_utc_str(evt_start)} UTC...')
    new_evts, tokens = fetch_events(config, tokens, evt_start, now_utc)
    merged_evts = merge_records(existing_evts, new_evts, 'recordId', 'systemTime')
    added_evts = len(merged_evts) - len(existing_evts)
    _save_cache(events_path, merged_evts)
    print(f'  events: fetched {len(new_evts)} | merged {len(merged_evts)} (+{added_evts} new)')

    # ── EGVs ──────────────────────────────────────────────────────────────────
    egvs_path     = DATA_DIR / 'egvs.json'
    existing_egvs = _load_cache(egvs_path)

    if args.full or not existing_egvs:
        egv_start = now_utc - timedelta(days=EGV_FULL_DAYS)
    else:
        max_egv = _max_time(existing_egvs, 'systemTime')
        egv_start = (max_egv or now_utc - timedelta(days=EGV_FULL_DAYS)) - timedelta(days=OVERLAP_DAYS)

    print(f'Fetching egvs from {_dt_to_utc_str(egv_start)} UTC...')
    new_egvs, tokens = fetch_egvs(config, tokens, egv_start, now_utc)
    merged_egvs = merge_records(existing_egvs, new_egvs, 'recordId', 'systemTime')
    added_egvs = len(merged_egvs) - len(existing_egvs)
    _save_cache(egvs_path, merged_egvs)
    print(f'  egvs: fetched {len(new_egvs)} | merged {len(merged_egvs)} (+{added_egvs} new)')

    print()
    print('SUMMARY')
    print('=' * 40)
    print(f'  events.json : {len(merged_evts)} records')
    print(f'  egvs.json   : {len(merged_egvs)} records')
    if merged_evts:
        first_evt = to_naive_local(merged_evts[0]['displayTime'])
        last_evt  = to_naive_local(merged_evts[-1]['displayTime'])
        print(f'  event range : {first_evt.date()} -> {last_evt.date()}')
    if merged_egvs:
        first_egv = to_naive_local(merged_egvs[0]['displayTime'])
        last_egv  = to_naive_local(merged_egvs[-1]['displayTime'])
        print(f'  egv range   : {first_egv.date()} -> {last_egv.date()}')
