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
from src.models.schemas import Listing, VisionAssessment

_client = Anthropic(api_key=settings.anthropic_api_key)

_PROMPT = """Du vurderer stand paa et brukt produkt fra en FINN-annonse.
Produkt: {title}
Kategori: {category}

Se paa bildene og vurder:
1. Synlig stand paa en skala 1-10 (10 = som ny)
2. Konkrete synlige skader (riper, sprekker, slitasje, manglende deler)
3. Hvor sikker du er (0-1), gitt bildekvalitet og vinkler

Svar KUN med JSON, ingen annen tekst:
{{"condition_score": <int>, "visible_damage": [<string>], "summary": "<kort>", "confidence": <float>}}"""


async def assess(listing: Listing) -> VisionAssessment | None:
    if not settings.vision_enabled or not listing.image_urls:
        return None

    images = await _download_images(listing.image_urls[:4])
    if not images:
        return None

    content: list[dict] = [
        {"type": "image", "source": {"type": "base64",
                                     "media_type": mt, "data": data}}
        for mt, data in images
    ]
    content.append({
        "type": "text",
        "text": _PROMPT.format(title=listing.title, category=listing.category.value),
    })

    resp = _client.messages.create(
        model="claude-sonnet-4-6",
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
