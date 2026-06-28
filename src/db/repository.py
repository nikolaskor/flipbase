"""Databaseoperasjoner pipelinen trenger. Tynt lag over Supabase."""
from __future__ import annotations

from datetime import datetime, timezone

from src.db.client import db
from src.models.schemas import Listing, ListingStatus


def upsert_listing(listing: Listing) -> None:
    """Sett inn ny annonse eller oppdater last_seen paa eksisterende."""
    db().table("listings").upsert({
        "source": listing.source,
        "external_id": listing.external_id,
        "category": listing.category.value,
        "model_key": listing.model_key,
        "title": listing.title,
        "price": listing.price,
        "description": listing.description,
        "image_urls": listing.image_urls,
        "location": listing.location,
        "distance_km": listing.distance_km,
        "seller_name": listing.seller_name,
        "seller_listing_count": listing.seller_listing_count,
        "posted_at": listing.posted_at.isoformat() if listing.posted_at else None,
        "url": listing.url,
        "status": listing.status.value,
        "last_seen": listing.last_seen.isoformat(),
    }, on_conflict="source,external_id").execute()


def get_active_listings_with_timestamps(source: str, category: str) -> list[dict]:
    """Henter external_id, first_seen og last_seen for alle aktive annonser."""
    rows = (db().table("listings")
            .select("external_id,first_seen,last_seen")
            .eq("source", source)
            .eq("category", category)
            .eq("status", ListingStatus.ACTIVE.value)
            .execute())
    return rows.data


def mark_disappeared(source: str, external_ids: list[str], status: ListingStatus) -> None:
    if not external_ids:
        return
    update: dict = {"status": status.value}
    if status == ListingStatus.SOLD:
        update["sold_at"] = datetime.now(timezone.utc).isoformat()
    (db().table("listings")
     .update(update)
     .eq("source", source)
     .in_("external_id", external_ids)
     .execute())


def reference_sample(model_key: str) -> list[int]:
    """Solgte priser for en model_key, til medianberegning."""
    rows = (db().table("listings")
            .select("price")
            .eq("model_key", model_key)
            .eq("status", ListingStatus.SOLD.value)
            .execute())
    return [r["price"] for r in rows.data if r["price"]]


def sold_durations(model_key: str) -> list[float]:
    """Dager-til-solgt per solgt annonse, til likviditetsmaal."""
    rows = (db().table("listings")
            .select("first_seen,sold_at")
            .eq("model_key", model_key)
            .eq("status", ListingStatus.SOLD.value)
            .execute())
    out: list[float] = []
    for r in rows.data:
        if r.get("first_seen") and r.get("sold_at"):
            fs = datetime.fromisoformat(r["first_seen"])
            sa = datetime.fromisoformat(r["sold_at"])
            out.append((sa - fs).total_seconds() / 86_400)
    return out


def already_alerted(source: str, external_id: str) -> bool:
    rows = (db().table("alerts_sent")
            .select("id")
            .eq("source", source)
            .eq("external_id", external_id)
            .execute())
    return len(rows.data) > 0


def record_alert(source: str, external_id: str, flip_score: float) -> None:
    db().table("alerts_sent").insert({
        "source": source,
        "external_id": external_id,
        "flip_score": flip_score,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
