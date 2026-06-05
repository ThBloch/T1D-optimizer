"""Unit tests for scripts/clarity_coverage.py.

Run from project root:
    py -X utf8 tests/test_clarity_coverage.py
"""
import sys, unittest
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))

from clarity_coverage import (
    find_gaps, day_coverage,
    EXPECTED_PER_DAY, MIN_READINGS_COMPLETE,
)


def _cov(start, counts):
    """Build a {date: count} dict starting at `start`, one entry per count.

    A count of None means the day is absent from the dict (no readings).
    """
    out = {}
    for i, c in enumerate(counts):
        if c is not None:
            out[start + timedelta(days=i)] = c
    return out


class TestFindGaps(unittest.TestCase):

    def test_empty_coverage_returns_empty(self):
        self.assertEqual(find_gaps({}, date(2026, 6, 4)), ([], []))

    def test_all_complete_no_gaps(self):
        cov = _cov(date(2026, 6, 1), [EXPECTED_PER_DAY] * 3)  # 1,2,3 full
        ranges, gaps = find_gaps(cov, date(2026, 6, 4))       # upper = 6-3
        self.assertEqual(ranges, [])
        self.assertEqual(gaps, [])

    def test_trailing_missing_grouped(self):
        # 6-1 full; 6-2,6-3 absent; today 6-4 -> upper 6-3 -> one range 6-2..6-3
        cov = _cov(date(2026, 6, 1), [EXPECTED_PER_DAY, None, None])
        ranges, gaps = find_gaps(cov, date(2026, 6, 4))
        self.assertEqual(ranges, [(date(2026, 6, 2), date(2026, 6, 3))])
        self.assertEqual(gaps, [date(2026, 6, 2), date(2026, 6, 3)])

    def test_partial_boundary_day_flagged(self):
        # last day present but only 56/288 -> below threshold -> a gap
        cov = _cov(date(2026, 5, 28), [EXPECTED_PER_DAY, 56])
        ranges, _ = find_gaps(cov, date(2026, 5, 30))  # upper = 5-29
        self.assertEqual(ranges, [(date(2026, 5, 29), date(2026, 5, 29))])

    def test_today_excluded(self):
        # today has zero readings but must NOT be flagged (in-progress day)
        cov = _cov(date(2026, 6, 1), [EXPECTED_PER_DAY])
        ranges, gaps = find_gaps(cov, date(2026, 6, 2))  # upper = 6-1
        self.assertEqual(ranges, [])
        self.assertEqual(gaps, [])

    def test_consecutive_gaps_merge_into_one_range(self):
        # full, gap, gap, gap, full -> single interior range
        cov = _cov(date(2026, 6, 1),
                   [EXPECTED_PER_DAY, None, None, None, EXPECTED_PER_DAY])
        ranges, _ = find_gaps(cov, date(2026, 6, 6))  # upper = 6-5 (last covered day)
        self.assertEqual(ranges, [(date(2026, 6, 2), date(2026, 6, 4))])

    def test_non_consecutive_gaps_stay_separate(self):
        # gap at 6-2, full 6-3, gap 6-4 -> two distinct ranges
        cov = _cov(date(2026, 6, 1),
                   [EXPECTED_PER_DAY, None, EXPECTED_PER_DAY, None, EXPECTED_PER_DAY])
        ranges, _ = find_gaps(cov, date(2026, 6, 6))  # upper = 6-5 (last covered day)
        self.assertEqual(ranges, [(date(2026, 6, 2), date(2026, 6, 2)),
                                  (date(2026, 6, 4), date(2026, 6, 4))])

    def test_ledgered_day_excluded(self):
        # a sub-threshold day in known_empty is not reported
        cov = _cov(date(2026, 6, 1), [EXPECTED_PER_DAY, 100, EXPECTED_PER_DAY])
        known = {date(2026, 6, 2)}
        ranges, gaps = find_gaps(cov, date(2026, 6, 4), known)  # upper = 6-3 (last covered)
        self.assertEqual(ranges, [])
        self.assertEqual(gaps, [])

    def test_lower_bound_is_first_reading_not_earlier(self):
        # coverage starts 2025-04-15; nothing before it should ever be a gap
        cov = _cov(date(2025, 4, 15), [EXPECTED_PER_DAY, None])
        _, gaps = find_gaps(cov, date(2025, 4, 18))  # upper = 4-17
        self.assertTrue(all(g >= date(2025, 4, 15) for g in gaps))
        self.assertEqual(gaps, [date(2025, 4, 16), date(2025, 4, 17)])

    def test_threshold_boundary_274_complete_273_gap(self):
        cov = _cov(date(2026, 6, 1), [MIN_READINGS_COMPLETE, MIN_READINGS_COMPLETE - 1])
        ranges, _ = find_gaps(cov, date(2026, 6, 3))  # upper = 6-2
        # 6-1 at exactly 274 is complete; 6-2 at 273 is a gap
        self.assertEqual(ranges, [(date(2026, 6, 2), date(2026, 6, 2))])


class TestDayCoverage(unittest.TestCase):

    def test_counts_readings_per_day(self):
        glucose = [
            (datetime(2025, 4, 15, 0, 0), 5.0),
            (datetime(2025, 4, 15, 0, 5), 5.1),
            (datetime(2025, 4, 15, 0, 10), 5.2),
            (datetime(2025, 4, 16, 0, 0), 6.0),
        ]
        cov = day_coverage(glucose)
        self.assertEqual(cov, {date(2025, 4, 15): 3, date(2025, 4, 16): 1})

    def test_empty_glucose_list(self):
        self.assertEqual(day_coverage([]), {})

    def test_constants_sane(self):
        self.assertEqual(EXPECTED_PER_DAY, 288)
        self.assertLess(MIN_READINGS_COMPLETE, EXPECTED_PER_DAY)
        self.assertGreater(MIN_READINGS_COMPLETE, EXPECTED_PER_DAY * 0.9)


if __name__ == '__main__':
    unittest.main(verbosity=2)
