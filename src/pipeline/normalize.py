"""Normalisering: raadata til strukturert Listing med en stabil model_key.

model_key er nokkelen til alt. Den grupperer "iPhone 13 128GB",
"iphone13 128 gb", "Apple iPhone 13" osv. til samme referansepris.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from src.models.schemas import Category, Listing, ListingStatus, RawListing

# Enkle regelbaserte modellnokler. Utvides etter hvert.
_MODEL_PATTERNS: list[tuple[Category, str, str]] = [
    (Category.PHONE, r"iphone\s*1[0-6]\s*(pro\s*max|pro|plus|mini)?", "iphone"),
    (Category.AIRPODS, r"airpods\s*(pro\s*2|pro|max|3|2)?", "airpods"),
    (Category.TABLET, r"ipad\s*(pro|air|mini)?", "ipad"),
    (Category.CONSOLE, r"(ps5|playstation\s*5)", "ps5"),
    (Category.CONSOLE, r"(nintendo\s*)?switch\s*(oled|lite)?", "switch"),
    (Category.CAMERA, r"(?:sony|canon|fujifilm|nikon)\s*(?:alpha\s+)?([a-z0-9][a-z0-9\-]*)", "camera"),
]

# Kanoniske aliaser: fullstavede merkenavn og med-prefix-varianter -> stabil nokkel.
# Noedvendig fordi regex-matchen inkluderer "Nintendo " og "PlayStation " i teksten.
_KEY_ALIASES: dict[str, str] = {
    "playstation_5": "ps5",
    "playstation_5_slim": "ps5",
    "nintendo_switch": "switch",
    "nintendo_switch_oled": "switch_oled",
    "nintendo_switch_lite": "switch_lite",
}

# Bare disse kategoriene bruker lagring (128GB/512GB) som prisdifferensiator.
_STORAGE_CATEGORIES = {Category.PHONE, Category.TABLET}


def normalize(raw: RawListing, category: Category) -> Listing | None:
    if raw.price is None:
        return None

    model_key = _derive_model_key(raw.title, category)
    now = datetime.now(timezone.utc)

    return Listing(
        source=raw.source,
        external_id=raw.external_id,
        category=category,
        model_key=model_key,
        title=raw.title,
        price=raw.price,
        description=raw.description,
        image_urls=raw.image_urls,
        location=raw.location,
        distance_km=raw.distance_km,
        seller_name=raw.seller_name,
        seller_listing_count=raw.seller_listing_count,
        posted_at=raw.posted_at,
        url=raw.url,
        status=ListingStatus.ACTIVE,
        first_seen=now,
        last_seen=now,
    )


def _derive_model_key(title: str, category: Category) -> str:
    t = title.lower()
    for cat, pattern, prefix in _MODEL_PATTERNS:
        if cat != category:
            continue
        m = re.search(pattern, t)
        if m:
            slug = re.sub(r"\s+", "_", m.group(0).strip())
            slug = slug.replace("-", "_")  # kamera-modeller: "zv-e10" -> "zv_e10"
            slug = _KEY_ALIASES.get(slug, slug)
            # lagring (128gb/512gb/1tb) er priskritisk bare for telefoner og nettbrett
            storage = re.search(r"(\d+)\s*(gb|tb)", t)
            if storage and category in _STORAGE_CATEGORIES:
                slug += f"_{storage.group(1)}{storage.group(2)}"
            return slug
    return f"{category.value}_unknown"
