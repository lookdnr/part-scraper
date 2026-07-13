#!/usr/bin/env python3
"""CLI entry point.

  python run.py                 normal run: fetch, record history, notify
  python run.py --dry-run       fetch and evaluate but write/send nothing
  python run.py --product ID    only check one product (parser debugging)
  python run.py -v              verbose logging
"""

import argparse
import logging
import sys

from pricetracker.runner import run


def main() -> int:
    ap = argparse.ArgumentParser(description="UK PC part price tracker")
    ap.add_argument("--config", default="config/products.yaml")
    ap.add_argument("--dry-run", action="store_true", help="no history writes, no notifications")
    ap.add_argument("--product", help="only run one product id")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return run(args.config, dry_run=args.dry_run, only_product=args.product)


if __name__ == "__main__":
    sys.exit(main())
