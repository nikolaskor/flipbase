"""Sold-tracking: den proprietaere dataen.

FINN gir ikke salgspriser. Men hver kjoring sammenligner forrige snapshot
mot dagens. En annonse som var aktiv og naa er borte antas solgt til
sin siste kjente pris. Over tid bygger dette en database over hva ting
FAKTISK selges for i Norge, som ingen konkurrent har.

Heuristikk for solgt vs bare fjernet:
  - Borte etter < 1 time live  -> sannsynligvis fjernet/feil (REMOVED)
  - Borte etter rimelig tid     -> antatt SOLD
  - "Solgt"-markor i tittel/status hvis tilgjengelig -> SOLD direkte
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.models.schemas import ListingStatus

MIN_LIVE_FOR_SOLD = timedelta(hours=1)


def classify_disappeared(first_seen: datetime, last_seen: datetime) -> ListingStatus:
    live_duration = last_seen - first_seen
    if live_duration < MIN_LIVE_FOR_SOLD:
        return ListingStatus.REMOVED
    return ListingStatus.SOLD


def days_live(first_seen: datetime, sold_at: datetime | None = None) -> float:
    end = sold_at or datetime.now(timezone.utc)
    return (end - first_seen).total_seconds() / 86_400
