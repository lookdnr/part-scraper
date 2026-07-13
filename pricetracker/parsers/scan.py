"""Scan.co.uk product page parser.

Verified against live pages (2026-07): price is in
<span itemprop="price" content="539.99"> inside the addtobasket panel, with
<link itemprop="availability" href="http://schema.org/InStock">.

Quirk: when a product is not purchasable (pre-order / no stock), Scan leaves a
placeholder price of 99999.99 in the microdata with availability PreOrder.
That must never enter price history.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from . import ParseResult, register
from .microdata import extract_offer

_PLACEHOLDER_THRESHOLD = 99999.0


@register("scan")
def parse(html: str) -> ParseResult:
    soup = BeautifulSoup(html, "html.parser")
    result = extract_offer(soup)
    if result.price is not None and result.price >= _PLACEHOLDER_THRESHOLD:
        return ParseResult(price=None, in_stock=False, currency=result.currency)
    return result
