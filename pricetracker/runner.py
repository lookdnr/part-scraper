"""Run orchestration: fetch every listing, record history, evaluate deals,
notify. Every listing is isolated — one broken parser or dead site never
stops the rest of the run."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import deals, history, notify
from .fetch import PoliteFetcher
from .parsers import ParseResult, get_parser

log = logging.getLogger(__name__)

# After this many consecutive failed runs for a listing, push a warning so a
# silently broken parser doesn't go unnoticed for weeks.
FAILURE_ALERT_THRESHOLD = 5


@dataclass
class ListingOutcome:
    listing_id: str
    site: str
    url: str
    result: ParseResult | None = None
    error: str | None = None


def load_config(path: str | Path) -> dict:
    cfg = yaml.safe_load(Path(path).read_text())
    seen: set[str] = set()
    for product in cfg["products"]:
        for listing in product["listings"]:
            listing_id = listing.get("id") or f"{product['id']}__{listing['site']}"
            if listing_id in seen:
                raise ValueError(
                    f"duplicate listing id '{listing_id}'; give one an explicit 'id'"
                )
            seen.add(listing_id)
            listing["id"] = listing_id
    return cfg


def run(config_path: str | Path, dry_run: bool = False, only_product: str | None = None) -> int:
    cfg = load_config(config_path)
    settings = cfg.get("settings", {})
    fetcher = PoliteFetcher()
    state = history.load_state()
    today = datetime.now(timezone.utc).date()

    products = cfg["products"]
    if only_product:
        products = [p for p in products if p["id"] == only_product]
        if not products:
            log.error("no product with id '%s' in config", only_product)
            return 2

    all_outcomes: list[ListingOutcome] = []
    deals_found: list[tuple[deals.Deal, str, str]] = []  # (deal, product name, best url)

    for product in products:
        outcomes = [_check_listing(fetcher, listing) for listing in product["listings"]]
        all_outcomes.extend(outcomes)

        if not dry_run:
            for oc in outcomes:
                if oc.result is not None:
                    history.append_observation(oc.listing_id, oc.result.price, oc.result.in_stock)
                _track_failures(state, oc, product["name"])

        in_stock = [
            oc for oc in outcomes
            if oc.result and oc.result.in_stock and oc.result.price is not None
        ]
        if not in_stock:
            log.info("%s: nothing in stock today", product["id"])
            continue
        best = min(in_stock, key=lambda oc: oc.result.price)

        series = deals.best_price_series(
            [history.load_daily_series(oc.listing_id) for oc in outcomes]
        )
        deal = deals.evaluate(
            product_id=product["id"],
            today=today,
            today_best=best.result.price,
            history=series,
            settings=settings,
            alert_state=state["alerts"].get(product["id"]),
        )
        if deal:
            deals_found.append((deal, product["name"], best.url))
            if not dry_run:
                notify.send(
                    title=f"Deal: {product['name']} £{deal.price:.2f}",
                    message=f"{deal.reason}\n{best.site}: {best.url}",
                    click_url=best.url,
                    priority="high",
                )
                # Record the alert even if the push failed, so a flaky ntfy
                # doesn't cause the same deal to re-alert every run.
                state["alerts"][product["id"]] = {
                    "date": today.isoformat(),
                    "price": deal.price,
                }

    if not dry_run:
        history.save_state(state)

    _print_summary(all_outcomes, deals_found)
    failed = [oc for oc in all_outcomes if oc.error]
    return 1 if all_outcomes and len(failed) == len(all_outcomes) else 0


def _check_listing(fetcher: PoliteFetcher, listing: dict) -> ListingOutcome:
    oc = ListingOutcome(listing_id=listing["id"], site=listing["site"], url=listing["url"])
    try:
        parser = get_parser(listing["site"])
        html = fetcher.get(listing["url"])
        oc.result = parser(html)
        log.info(
            "%s: %s (in stock: %s)",
            oc.listing_id,
            f"£{oc.result.price:.2f}" if oc.result.price is not None else "no price",
            oc.result.in_stock,
        )
    except Exception as exc:  # noqa: BLE001 — isolation is the point
        oc.error = f"{type(exc).__name__}: {exc}"
        log.warning("%s failed: %s", oc.listing_id, oc.error)
    return oc


def _track_failures(state: dict, oc: ListingOutcome, product_name: str) -> None:
    failures = state.setdefault("failures", {})
    if oc.error is None:
        failures.pop(oc.listing_id, None)
        return
    count = failures.get(oc.listing_id, 0) + 1
    failures[oc.listing_id] = count
    if count == FAILURE_ALERT_THRESHOLD:
        notify.send(
            title=f"Tracker broken: {oc.listing_id}",
            message=(
                f"{product_name} on {oc.site} has failed {count} runs in a row.\n"
                f"Last error: {oc.error}\n{oc.url}"
            ),
            click_url=oc.url,
            priority="default",
        )


def _print_summary(outcomes: list[ListingOutcome], deals_found: list) -> None:
    ok = sum(1 for oc in outcomes if oc.error is None)
    print(f"\n=== Run summary: {ok}/{len(outcomes)} listings OK, {len(deals_found)} deal(s) ===")
    for oc in outcomes:
        if oc.error:
            status = f"FAILED  {oc.error}"
        elif oc.result.price is None or not oc.result.in_stock:
            status = "no buyable price (out of stock / placeholder)"
        else:
            status = f"£{oc.result.price:.2f}"
        print(f"  {oc.listing_id:50s} {status}")
    for deal, name, url in deals_found:
        print(f"  DEAL: {name} £{deal.price:.2f} — {deal.reason} — {url}")
