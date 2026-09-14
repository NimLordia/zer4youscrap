"""Offline tests: no Selenium session and no live website requests."""

from contextlib import closing, redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, PropertyMock, patch

from zer4u.__main__ import main
from zer4u.demo import BASE_URL, HTML
from zer4u.scraper import (
    ExtractionError, _wait_for_content, category_page_url, normalize_url, parse_cards, parse_detail,
    parse_product_links, save_products, scrape, srcset_url,
)


class ParsingTests(unittest.TestCase):
    def test_hebrew_srcset_and_lazy_placeholder(self):
        products = parse_cards(HTML, BASE_URL)
        self.assertEqual(products[0].name, "זר הדגמה סינתטי – אדום")
        self.assertEqual(products[0].price, "₪123.00")
        self.assertEqual(products[0].img_url, "https://example.invalid/demo/red-large.webp")
        self.assertEqual(products[1].img_url, "https://example.invalid/demo/white.jpg")

    def test_required_field_errors_and_empty_page(self):
        with self.assertRaisesRegex(ExtractionError, "No product cards"):
            parse_cards("<html>Access denied</html>", BASE_URL)
        with self.assertRaisesRegex(ExtractionError, "Missing price"):
            parse_cards(HTML.replace('class="saleprice"', 'class="changed"'), BASE_URL)
        with self.assertRaisesRegex(ExtractionError, "no link"):
            parse_cards(HTML.replace("href=", "data-link="), BASE_URL)

    def test_card_and_link_deduplication(self):
        self.assertEqual(len(parse_cards(HTML + HTML, BASE_URL)), 2)
        self.assertEqual(len(parse_product_links(HTML + HTML, BASE_URL)), 2)

    def test_detail_original_selectors_and_image_fallback(self):
        product = parse_detail(
            '<span class="ptitle">זר סינתטי</span><span class="saleprice">₪50</span>'
            '<picture><source type="image/webp" srcset="/Media/PreloadImages/p.webp 2x"></picture>'
            '<img class="img-responsive center-block" src="../images/a.jpg">',
            "https://example.invalid/items/one",
        )
        self.assertEqual(product.name, "זר סינתטי")
        self.assertEqual(product.img_url, "https://example.invalid/images/a.jpg")
        with self.assertRaisesRegex(ExtractionError, "product name"):
            parse_detail("<h1>Unexpected page</h1>", BASE_URL)

    def test_missing_optional_image_stays_empty(self):
        html = '<div class="product_in_list"><a href="/p">p</a>' \
               '<h2 data-equalheight="prodTitle">Example</h2><span class="saleprice">1</span></div>'
        self.assertEqual(parse_cards(html, BASE_URL)[0].img_url, "")

    def test_srcset_does_not_store_descriptors_or_data_uri_fragments(self):
        self.assertEqual(srcset_url("/small.webp 1x, //cdn.example.invalid/big.webp 2x", BASE_URL),
                         "https://cdn.example.invalid/big.webp")
        self.assertEqual(srcset_url("data:image/png;base64,AAAA 4x, /ok.png 1x", BASE_URL),
                         "https://example.invalid/ok.png")
        self.assertEqual(srcset_url("/invalid.png 0w, /ok.png 320w", BASE_URL),
                         "https://example.invalid/ok.png")
        self.assertEqual(srcset_url("javascript:alert(1) 2x", BASE_URL), "")

    def test_url_normalization(self):
        self.assertEqual(normalize_url("../זר חדש#info", "https://EXAMPLE.invalid:443/catalog/"),
                         "https://example.invalid/%D7%96%D7%A8%20%D7%97%D7%93%D7%A9")
        for bad in ("", "javascript:alert(1)", "data:image/png;base64,AAAA", "https://bad host/p", "https://a.invalid:bad/p"):
            with self.subTest(url=bad), self.assertRaises(ExtractionError):
                normalize_url(bad, BASE_URL)

    def test_pagination_preserves_other_filters_and_starting_page(self):
        self.assertEqual(category_page_url("https://example.invalid/flowers?color=red&bscrp=2#top", 1),
                         "https://example.invalid/flowers?color=red&bscrp=3")
        for query in ("bscrp=no", "bscrp=0", "bscrp=1&bscrp=2"):
            with self.subTest(query=query), self.assertRaises(ValueError):
                category_page_url(f"{BASE_URL}?{query}", 0)


class StorageTests(unittest.TestCase):
    def test_upsert_updates_existing_url_and_preserves_hebrew(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "nested" / "products.sqlite3"
            products = parse_cards(HTML, BASE_URL)
            self.assertEqual(save_products(products + products, database), 2)
            save_products([replace(products[0], price="₪999")], database)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM products").fetchone()[0], 2)
                self.assertEqual(connection.execute("SELECT name, price FROM products WHERE product_url = ?",
                                                    (products[0].product_url,)).fetchone(),
                                 (products[0].name, "₪999"))

    def test_refuses_legacy_schema_without_destroying_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "legacy.sqlite3"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("CREATE TABLE products (name TEXT, price TEXT, img_url TEXT)")
                connection.execute("INSERT INTO products VALUES ('existing', '1', '')")
                connection.commit()
            with self.assertRaisesRegex(sqlite3.DatabaseError, "Legacy products schema"):
                save_products(parse_cards(HTML, BASE_URL), database)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute("SELECT name FROM products").fetchall(), [("existing",)])


