"""Deal-detection unit tests (run: python -m pytest or python tests/test_deals.py)."""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pricetracker.deals import best_price_series, evaluate  # noqa: E402

TODAY = date(2026, 7, 13)


def days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)


def flat_history(price: float, days: int = 30) -> dict:
    return {days_ago(i): price for i in range(1, days + 1)}


def test_no_deal_on_flat_price():
    assert evaluate("p", TODAY, 500.0, flat_history(500.0), {}, None) is None


def test_rolling_low_fires():
    hist = flat_history(500.0)
    deal = evaluate("p", TODAY, 485.0, hist, {}, None)  # 3% under the 30d low
    assert deal and "low" in deal.reason


def test_tiny_undercut_ignored():
    hist = flat_history(500.0)
    assert evaluate("p", TODAY, 499.0, hist, {}, None) is None  # only 0.2%


def test_median_drop_fires_even_if_not_a_low():
    # Was 400 once 3 weeks ago, then 500 since: 440 is no rolling low,
    # but it's 12% under the median.
    hist = flat_history(500.0)
    hist[days_ago(21)] = 400.0
    deal = evaluate("p", TODAY, 440.0, hist, {}, None)
    assert deal and "median" in deal.reason


def test_insufficient_history_stays_quiet():
    hist = {days_ago(i): 500.0 for i in range(1, 5)}  # 4 days only
    assert evaluate("p", TODAY, 300.0, hist, {}, None) is None


def test_bootstrap_all_time_low():
    hist = {days_ago(i): 500.0 for i in range(1, 9)}  # 8 days: bootstrap zone
    deal = evaluate("p", TODAY, 470.0, hist, {}, None)  # 6% under min seen
    assert deal and "early signal" in deal.reason
    assert evaluate("p", TODAY, 490.0, hist, {}, None) is None  # only 2% under


def test_cooldown_suppresses_repeat():
    hist = flat_history(500.0)
    alerted = {"date": days_ago(1).isoformat(), "price": 480.0}
    assert evaluate("p", TODAY, 480.0, hist, {}, alerted) is None


def test_cooldown_broken_by_further_drop():
    hist = flat_history(500.0)
    alerted = {"date": days_ago(1).isoformat(), "price": 480.0}
    deal = evaluate("p", TODAY, 460.0, hist, {}, alerted)  # >3% below alert
    assert deal is not None


def test_cooldown_expires():
    hist = flat_history(500.0)
    alerted = {"date": days_ago(5).isoformat(), "price": 480.0}
    assert evaluate("p", TODAY, 480.0, hist, {}, alerted) is not None


def test_best_price_series_takes_min_across_listings():
    a = {days_ago(1): 500.0, days_ago(2): 490.0}
    b = {days_ago(1): 480.0}
    merged = best_price_series([a, b])
    assert merged[days_ago(1)] == 480.0
    assert merged[days_ago(2)] == 490.0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
