"""Unit tests for scripts/night_stats.py.

Run from project root:
    py -X utf8 -m unittest tests.test_night_stats -v
Or directly:
    py -X utf8 tests/test_night_stats.py
"""
import sys, unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))

from night_stats import (
    night_stats, second_half_trend,
    HYPO_THR, HYPO_CORRECTION_THR,
    CLINICAL_TIR_LO, CLINICAL_TIR_HI,
    TARGET_LO, TARGET_HI,
    SH_MIN_READINGS,
)


T0 = datetime(2026, 1, 1, 22, 0)


def _hourly(values, anchor=T0):
    """Build (datetime, value) tuples at one-hour intervals."""
    return [(anchor + timedelta(hours=i), v) for i, v in enumerate(values)]


def _by_minutes(values, step_minutes=5, anchor=T0):
    """Build (datetime, value) tuples at `step_minutes`-minute intervals."""
    return [(anchor + timedelta(minutes=step_minutes * i), v)
            for i, v in enumerate(values)]


class TestSecondHalfTrend(unittest.TestCase):

    def test_empty_returns_zero_count(self):
        slope, delta, n = second_half_trend([])
        self.assertIsNone(slope)
        self.assertIsNone(delta)
        self.assertEqual(n, 0)

    def test_insufficient_second_half_returns_none(self):
        # 10 readings -> split=5 -> sh_n=5 < SH_MIN_READINGS(10)
        readings = _hourly([6.0] * 10)
        slope, delta, n = second_half_trend(readings)
        self.assertIsNone(slope)
        self.assertIsNone(delta)
        self.assertEqual(n, 5)
        self.assertLess(n, SH_MIN_READINGS)

    def test_rising_slope_per_hour(self):
        # 20 readings hourly, values rising 0.1 mmol/L per hour.
        # Second half = readings[10:20], 10 points; slope must be 0.1/h.
        readings = _hourly([5.0 + i * 0.1 for i in range(20)])
        slope, delta, n = second_half_trend(readings)
        self.assertAlmostEqual(slope, 0.1, places=6)
        self.assertAlmostEqual(delta, 0.9, places=6)
        self.assertEqual(n, 10)

    def test_falling_slope_negative(self):
        readings = _hourly([7.0 - i * 0.1 for i in range(20)])
        slope, delta, n = second_half_trend(readings)
        self.assertAlmostEqual(slope, -0.1, places=6)
        self.assertAlmostEqual(delta, -0.9, places=6)
        self.assertEqual(n, 10)

    def test_flat_slope_distinct_timestamps(self):
        readings = _hourly([6.0] * 20)
        slope, delta, n = second_half_trend(readings)
        self.assertAlmostEqual(slope, 0.0, places=10)
        self.assertAlmostEqual(delta, 0.0, places=10)
        self.assertEqual(n, 10)

    def test_degenerate_identical_timestamps_returns_none(self):
        # All 20 readings at exactly T0 -> den == 0 -> new contract returns None.
        readings = [(T0, 6.0 + i * 0.1) for i in range(20)]
        slope, delta, n = second_half_trend(readings)
        self.assertIsNone(slope)
        self.assertIsNone(delta)
        self.assertEqual(n, 10)

    def test_narrow_window_per_hour_scaling(self):
        # 19 readings, 1 minute apart, second half spans 9 minutes.
        # Values rise 0.1 mmol/L per minute -> 6.0 mmol/L per hour.
        readings = _by_minutes([6.0 + i * 0.1 for i in range(19)], step_minutes=1)
        slope, _, n = second_half_trend(readings)
        self.assertEqual(n, 10)
        self.assertAlmostEqual(slope, 6.0, places=3)

    def test_first_half_does_not_affect_slope(self):
        # First half flat, second half rises. Slope reflects only the second half.
        values = [6.0] * 10 + [5.0 + i * 0.2 for i in range(10)]
        readings = _hourly(values)
        slope, _, n = second_half_trend(readings)
        self.assertEqual(n, 10)
        self.assertAlmostEqual(slope, 0.2, places=6)


