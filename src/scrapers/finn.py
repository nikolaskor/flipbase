"""FINN.no scraper (Playwright).

Henter nye annonser per kategori. Holder volumet lavt og feiler mykt.
Selektorene under er plassholdere: FINN endrer DOM jevnlig, sa de
ma verifiseres mot live HTML naar du bygger.
"""
from __future__ import annotations

from datetime import datetime, timezone

from playwright.async_api import async_playwright
from tenacity import retry, stop_after_attempt, wait_exponential

from src.models.schemas import Category, RawListing
from src.scrapers.base import BaseScraper


class FinnScraper(BaseScraper):
    source = "finn"

    def __init__(self, headless: bool = True):
        self.headless = headless

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20))
    async def fetch_new(self, category: Category, search_filter: dict) -> list[RawListing]:
        url = self._build_url(search_filter)
        results: list[RawListing] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36"
                )
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

            # TODO: verifiser selektorer mot live FINN-HTML
            cards = await page.query_selector_all("article")
            for card in cards:
                try:
                    results.append(await self._parse_card(card))
                except Exception:
                    # En enkelt kortfeil skal aldri rive hele kjoringen
                    continue

            await browser.close()

        return results

    async def _parse_card(self, card) -> RawListing:
        """Plassholder-parsing. Fyll inn faktiske selektorer."""
        title = (await self._text(card, "h2")) or ""
        href = await self._attr(card, "a", "href") or ""
        price_text = (await self._text(card, "[class*=price]")) or ""

        return RawListing(
            external_id=self._id_from_url(href),
            title=title.strip(),
            price=self._parse_price(price_text),
            description="",          # hentes ved a aapne detaljsiden
            image_urls=[],           # hentes ved a aapne detaljsiden
            location="",
            seller_name="",
            posted_at=datetime.now(timezone.utc),
            url=href,
        )

    # --- hjelpere ---------------------------------------------------------

    def _build_url(self, search_filter: dict) -> str:
        base = "https://www.finn.no/recommerce/forsale/search"
        query = search_filter.get("query", "")
        return f"{base}?q={query}&sort=PUBLISHED_DESC"

    @staticmethod
    def _parse_price(text: str) -> int | None:
        digits = "".join(ch for ch in text if ch.isdigit())
        return int(digits) if digits else None

    @staticmethod
    def _id_from_url(url: str) -> str:
        return url.rstrip("/").split("/")[-1] if url else ""

    @staticmethod
    async def _text(node, selector: str) -> str | None:
        el = await node.query_selector(selector)
        return await el.inner_text() if el else None

    @staticmethod
    async def _attr(node, selector: str, attr: str) -> str | None:
        el = await node.query_selector(selector)
        return await el.get_attribute(attr) if el else None