class BrowserLifecycleTests(unittest.TestCase):
    def make_driver(self):
        driver = Mock()
        driver.page_source = HTML
        driver.current_url = BASE_URL
        return driver

    def test_wait_allows_existing_cards_to_hydrate_required_fields(self):
        driver = self.make_driver()
        snapshots = PropertyMock(side_effect=[HTML.replace('class="saleprice"', 'class="loading"'), HTML])
        type(driver).page_source = snapshots
        with patch("selenium.webdriver.support.wait.time.sleep"):
            _wait_for_content(driver, parse_cards, timeout=1)
        self.assertEqual(snapshots.call_count, 2)

    @patch("zer4u.scraper.time.sleep")
    @patch("zer4u.scraper._wait_for_content")
    @patch("zer4u.scraper._create_driver")
    def test_repeated_page_stops_and_browser_closes(self, create, wait, sleep):
        driver = create.return_value = self.make_driver()
        products = scrape(BASE_URL, max_pages=10, max_scrolls=2, delay=0)
        self.assertEqual(len(products), 2)
        self.assertEqual(driver.get.call_count, 2)
        self.assertEqual(driver.execute_script.call_count, 4)
        driver.quit.assert_called_once()

    @patch("zer4u.scraper._wait_for_content")
    @patch("zer4u.scraper._create_driver")
    def test_extraction_failure_closes_browser(self, create, wait):
        driver = create.return_value = self.make_driver()
        driver.page_source = "<html>Website changed</html>"
        with self.assertRaises(ExtractionError):
            scrape(BASE_URL, max_scrolls=0)
        driver.quit.assert_called_once()

    @patch("zer4u.scraper._create_driver")
    def test_setup_failure_closes_browser(self, create):
        driver = create.return_value = self.make_driver()
        driver.set_page_load_timeout.side_effect = RuntimeError("timeout setup failed")
        with self.assertRaisesRegex(RuntimeError, "timeout setup failed"):
            scrape(BASE_URL)
        driver.quit.assert_called_once()

    @patch("zer4u.scraper.time.sleep")
    @patch("zer4u.scraper._wait_for_content")
    @patch("zer4u.scraper._create_driver")
    def test_details_visits_are_bounded(self, create, wait, sleep):
        driver = create.return_value = self.make_driver()

        def navigate(url):
            driver.current_url = url
            driver.page_source = HTML if "bscrp=" in url else \
                '<span class="ptitle">Synthetic detail</span><span class="saleprice">42</span>'

        driver.get.side_effect = navigate
        products = scrape(BASE_URL, mode="details", max_products=1, max_pages=5, max_scrolls=0, delay=0)
        self.assertEqual(len(products), 1)
        self.assertEqual(driver.get.call_count, 2)
        self.assertEqual(products[0].name, "Synthetic detail")
        driver.quit.assert_called_once()

    @patch("zer4u.scraper._create_driver")
    def test_bad_limits_fail_before_browser_start(self, create):
        for options in ({"delay": -1}, {"timeout": float("nan")}, {"max_pages": 0},
                        {"max_scrolls": -1}, {"max_products": 0}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                scrape(BASE_URL, **options)
        create.assert_not_called()


class CliTests(unittest.TestCase):
    @patch("zer4u.__main__.scrape", side_effect=KeyboardInterrupt)
    def test_keyboard_interrupt_is_concise(self, live_scrape):
        with redirect_stderr(StringIO()) as output:
            self.assertEqual(main([]), 130)
        self.assertEqual(output.getvalue(), "Interrupted.\n")

    @patch("zer4u.__main__.scrape", side_effect=AssertionError("Demo must not scrape"))
    def test_demo_runs_offline_and_is_repeatable(self, live_scrape):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(StringIO()) as output:
            database = Path(directory) / "demo.sqlite3"
            self.assertEqual(main(["--demo", "--db", str(database)]), 0)
            self.assertEqual(main(["--demo", "--db", str(database)]), 0)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM products").fetchone()[0], 2)
        live_scrape.assert_not_called()
        self.assertIn("synthetic sample", output.getvalue())

    @patch("zer4u.__main__.scrape", side_effect=ExtractionError("No product cards found"))
    def test_failure_is_nonzero_and_does_not_create_database(self, live_scrape):
        with tempfile.TemporaryDirectory() as directory, redirect_stderr(StringIO()) as output:
            database = Path(directory) / "failed.sqlite3"
            self.assertEqual(main(["--db", str(database)]), 1)
            self.assertFalse(database.exists())
        self.assertIn("ExtractionError", output.getvalue())


if __name__ == "__main__":
    unittest.main()
