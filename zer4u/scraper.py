"""Original Zer4U selectors, with offline parsing and bounded browser collection."""

from dataclasses import dataclass
from pathlib import Path
import math
import re
import sqlite3
import time
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup


DEFAULT_CATEGORY_URL = "https://www.zer4u.co.il/זרי_פרחים"
CARD_SELECTOR = "div.product_in_list"


class ExtractionError(ValueError):
    """The HTML did not contain the required product data."""


@dataclass(frozen=True)
class Product:
    product_url: str
    name: str
    price: str
    img_url: str = ""


def normalize_url(value: str, base_url: str) -> str:
    """Resolve HTTP(S) URLs, encode Unicode/spaces, and remove fragments."""
    if not value or not value.strip():
        raise ExtractionError("Missing URL")
    candidate = value.strip()
    if any(character.isspace() for character in candidate):
        # Spaces in paths are permitted and encoded; control characters are not.
        if any(character in candidate for character in "\r\n\t"):
            raise ExtractionError("URL contains a control character")
    try:
        parts = urlsplit(urljoin(base_url, candidate))
    except ValueError as error:
        raise ExtractionError(f"Invalid URL: {value!r}") from error
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ExtractionError(f"Expected an HTTP(S) URL: {value!r}")
    if parts.username or parts.password:
        raise ExtractionError("URLs containing credentials are not supported")
    if re.search(r"[\s\\]", parts.netloc):
        raise ExtractionError("URL has an invalid hostname")
    try:
        host = parts.hostname.encode("idna").decode("ascii").lower()
        if ":" in host:  # IPv6 literals need brackets when rebuilding netloc.
            host = f"[{host}]"
        port = parts.port
    except (ValueError, UnicodeError) as error:
        raise ExtractionError(f"Invalid URL: {value!r}") from error
    scheme = parts.scheme.lower()
    if port is not None and (scheme, port) not in {("https", 443), ("http", 80)}:
        host += f":{port}"
    return urlunsplit((scheme, host, quote(parts.path or "/", safe="/%:@!$&'()*+,;="),
                       quote(parts.query, safe="%=&?/:;+,$@!()*'"), ""))


def _usable_image(value: str, base_url: str) -> str:
    if "media/preloadimages" in value.lower():
        return ""
    try:
        return normalize_url(value, base_url)
    except (ExtractionError, ValueError):
        return ""


def srcset_url(srcset: str, base_url: str) -> str:
    """Choose the largest valid HTTP(S) candidate from a normal w/x srcset."""
    candidates = []
    # A comma may belong to a URL (especially a data URI). Consume the URL
    # token before splitting descriptors, instead of blindly splitting commas.
    position = 0
    while position < len(srcset):
        while position < len(srcset) and (srcset[position].isspace() or srcset[position] == ","):
            position += 1
        match = re.match(r"\S+", srcset[position:])
        if match is None:
            break
        candidate = match.group()
        position += len(candidate)
        if candidate.endswith(","):
            candidate = candidate.rstrip(",")
            descriptors = []
        else:
            end = srcset.find(",", position)
            end = len(srcset) if end == -1 else end
            descriptors = srcset[position:end].split()
            position = end + 1
        if len(descriptors) > 1:
            continue
        score = 1.0
        if descriptors:
            descriptor = descriptors[0]
            if descriptor[-1:] not in {"w", "x"}:
                continue
            try:
                score = float(descriptor[:-1])
            except ValueError:
                continue
            if not 0 < score < float("inf"):
                continue
        resolved = _usable_image(candidate, base_url)
        if resolved:
            candidates.append((score, resolved))
    return max(candidates, key=lambda item: item[0])[1] if candidates else ""


def _image_url(node, base_url: str, *, detail: bool = False) -> str:
    sources = node.select("picture source[type='image/webp']") + node.select("picture source")
    images = node.select("img.img-responsive.center-block") if detail else node.select("div.image img")
    for image in sources + images:
        for attribute in ("data-srcset", "srcset"):
            resolved = srcset_url(image.get(attribute, ""), base_url)
            if resolved:
                return resolved
        for attribute in ("data-src", "src"):
            resolved = _usable_image(image.get(attribute, ""), base_url)
            if resolved:
                return resolved
    return ""


def _required_text(node, selector: str, label: str) -> str:
    element = node.select_one(selector)
    value = element.get_text(" ", strip=True) if element else ""
    if not value:
        raise ExtractionError(f"Missing {label} (selector: {selector})")
    return value


def _cards(html: str):
    cards = BeautifulSoup(html, "html.parser").select(CARD_SELECTOR)
    if not cards:
        raise ExtractionError(f"No product cards found ({CARD_SELECTOR}); check the URL or selectors")
    return cards


def _card_url(card, base_url: str) -> str:
    link = card.select_one("a[href]")
    if link is None:
        raise ExtractionError("Product card has no link")
    return normalize_url(link.get("href", ""), base_url)


def parse_product_links(html: str, base_url: str) -> list[str]:
    return list(dict.fromkeys(_card_url(card, base_url) for card in _cards(html)))


def parse_cards(html: str, base_url: str) -> list[Product]:
    """Extract required URL/name/price; absent or placeholder images become empty."""
    products = {}
    for card in _cards(html):
        product_url = _card_url(card, base_url)
        product = Product(
            product_url=product_url,
            name=_required_text(card, "h2[data-equalheight='prodTitle']", "product name"),
            price=_required_text(card, "span.saleprice", "price"),
            img_url=_image_url(card, base_url),
        )
        products[product_url] = product
    return list(products.values())


