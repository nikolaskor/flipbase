"""Tester for sold_tracker + reconcile-logikk.

Rene enhetstester, ingen database, ingen browser.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.models.schemas import ListingStatus
from src.pipeline.sold_tracker import MIN_LIVE_FOR_SOLD, classify_disappeared


def _dt(hours_ago: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours_ago)


# --- classify_disappeared ---------------------------------------------------

def test_borte_etter_kort_tid_er_removed():
    first = _dt(0.5)
    last = _dt(0.1)
    assert classify_disappeared(first, last) == ListingStatus.REMOVED


def test_borte_etter_lang_tid_er_sold():
    first = _dt(48)
    last = _dt(1)
    assert classify_disappeared(first, last) == ListingStatus.SOLD


def test_grenseverdi_akkurat_en_time_er_sold():
    first = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    last = first + MIN_LIVE_FOR_SOLD
    assert classify_disappeared(first, last) == ListingStatus.SOLD


def test_grenseverdi_rett_under_en_time_er_removed():
    first = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    last = first + MIN_LIVE_FOR_SOLD - timedelta(seconds=1)
    assert classify_disappeared(first, last) == ListingStatus.REMOVED


# --- _reconcile_sold --------------------------------------------------------
# Tester schedulerens reconcile-logikk med mock-repository.

def _make_row(external_id: str, hours_live: float) -> dict:
    first = _dt(hours_live)
    last = _dt(0)
    return {
        "external_id": external_id,
        "first_seen": first.isoformat(),
        "last_seen": last.isoformat(),
    }


def test_reconcile_splitter_sold_og_removed():
    active_rows = [
        _make_row("sell_me", 24),   # lenge ute -> SOLD
        _make_row("rm_me", 0.3),    # knapt sett -> REMOVED
        _make_row("still_here", 5), # fortsatt synlig
    ]
    seen_now = {"still_here"}

    with (
        patch("src.scheduler.repo.get_active_listings_with_timestamps", return_value=active_rows),
        patch("src.scheduler.repo.mark_disappeared") as mock_mark,
    ):
        from src.scheduler import _reconcile_sold
        _reconcile_sold("finn", "phone", seen_now)

    calls = {str(c): c for c in mock_mark.call_args_list}
    sell_call = mock_mark.call_args_list[0]
    remove_call = mock_mark.call_args_list[1]

    assert sell_call.args[1] == ["sell_me"]
    assert sell_call.args[2] == ListingStatus.SOLD
    assert remove_call.args[1] == ["rm_me"]
    assert remove_call.args[2] == ListingStatus.REMOVED


def test_reconcile_ingenting_forsvant():
    active_rows = [_make_row("a", 5), _make_row("b", 5)]
    seen_now = {"a", "b"}

    with (
        patch("src.scheduler.repo.get_active_listings_with_timestamps", return_value=active_rows),
        patch("src.scheduler.repo.mark_disappeared") as mock_mark,
    ):
        from src.scheduler import _reconcile_sold
        _reconcile_sold("finn", "phone", seen_now)

    # Ingen kall med ikke-tomme lister
    for call in mock_mark.call_args_list:
        assert call.args[1] == []


def test_reconcile_alle_forsvant_etter_lang_tid():
    active_rows = [_make_row("x", 10), _make_row("y", 48)]
    seen_now: set[str] = set()

    with (
        patch("src.scheduler.repo.get_active_listings_with_timestamps", return_value=active_rows),
        patch("src.scheduler.repo.mark_disappeared") as mock_mark,
    ):
        from src.scheduler import _reconcile_sold
        _reconcile_sold("finn", "phone", seen_now)

    sell_call = mock_mark.call_args_list[0]
    assert set(sell_call.args[1]) == {"x", "y"}
    assert sell_call.args[2] == ListingStatus.SOLD
    remove_call = mock_mark.call_args_list[1]
    assert remove_call.args[1] == []


# --- mark_disappeared sold_at-logikk ----------------------------------------
# Tester at sold_at bare settes for SOLD, ikke REMOVED.

def test_mark_disappeared_sold_setter_sold_at():
    mock_db = MagicMock()
    with patch("src.db.repository.db", return_value=mock_db):
        from src.db import repository as repo
        repo.mark_disappeared("finn", ["123"], ListingStatus.SOLD)

    update_payload = mock_db.table().update.call_args[0][0]
    assert update_payload["status"] == "sold"
    assert "sold_at" in update_payload


def test_mark_disappeared_removed_setter_ikke_sold_at():
    mock_db = MagicMock()
    with patch("src.db.repository.db", return_value=mock_db):
        from src.db import repository as repo
        repo.mark_disappeared("finn", ["123"], ListingStatus.REMOVED)

    update_payload = mock_db.table().update.call_args[0][0]
    assert update_payload["status"] == "removed"
    assert "sold_at" not in update_payload


def test_mark_disappeared_tom_liste_gjor_ingenting():
    mock_db = MagicMock()
    with patch("src.db.repository.db", return_value=mock_db):
        from src.db import repository as repo
        repo.mark_disappeared("finn", [], ListingStatus.SOLD)

    mock_db.table.assert_not_called()
