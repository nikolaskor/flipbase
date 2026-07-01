"""Scheduler / orchestrator.

Railway cron kaller denne hvert N. minutt. Den binder sammen hele
pipelinen: scrape -> normaliser -> sold-tracking -> pris -> likviditet
-> red-flags -> vision -> varsel.

Prisjakt-priser oppdateres maksimalt en gang per dag per modell og
caches i Supabase. Disse brukes som fallback naar vi mangler FINN-salgdata.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from statistics import median as _median

from src.config import settings
from src.db import repository as repo
from src.models.schemas import (
    Category, FlipOpportunity, Listing, ListingStatus,
)
from src.pipeline import liquidity, pricing, redflags, vision
from src.pipeline.normalize import is_allowed_iphone_model_key, normalize
from src.pipeline.pricing import PriceContext
from src.pipeline.sold_tracker import classify_disappeared
from src.notify import telegram
from src.scrapers.finn import FinnScraper
from src.scrapers.prisjakt import fetch_new_price, used_estimate_from_new


def _parse_ts(ts: str) -> datetime:
    """Parser Supabase-tidsstempler paa Python 3.10 (krever 0/3/6 desimalsekunder)."""
    ts = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], ts)
    return datetime.fromisoformat(ts)


# Watchlists: kategori -> sokefilter.
# Utvid med airpods, tablet, console, camera naar telefon-logikken er stabil.
WATCHLISTS: list[tuple[Category, dict]] = [
    (Category.PHONE, {"query": "iphone"}),
]

# Statisk fallback brukes NÅR Prisjakt-scraper feiler og vi mangler FINN-data.
# Dekker baade modeller med lagring i tittel ("iphone_13_128gb") og uten
# ("iphone_13"). normalize() legger til lagring naar den finnes i tittelen.
STATIC_FALLBACK: dict[str, int] = {
    # iphone med lagring
    "iphone_11_64gb": 1800, "iphone_11_128gb": 2000, "iphone_11_256gb": 2300,
    "iphone_12_64gb": 2400, "iphone_12_128gb": 2700, "iphone_12_256gb": 3000,
    "iphone_13_128gb": 3400, "iphone_13_256gb": 3800, "iphone_13_512gb": 4200,
    "iphone_14_128gb": 4500, "iphone_14_256gb": 5000, "iphone_14_512gb": 5500,
    "iphone_15_128gb": 6000, "iphone_15_256gb": 6500,
    # iphone uten lagring (fallback for titler som ikke nevner GB)
    "iphone_11": 2000, "iphone_12": 2700, "iphone_13": 3400,
    "iphone_14": 4500, "iphone_14_plus": 4800,
    "iphone_14_pro": 6000, "iphone_14_pro_max": 7000,
    "iphone_15": 6000, "iphone_15_plus": 6500,
    "iphone_15_pro": 8000, "iphone_15_pro_max": 9000,
    "iphone_16": 7500, "iphone_16_plus": 8000,
    "iphone_16_pro": 9500, "iphone_16_pro_max": 10500,
    # tilbehoer og annet
    "airpods_pro_2": 1200, "airpods_pro": 900, "airpods_3": 700,
    "ipad_air": 3200, "ipad_pro": 5000, "ipad_mini": 2500,
    "ps5": 4500, "switch_oled": 2000, "switch": 1500, "switch_lite": 1200,
    "sony_zv_e10": 3000, "sony_a6000": 2500, "sony_a6400": 5000,
    "sony_a7": 12000, "sony_a7c": 10000, "sony_a7iii": 12000,
}

_PRISJAKT_TTL = timedelta(days=1)


async def _prisjakt_used_estimate(model_key: str) -> int | None:
    """Returnerer brukt-estimat fra Prisjakt (cachet i DB, oppdateres daglig)."""
    cached = repo.get_prisjakt_price(model_key)
    if cached:
        new_price, fetched_at = cached
        age = datetime.now(timezone.utc) - fetched_at.replace(tzinfo=timezone.utc)
        if age < _PRISJAKT_TTL:
            return used_estimate_from_new(model_key, new_price)

    # Cache er utloept eller mangler; hent live fra Prisjakt.
    new_price = await fetch_new_price(model_key)
    if new_price:
        repo.upsert_prisjakt_price(model_key, new_price)
        return used_estimate_from_new(model_key, new_price)

    # Prisjakt feilet; bruk cachet verdi selv om den er gammel.
    if cached:
        return used_estimate_from_new(model_key, cached[0])
    return None


async def run_once() -> None:
    scraper = FinnScraper()
    vision_budget = settings.vision_max_per_run

    for category, search_filter in WATCHLISTS:
        raw_list = await scraper.fetch_new(category, search_filter)
        seen_now: set[str] = set()

        for raw in raw_list:
            listing = normalize(raw, category)
            if listing is None:
                continue
            seen_now.add(listing.external_id)
            repo.upsert_listing(listing)

            vision_budget = await _evaluate(listing, vision_budget)

        _reconcile_sold(scraper.source, category.value, seen_now)


async def _evaluate(listing: Listing, vision_budget: int) -> int:
    if listing.category == Category.PHONE and not is_allowed_iphone_model_key(listing.model_key):
        return vision_budget

    if repo.already_alerted(listing.source, listing.external_id):
        return vision_budget

    sample = repo.reference_sample(listing.model_key)
    ref_price = int(_median(sample)) if sample else 0
    market_sample = repo.active_market_sample(listing.model_key)
    market_med = int(_median(market_sample)) if market_sample else None
    prisjakt_est = await _prisjakt_used_estimate(listing.model_key)
    ctx = PriceContext(
        reference_price=ref_price,
        sample_size=len(sample),
        static_fallback=STATIC_FALLBACK.get(listing.model_key),
        market_median=market_med,
        prisjakt_used_estimate=prisjakt_est,
    )
    if ctx.reference_price == 0 and ctx.market_median is None \
            and ctx.static_fallback is None and ctx.prisjakt_used_estimate is None:
        return vision_budget  # ingen prisbasis enda

    # Trekk flagg fra beskrivelsestekst og juster salgspris FoR terskelvurdering.
    # Slik slipper vi aa sende vision-budsjett paa aapenlyst defekte annonser.
    text_flags = redflags.detect(listing)
    _, raw_sell, _ = pricing.compute_flip_score(listing, ctx)
    sell = pricing.adjust_for_flags(raw_sell, text_flags)

    ship = pricing.shipping_cost(listing)
    net_margin = sell - listing.price - ship
    flip_score = round(net_margin / listing.price, 3) if listing.price else 0.0

    dts = liquidity.median_days_to_sold(repo.sold_durations(listing.model_key))
    adj = liquidity.adjusted_score(flip_score, dts)

    if adj < settings.flip_score_threshold:
        return vision_budget

    v = None
    if vision_budget > 0:
        v = await vision.assess(listing)
        vision_budget -= 1
        if v:
            sell = pricing.adjust_for_vision(sell, v)
            net_margin = sell - listing.price - ship
            adj = round(net_margin / listing.price, 3) if listing.price else 0.0

    haggle = pricing.compute_haggle_price(listing.price, sell, ship, v, text_flags)

    opp = FlipOpportunity(
        listing=listing,
        reference_price=ctx.reference_price or prisjakt_est or (ctx.static_fallback or 0),
        estimated_sell_price=sell,
        shipping_cost=ship,
        flip_score=adj,
        net_margin=net_margin,
        median_days_to_sold=dts,
        red_flags=text_flags,
        vision=v,
        haggle_price=haggle,
    )
    if await telegram.send(opp):
        repo.record_alert(listing.source, listing.external_id, adj)

    return vision_budget


def _reconcile_sold(source: str, category: str, seen_now: set[str]) -> None:
    """Annonser som var aktive men ikke dukket opp naa: klassifiser som solgt eller fjernet."""
    active_rows = repo.get_active_listings_with_timestamps(source, category)
    disappeared = [r for r in active_rows if r["external_id"] not in seen_now]

    to_sell: list[str] = []
    to_remove: list[str] = []
    for r in disappeared:
        first = _parse_ts(r["first_seen"])
        last = _parse_ts(r["last_seen"])
        status = classify_disappeared(first, last)
        if status == ListingStatus.SOLD:
            to_sell.append(r["external_id"])
        else:
            to_remove.append(r["external_id"])

    repo.mark_disappeared(source, to_sell, ListingStatus.SOLD)
    repo.mark_disappeared(source, to_remove, ListingStatus.REMOVED)


if __name__ == "__main__":
    asyncio.run(run_once())
