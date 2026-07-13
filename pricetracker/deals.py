"""Deal detection.

A product's daily series is the minimum in-stock price across all of its
listings for each day ("best price"). Deals are judged on that series, so a
price only counts as a deal relative to what you could actually have paid
recently, not relative to one shop's history.

Two signals, either of which fires (both require min_history_days of data):

1. rolling-low: today's best price is below the minimum of the previous
   `lookback_days`, by at least `min_drop_pct`. Catches "cheapest it's been
   in a month", including slow drift to a new floor.

2. median-drop: today's best price is at least `median_drop_pct` below the
   *median* of the previous `lookback_days`. Catches sharp one-off discounts
   even when the price has been lower at some point in the window. Median,
   not mean: one day of scalper pricing or a mis-parse would drag a mean.

Bootstrap: with fewer than min_history_days but at least bootstrap_min_days
of history, alert only when today beats everything seen so far by
`bootstrap_drop_pct` — cruder, but you're not blind for the first two weeks.

Cooldown: after alerting, stay quiet for `cooldown_days` unless the price
falls another `cooldown_break_pct` below the alerted price.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, timedelta

DEFAULTS = {
    "lookback_days": 30,
    "min_history_days": 14,
    "min_drop_pct": 2.0,
    "median_drop_pct": 10.0,
    "bootstrap_min_days": 7,
    "bootstrap_drop_pct": 5.0,
    "cooldown_days": 3,
    "cooldown_break_pct": 3.0,
}


@dataclass
class Deal:
    product_id: str
    price: float
    reason: str


def best_price_series(listing_series: list[dict[date, float]]) -> dict[date, float]:
    merged: dict[date, float] = {}
    for series in listing_series:
        for day, price in series.items():
            if day not in merged or price < merged[day]:
                merged[day] = price
    return merged


def evaluate(
    product_id: str,
    today: date,
    today_best: float,
    history: dict[date, float],
    settings: dict,
    alert_state: dict | None,
) -> Deal | None:
    """history: product best-price-per-day series, which may include today.
    today_best: today's best in-stock price from the current run."""
    cfg = {**DEFAULTS, **settings}

    window_start = today - timedelta(days=cfg["lookback_days"])
    past = {d: p for d, p in history.items() if window_start <= d < today}
    all_past = {d: p for d, p in history.items() if d < today}

    deal: Deal | None = None
    if len(past) >= cfg["min_history_days"]:
        window_min = min(past.values())
        window_median = statistics.median(past.values())
        if today_best <= window_min * (1 - cfg["min_drop_pct"] / 100):
            deal = Deal(
                product_id,
                today_best,
                f"new {cfg['lookback_days']}-day low: £{today_best:.2f} vs "
                f"previous low £{window_min:.2f}",
            )
        elif today_best <= window_median * (1 - cfg["median_drop_pct"] / 100):
            pct = (1 - today_best / window_median) * 100
            deal = Deal(
                product_id,
                today_best,
                f"{pct:.0f}% below {cfg['lookback_days']}-day median "
                f"(£{window_median:.2f})",
            )
    elif len(all_past) >= cfg["bootstrap_min_days"]:
        seen_min = min(all_past.values())
        if today_best <= seen_min * (1 - cfg["bootstrap_drop_pct"] / 100):
            deal = Deal(
                product_id,
                today_best,
                f"lowest seen so far: £{today_best:.2f} vs £{seen_min:.2f} "
                f"(early signal, only {len(all_past)} days of history)",
            )

    if deal is None:
        return None

    # Cooldown: suppress repeats unless the price kept falling meaningfully.
    if alert_state:
        last_day = date.fromisoformat(alert_state["date"])
        last_price = float(alert_state["price"])
        within_cooldown = (today - last_day).days < cfg["cooldown_days"]
        broke_lower = deal.price <= last_price * (1 - cfg["cooldown_break_pct"] / 100)
        if within_cooldown and not broke_lower:
            return None
    return deal
