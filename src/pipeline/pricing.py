"""Prismotor: referansepris, fraktjustering og flip_score.

Referansepris bygges fra to kilder:
  1. Median av aktive + historiske annonser for samme model_key (egen data)
  2. Valgfri statisk fallback (Prisjakt bruktpris) til du har nok egen data

flip_score = (estimert_salg - kjopspris - frakt) / kjopspris
"""
from __future__ import annotations

from dataclasses import dataclass

from src.models.schemas import Listing


@dataclass
class PriceContext:
    reference_price: int          # median salgsverdi for model_key
    sample_size: int              # antall datapunkter bak referansen
    static_fallback: int | None   # Prisjakt-referanse hvis lite egen data


# Grov fraktmatrise per kategori (Bring/Posten, justeres etter erfaring).
_SHIPPING_BY_CATEGORY = {
    "airpods": 99,
    "phone": 149,
    "tablet": 149,
    "console": 249,
    "gaming_gear": 149,
    "camera": 199,
}


def estimate_sell_price(ctx: PriceContext) -> int:
    """Blander egen median og statisk fallback basert paa hvor mye data vi har."""
    if ctx.sample_size >= 8:
        return ctx.reference_price
    if ctx.static_fallback is not None:
        # vekt mot fallback naar egen data er tynn
        w = ctx.sample_size / 8
        return round(ctx.reference_price * w + ctx.static_fallback * (1 - w))
    return ctx.reference_price


def shipping_cost(listing: Listing) -> int:
    return _SHIPPING_BY_CATEGORY.get(listing.category.value, 149)


def compute_flip_score(listing: Listing, ctx: PriceContext) -> tuple[float, int, int]:
    """Returnerer (flip_score, estimert_salgspris, netto_margin)."""
    sell = estimate_sell_price(ctx)
    ship = shipping_cost(listing)
    net_margin = sell - listing.price - ship
    flip_score = net_margin / listing.price if listing.price else 0.0
    return round(flip_score, 3), sell, net_margin
