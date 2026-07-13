"""Parser registry.

Each parser is a function taking the page HTML and returning a ParseResult.
Register new sites with @register("sitekey"); listings in config/products.yaml
reference the site key.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class ParseResult:
    price: float | None  # GBP; None when the product has no buyable price
    in_stock: bool
    currency: str = "GBP"


class ParserError(Exception):
    """The page was fetched but no price could be extracted from it."""


ParserFunc = Callable[[str], ParseResult]

_REGISTRY: dict[str, ParserFunc] = {}


def register(site: str) -> Callable[[ParserFunc], ParserFunc]:
    def deco(fn: ParserFunc) -> ParserFunc:
        _REGISTRY[site] = fn
        return fn

    return deco


def get_parser(site: str) -> ParserFunc:
    try:
        return _REGISTRY[site]
    except KeyError:
        raise ParserError(f"no parser registered for site '{site}'") from None


# Import site modules for their registration side effects.
from . import scan, novatech, awdit  # noqa: E402,F401
