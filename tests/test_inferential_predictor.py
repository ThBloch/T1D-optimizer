"""Unit tests for the three pure utility functions in inferential_predictor.py.

main() loads real data files and is excluded. Only spearman_np, multi_residuals,
and f_test_nested are tested here.

Run from project root:
    py -X utf8 tests/test_inferential_predictor.py
"""
import sys, unittest
import numpy as np
from pathlib import Path
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
from inferential_predictor import spearman_np, multi_residuals, f_test_nested


class TestSpearmanNp(unittest.TestCase):

    def test_too_short_returns_none(self):
        r, p = spearman_np([1, 2, 3], [1, 2, 3])
        self.assertIsNone(r)
        self.assertIsNone(p)

    def test_exactly_four_returns_none(self):
        r, p = spearman_np([1, 2, 3, 4], [4, 3, 2, 1])
        self.assertIsNone(r)
        self.assertIsNone(p)

    def test_perfect_positive_correlation(self):
        r, p = spearman_np([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
        self.assertAlmostEqual(r, 1.0, places=10)
        self.assertAlmostEqual(p, 0.0, places=5)

    def test_perfect_negative_correlation(self):
        r, p = spearman_np([1, 2, 3, 4, 5], [5, 4, 3, 2, 1])
        self.assertAlmostEqual(r, -1.0, places=10)
        self.assertAlmostEqual(p, 0.0, places=5)

    def test_returns_floats_not_numpy_scalars(self):
        r, p = spearman_np([1, 2, 3, 4, 5], [2, 1, 4, 3, 5])
        self.assertIsInstance(r, float)
        self.assertIsInstance(p, float)


class TestMultiResiduals(unittest.TestCase):

    def _design(self, x):
        """Intercept column prepended."""
        x = np.array(x, dtype=float)
        return np.column_stack([np.ones(len(x)), x])

    def test_residuals_sum_to_zero(self):
        X = self._design([1, 2, 3, 4, 5])
        y = np.array([2.1, 3.9, 6.2, 7.8, 10.1])
        resid = multi_residuals(X, y)
        self.assertAlmostEqual(float(np.sum(resid)), 0.0, places=10)

    def test_exact_fit_has_zero_residuals(self):
        # y lies exactly on the plane spanned by X
        beta = np.array([1.0, 2.0])
        X = self._design([0, 1, 2, 3, 4])
        y = X @ beta
        resid = multi_residuals(X, y)
        self.assertTrue(np.all(np.abs(resid) < 1e-10))

    def test_residuals_orthogonal_to_columns(self):
        # OLS invariant: X^T resid = 0
        X = self._design([3, 1, 4, 1, 5])
        y = np.array([7.0, 2.5, 9.1, 3.3, 11.0])
        resid = multi_residuals(X, y)
        self.assertTrue(np.all(np.abs(X.T @ resid) < 1e-9))


class TestFTestNested(unittest.TestCase):

    def test_identical_models_gives_f_zero(self):
        f, p = f_test_nested(rss_small=4.0, rss_big=4.0, df_small=8, df_big=6, k_added=2)
        self.assertAlmostEqual(f, 0.0, places=10)
        self.assertAlmostEqual(p, 1.0, places=10)

    def test_known_f_value(self):
        # rss_small=10, rss_big=4, k_added=2, df_big=6
        # F = ((10-4)/2) / (4/6) = 3.0 / 0.6667 = 4.5
        f, p = f_test_nested(rss_small=10.0, rss_big=4.0, df_small=8, df_big=6, k_added=2)
        expected_f = 4.5
        expected_p = float(1.0 - stats.f.cdf(expected_f, 2, 6))
        self.assertAlmostEqual(f, expected_f, places=10)
        self.assertAlmostEqual(p, expected_p, places=10)

    def test_returns_floats(self):
        f, p = f_test_nested(5.0, 3.0, 10, 8, 2)
        self.assertIsInstance(f, float)
        self.assertIsInstance(p, float)


if __name__ == '__main__':
    unittest.main(verbosity=2)
