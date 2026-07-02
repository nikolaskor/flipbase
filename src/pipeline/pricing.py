"""Prismotor: referansepris, fraktjustering, kondisjonsjustering og flip_score.

Referansepris bygges fra tre kilder (prioritet):
  1. Median av solgte FINN-annonser for samme model_key (vaar egen data)
  2. Prisjakt ny-pris * avskrivningsfaktor (live, oppdateres daglig)
  3. Statisk fallback (hardkodet, brukes bare naar alt annet mangler)

Kondisjonsjustering:
  - Tekst-basert (rod flags fra beskrivelse): brukes naar beskrivelsen er paalitelig
  - Visjon-basert (Claude score): paakrevd naar beskrivelsen er tynn/mangler
  - adjust_sell_price() velger riktig strategi

flip_score = (estimert_salg - kjopspris - frakt) / kjopspris
"""
from __future__ import annotations

from dataclasses import dataclass

from src.models.schemas import Listing, RedFlag, VisionAssessment


@dataclass
class PriceContext:
    reference_price: int          # median av solgte annonser for model_key
    sample_size: int              # antall datapunkter bak referansen
    static_fallback: int | None   # hardkodet fallback naar alt annet mangler
    market_median: int | None = None  # median av aktive FINN-annonser for model_key
    prisjakt_used_estimate: int | None = None  # Prisjakt ny-pris * avskrivning


# Grov fraktmatrise per kategori (Bring/Posten).
_SHIPPING_BY_CATEGORY = {
    "airpods": 99,
    "phone": 149,
    "tablet": 149,
    "console": 249,
    "gaming_gear": 149,
    "camera": 199,
}

# Kondisjonsdiskontering basert paa roed-flagg i beskrivelsestekst.
# Kjoeres foer vision, saa vi filtrerer aapenlyst defekte annonser tidlig.
_FLAG_DISCOUNTS: dict[str, float] = {
    "non_original_parts": 0.22,
    "damage_keywords":    0.12,
}

# Kondisjonsdiskontering basert paa Claude vision-score (1-10).
_VISION_DISCOUNTS: list[tuple[int, float]] = [
    (8, 0.00),   # 8-10: ingen rabatt
    (6, 0.10),   # 6-7:  lett slitasje
    (4, 0.20),   # 4-5:  synlige skader
    (0, 0.32),   # 1-3:  betydelig skade
]


def estimate_sell_price(ctx: PriceContext) -> int:
    """Returnerer beste estimat for hva annonsen selges for.

    Vekter egne FINN-salgdata tyngst. Naar disse er sparsomme, blander vi inn
    Prisjakt-estimat (live) eller statisk fallback.
    """
    if ctx.sample_size >= 8:
        return ctx.reference_price

    # Velg beste fallback: Prisjakt-estimat > markedsmedian > statisk
    fallback = (
        ctx.prisjakt_used_estimate
        or ctx.market_median
        or ctx.static_fallback
    )
    if fallback is None:
        return ctx.reference_price

    w = ctx.sample_size / 8
    return round(ctx.reference_price * w + fallback * (1 - w))


def adjust_for_flags(sell_price: int, flags: list[RedFlag]) -> int:
    """Trekker fra kondisjonsdiskontering basert paa tekstbaserte roed-flagg.

    Kjoeres foer terskelvurdering slik at aapenlyst defekte annonser filtreres
    uten aa bruke vision-budsjett.
    """
    total_discount = sum(
        _FLAG_DISCOUNTS.get(f.code, 0.0) for f in flags
    )
    total_discount = min(total_discount, 0.40)
    return round(sell_price * (1 - total_discount))


def adjust_for_vision(sell_price: int, vision: VisionAssessment) -> int:
    """Trekker fra kondisjonsdiskontering basert paa Claude vision-score."""
    discount = 0.0
    for threshold, d in _VISION_DISCOUNTS:
        if vision.condition_score >= threshold:
            discount = d
            break
    return round(sell_price * (1 - discount))


def adjust_sell_price(
    sell_price: int,
    flags: list[RedFlag],
    vision: VisionAssessment | None = None,
    *,
    trust_vision: bool = False,
) -> int:
    """Justerer salgsestimat etter stand.

    Naar trust_vision=True (tynn/manglende beskrivelse), styrer vision-score
    kondisjonen. Tekstbaserte skadeord ignoreres da de ofte mangler.
    Ettermarkedsdeler fra tekst beholdes fordi selger noen ganger skriver det eksplisitt.
    """
    if trust_vision:
        if not vision:
            return sell_price
        price = adjust_for_vision(sell_price, vision)
        text_only = [f for f in flags if f.code == "non_original_parts"]
        return adjust_for_flags(price, text_only)

    price = adjust_for_flags(sell_price, flags)
    if vision:
        price = adjust_for_vision(price, vision)
    return price


def compute_haggle_price(
    listing_price: int,
    sell_price: int,
    ship: int,
    vision: VisionAssessment | None,
    flags: list[RedFlag],
) -> int:
    """Anbefalt aapningstilbud til selger.

    Basert paa: hva du maksimalt kan betale for aa treffe minimumsmargin, men
    aldri mer enn et rimelig prosentvis avslag fra listeprisen.

    Rundes ned til naermeste 50 kr.
    """
    min_profit = 400
    max_you_can_pay = sell_price - ship - min_profit

    # Prosentvis avslag basert paa stand
    if vision and vision.condition_score <= 5:
        rate = 0.22
    elif any(f.code == "non_original_parts" for f in flags):
        rate = 0.20
    elif vision and vision.condition_score <= 7:
        rate = 0.15
    else:
        rate = 0.10

    pct_offer = round(listing_price * (1 - rate))
    offer = min(pct_offer, max_you_can_pay)
    offer = max(offer, listing_price - 1000)  # ikke mer enn 1000 kr under uansett
    return (offer // 50) * 50  # rund ned til naermeste 50


def shipping_cost(listing: Listing) -> int:
    return _SHIPPING_BY_CATEGORY.get(listing.category.value, 149)


def compute_flip_score(listing: Listing, ctx: PriceContext) -> tuple[float, int, int]:
    """Returnerer (flip_score, estimert_salgspris, netto_margin).

    Salgsprisen her er RAA (ukondisjonsjustert). Juster separat med
    adjust_for_flags() og adjust_for_vision() etter behov.
    """
    sell = estimate_sell_price(ctx)
    ship = shipping_cost(listing)
    net_margin = sell - listing.price - ship
    flip_score = net_margin / listing.price if listing.price else 0.0
    return round(flip_score, 3), sell, net_margin
