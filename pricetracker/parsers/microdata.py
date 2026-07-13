"""Shared schema.org microdata extraction.

All three supported sites embed the product price as schema.org microdata
(itemprop="price" / itemprop="availability"), which is far more stable than
visual CSS classes: retailers maintain it for Google Shopping, so it survives
redesigns. Site modules wrap this with their own quirks.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from . import ParseResult, ParserError

# schema.org availability states that mean "you can buy this right now".
_BUYABLE = ("InStock", "LimitedAvailability", "OnlineOnly", "InStoreOnly")


def parse_price_text(text: str) -> float:
    cleaned = text.replace("£", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        raise ParserError(f"unparseable price text: {text!r}") from None


def extract_offer(soup: BeautifulSoup) -> ParseResult:
    price_tag = soup.find(attrs={"itemprop": "price"})
    if price_tag is None:
        raise ParserError("no itemprop='price' element found")
    raw = price_tag.get("content") or price_tag.get_text()
    if not raw or not raw.strip():
        raise ParserError("itemprop='price' element has no value")
    price = parse_price_text(raw)

    avail_tag = soup.find(attrs={"itemprop": "availability"})
    if avail_tag is not None:
        avail = avail_tag.get("href") or avail_tag.get("content") or ""
        in_stock = any(state in avail for state in _BUYABLE)
    else:
        # No availability markup: assume a listed price means buyable.
        in_stock = True

    currency = "GBP"
    cur_tag = soup.find(attrs={"itemprop": "priceCurrency"})
    if cur_tag is not None:
        currency = (cur_tag.get("content") or cur_tag.get_text() or "GBP").strip()

    return ParseResult(price=price, in_stock=in_stock, currency=currency)
