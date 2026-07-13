"""AWD-IT (awd-it.co.uk, Magento) product page parser.

Verified against live pages (2026-07): price appears both as
<meta itemprop="price" content="599.95"> and as OpenGraph
<meta property="product:price:amount" content="599.95">. Microdata is
primary; OpenGraph is the fallback if the microdata block disappears.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from . import ParseResult, ParserError, register
from .microdata import extract_offer, parse_price_text


@register("awdit")
def parse(html: str) -> ParseResult:
    soup = BeautifulSoup(html, "html.parser")
    try:
        return extract_offer(soup)
    except ParserError:
        og = soup.find("meta", attrs={"property": "product:price:amount"})
        if og is None or not og.get("content"):
            raise
        return ParseResult(price=parse_price_text(og["content"]), in_stock=True)
