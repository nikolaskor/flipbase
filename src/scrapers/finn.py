"""FINN.no scraper (Playwright).

Henter ferske annonser per kategori fra FINN sitt Torget-sok. Holder volumet
lavt og feiler mykt, i trad med de harde reglene i CLAUDE.md (respekter ToS,
ikke hamre serveren, en enkelt kortfeil river aldri hele kjoringen).

Selektorene er samlet som konstanter ovenfor klassen. FINN er en JS-rendret
app og bytter klassenavn ofte, sa annonsekort kjennes igjen paa lenke-monsteret
til selve annonsen (stabilt) heller enn skjore klassenavn. Tittel, pris og
bilde hentes innenfor kortet.

VERIFISER selektorene mot live HTML for produksjon. Bruk
`python -m scripts.verify_finn --dump` til a laste et ekte iPhone-sok, se hva
parseren finner og dumpe HTML for selektor-revisjon. Kjernelogikken er skilt ut
i rene metoder (`_extract_cards`, `_parse_detail`) som testes offline med
Playwright `set_content` mot fikstur-HTML i `tests/test_finn_scraper.py`.
"""
from __future__ import annotations

import asyncio
import os
import re
from urllib.parse import parse_qs, urljoin, urlparse

from tenacity import retry, stop_after_attempt, wait_exponential

from src.models.schemas import Category, RawListing
from src.scrapers.base import BaseScraper

FINN_BASE = "https://www.finn.no"
SEARCH_PATH = "/recommerce/forsale/search"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)

# --- Selektorer (VERIFISER mot live FINN-HTML) -----------------------------
# Annonsekort gjenkjennes paa lenke-monsteret, ikke klassenavn. Et kort er et
# <article> som inneholder en lenke til selve annonsen. Faller tilbake til a
# behandle hver annonselenke som sitt eget kort hvis <article> ikke brukes.
SEL_CARD = "article"
SEL_AD_LINK = "a[href*='/item/'], a[href*='finnkode=']"
SEL_TITLE = "h2, h3"
SEL_IMG = "img"
# Detaljside: hent full beskrivelse fra rendret DOM (og:description er ofte avkortet).
SEL_DESCRIPTION = '[data-testid="description"]'
SEL_DESCRIPTION_BODY = '[data-testid="description"] .whitespace-pre-wrap'
SEL_TOGGLE_DESCRIPTION = '[data-testid="toggle-description"]'
SEL_OG_DESCRIPTION = "meta[property='og:description']"
SEL_OG_IMAGE = "meta[property='og:image']"
SEL_DETAIL_IMG = "img[src*='finncdn']"

# Pris vises som "2 500 kr" / "2 500 kr". Ta forste treff (frakt kan komme etter).
PRICE_RE = re.compile(r"(\d[\d\s  ]*)\s*kr", re.IGNORECASE)
ITEM_ID_RE = re.compile(r"/item/(\d+)")

# Lavt volum: tak paa antall detaljsider per kjoring og pause mellom besok.
MAX_DETAIL_FETCHES = 25
DETAIL_DELAY_SECONDS = 1.5


