"""Enhetstester for prismotor og format_alert. Ingen nettverk, ingen DB."""
from __future__ import annotations

from datetime import datetime, timezone

from src.models.schemas import (
    Category, FlipOpportunity, Listing, ListingStatus, RedFlag,
)
from src.pipeline.pricing import PriceContext, compute_flip_score, estimate_sell_price
from src.notify.telegram import format_alert, _kr


def _listing(price: int, category: Category = Category.PHONE) -> Listing:
    now = datetime.now(timezone.utc)
    return Listing(
        source="finn", external_id="1", category=category,
        model_key="iphone_13_128gb", title="iPhone 13 128GB",
        price=price, description="ok", image_urls=[], location="Oslo",
        distance_km=None, seller_name="", seller_listing_count=None,
        posted_at=now, url="https://finn.no/item/1",
        status=ListingStatus.ACTIVE, first_seen=now, last_seen=now,
    )


def _opp(listing: Listing, sell: int, margin: int, score: float) -> FlipOpportunity:
    return FlipOpportunity(
        listing=listing, reference_price=sell, estimated_sell_price=sell,
        shipping_cost=149, flip_score=score, net_margin=margin,
        median_days_to_sold=None, red_flags=[], vision=None,
    )


# --- compute_flip_score ------------------------------------------------------

def test_flip_score_konkrete_tall():
    ctx = PriceContext(reference_price=3400, sample_size=10, static_fallback=None)
    score, sell, margin = compute_flip_score(_listing(2500), ctx)
    # sell = 3400, shipping = 149, margin = 3400 - 2500 - 149 = 751
    assert sell == 3400
    assert margin == 751
    assert abs(score - round(751 / 2500, 3)) < 0.001


def test_flip_score_null_pris_gir_null_score():
    listing = _listing(0)
    ctx = PriceContext(reference_price=3400, sample_size=5, static_fallback=None)
    score, _, _ = compute_flip_score(listing, ctx)
    assert score == 0.0


def test_flip_score_negativ_margin():
    ctx = PriceContext(reference_price=2000, sample_size=5, static_fallback=None)
    score, sell, margin = compute_flip_score(_listing(2500), ctx)
    assert margin < 0
    assert score < 0


# --- estimate_sell_price (fallback-blending) ---------------------------------

def test_ingen_data_bruker_fallback():
    ctx = PriceContext(reference_price=0, sample_size=0, static_fallback=3400)
    assert estimate_sell_price(ctx) == 3400


def test_nok_data_bruker_kun_median():
    ctx = PriceContext(reference_price=3200, sample_size=8, static_fallback=3400)
    assert estimate_sell_price(ctx) == 3200


def test_liten_data_blandes_50_50():
    ctx = PriceContext(reference_price=3000, sample_size=4, static_fallback=4000)
    # w = 4/8 = 0.5 -> 3000*0.5 + 4000*0.5 = 3500
    assert estimate_sell_price(ctx) == 3500


def test_ingen_data_og_ingen_fallback_gir_null():
    ctx = PriceContext(reference_price=0, sample_size=0, static_fallback=None)
    assert estimate_sell_price(ctx) == 0


# --- format_alert (HTML) -----------------------------------------------------

def test_format_inneholder_paakreved_info():
    opp = _opp(_listing(2500), sell=3400, margin=751, score=0.30)
    text = format_alert(opp)
    assert "2 500 kr" in text
    assert "3 400 kr" in text
    assert "751" in text
    assert "30%" in text
    assert "finn.no" in text


def test_format_escaper_html_tegn_i_tittel():
    listing = _listing(2500)
    object.__setattr__(listing, "title", "iPhone 13 <gratis> & 'god stand'")
    opp = _opp(listing, sell=3400, margin=751, score=0.30)
    text = format_alert(opp)
    assert "<gratis>" not in text
    assert "&lt;gratis&gt;" in text
    assert "&amp;" in text


def test_format_red_flags_vises():
    opp = _opp(_listing(2500), sell=3400, margin=751, score=0.30)
    opp.red_flags.append(RedFlag(code="few_images", label="Faa bilder", severity="warn"))
    text = format_alert(opp)
    assert "Faa bilder" in text
    assert "⚠️" in text


def test_format_ingen_emdash():
    opp = _opp(_listing(2500), sell=3400, margin=751, score=0.30)
    assert "—" not in format_alert(opp)


def test_kr_formatering():
    assert _kr(3400) == "3 400 kr"
    assert _kr(149) == "149 kr"
    assert _kr(10000) == "10 000 kr"
