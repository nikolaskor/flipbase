"""Enhetstester for vision-modulen. Ingen nettverkskall, ingen Anthropic-API."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.models.schemas import Category, Listing, ListingStatus, VisionAssessment
from src.pipeline.vision import _parse


def _listing(image_urls: list[str]) -> Listing:
    now = datetime.now(timezone.utc)
    return Listing(
        source="finn", external_id="1", category=Category.PHONE,
        model_key="iphone_13", title="iPhone 13",
        price=2500, description="God stand.",
        image_urls=image_urls, location="Oslo", distance_km=None,
        seller_name="", seller_listing_count=None,
        posted_at=now, url="https://finn.no/item/1",
        status=ListingStatus.ACTIVE, first_seen=now, last_seen=now,
    )


# --- _parse ------------------------------------------------------------------

def test_parse_gyldig_json():
    raw = json.dumps({
        "condition_score": 8, "visible_damage": [], "summary": "Pen", "confidence": 0.9,
    })
    result = _parse(raw)
    assert isinstance(result, VisionAssessment)
    assert result.condition_score == 8
    assert result.confidence == 0.9


def test_parse_json_med_kodeblokk():
    raw = '```json\n{"condition_score": 7, "visible_damage": ["ripe"], "summary": "OK", "confidence": 0.7}\n```'
    result = _parse(raw)
    assert result is not None
    assert result.visible_damage == ["ripe"]


def test_parse_ugyldig_json_gir_none():
    assert _parse("ikke json") is None


def test_parse_manglende_felt_gir_none():
    raw = json.dumps({"condition_score": 5})
    assert _parse(raw) is None


def test_parse_tom_streng_gir_none():
    assert _parse("") is None


# --- assess ------------------------------------------------------------------

def test_assess_returnerer_none_uten_bilder():
    from src.pipeline import vision
    with patch.object(vision.settings, "vision_enabled", True):
        result = asyncio.run(vision.assess(_listing([])))
    assert result is None


def test_assess_returnerer_none_naar_vision_disabled():
    from src.pipeline import vision
    with patch.object(vision.settings, "vision_enabled", False):
        result = asyncio.run(vision.assess(_listing(["https://img.finncdn.no/a.jpg"])))
    assert result is None


def test_assess_kaller_haiku_modellen():
    """Verifiser at vi bruker claude-haiku-4-5, ikke sonnet."""
    from src.pipeline import vision

    fake_resp = MagicMock()
    fake_resp.content = [MagicMock(type="text", text=json.dumps({
        "condition_score": 9, "visible_damage": [], "summary": "Topp stand", "confidence": 0.95,
    }))]

    fake_image_data = b"\xff\xd8\xff"
    mock_http_resp = MagicMock()
    mock_http_resp.content = fake_image_data
    mock_http_resp.headers = {"content-type": "image/jpeg"}
    mock_http_resp.raise_for_status = MagicMock()

    with (
        patch.object(vision.settings, "vision_enabled", True),
        patch.object(vision._client.messages, "create", return_value=fake_resp) as mock_create,
        patch("httpx.AsyncClient") as mock_http,
    ):
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_ctx.get = AsyncMock(return_value=mock_http_resp)
        mock_http.return_value = mock_ctx

        result = asyncio.run(vision.assess(_listing(["https://img.finncdn.no/a.jpg"])))

    assert result is not None
    assert result.condition_score == 9
    assert mock_create.call_args.kwargs["model"] == "claude-haiku-4-5"
