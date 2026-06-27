"""Abstrakt scraper-grensesnitt.

Alle kilder (FINN na, Tise/Facebook i fase 2) implementerer dette,
sa resten av pipelinen ikke vet eller bryr seg om hvor dataen kommer fra.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.models.schemas import Category, RawListing


class BaseScraper(ABC):
    source: str

    @abstractmethod
    async def fetch_new(self, category: Category, search_filter: dict) -> list[RawListing]:
        """Hent ferske annonser for en kategori gitt et sokefilter."""
        raise NotImplementedError