class FinnScraper(BaseScraper):
    source = "finn"

    def __init__(
        self,
        headless: bool = True,
        executable_path: str | None = None,
        detail_limit: int = MAX_DETAIL_FETCHES,
        detail_delay: float = DETAIL_DELAY_SECONDS,
    ):
        self.headless = headless
        # Lar sandbox/test peke paa en forhaandsinstallert Chromium.
        self.executable_path = executable_path or os.getenv("PLAYWRIGHT_EXECUTABLE_PATH") or None
        self.detail_limit = detail_limit
        self.detail_delay = detail_delay

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20))
    async def fetch_new(self, category: Category, search_filter: dict) -> list[RawListing]:
        from playwright.async_api import async_playwright  # lazy: holder modulen importerbar uten browser

        url = self._build_url(search_filter)
        results: list[RawListing] = []

        async with async_playwright() as p:
            launch_kwargs: dict = {"headless": self.headless}
            if self.executable_path:
                launch_kwargs["executable_path"] = self.executable_path
            browser = await p.chromium.launch(**launch_kwargs)
            context = await browser.new_context(
                user_agent=USER_AGENT,
                locale="nb-NO",
                timezone_id="Europe/Oslo",
                viewport={"width": 1366, "height": 900},
                extra_http_headers={"Accept-Language": "nb-NO,nb;q=0.9,en;q=0.8"},
            )
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                # Vent mykt paa at minst en annonselenke dukker opp.
                try:
                    await page.wait_for_selector(SEL_AD_LINK, timeout=10_000)
                except Exception:
                    pass
                results = await self._extract_cards(page)
                await self._enrich(context, results)
            finally:
                await browser.close()

        return results

    # --- ekstrahering (rene metoder, testes offline) ----------------------

    async def _extract_cards(self, page) -> list[RawListing]:
        """Parser sokeresultatsiden til RawListing-er. Dedupliserer paa ID."""
        results: list[RawListing] = []
        seen: set[str] = set()

        for card in await page.query_selector_all(SEL_CARD):
            link = await card.query_selector(SEL_AD_LINK)
            if link is None:
                continue
            raw = await self._safe_build(card, link)
            if raw and raw.external_id not in seen:
                seen.add(raw.external_id)
                results.append(raw)

        # Fallback: ingen <article>-kort (eller ingen med annonselenke). Behandle
        # hver annonselenke som sitt eget kort via naermeste forfar.
        if not results:
            for link in await page.query_selector_all(SEL_AD_LINK):
                card = (
                    await link.query_selector("xpath=ancestor::article[1]")
                    or await link.query_selector("xpath=ancestor::li[1]")
                    or link
                )
                raw = await self._safe_build(card, link)
                if raw and raw.external_id not in seen:
                    seen.add(raw.external_id)
                    results.append(raw)

        return results

    async def _safe_build(self, card, link) -> RawListing | None:
        """En enkelt kortfeil skal aldri rive hele kjoringen."""
        try:
            return await self._build_raw(card, link)
        except Exception:
            return None

    async def _build_raw(self, card, link) -> RawListing | None:
        href = await link.get_attribute("href") or ""
        external_id = self._id_from_url(href)
        if not external_id:
            return None

        title = (
            (await self._text(card, SEL_TITLE))
            or (await link.inner_text())
            or (await link.get_attribute("aria-label"))
            or ""
        )
        price = self._parse_price(await card.inner_text())
        image = await self._first_image(card)

        return RawListing(
            external_id=external_id,
            title=title.strip(),
            price=price,
            image_urls=[image] if image else [],
            url=self._abs_url(href),
        )

    async def _enrich(self, context, results: list[RawListing]) -> None:
        """Aapner detaljsiden for a hente beskrivelse + bilde-URLer.

        Lavt volum: maks `detail_limit` sider per kjoring, pause mellom hver.
        """
        if not results:
            return
        page = await context.new_page()
        try:
            for raw in results[: self.detail_limit]:
                try:
                    await page.goto(raw.url, wait_until="domcontentloaded", timeout=30_000)
                    try:
                        await page.wait_for_selector(SEL_DESCRIPTION, timeout=10_000)
                    except Exception:
                        pass
                    description, images = await self._parse_detail(page)
                    if description:
                        raw.description = description
                    if images:
                        raw.image_urls = images
                except Exception:
                    # Feil paa en detaljside skal ikke stoppe resten.
                    continue
                await asyncio.sleep(self.detail_delay)
        finally:
            await page.close()

    async def _parse_detail(self, page) -> tuple[str, list[str]]:
        """Henter full beskrivelse fra detaljsiden og bilde-URLer."""
        description = await self._extract_description(page)

        images: list[str] = []
        og_image = await self._meta(page, SEL_OG_IMAGE)
        if og_image:
            images.append(og_image)
        for img in await page.query_selector_all(SEL_DETAIL_IMG):
            src = await img.get_attribute("src")
            if src and src not in images:
                images.append(src)

        return description.strip(), images

    async def _extract_description(self, page) -> str:
        """Henter full beskrivelse fra rendret DOM. Klikker utvid-knapp om den finnes."""
        try:
            toggle = await page.query_selector(SEL_TOGGLE_DESCRIPTION)
            if toggle:
                # JS-klikk fungerer selv naar knappen er skjult av CSS (read-more).
                await page.evaluate("(el) => el.click()", toggle)

            body = await page.query_selector(SEL_DESCRIPTION_BODY)
            if body:
                return self._clean_description(await body.inner_text())

            root = await page.query_selector(SEL_DESCRIPTION)
            if root:
                return self._clean_description(await root.inner_text())
        except Exception:
            pass

        return (await self._meta(page, SEL_OG_DESCRIPTION) or "").strip()

    @staticmethod
    def _clean_description(text: str) -> str:
        """Fjerner overskrift, utvid-knapp og hjelpetekst fra beskrivelsesfeltet."""
        cleaned = text.strip()
        if cleaned.lower().startswith("beskrivelse"):
            cleaned = cleaned[len("beskrivelse"):].strip()
        cleaned = re.sub(r"\s*Vis hele beskrivelsen\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*NB:.*$", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
        return cleaned.strip()

    # --- hjelpere ---------------------------------------------------------

    def _build_url(self, search_filter: dict) -> str:
        query = search_filter.get("query", "")
        return f"{FINN_BASE}{SEARCH_PATH}?q={query}&sort=PUBLISHED_DESC"

    @staticmethod
    def _abs_url(href: str) -> str:
        return urljoin(FINN_BASE, href) if href else ""

    @staticmethod
    def _id_from_url(url: str) -> str:
        """Henter finnkode fra /item/<id> eller ?finnkode=<id>."""
        if not url:
            return ""
        m = ITEM_ID_RE.search(url)
        if m:
            return m.group(1)
        finnkode = parse_qs(urlparse(url).query).get("finnkode")
        if finnkode:
            return finnkode[0]
        tail = url.split("?")[0].rstrip("/").split("/")[-1]
        return tail if tail.isdigit() else ""

    @staticmethod
    def _parse_price(text: str) -> int | None:
        if not text:
            return None
        m = PRICE_RE.search(text)
        if not m:
            return None
        digits = "".join(ch for ch in m.group(1) if ch.isdigit())
        return int(digits) if digits else None

    async def _first_image(self, card) -> str | None:
        img = await card.query_selector(SEL_IMG)
        if img is None:
            return None
        src = await img.get_attribute("src")
        if src and "finncdn" in src:
            return src
        srcset = await img.get_attribute("srcset")
        if srcset:
            first = srcset.split(",")[0].strip().split(" ")[0]
            if first:
                return first
        return src or None

    @staticmethod
    async def _text(node, selector: str) -> str | None:
        el = await node.query_selector(selector)
        return await el.inner_text() if el else None

    @staticmethod
    async def _attr(node, selector: str, attr: str) -> str | None:
        el = await node.query_selector(selector)
        return await el.get_attribute(attr) if el else None

    @staticmethod
    async def _meta(page, selector: str) -> str | None:
        el = await page.query_selector(selector)
        return await el.get_attribute("content") if el else None
