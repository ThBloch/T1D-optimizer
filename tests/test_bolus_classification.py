"""Unit tests for scripts/bolus_classification.py.

Run from project root:
    py -X utf8 -m unittest tests.test_bolus_classification -v
Or directly:
    py -X utf8 tests/test_bolus_classification.py
"""
import sys, unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))

from bolus_classification import filter_primes, PRIME_MAX_U, PRIME_WINDOW


T0 = datetime(2026, 1, 1, 12, 0)


def _at(minutes_offset, units):
    return (T0 + timedelta(minutes=minutes_offset), units)


class TestFilterPrimes(unittest.TestCase):

    def test_empty_input(self):
        self.assertEqual(filter_primes([]), [])

    def test_single_non_prime_event_returned_as_is(self):
        events = [_at(0, 10.0)]
        self.assertEqual(filter_primes(events), events)

    def test_single_small_event_with_no_neighbor_is_not_prime(self):
        # 1u alone (no neighbour within PRIME_WINDOW) is a real micro-dose, not a prime.
        events = [_at(0, 1.0)]
        self.assertEqual(filter_primes(events), events)

    def test_prime_filtered_when_followed_within_window(self):
        # 1u then 10u within window -> 1u dropped, 10u kept.
        events = [_at(0, 1.0), _at(2, 10.0)]
        self.assertEqual(filter_primes(events), [_at(2, 10.0)])

    def test_small_event_after_window_not_filtered(self):
        # 1u then 10u, but gap > PRIME_WINDOW -> both retained.
        events = [_at(0, 1.0), _at(20, 10.0)]
        self.assertEqual(filter_primes(events), events)

    def test_prime_filtered_bidirectionally(self):
        # 10u first, then 1u within window -> 1u still filtered (lookback hits the 10u).
        events = [_at(0, 10.0), _at(2, 1.0)]
        self.assertEqual(filter_primes(events), [_at(0, 10.0)])

    def test_boundary_at_prime_max_u(self):
        # Exactly PRIME_MAX_U (2.0) with neighbour -> filtered.
        # Just above (2.1) with same neighbour -> retained.
        e_at_max  = [_at(0, PRIME_MAX_U),       _at(2, 10.0)]
        e_above   = [_at(0, PRIME_MAX_U + 0.1), _at(2, 10.0)]
        self.assertEqual(filter_primes(e_at_max), [_at(2, 10.0)])
        self.assertEqual(filter_primes(e_above), e_above)

    def test_boundary_at_prime_window(self):
        # Exactly PRIME_WINDOW (6 min) gap to neighbour -> filtered (strict-greater-than
        # break condition means "<=" stays inside the window).
        # Just above PRIME_WINDOW -> retained.
        window_minutes = int(PRIME_WINDOW.total_seconds() / 60)
        e_at_boundary = [_at(0, 1.0), _at(window_minutes, 10.0)]
        e_above       = [_at(0, 1.0), _at(window_minutes + 1, 10.0)]
        self.assertEqual(filter_primes(e_at_boundary), [_at(window_minutes, 10.0)])
        self.assertEqual(filter_primes(e_above), e_above)


if __name__ == '__main__':
    unittest.main(verbosity=2)
