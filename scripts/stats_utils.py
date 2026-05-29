"""Shared statistical helpers for analysis scripts."""

import math


def spearman(x, y):
    n = len(x)
    if n < 5:
        return None, None
    rx = sorted(range(n), key=lambda i: x[i])
    ry = sorted(range(n), key=lambda i: y[i])
    rankx = [0] * n
    ranky = [0] * n
    for r, i in enumerate(rx): rankx[i] = r + 1
    for r, i in enumerate(ry): ranky[i] = r + 1
    d2 = sum((rankx[i] - ranky[i]) ** 2 for i in range(n))
    rs = 1 - 6 * d2 / (n * (n ** 2 - 1))
    if abs(rs) >= 1.0:
        return round(rs, 3), 0.0
    t = rs * math.sqrt(n - 2) / math.sqrt(1 - rs ** 2)
    p = 2 * (1 / (1 + math.exp(1.7 * abs(t) * math.sqrt(n) / math.sqrt(n - 1))))
    return round(rs, 3), round(p, 4)


def linreg(x, y):
    n = len(x)
    mx = sum(x) / n
    my = sum(y) / n
    ssxx = sum((xi - mx) ** 2 for xi in x)
    ssxy = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    if ssxx == 0:
        return None
    b1 = ssxy / ssxx
    b0 = my - b1 * mx
    yhat = [b0 + b1 * xi for xi in x]
    ssres = sum((yi - yhi) ** 2 for yi, yhi in zip(y, yhat))
    sstot = sum((yi - my) ** 2 for yi in y)
    r2 = 1 - ssres / sstot if sstot > 0 else 0
    return b0, b1, round(r2, 4), [b0 + b1 * xi for xi in x], ssres


def residuals(x, y):
    result = linreg(x, y)
    if result is None:
        return None
    b0, b1, *_ = result
    return [yi - (b0 + b1 * xi) for xi, yi in zip(x, y)]
