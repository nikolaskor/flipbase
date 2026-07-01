"""Normalisering: raadata til strukturert Listing med en stabil model_key.

model_key er nokkelen til alt. Den grupperer "iPhone 13 128GB",
"iphone13 128 gb", "Apple iPhone 13" osv. til samme referansepris.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from src.models.schemas import Category, Listing, ListingStatus, RawListing

# Kun iPhone 12-14 (standard, Pro, Pro Max, Plus, mini) er i watchlisten.
_ALLOWED_IPHONE_GENERATIONS = frozenset({12, 13, 14})

# Enkle regelbaserte modellnokler. Utvides etter hvert.
_MODEL_PATTERNS: list[tuple[Category, str, str]] = [
    (Category.PHONE, r"iphone\s*1[234]\s*(pro\s*max|pro|plus|mini)?", "iphone"),
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

# Tilbehoer-nokkelord per kategori. Annonser der tittelen inneholder ett av disse
# er aksessorier, ikke enheter vi vil flippe -- silt ut foer model_key-derivasjon.
_ACCESSORY_KEYWORDS: dict[Category, frozenset[str]] = {
    Category.PHONE: frozenset({
        "deksel", "case", "cover", "lader", "kabel", "adapter",
        "skjermbeskytter", "panzerglass", "holder", "sugekopp",
        "stativ", "feste", "wallet", "kortholder", "magsafe pad",
        "lightning", "usb-c hub", "airtag", "reim", "strap",
        "etui",
    }),
    Category.TABLET: frozenset({
        "deksel", "case", "cover", "tastatur", "keyboard", "lader",
        "kabel", "adapter", "skjermbeskytter", "panzerglass", "stativ",
    }),
    Category.CONSOLE: frozenset({
        "kontroller", "controller", "joystick", "kabel", "lader",
        "headset", "headphones", "spill", "game", "dock",
    }),
}


def is_allowed_iphone_model_key(model_key: str) -> bool:
    """True bare for iphone_12/13/14-varianter (inkl. Pro, Pro Max, Plus, mini)."""
    m = re.match(r"iphone_(\d+)", model_key)
    if not m:
        return False
    return int(m.group(1)) in _ALLOWED_IPHONE_GENERATIONS


def _title_has_allowed_iphone(title: str) -> bool:
    """Krever at tittelen faktisk nevner en iPhone 12, 13 eller 14."""
    m = re.search(
        r"iphone\s*(\d{1,2})\s*(pro\s*max|pro|plus|mini)?",
        title.lower(),
    )
    if not m:
        return False
    return int(m.group(1)) in _ALLOWED_IPHONE_GENERATIONS


def normalize(raw: RawListing, category: Category) -> Listing | None:
    if raw.price is None:
        return None

    t_lower = raw.title.lower()
    if any(kw in t_lower for kw in _ACCESSORY_KEYWORDS.get(category, frozenset())):
        return None

    if category == Category.PHONE and not _title_has_allowed_iphone(raw.title):
        return None

    model_key = _derive_model_key(raw.title, category)
    if category == Category.PHONE and not is_allowed_iphone_model_key(model_key):
        return None
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
