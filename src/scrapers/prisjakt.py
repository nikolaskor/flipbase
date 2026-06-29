"""Prisjakt ny-prisfetcher.

Henter laveste ny-pris fra prisjakt.no for iPhone-modeller og lagrer
i Supabase. Kjoeres maksimalt en gang per dag per modell via
`maybe_refresh()` i scheduler.

Prisjakt er klientrendret (Next.js), saa vi bruker Playwright.
Selektorene maa verifiseres mot live HTML hvis prisene slutter aa dukke opp.
"""
from __future__ import annotations

import re

PRISJAKT_BASE = "https://www.prisjakt.no"

# model_key -> relativ URL paa prisjakt.no. Oppdater ved nye iPhone-modeller.
MODEL_URLS: dict[str, str] = {
    "iphone_11_64gb":   "/mobiler/apple-iphone-11-64gb",
    "iphone_11_128gb":  "/mobiler/apple-iphone-11-128gb",
    "iphone_11_256gb":  "/mobiler/apple-iphone-11-256gb",
    "iphone_12_64gb":   "/mobiler/apple-iphone-12-64gb",
    "iphone_12_128gb":  "/mobiler/apple-iphone-12-128gb",
    "iphone_12_256gb":  "/mobiler/apple-iphone-12-256gb",
    "iphone_13_128gb":  "/mobiler/apple-iphone-13-128gb",
    "iphone_13_256gb":  "/mobiler/apple-iphone-13-256gb",
    "iphone_13_512gb":  "/mobiler/apple-iphone-13-512gb",
    "iphone_14_128gb":  "/mobiler/apple-iphone-14-128gb",
    "iphone_14_256gb":  "/mobiler/apple-iphone-14-256gb",
    "iphone_14_512gb":  "/mobiler/apple-iphone-14-512gb",
    "iphone_14_plus_128gb": "/mobiler/apple-iphone-14-plus-128gb",
    "iphone_14_pro_128gb":  "/mobiler/apple-iphone-14-pro-128gb",
    "iphone_14_pro_256gb":  "/mobiler/apple-iphone-14-pro-256gb",
    "iphone_14_pro_max_256gb": "/mobiler/apple-iphone-14-pro-max-256gb",
    "iphone_15_128gb":  "/mobiler/apple-iphone-15-128gb",
    "iphone_15_256gb":  "/mobiler/apple-iphone-15-256gb",
    "iphone_15_pro_128gb":  "/mobiler/apple-iphone-15-pro-128gb",
    "iphone_15_pro_max_256gb": "/mobiler/apple-iphone-15-pro-max-256gb",
    "iphone_16_128gb":  "/mobiler/apple-iphone-16-128gb",
    "iphone_16_256gb":  "/mobiler/apple-iphone-16-256gb",
    "iphone_16_512gb":  "/mobiler/apple-iphone-16-512gb",
    "iphone_16_pro_128gb":  "/mobiler/apple-iphone-16-pro-128gb",
    "iphone_16_pro_max_256gb": "/mobiler/apple-iphone-16-pro-max-256gb",
}

# Avskrivningsfaktor: andel av ny-pris som en brukt telefon typisk selges for
# paa det norske markedet. Basert paa observerte FINN-priser relativt til Prisjakt.
# Justeres naar vi har nok egne FINN-salgdata (da brukes den dataen direkte).
DEPRECIATION: dict[str, float] = {
    "iphone_11": 0.28,
    "iphone_12": 0.34,
    "iphone_13": 0.44,
    "iphone_14": 0.52,
    "iphone_14_plus": 0.50,
    "iphone_14_pro": 0.55,
    "iphone_14_pro_max": 0.55,
    "iphone_15": 0.62,
    "iphone_15_pro": 0.65,
    "iphone_15_pro_max": 0.65,
    "iphone_16": 0.72,
    "iphone_16_pro": 0.75,
    "iphone_16_pro_max": 0.75,
}

# VERIFISER disse mot live prisjakt.no HTML.
# Prissiden er JS-rendret; vent til priscontaineren dukker opp.
SEL_PRICE_WAIT = "main"
SEL_PRICE_CONTAINER = "[class*='PriceList'], [class*='price-list'], table"

_PRICE_RE = re.compile(r"(\d[\d\s\xa0]{2,7})\s*(?:kr|,-)", re.IGNORECASE)
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def used_estimate_from_new(model_key: str, new_price: int) -> int:
    """Beregner brukt-estimat fra Prisjakt ny-pris via avskrivningsfaktor.

    Fjerner lagrings-suffiks (128gb etc.) for aa finne riktig faktor.
    Runder til naermeste 100 kr.
    """
    base = model_key
    for suffix in ("_64gb", "_128gb", "_256gb", "_512gb", "_1tb"):
        base = base.replace(suffix, "")
    factor = DEPRECIATION.get(base, 0.40)
    return round(round(new_price * factor) / 100) * 100


async def fetch_new_price(model_key: str) -> int | None:
    """Henter laveste ny-pris fra Prisjakt for model_key. Returnerer None ved feil."""
    url_path = MODEL_URLS.get(model_key)
    if not url_path:
        return None

    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=_USER_AGENT,
                locale="nb-NO",
                extra_http_headers={"Accept-Language": "nb-NO,nb;q=0.9"},
            )
            page = await context.new_page()
            await page.goto(
                PRISJAKT_BASE + url_path,
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            try:
                await page.wait_for_selector(SEL_PRICE_WAIT, timeout=10_000)
            except Exception:
                pass
            price = await _extract_lowest_price(page)
            await browser.close()
            return price
    except Exception:
        return None


async def _extract_lowest_price(page) -> int | None:
    """Skanner rendret pris-tekst etter det laveste rimelige pris-tallet."""
    try:
        container = await page.query_selector(SEL_PRICE_CONTAINER)
        text = await container.inner_text() if container else await page.inner_text("body")
    except Exception:
        text = await page.inner_text("body")

    candidates: list[int] = []
    for m in _PRICE_RE.finditer(text):
        digits = "".join(ch for ch in m.group(1) if ch.isdigit())
        if not digits:
            continue
        val = int(digits)
        if 1_000 < val < 25_000:
            candidates.append(val)

    return min(candidates) if candidates else None
