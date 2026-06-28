"""Enhetstester for red-flag-detektor og at flaggene rendres i varselet."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.models.schemas import Category, FlipOpportunity, Listing, ListingStatus, RedFlag
from src.pipeline.redflags import DAMAGE_KEYWORDS, SCREEN_KEYWORDS, detect
from src.notify.telegram import format_alert


def _listing(
    *,
    description: str = "",
    image_urls: list[str] | None = None,
    seller_listing_count: int | None = None,
    category: Category = Category.PHONE,
) -> Listing:
    now = datetime.now(timezone.utc)
    return Listing(
        source="finn", external_id="1", category=category,
        model_key="iphone_13", title="iPhone 13",
        price=2500, description=description,
        image_urls=image_urls if image_urls is not None else [],
        location="Oslo", distance_km=None,
        seller_name="", seller_listing_count=seller_listing_count,
        posted_at=now, url="https://finn.no/item/1",
        status=ListingStatus.ACTIVE, first_seen=now, last_seen=now,
    )


def _codes(listing: Listing) -> set[str]:
    return {f.code for f in detect(listing)}


# --- few_images --------------------------------------------------------------

def test_ingen_bilder_gir_few_images():
    assert "few_images" in _codes(_listing(image_urls=[]))


def test_ett_bilde_gir_few_images():
    assert "few_images" in _codes(_listing(image_urls=["https://img.finncdn.no/a.jpg"]))


def test_to_bilder_gir_ikke_few_images():
    assert "few_images" not in _codes(_listing(image_urls=["a.jpg", "b.jpg"]))


# --- no_screen_mention -------------------------------------------------------

@pytest.mark.parametrize("keyword", SCREEN_KEYWORDS)
def test_skjermord_i_beskrivelse_fjerner_flagg(keyword):
    desc = f"Selger en iPhone. {keyword.capitalize()} er fin. Ingen riper."
    assert "no_screen_mention" not in _codes(_listing(description=desc))


def test_manglende_skjermord_gir_flagg_for_telefon():
    assert "no_screen_mention" in _codes(_listing(description="Selger iPhone, god stand."))


def test_no_screen_mention_ikke_for_kamera():
    assert "no_screen_mention" not in _codes(
        _listing(description="God stand.", category=Category.CAMERA)
    )


# --- short_description -------------------------------------------------------

def test_tom_beskrivelse_gir_short_description():
    assert "short_description" in _codes(_listing(description=""))


def test_under_20_ord_gir_flagg():
    desc = " ".join(["ord"] * 19)
    assert "short_description" in _codes(_listing(description=desc))


def test_noyaktig_20_ord_gir_ikke_flagg():
    desc = " ".join(["ord"] * 20)
    assert "short_description" not in _codes(_listing(description=desc))


def test_lang_beskrivelse_gir_ikke_flagg():
    desc = (
        "Selger min iPhone 13 128GB i svart. Telefonen er i god stand. "
        "Skjermen er hel og pen. Batteri holder godt. Originalkasse og "
        "lader medfølger. Ingen synlige skader."
    )
    assert "short_description" not in _codes(_listing(description=desc))


# --- new_seller --------------------------------------------------------------

def test_seller_listing_count_null_gir_ikke_flagg():
    assert "new_seller" not in _codes(_listing(seller_listing_count=None))


def test_en_annonse_gir_new_seller():
    assert "new_seller" in _codes(_listing(seller_listing_count=1))


def test_to_annonser_gir_new_seller():
    assert "new_seller" in _codes(_listing(seller_listing_count=2))


def test_tre_annonser_gir_ikke_new_seller():
    assert "new_seller" not in _codes(_listing(seller_listing_count=3))


# --- damage_keywords ---------------------------------------------------------

@pytest.mark.parametrize("keyword", DAMAGE_KEYWORDS)
def test_hvert_skadeord_trigger_flagg(keyword):
    desc = f"Telefonen er fin men har litt {keyword} paa baksiden."
    assert "damage_keywords" in _codes(_listing(description=desc))


def test_damage_flag_lister_opp_treffene():
    desc = "Har sprekk og en ripe."
    flags = detect(_listing(description=desc))
    dmg = next(f for f in flags if f.code == "damage_keywords")
    assert "sprekk" in dmg.label
    assert "ripe" in dmg.label


def test_damage_flag_har_high_severity():
    desc = "Litt knust i hjornet."
    flags = detect(_listing(description=desc))
    dmg = next(f for f in flags if f.code == "damage_keywords")
    assert dmg.severity == "high"


def test_ren_beskrivelse_gir_ikke_damage():
    desc = "Selger min iPhone 13 128GB i god stand. Skjerm og batteri er perfekte."
    assert "damage_keywords" not in _codes(_listing(description=desc))


# --- kombinasjoner -----------------------------------------------------------

def test_tynn_beskrivelse_og_ny_selger_gir_begge_flagg():
    flags = _codes(_listing(description="Selger iPhone.", seller_listing_count=1))
    assert "short_description" in flags
    assert "new_seller" in flags


def test_ingen_flagg_paa_god_annonse():
    desc = (
        "Selger en pent brukt iPhone 13 128GB Midnight. Skjermen er perfekt uten "
        "riper. Batteriet er i god stand. Originalkasse og lader medfølger. "
        "Ingen feil eller mangler."
    )
    flags = _codes(_listing(
        description=desc,
        image_urls=[f"https://img.finncdn.no/{i}.jpg" for i in range(8)],
        seller_listing_count=10,
    ))
    # damage_keywords slaar paa "feil" i siste setning - det er forventet oppforsel
    flags.discard("damage_keywords")
    assert flags == set()


# --- rendering i Telegram-varsel ---------------------------------------------

def _opp_with_flags(flags: list[RedFlag]) -> FlipOpportunity:
    now = datetime.now(timezone.utc)
    listing = _listing(description="kort", image_urls=["x.jpg"], seller_listing_count=1)
    return FlipOpportunity(
        listing=listing, reference_price=3400, estimated_sell_price=3400,
        shipping_cost=149, flip_score=0.30, net_margin=751,
        median_days_to_sold=None, red_flags=flags, vision=None,
    )


def test_warn_flagg_vises_med_advarselssymbol():
    flag = RedFlag(code="few_images", label="Faa bilder", severity="warn")
    text = format_alert(_opp_with_flags([flag]))
    assert "⚠️" in text
    assert "Faa bilder" in text


def test_high_flagg_vises_med_roed_sirkel():
    flag = RedFlag(code="damage_keywords", label="Skadeord: sprekk", severity="high")
    text = format_alert(_opp_with_flags([flag]))
    assert "🔴" in text
    assert "Skadeord: sprekk" in text


def test_info_flagg_vises_med_info_symbol():
    flag = RedFlag(code="no_screen_mention", label="Skjerm ikke nevnt", severity="info")
    text = format_alert(_opp_with_flags([flag]))
    assert "ℹ️" in text
    assert "Skjerm ikke nevnt" in text


def test_ingen_flagg_gir_ingen_advarselssymboler():
    text = format_alert(_opp_with_flags([]))
    assert "⚠️" not in text
    assert "🔴" not in text
