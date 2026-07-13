"""Price history persistence.

One CSV per listing under data/history/, plus data/state.json for
notification cooldowns and consecutive-failure counters. Plain files so the
GitHub Actions run can commit them back to the repo — git is the database.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

HISTORY_DIR = Path("data/history")
STATE_PATH = Path("data/state.json")

FIELDS = ["timestamp_utc", "date", "price", "in_stock"]


@dataclass
class Observation:
    day: date
    price: float | None
    in_stock: bool


def _listing_path(listing_id: str) -> Path:
    return HISTORY_DIR / f"{listing_id}.csv"


def append_observation(listing_id: str, price: float | None, in_stock: bool) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path = _listing_path(listing_id)
    new_file = not path.exists()
    now = datetime.now(timezone.utc)
    with path.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp_utc": now.isoformat(timespec="seconds"),
                "date": now.date().isoformat(),
                "price": "" if price is None else f"{price:.2f}",
                "in_stock": "1" if in_stock else "0",
            }
        )


def load_daily_series(listing_id: str) -> dict[date, float]:
    """Per-day lowest in-stock price for a listing. Days where the item was
    never in stock (or had no price) are absent — unavailable is not a price."""
    path = _listing_path(listing_id)
    if not path.exists():
        return {}
    series: dict[date, float] = {}
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            if row["in_stock"] != "1" or not row["price"]:
                continue
            day = date.fromisoformat(row["date"])
            price = float(row["price"])
            if day not in series or price < series[day]:
                series[day] = price
    return series


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"alerts": {}, "failures": {}}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
