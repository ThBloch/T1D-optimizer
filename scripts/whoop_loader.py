"""WHOOP data loader — reads from data/whoop_api/*.json (built by whoop_api_fetch.py)."""
import json
from datetime import datetime, timedelta
from pathlib import Path

API_DIR = Path('D:/claude/t1d/data/whoop_api')

def _parse_offset(s):
    if s == 'Z':
        return timedelta(0)
    sign = 1 if s[0] == '+' else -1
    h, m = s[1:].split(':')
    return timedelta(hours=sign * int(h), minutes=sign * int(m))

def _parse_iso(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00'))

def _cycle_date(cycle):
    """Local date the cycle represents — matches old CSV logic (end-6h, or start if in-progress)."""
    offset = _parse_offset(cycle['timezone_offset'])
    if cycle.get('end'):
        return ((_parse_iso(cycle['end']) + offset) - timedelta(hours=6)).date()
    return (_parse_iso(cycle['start']) + offset).date()

def load_whoop():
    """Return {date: {'date', 'strain', 'recovery', 'hrv', 'rhr', 'sleep_perf'}}."""
    cycles   = json.loads((API_DIR / 'cycles.json').read_text())['records']
    recovery = json.loads((API_DIR / 'recovery.json').read_text())['records']
    sleep    = json.loads((API_DIR / 'sleep.json').read_text())['records']

    rec_by_cycle = {r['cycle_id']: r for r in recovery}
    slp_by_cycle = {s['cycle_id']: s for s in sleep if not s.get('nap')}

    out = {}
    for c in cycles:
        score = c.get('score') or {}
        strain = score.get('strain')
        if strain is None:
            continue
        d = _cycle_date(c)
        r_score = (rec_by_cycle.get(c['id']) or {}).get('score') or {}
        s_score = (slp_by_cycle.get(c['id']) or {}).get('score') or {}
        out[d] = {
            'date':       d,
            'strain':     round(float(strain), 2),
            'recovery':   r_score.get('recovery_score'),
            'hrv':        r_score.get('hrv_rmssd_milli'),
            'rhr':        r_score.get('resting_heart_rate'),
            'sleep_perf': s_score.get('sleep_performance_percentage'),
        }
    return out
