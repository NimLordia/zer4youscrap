"""Run with python -m zer4u --help."""

import argparse
import math
from pathlib import Path
import sys

from .scraper import DEFAULT_CATEGORY_URL, parse_cards, save_products, scrape


def _positive_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite number greater than zero")
    return number


def _nonnegative_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must be a finite nonnegative number")
    return number


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def _nonnegative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m zer4u", description="Extract Zer4U products into SQLite using the original selectors.")
    parser.add_argument("--demo", action="store_true", help="use synthetic examples; no browser or network")
    parser.add_argument("--category-url", default=DEFAULT_CATEGORY_URL, help="category URL; preserves filters and starting bscrp")
    parser.add_argument("--db", type=Path, help="SQLite destination (default: data/zer4u_products.sqlite3; demo uses data/zer4u_demo.sqlite3)")
    parser.add_argument("--mode", choices=("cards", "details"), default="cards", help="parse category cards or visit product detail pages")
    parser.add_argument("--timeout", type=_positive_float, default=30, help="page-load and selector-wait limit in seconds (default: 30)")
    parser.add_argument("--delay", type=_nonnegative_float, default=2, help="seconds between page loads/scrolls (default: 2)")
    parser.add_argument("--max-pages", type=_positive_int, default=1, help="maximum bscrp category pages (default: 1)")
    parser.add_argument("--max-scrolls", type=_nonnegative_int, default=3, help="maximum scroll-to-bottom attempts per page (default: 3)")
    parser.add_argument("--max-products", type=_positive_int, default=100, help="maximum products saved or detail pages visited (default: 100)")
    args = parser.parse_args(argv)
    database = args.db or Path("data/zer4u_demo.sqlite3" if args.demo else "data/zer4u_products.sqlite3")
    try:
        if args.demo:
            from .demo import BASE_URL, HTML

            products = parse_cards(HTML, BASE_URL)[:args.max_products]
            print("Demo: synthetic sample records; no network or browser used.")
        else:
            products = scrape(args.category_url, mode=args.mode, timeout=args.timeout,
                              delay=args.delay, max_pages=args.max_pages,
                              max_scrolls=args.max_scrolls, max_products=args.max_products)
        count = save_products(products, database)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"Error: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print(f"Saved {count} unique product(s) to {database}. Existing URLs are updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
