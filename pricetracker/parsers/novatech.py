"""Novatech.co.uk product page parser.

Verified against live pages (2026-07): price is in
<meta itemprop="price" content="629.99"> with
<meta itemprop="priceCurrency" content="GBP">.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from . import ParseResult, register
from .microdata import extract_offer


@register("novatech")
def parse(html: str) -> ParseResult:
    soup = BeautifulSoup(html, "html.parser")
    return extract_offer(soup)
