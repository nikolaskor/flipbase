"""Scheduler / orchestrator.

Railway cron kaller denne hvert N. minutt. Den binder sammen hele
pipelinen: scrape -> normaliser -> sold-tracking -> pris -> likviditet
-> red-flags -> vision -> varsel.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from src.config import settings
from src.db import repository as repo
from src.models.schemas import (
    Category, FlipOpportunity, Listing, ListingStatus,
)
from src.pipeline import liquidity, pricing, redflags, vision
from src.pipeline.normalize import normalize
from src.pipeline.pricing import PriceContext
from src.pipeline.sold_tracker import classify_disappeared
from src.notify import telegram
from src.scrapers.finn import FinnScraper

# Watchlists: kategori -> sokefilter. Statiske fallbackpriser kan ligge her.
WATCHLISTS: list[tuple[Category, dict]] = [
    (Category.PHONE, {"query": "iphone"}),
    (Category.AIRPODS, {"query": "airpods+pro"}),
    (Category.TABLET, {"query": "ipad"}),
    (Category.CONSOLE, {"query": "ps5"}),
    (Category.CONSOLE, {"query": "nintendo+switch"}),
    (Category.CAMERA, {"query": "sony+kamera"}),
]

# Midlertidige statiske referanser til egen sold-data er tykk nok.
STATIC_FALLBACK: dict[str, int] = {
    "iphone_13_128gb": 3400,
    "airpods_pro_2": 1200,
    "ipad_air": 3200,
    "ps5": 4500,
    "switch_oled": 2000,
}


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
    if repo.already_alerted(listing.source, listing.external_id):
        return vision_budget

    sample = repo.reference_sample(listing.model_key)
    ref_price = int(sum(sample) / len(sample)) if sample else 0
    ctx = PriceContext(
        reference_price=ref_price,
        sample_size=len(sample),
        static_fallback=STATIC_FALLBACK.get(listing.model_key),
    )
    if ctx.reference_price == 0 and ctx.static_fallback is None:
        return vision_budget  # ingen prisbasis enda

    flip_score, sell, net_margin = pricing.compute_flip_score(listing, ctx)
    dts = liquidity.median_days_to_sold(repo.sold_durations(listing.model_key))
    adj = liquidity.adjusted_score(flip_score, dts)

    if adj < settings.flip_score_threshold:
        return vision_budget

    v = None
    if vision_budget > 0:
        v = await vision.assess(listing)
        vision_budget -= 1

    opp = FlipOpportunity(
        listing=listing,
        reference_price=ctx.reference_price or (ctx.static_fallback or 0),
        estimated_sell_price=sell,
        shipping_cost=pricing.shipping_cost(listing),
        flip_score=adj,
        net_margin=net_margin,
        median_days_to_sold=dts,
        red_flags=redflags.detect(listing),
        vision=v,
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
        first = datetime.fromisoformat(r["first_seen"])
        last = datetime.fromisoformat(r["last_seen"])
        status = classify_disappeared(first, last)
        if status == ListingStatus.SOLD:
            to_sell.append(r["external_id"])
        else:
            to_remove.append(r["external_id"])

    repo.mark_disappeared(source, to_sell, ListingStatus.SOLD)
    repo.mark_disappeared(source, to_remove, ListingStatus.REMOVED)


if __name__ == "__main__":
    asyncio.run(run_once())
