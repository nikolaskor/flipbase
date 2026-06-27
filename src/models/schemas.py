"""Datamodeller som flyter gjennom pipelinen."""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Category(str, Enum):
    PHONE = "phone"
    AIRPODS = "airpods"
    TABLET = "tablet"
    CONSOLE = "console"
    GAMING_GEAR = "gaming_gear"
    CAMERA = "camera"


class ListingStatus(str, Enum):
    ACTIVE = "active"
    SOLD = "sold"        # forsvunnet fra FINN, antatt solgt
    REMOVED = "removed"  # fjernet uten salg (utledet)


class RawListing(BaseModel):
    """Rett ut av scraperen, for normalisering."""
    source: str = "finn"
    external_id: str
    title: str
    price: int | None = None
    description: str = ""
    image_urls: list[str] = Field(default_factory=list)
    location: str = ""
    distance_km: float | None = None
    seller_name: str = ""
    seller_listing_count: int | None = None
    posted_at: datetime | None = None
    url: str


class Listing(BaseModel):
    """Normalisert annonse, lagres i `listings`."""
    source: str
    external_id: str
    category: Category
    model_key: str          # normalisert modell, f.eks. "iphone_13_128"
    title: str
    price: int
    description: str
    image_urls: list[str]
    location: str
    distance_km: float | None
    seller_name: str
    seller_listing_count: int | None
    posted_at: datetime | None
    url: str
    status: ListingStatus = ListingStatus.ACTIVE
    first_seen: datetime
    last_seen: datetime


class RedFlag(BaseModel):
    code: str        # f.eks. "no_screen_photo"
    label: str       # menneskelesbar tekst for varselet
    severity: str    # "info" | "warn" | "high"


class VisionAssessment(BaseModel):
    condition_score: int       # 1-10
    visible_damage: list[str]
    summary: str
    confidence: float          # 0-1


class FlipOpportunity(BaseModel):
    """Det ferdige resultatet som sendes til Telegram."""
    listing: Listing
    reference_price: int
    estimated_sell_price: int
    shipping_cost: int
    flip_score: float
    net_margin: int
    median_days_to_sold: float | None
    red_flags: list[RedFlag] = Field(default_factory=list)
    vision: VisionAssessment | None = None