def parse_detail(html: str, product_url: str) -> Product:
    page = BeautifulSoup(html, "html.parser")
    return Product(
        product_url=normalize_url(product_url, product_url),
        name=_required_text(page, "span.ptitle", "product name"),
        price=_required_text(page, "span.saleprice", "price"),
        img_url=_image_url(page, product_url, detail=True),
    )


def category_page_url(category_url: str, offset: int) -> str:
    """Increment the original bscrp page parameter while retaining other filters."""
    parts = urlsplit(normalize_url(category_url, category_url))
    query = parse_qsl(parts.query, keep_blank_values=True)
    starts = [value for key, value in query if key == "bscrp"]
    try:
        if len(starts) > 1:
            raise ValueError
        start = int(starts[0]) if starts else 1
        if start < 1 or offset < 0:
            raise ValueError
    except ValueError as error:
        raise ValueError("bscrp must be a single positive integer") from error
    query = [(key, value) for key, value in query if key != "bscrp"]
    query.append(("bscrp", str(start + offset)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def _create_driver():
    # Selenium is only needed for a live run, never for imports, fixtures or --demo.
    from selenium import webdriver

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    return webdriver.Chrome(options=options)


def _wait_for_content(driver, parse_page, timeout: float) -> None:
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.support.ui import WebDriverWait

    last_error = "Required product content is missing"

    def content_ready(current_driver):
        nonlocal last_error
        try:
            parse_page(current_driver.page_source, current_driver.current_url)
        except ExtractionError as error:
            last_error = str(error)
            return False
        return True

    try:
        # Containers may appear before their text/links hydrate. Wait for the
        # same required fields that extraction uses, not just element presence.
        WebDriverWait(driver, timeout, poll_frequency=0.25).until(content_ready)
    except TimeoutException as error:
        raise ExtractionError(f"Timed out waiting for product content: {last_error}") from error


def scrape(category_url: str = DEFAULT_CATEGORY_URL, *, mode: str = "cards",
           timeout: float = 30, delay: float = 2, max_pages: int = 1,
           max_scrolls: int = 3, max_products: int = 100) -> list[Product]:
    """Collect a bounded category run, failing visibly if required fields disappear.

    Pagination stops when a page provides no unseen product URLs. Empty pages
    are treated as extraction errors because no site's empty-state is verified.
    """
    if mode not in {"cards", "details"}:
        raise ValueError("mode must be cards or details")
    if (not math.isfinite(timeout) or timeout <= 0 or not math.isfinite(delay) or delay < 0
            or max_pages < 1 or max_scrolls < 0 or max_products < 1):
        raise ValueError("Invalid collection limits")
    category_page_url(category_url, 0)  # Validate before launching a browser.
    driver = _create_driver()
    try:
        driver.set_page_load_timeout(timeout)
        products = {}
        links = {}
        parse_category = parse_cards if mode == "cards" else parse_product_links
        for offset in range(max_pages):
            page_url = category_page_url(category_url, offset)
            if offset:
                time.sleep(delay)
            driver.get(page_url)
            _wait_for_content(driver, parse_category, timeout)
            page_products = {}
            page_links = {}
            for scroll in range(max_scrolls + 1):
                if scroll:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(delay)
                    _wait_for_content(driver, parse_category, timeout)
                # Parse every snapshot so virtualized cards are not lost on scroll.
                html = driver.page_source
                base_url = driver.current_url
                if mode == "cards":
                    for product in parse_cards(html, base_url):
                        page_products[product.product_url] = product
                else:
                    page_links.update(dict.fromkeys(parse_product_links(html, base_url)))
            if mode == "cards":
                new_urls = page_products.keys() - products.keys()
                products.update(page_products)
                if not new_urls or len(products) >= max_products:
                    break
            else:
                new_urls = page_links.keys() - links.keys()
                links.update(page_links)
                if not new_urls or len(links) >= max_products:
                    break
        if mode == "details":
            for product_url in list(links)[:max_products]:
                time.sleep(delay)
                driver.get(product_url)
                _wait_for_content(driver, parse_detail, timeout)
                # Retain the category's identity URL if the browser redirects.
                parsed = parse_detail(driver.page_source, driver.current_url)
                products[product_url] = Product(product_url, parsed.name, parsed.price, parsed.img_url)
        result = list(products.values())[:max_products]
        if not result:
            raise ExtractionError("No products extracted")
        return result
    finally:
        driver.quit()


def save_products(products: list[Product], database: str | Path) -> int:
    """Upsert by product URL in one transaction; never silently mix old schemas."""
    if not products:
        raise ExtractionError("No products to save")
    path = Path(database)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY,
                    product_url TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    price TEXT NOT NULL,
                    img_url TEXT NOT NULL DEFAULT ''
                )
            """)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(products)")}
            if not {"product_url", "name", "price", "img_url"}.issubset(columns):
                raise sqlite3.DatabaseError(
                    "Legacy products schema detected; choose a new --db path. Existing data was not migrated."
                )
            connection.executemany("""
                INSERT INTO products (product_url, name, price, img_url) VALUES (?, ?, ?, ?)
                ON CONFLICT(product_url) DO UPDATE SET
                    name = excluded.name, price = excluded.price, img_url = excluded.img_url
            """, [(item.product_url, item.name, item.price, item.img_url) for item in products])
        return len({item.product_url for item in products})
    finally:
        connection.close()
