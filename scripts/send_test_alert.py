"""Send et testvarsel til Telegram og bekreft at dedup virker.

Brukes for aa verifisere at boten er konfigurert riktig og at varselet
ser bra ut i chatten forst.

Bruk:
    python -m scripts.send_test_alert          # send eitt varsel, print teksten
    python -m scripts.send_test_alert --dedup  # send en gang til, skal bli blokkert
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from src.models.schemas import (
    Category, FlipOpportunity, Listing, ListingStatus, RedFlag,
)
from src.notify.telegram import format_alert, send

_FAKE_LISTING = Listing(
    source="finn",
    external_id="TEST-999",
    category=Category.PHONE,
    model_key="iphone_13_128gb",
    title="iPhone 13 128GB Midnight (testannonse)",
    price=2500,
    description="Pent brukt, ingen riper. Originalkasse medfølger.",
    image_urls=["https://images.finncdn.no/test.jpg"],
    location="Oslo",
    distance_km=None,
    seller_name="TestSelger",
    seller_listing_count=None,
    posted_at=datetime.now(timezone.utc),
    url="https://www.finn.no/recommerce/forsale/item/TEST-999",
    status=ListingStatus.ACTIVE,
    first_seen=datetime.now(timezone.utc),
    last_seen=datetime.now(timezone.utc),
)

_FAKE_OPP = FlipOpportunity(
    listing=_FAKE_LISTING,
    reference_price=3400,
    estimated_sell_price=3400,
    shipping_cost=149,
    flip_score=0.30,
    net_margin=751,
    median_days_to_sold=None,
    red_flags=[
        RedFlag(code="few_images", label="Faa bilder (1 eller faerre)", severity="warn"),
    ],
    vision=None,
)


async def run(dedup: bool) -> None:
    text = format_alert(_FAKE_OPP)
    print("=== Formatert varsel ===")
    print(text)
    print()

    if dedup:
        from src.db import repository as repo
        if repo.already_alerted("finn", "TEST-999"):
            print("DEDUP OK: TEST-999 er allerede varslet, sender ikke paa nytt.")
            return
        print("ADVARSEL: TEST-999 er ikke i alerts_sent. Kjor uten --dedup forst.")
        return

    ok = await send(_FAKE_OPP)
    if ok:
        print("Telegram: sendt OK.")
        from src.db import repository as repo
        repo.record_alert("finn", "TEST-999", _FAKE_OPP.flip_score)
        print("alerts_sent: registrert.")
    else:
        print("Telegram: sending feilet. Sjekk TELEGRAM_BOT_TOKEN og TELEGRAM_CHAT_ID.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dedup", action="store_true", help="verifiser dedup, ikke send")
    asyncio.run(run(parser.parse_args().dedup))


if __name__ == "__main__":
    main()
