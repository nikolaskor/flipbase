"""Offline-tester for FINN-parseren.

Kjorer mot fikstur-HTML via Playwright `set_content`, sa de trenger hverken
nett eller live FINN. Fiksturen etterligner FINN sin struktur (annonsekort med
lenke til /item/<id>, tittel, pris, bilde). De verifiserer at parseren henter
rett data ut av den strukturen, ikke at strukturen matcher live FINN, den
maa fortsatt verifiseres med `scripts/verify_finn.py` mot ekte HTML.

Rene hjelpere (pris/ID/URL) testes uten browser.
"""
from __future__ import annotations

import asyncio
import os

import pytest

from src.scrapers.finn import FinnScraper

# Forhaandsinstallert Chromium i dette miljoet bruker gammel headless-modus,
# som bare headless_shell stotter. Lokalt/Railway faller dette tilbake til
# Playwright sin egen chromium.
_DEFAULT_SHELL = "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell"
EXECUTABLE_PATH = os.getenv("PLAYWRIGHT_EXECUTABLE_PATH") or (
    _DEFAULT_SHELL if os.path.exists(_DEFAULT_SHELL) else None
)

SEARCH_FIXTURE = """
<!doctype html><html><body>
<main>
  <article>
    <a href="/recommerce/forsale/item/388123456" aria-label="iPhone 13 128GB">
      <img src="https://images.finncdn.no/dynamic/480w/2024/iphone13.jpg">
      <h2>iPhone 13 128GB Blue</h2>
    </a>
    <span>2 500 kr</span>
    <span>Frakt 149 kr</span>
  </article>
  <article>
    <a href="/recommerce/forsale/item/388999000">
      <img srcset="https://images.finncdn.no/small.jpg 480w, https://images.finncdn.no/big.jpg 960w">
      <h2>Apple iPhone 14 Pro 256 GB</h2>
    </a>
    <span>7 900 kr</span>
  </article>
  <article>
    <a href="https://www.finn.no/bap/forsale/ad.html?finnkode=300111222">
      <h2>iPhone 12 64GB</h2>
    </a>
    <div>Pris: 1 999 kr</div>
  </article>
  <article>
    <a href="/recommerce/forsale/item/388123456">
      <h2>iPhone 13 128GB (duplikat)</h2>
    </a>
    <span>2 500 kr</span>
  </article>
  <article><h2>Reklamekort uten annonselenke</h2></article>
</main>
</body></html>
"""

DETAIL_FIXTURE = """
<!doctype html><html><head>
  <meta property="og:description" content="Pent brukt iPhone 13, 128GB, ingen riper. Kvittering finnes.">
  <meta property="og:image" content="https://images.finncdn.no/dynamic/1600w/main.jpg">
</head><body>
  <img src="https://images.finncdn.no/dynamic/1600w/img1.jpg">
  <img src="https://images.finncdn.no/dynamic/1600w/img2.jpg">
  <img src="https://www.example.com/tracking-pixel.gif">
</body></html>
"""


async def _extract(html: str):
    from playwright.async_api import async_playwright

    scraper = FinnScraper(executable_path=EXECUTABLE_PATH)
    async with async_playwright() as p:
        kwargs = {"headless": True}
        if EXECUTABLE_PATH:
            kwargs["executable_path"] = EXECUTABLE_PATH
        browser = await p.chromium.launch(**kwargs)
        page = await browser.new_page()
        await page.set_content(html)
        cards = await scraper._extract_cards(page)
        await browser.close()
    return cards


async def _detail(html: str):
    from playwright.async_api import async_playwright

    scraper = FinnScraper(executable_path=EXECUTABLE_PATH)
    async with async_playwright() as p:
        kwargs = {"headless": True}
        if EXECUTABLE_PATH:
            kwargs["executable_path"] = EXECUTABLE_PATH
        browser = await p.chromium.launch(**kwargs)
        page = await browser.new_page()
        await page.set_content(html)
        result = await scraper._parse_detail(page)
        await browser.close()
    return result


def _run(coro):
    try:
        return asyncio.run(coro)
    except Exception as e:  # noqa: BLE001
        if "executable" in str(e).lower() or "headless" in str(e).lower():
            pytest.skip(f"Chromium ikke tilgjengelig for offline browser-test: {e}")
        raise


# --- browser-baserte parser-tester ------------------------------------------

def test_extract_cards_parses_listings():
    cards = _run(_extract(SEARCH_FIXTURE))
    by_id = {c.external_id: c for c in cards}

    # Duplikat slaas sammen, kort uten annonselenke ignoreres.
    assert set(by_id) == {"388123456", "388999000", "300111222"}

    first = by_id["388123456"]
    assert first.title == "iPhone 13 128GB Blue"
    assert first.price == 2500  # tar pris, ikke frakt
    assert first.image_urls == ["https://images.finncdn.no/dynamic/480w/2024/iphone13.jpg"]
    assert first.url == "https://www.finn.no/recommerce/forsale/item/388123456"

    # srcset-bilde plukkes naar src mangler.
    assert by_id["388999000"].image_urls == ["https://images.finncdn.no/small.jpg"]
    assert by_id["388999000"].price == 7900

    # finnkode-lenke gir rett ID og pris.
    assert by_id["300111222"].price == 1999


def test_parse_detail_extracts_description_and_images():
    description, images = _run(_detail(DETAIL_FIXTURE))
    assert description.startswith("Pent brukt iPhone 13")
    # og:image forst, deretter finncdn-bilder, ikke-finncdn filtreres bort.
    assert images == [
        "https://images.finncdn.no/dynamic/1600w/main.jpg",
        "https://images.finncdn.no/dynamic/1600w/img1.jpg",
        "https://images.finncdn.no/dynamic/1600w/img2.jpg",
    ]


# --- rene hjelpere (ingen browser) ------------------------------------------

def test_id_from_url_variants():
    f = FinnScraper._id_from_url
    assert f("/recommerce/forsale/item/388123456") == "388123456"
    assert f("https://www.finn.no/recommerce/forsale/item/388123456?utm=x") == "388123456"
    assert f("https://www.finn.no/bap/forsale/ad.html?finnkode=300111222") == "300111222"
    assert f("/recommerce/forsale/search?q=iphone") == ""
    assert f("") == ""


def test_parse_price_picks_amount():
    f = FinnScraper._parse_price
    assert f("2 500 kr") == 2500
    assert f("Pris: 1 999 kr Frakt 149 kr") == 1999
    assert f("Gis bort") is None
    assert f("") is None


def test_build_url():
    url = FinnScraper()._build_url({"query": "iphone"})
    assert url == "https://www.finn.no/recommerce/forsale/search?q=iphone&sort=PUBLISHED_DESC"
