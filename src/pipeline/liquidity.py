"""Likviditet: median dager-til-solgt per model_key.

Naar du compounder fra 2000 kr er kapitalomlop taket, ikke margin.
En iPhone som selger paa 2 dager slaar et kamera med 1500 kr margin
som tar 3 uker. Denne modulen vekter flip_score mot omlopshastighet.
"""
from __future__ import annotations

from statistics import median


def median_days_to_sold(sold_durations_days: list[float]) -> float | None:
    """Median basert paa observerte solgte annonser for en model_key."""
    if not sold_durations_days:
        return None
    return round(median(sold_durations_days), 1)


def liquidity_weight(days_to_sold: float | None) -> float:
    """Multiplikator paa flip_score. Raske flips loftes, trege straffes.

    < 3 dager   -> 1.25x
    3-7 dager   -> 1.0x
    7-14 dager  -> 0.85x
    > 14 dager  -> 0.7x
    ukjent      -> 1.0x (ingen data enda)
    """
    if days_to_sold is None:
        return 1.0
    if days_to_sold < 3:
        return 1.25
    if days_to_sold <= 7:
        return 1.0
    if days_to_sold <= 14:
        return 0.85
    return 0.7


def adjusted_score(flip_score: float, days_to_sold: float | None) -> float:
    return round(flip_score * liquidity_weight(days_to_sold), 3)