class TestNightStats(unittest.TestCase):

    def test_empty_returns_none(self):
        self.assertIsNone(night_stats([]))

    def test_below_min_readings_returns_none(self):
        readings = _by_minutes([6.0] * 5)
        self.assertIsNone(night_stats(readings, min_readings=6))

    def test_normal_night_fields(self):
        values = [5.0, 6.0, 7.0, 5.0, 6.0, 7.0, 5.0, 6.0, 7.0, 6.0]
        readings = _by_minutes(values)
        stats = night_stats(readings)
        self.assertEqual(stats['n_readings'], 10)
        self.assertEqual(stats['fasting'], 6.0)
        self.assertEqual(stats['inj_g'], 5.0)
        self.assertEqual(stats['min_g'], 5.0)
        self.assertEqual(stats['max_g'], 7.0)
        self.assertEqual(stats['mean'], 6.0)

    def test_hypo_events_zero_when_all_above_threshold(self):
        readings = _by_minutes([5.0] * 10)
        stats = night_stats(readings)
        self.assertEqual(stats['hypo_events'], 0)
        self.assertFalse(stats['hypo_correction'])

    def test_hypo_events_single_dip(self):
        # one dip below HYPO_THR (4.0), then recovery
        values = [5.0, 3.5, 5.0, 5.5, 6.0, 6.0, 5.5, 5.0, 4.5, 4.5]
        stats = night_stats(_by_minutes(values))
        self.assertEqual(stats['hypo_events'], 1)

    def test_hypo_events_two_separate(self):
        # two distinct dips with recovery between
        values = [5.0, 3.5, 5.0, 5.5, 5.0, 3.8, 5.0, 5.0, 5.0, 5.0]
        stats = night_stats(_by_minutes(values))
        self.assertEqual(stats['hypo_events'], 2)

    def test_hypo_events_sustained_is_one_episode(self):
        # sustained sub-HYPO_THR run counts as a single episode
        values = [5.0, 3.5, 3.6, 3.7, 3.8, 5.0, 5.5, 6.0, 5.5, 5.0]
        stats = night_stats(_by_minutes(values))
        self.assertEqual(stats['hypo_events'], 1)

    def test_hypo_at_threshold_boundary_not_counted(self):
        # HYPO_THR is 4.0; strict less-than. 4.0 itself does NOT count.
        values = [5.0, 4.0, 5.0] + [5.0] * 7
        stats = night_stats(_by_minutes(values))
        self.assertEqual(stats['hypo_events'], 0)

    def test_hypo_correction_trigger(self):
        # hypo followed by max > HYPO_CORRECTION_THR (10.0)
        values = [5.0, 3.5, 5.0, 8.0, 12.0, 11.0, 10.5, 9.0, 8.0, 7.0]
        stats = night_stats(_by_minutes(values))
        self.assertTrue(stats['hypo_correction'])
        self.assertTrue(stats['correction_spike_above_10'])

    def test_hypo_correction_boundary_not_triggered(self):
        # post-hypo peak is exactly HYPO_CORRECTION_THR; strict greater-than means no trigger.
        values = [5.0, 3.5, 5.0, 8.0, 10.0, 9.5, 9.0, 8.0, 7.0, 6.0]
        stats = night_stats(_by_minutes(values))
        self.assertFalse(stats['hypo_correction'])

    def test_hypo_correction_no_hypo_no_trigger(self):
        # spike > 10.0 but no preceding hypo
        values = [5.0, 5.5, 12.0, 11.0, 10.0, 9.0, 8.0, 7.0, 6.5, 6.0]
        stats = night_stats(_by_minutes(values))
        self.assertFalse(stats['hypo_correction'])
        self.assertFalse(stats['correction_spike_above_10'])

    def test_hyper_adj_zero_when_correction(self):
        values = [5.0, 3.5, 5.0, 8.0, 12.0, 12.0, 11.0, 10.5, 9.0, 8.0]
        stats = night_stats(_by_minutes(values))
        self.assertTrue(stats['hypo_correction'])
        self.assertGreater(stats['hyper_pct'], 0)
        self.assertEqual(stats['hyper_adj'], 0.0)

    def test_hyper_adj_equals_hyper_pct_when_no_correction(self):
        values = [5.0, 5.5, 12.0, 11.0, 10.5, 9.0, 8.0, 7.0, 6.5, 6.0]
        stats = night_stats(_by_minutes(values))
        self.assertFalse(stats['hypo_correction'])
        self.assertEqual(stats['hyper_adj'], stats['hyper_pct'])

    def test_tir_target_range(self):
        # 5 readings inside [TARGET_LO, TARGET_HI] = [5.0, 8.0]
        values = [5.0, 5.5, 6.0, 7.0, 8.0, 4.5, 4.5, 9.0, 9.5, 9.0]
        stats = night_stats(_by_minutes(values))
        self.assertAlmostEqual(stats['tir'], 50.0, places=1)

    def test_tir_full_clinical_range(self):
        # 8 readings inside [CLINICAL_TIR_LO, CLINICAL_TIR_HI] = [4.0, 10.0]
        # Outside: 11.0 (above) and 3.5 (below) - but 3.5 also triggers a hypo.
        values = [4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 9.5, 11.0, 3.5]
        stats = night_stats(_by_minutes(values))
        self.assertAlmostEqual(stats['tir_full'], 80.0, places=1)

    def test_constants_imported_match_module(self):
        # Defensive: protect downstream consumers if any constant is renamed
        # or moved. If this test fails the import block at top of file is
        # the place to update.
        self.assertEqual(HYPO_THR, 4.0)
        self.assertEqual(HYPO_CORRECTION_THR, 10.0)
        self.assertEqual(CLINICAL_TIR_LO, 4.0)
        self.assertEqual(CLINICAL_TIR_HI, 10.0)
        self.assertEqual(TARGET_LO, 5.0)
        self.assertEqual(TARGET_HI, 8.0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
