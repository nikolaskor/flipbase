"""Claude vision standvurdering.

Sender annonsebildene til Claude og far en strukturert standkarakter
tilbake. Forhaandssorterer kandidatene sa du aapner de 3 beste forst.
Kjores bare paa annonser som allerede passerte pristerskelen, sa
kostnaden holdes lav (vision_max_per_run i config).
"""
from __future__ import annotations

import base64
import json

import httpx
from anthropic import Anthropic

from src.config import settings
from src.models.schemas import Listing, RedFlag, VisionAssessment

_client = Anthropic(api_key=settings.anthropic_api_key)

_PROMPT = """Du vurderer salgsverdien paa et brukt produkt fra en FINN-annonse.
Produkt: {title}
Kategori: {category}
Selgers beskrivelse: {description}

Vurder BAADE bildene og beskrivelsen samlet:
1. Samlet stand paa en skala 1-10 (10 = som ny). Trekk ned for ikke-originale deler
   (skjerm, batteri), synlige skader, eller mistillit mellom bilde og tekst.
2. Konkrete problemer: riper, sprekker, slitasje, ettermarkedsdeler, uoverensstemmelser
3. Hvor sikker du er (0-1)

Svar KUN med JSON, ingen annen tekst:
{{"condition_score": <int>, "visible_damage": [<string>], "summary": "<kort>", "confidence": <float>}}"""

_MAX_DESC_CHARS = 600
_MIN_RELIABLE_DESC_WORDS = 20


def needs_for_pricing(listing: Listing, flags: list[RedFlag]) -> bool:
    """True naar beskrivelsen er for tynn til aa stole paa uten bildeanalyse."""
    desc = listing.description.strip()
    if not desc or len(desc.split()) < _MIN_RELIABLE_DESC_WORDS:
        return True
    unreliable_codes = {"few_images", "no_screen_mention", "short_description"}
    return any(f.code in unreliable_codes for f in flags)


async def assess(listing: Listing) -> VisionAssessment | None:
    if not settings.vision_enabled or not listing.image_urls:
        return None

    images = await _download_images(listing.image_urls[:4])
    if not images:
        return None

    desc = listing.description[:_MAX_DESC_CHARS].strip() or "Ingen beskrivelse"
    content: list[dict] = [
        {"type": "image", "source": {"type": "base64",
                                     "media_type": mt, "data": data}}
        for mt, data in images
    ]
    content.append({
        "type": "text",
        "text": _PROMPT.format(
            title=listing.title,
            category=listing.category.value,
            description=desc,
        ),
    })

    resp = _client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=400,
        messages=[{"role": "user", "content": content}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    return _parse(text)


async def _download_images(urls: list[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    async with httpx.AsyncClient(timeout=15) as client:
        for url in urls:
            try:
                r = await client.get(url)
                r.raise_for_status()
                mt = r.headers.get("content-type", "image/jpeg").split(";")[0]
                out.append((mt, base64.b64encode(r.content).decode()))
            except Exception:
                continue
    return out


def _parse(text: str) -> VisionAssessment | None:
    try:
        clean = text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        return VisionAssessment(**data)
    except Exception:
        return None
