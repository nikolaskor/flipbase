"""Tester for likviditetsmodulen.

Dekker median_days_to_sold, liquidity_weight, adjusted_score,
repository.sold_durations, og akseptansekravet:
  to like marginer rangeres ulikt naar den ene modellen selger raskere.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from src.pipeline.liquidity import adjusted_score, liquidity_weight, median_days_to_sold


# --- median_days_to_sold -----------------------------------------------------

def test_tom_liste_gir_none():
    assert median_days_to_sold([]) is None


def test_enkeltverdi():
    assert median_days_to_sold([5.0]) == 5.0


def test_median_av_flere():
    assert median_days_to_sold([1.0, 3.0, 5.0]) == 3.0


def test_median_avrunding():
    # median([1, 2]) = 1.5 -> avrundet til 1 desimal
    assert median_days_to_sold([1.0, 2.0]) == 1.5


# --- liquidity_weight --------------------------------------------------------

def test_ukjent_dager_gir_noytralt_vekt():
    assert liquidity_weight(None) == 1.0


def test_under_3_dager_loftes():
    assert liquidity_weight(2.9) == 1.25


def test_noyaktig_3_dager_er_normal():
    assert liquidity_weight(3.0) == 1.0


def test_mellom_3_og_7_er_normal():
    assert liquidity_weight(5.0) == 1.0


def test_noyaktig_7_dager_er_normal():
    assert liquidity_weight(7.0) == 1.0


def test_mellom_7_og_14_straffes_lett():
    assert liquidity_weight(10.0) == 0.85


def test_noyaktig_14_dager_straffes_lett():
    assert liquidity_weight(14.0) == 0.85


def test_over_14_dager_straffes_mer():
    assert liquidity_weight(21.0) == 0.7


# --- adjusted_score ----------------------------------------------------------

def test_adjusted_score_rask_flip():
    # flip_score 0.30 * 1.25 = 0.375
    assert adjusted_score(0.30, 2.0) == 0.375


def test_adjusted_score_normal():
    assert adjusted_score(0.30, 5.0) == 0.30


def test_adjusted_score_treg_flip():
    # 0.30 * 0.7 = 0.21
    assert adjusted_score(0.30, 20.0) == 0.21


def test_adjusted_score_uten_data():
    assert adjusted_score(0.30, None) == 0.30


# --- akseptansekrav: to like marginer, ulik rangering -----------------------

def test_rask_modell_slaar_treg_modell_over_terskel():
    """Samme raw flip_score, men rask modell passerer terskel og treg gjor ikke."""
    threshold = 0.30
    raw_score = 0.26  # under terskel som raa score

    adj_rask = adjusted_score(raw_score, days_to_sold=2.0)   # *1.25 = 0.325
    adj_treg = adjusted_score(raw_score, days_to_sold=20.0)  # *0.70 = 0.182

    assert adj_rask > threshold, "Rask modell skal passere terskel"
    assert adj_treg < threshold, "Treg modell skal ikke passere terskel"


def test_adjusted_score_er_hoyere_for_rask_vs_treg():
    score = 0.30
    assert adjusted_score(score, 2.0) > adjusted_score(score, 20.0)


# --- repository.sold_durations -----------------------------------------------

def _iso(dt: datetime) -> str:
    return dt.isoformat()


def test_sold_durations_beregner_dager_korrekt():
    now = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
    first = now - timedelta(days=3)
    sold = now

    mock_db = MagicMock()
    mock_db.table().select().eq().eq().execute.return_value.data = [
        {"first_seen": _iso(first), "sold_at": _iso(sold)},
    ]

    with patch("src.db.repository.db", return_value=mock_db):
        from src.db import repository as repo
        durations = repo.sold_durations("iphone_13_128gb")

    assert len(durations) == 1
    assert abs(durations[0] - 3.0) < 0.01


def test_sold_durations_flere_rader():
    now = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
    rows = [
        {"first_seen": _iso(now - timedelta(days=2)), "sold_at": _iso(now)},
        {"first_seen": _iso(now - timedelta(days=7)), "sold_at": _iso(now)},
    ]
    mock_db = MagicMock()
    mock_db.table().select().eq().eq().execute.return_value.data = rows

    with patch("src.db.repository.db", return_value=mock_db):
        from src.db import repository as repo
        durations = repo.sold_durations("iphone_13_128gb")

    assert len(durations) == 2
    assert abs(durations[0] - 2.0) < 0.01
    assert abs(durations[1] - 7.0) < 0.01


def test_sold_durations_hopper_over_rader_uten_sold_at():
    now = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
    rows = [
        {"first_seen": _iso(now - timedelta(days=5)), "sold_at": None},
        {"first_seen": _iso(now - timedelta(days=4)), "sold_at": _iso(now)},
    ]
    mock_db = MagicMock()
    mock_db.table().select().eq().eq().execute.return_value.data = rows

    with patch("src.db.repository.db", return_value=mock_db):
        from src.db import repository as repo
        durations = repo.sold_durations("iphone_13_128gb")

    assert len(durations) == 1


def test_sold_durations_tom_tabell():
    mock_db = MagicMock()
    mock_db.table().select().eq().eq().execute.return_value.data = []

    with patch("src.db.repository.db", return_value=mock_db):
        from src.db import repository as repo
        durations = repo.sold_durations("iphone_13_128gb")

    assert durations == []


# --- Telegram-varsel viser dager-til-solgt ------------------------------------

def test_format_alert_viser_dager_til_solgt():
    from datetime import datetime, timezone
    from src.models.schemas import (
        Category, FlipOpportunity, Listing, ListingStatus,
    )
    from src.notify.telegram import format_alert

    now = datetime.now(timezone.utc)
    listing = Listing(
        source="finn", external_id="1", category=Category.PHONE,
        model_key="iphone_13", title="iPhone 13",
        price=2500, description="ok", image_urls=[], location="Oslo",
        distance_km=None, seller_name="", seller_listing_count=None,
        posted_at=now, url="https://finn.no/item/1",
        status=ListingStatus.ACTIVE, first_seen=now, last_seen=now,
    )
    opp = FlipOpportunity(
        listing=listing, reference_price=3400, estimated_sell_price=3400,
        shipping_cost=149, flip_score=0.30, net_margin=751,
        median_days_to_sold=2.5, red_flags=[], vision=None,
    )
    text = format_alert(opp)
    assert "2.5 dager" in text
    assert "⚡" in text


def test_format_alert_skjuler_dager_naar_ingen_data():
    from datetime import datetime, timezone
    from src.models.schemas import (
        Category, FlipOpportunity, Listing, ListingStatus,
    )
    from src.notify.telegram import format_alert

    now = datetime.now(timezone.utc)
    listing = Listing(
        source="finn", external_id="1", category=Category.PHONE,
        model_key="iphone_13", title="iPhone 13",
        price=2500, description="ok", image_urls=[], location="Oslo",
        distance_km=None, seller_name="", seller_listing_count=None,
        posted_at=now, url="https://finn.no/item/1",
        status=ListingStatus.ACTIVE, first_seen=now, last_seen=now,
    )
    opp = FlipOpportunity(
        listing=listing, reference_price=3400, estimated_sell_price=3400,
        shipping_cost=149, flip_score=0.30, net_margin=751,
        median_days_to_sold=None, red_flags=[], vision=None,
    )
    text = format_alert(opp)
    assert "⚡" not in text
