"""WHOOP cycle-to-local-date mapping.

A WHOOP cycle covers roughly one day of physiological data but its
ISO timestamps don't align with a calendar day. The convention used
across this project (matching the historical CSV behaviour) is:

  - closed cycle: local date = (end + timezone_offset - 6h).date()
  - in-progress cycle (no `end`): local date = (start + offset).date()

This module is the single source of truth for that mapping.
Imported by `whoop_loader.py`. Loader code never reimplements the
rule.
"""

from datetime import datetime, timedelta


def _parse_offset(s):
    if s == 'Z':
        return timedelta(0)
    sign = 1 if s[0] == '+' else -1
    h, m = s[1:].split(':')
    return timedelta(hours=sign * int(h), minutes=sign * int(m))


def _parse_iso(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00'))


def cycle_date_for(cycle):
    """Local date the cycle represents (end-6h, or start if in-progress)."""
    offset = _parse_offset(cycle['timezone_offset'])
    if cycle.get('end'):
        return ((_parse_iso(cycle['end']) + offset) - timedelta(hours=6)).date()
    return (_parse_iso(cycle['start']) + offset).date()
