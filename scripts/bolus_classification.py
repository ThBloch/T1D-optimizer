"""Glooko Prime Detection rule.

Glooko's published rule for distinguishing prime taps from real
insulin injections in NovoPen 6 event streams:

    An event is a PRIME iff
      (amount <= PRIME_MAX_U)
    AND
      (another insulin event lies within PRIME_WINDOW, either before
       or after, since same-timestamp ordering in the export is
       arbitrary).

This module is the single source of truth for the rule.
`novopen_loader.load_glooko_bolus()` parses the Glooko CSV and
delegates classification here.
"""

from datetime import timedelta

PRIME_MAX_U  = 2.0
PRIME_WINDOW = timedelta(minutes=6)


def _has_neighbor_within_window(events, i):
    """True if some other event in `events` lies within +/- PRIME_WINDOW of events[i]."""
    dt, _ = events[i]
    # Look backwards
    for j in range(i - 1, -1, -1):
        if dt - events[j][0] > PRIME_WINDOW:
            break
        return True
    # Look forwards
    for j in range(i + 1, len(events)):
        if events[j][0] - dt > PRIME_WINDOW:
            break
        return True
    return False


def filter_primes(events):
    """Return `events` with prime taps removed.

    `events` must be a list of (datetime, units) tuples sorted by
    timestamp. Returns a new list, sorted, with prime entries
    dropped.
    """
    return [
        (dt, u) for i, (dt, u) in enumerate(events)
        if not (u <= PRIME_MAX_U and _has_neighbor_within_window(events, i))
    ]
