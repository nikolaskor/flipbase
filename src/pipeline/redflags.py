"""Red-flag-detektor: raske heuristikker som hjelper deg prioritere
hvilke kandidater du gidder a aapne. Erstatter ikke manuell vurdering.
"""
from __future__ import annotations

from src.models.schemas import Listing, RedFlag

SCREEN_KEYWORDS = ("skjerm", "display", "screen")
DAMAGE_KEYWORDS = ("sprekk", "knust", "ripe", "bulk", "defekt", "virker ikke", "feil")

# Ettermarkedsdeler gjor "100% batteri" ubrukelig og senker videresalgsverdi betydelig.
NON_ORIGINAL_KEYWORDS = ("ikke original", "ikke-original", "ikke originalt", "tredjeparts", "ettermarked")


def detect(listing: Listing) -> list[RedFlag]:
    flags: list[RedFlag] = []
    desc = listing.description.lower()

    # Faa eller ingen bilder
    if len(listing.image_urls) <= 1:
        flags.append(RedFlag(
            code="few_images",
            label="Faa bilder (1 eller faerre)",
            severity="warn",
        ))

    # Mangler bilde av skjerm for skjermprodukter
    if listing.category.value in ("phone", "tablet", "console"):
        if not any(k in desc for k in SCREEN_KEYWORDS):
            flags.append(RedFlag(
                code="no_screen_mention",
                label="Skjerm ikke nevnt i beskrivelse",
                severity="info",
            ))

    # Tynn beskrivelse
    if len(desc.split()) < 20:
        flags.append(RedFlag(
            code="short_description",
            label="Kort beskrivelse (under 20 ord)",
            severity="warn",
        ))

    # Ny selger
    if listing.seller_listing_count is not None and listing.seller_listing_count < 3:
        flags.append(RedFlag(
            code="new_seller",
            label="Ny FINN-profil (under 3 annonser)",
            severity="warn",
        ))

    # Eksplisitte skade-ord
    hit = [k for k in DAMAGE_KEYWORDS if k in desc]
    if hit:
        flags.append(RedFlag(
            code="damage_keywords",
            label=f"Skadeord i tekst: {', '.join(hit)}",
            severity="high",
        ))

    # Ettermarkedsdeler: skjerm eller batteri som ikke er original
    non_orig_hit = [k for k in NON_ORIGINAL_KEYWORDS if k in desc]
    if non_orig_hit:
        flags.append(RedFlag(
            code="non_original_parts",
            label="Ettermarkedsdeler nevnt: margin og batteri-% er upaalitelig",
            severity="high",
        ))

    return flags
