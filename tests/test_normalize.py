"""Tester for normalize._derive_model_key og normalize().

Dekker telefon, konsoll og kamera, og akseptansekravet:
  to kategorier med like marginer rangeres ulikt uten falske model_key-sammenslaainger.
"""
from __future__ import annotations

import pytest

from src.models.schemas import Category, RawListing
from src.pipeline.normalize import _derive_model_key, normalize


def _raw(title: str, price: int = 500) -> RawListing:
    return RawListing(external_id="x", title=title, price=price, url="https://finn.no/x")


# --- aksessorier filtreres ut (returnerer None) --------------------------------

@pytest.mark.parametrize("title", [
    "iPhone 15 Pro Max deksel med MagSafe + sugekopp-pad",
    "dbramante1928 iPhone 15 Pro deksel",
    "iPhone 14 pro deksel",
    "iPhone 13 cover",
    "Apple lader til iPhone 12",
    "MagSafe kabel til iPhone",
    "iPhone 15 kortholder wallet",
])
def test_telefon_aksessorier_filtreres_ut(title: str):
    assert normalize(_raw(title), Category.PHONE) is None


@pytest.mark.parametrize("title", [
    "iPad Air deksel med tastatur",
    "iPad Pro cover",
    "iPad skjermbeskytter panzerglass",
])
def test_tablet_aksessorier_filtreres_ut(title: str):
    assert normalize(_raw(title), Category.TABLET) is None


def test_ekte_iphone_passerer_filteret():
    result = normalize(_raw("iPhone 13 128GB"), Category.PHONE)
    assert result is not None
    assert result.model_key == "iphone_13_128gb"


def test_ekte_ipad_passerer_filteret():
    result = normalize(_raw("iPad Air"), Category.TABLET)
    assert result is not None


# --- telefon (eksisterende kategori, verifiser at den ikke er brutt) ----------

@pytest.mark.parametrize("title,expected", [
    ("iPhone 13 128GB",          "iphone_13_128gb"),
    ("iPhone 13 Pro 256GB",      "iphone_13_pro_256gb"),
    ("iPhone 14 Pro Max 512GB",  "iphone_14_pro_max_512gb"),
    ("iPhone 12 64GB",           "iphone_12_64gb"),
    ("Apple iPhone 13 128GB",    "iphone_13_128gb"),
])
def test_iphone_model_key(title: str, expected: str):
    assert _derive_model_key(title, Category.PHONE) == expected


def test_iphone_uten_lagring():
    # Titler uten GB-angivelse faar key uten lagringssufiks
    assert _derive_model_key("iPhone 13", Category.PHONE) == "iphone_13"


# --- konsoll: PS5 ------------------------------------------------------------

@pytest.mark.parametrize("title,expected", [
    ("PS5",                  "ps5"),
    ("PS5 Digital Edition",  "ps5"),
    ("PS5 Slim",             "ps5"),
    ("PlayStation 5",        "ps5"),       # alias-normalisering
    ("PlayStation 5 Slim",   "ps5"),       # alias-normalisering
])
def test_ps5_model_key(title: str, expected: str):
    assert _derive_model_key(title, Category.CONSOLE) == expected


# --- konsoll: Switch ---------------------------------------------------------

@pytest.mark.parametrize("title,expected", [
    ("Switch",                  "switch"),
    ("Nintendo Switch",         "switch"),       # alias: nintendo_ prefix fjernes
    ("Switch OLED",             "switch_oled"),
    ("Nintendo Switch OLED",    "switch_oled"),  # alias
    ("Switch Lite",             "switch_lite"),
    ("Nintendo Switch Lite",    "switch_lite"),  # alias
])
def test_switch_model_key(title: str, expected: str):
    assert _derive_model_key(title, Category.CONSOLE) == expected


def test_ps5_og_switch_gir_ulike_nokler():
    assert _derive_model_key("PS5", Category.CONSOLE) != _derive_model_key("Nintendo Switch", Category.CONSOLE)


def test_switch_og_switch_oled_gir_ulike_nokler():
    assert _derive_model_key("Switch", Category.CONSOLE) != _derive_model_key("Switch OLED", Category.CONSOLE)


# --- konsoll: lagring skal IKKE appending paa konsoll-nokkel ----------------

def test_ps5_med_lagringstittel_faar_ikke_storage_sufiks():
    # "PS5 825GB" er en faktisk FINN-tittel. Lagringsdeteksjon skal ikke slaa til.
    assert _derive_model_key("PS5 825GB intern lagring", Category.CONSOLE) == "ps5"


def test_switch_med_lagringstittel_faar_ikke_storage_sufiks():
    assert _derive_model_key("Nintendo Switch OLED 64GB", Category.CONSOLE) == "switch_oled"


# --- kamera: Sony ------------------------------------------------------------

@pytest.mark.parametrize("title,expected", [
    ("Sony A7 III",    "sony_a7"),
    ("Sony A6400",     "sony_a6400"),
    ("Sony ZV-E10",    "sony_zv_e10"),   # bindestrek normaliseres til _
])
def test_sony_camera_model_key(title: str, expected: str):
    assert _derive_model_key(title, Category.CAMERA) == expected


def test_kamera_faar_ikke_storage_sufiks():
    # SD-kort nevnt i tittelen skal ikke pavirke model_key
    assert _derive_model_key("Sony A6400 med 64GB minnekort", Category.CAMERA) == "sony_a6400"


def test_ulike_merker_gir_ulike_nokler():
    assert _derive_model_key("Sony A7", Category.CAMERA) != _derive_model_key("Canon R50", Category.CAMERA)


# --- ukjente titler ----------------------------------------------------------

def test_ukjent_konsoll_gir_fallback():
    assert _derive_model_key("Xbox Series X", Category.CONSOLE) == "console_unknown"


def test_ukjent_telefon_gir_fallback():
    assert _derive_model_key("Samsung Galaxy S24", Category.PHONE) == "phone_unknown"


def test_iphone_15_gir_ukjent_model_key():
    assert _derive_model_key("iPhone 15 128 GB", Category.PHONE) == "phone_unknown"


# --- kun iPhone 12-14 slipper gjennom normalize --------------------------------

@pytest.mark.parametrize("title", [
    "UAG reim til Apple Watch 42/44/49",
    "ISY TRÅDLØS MUS (brukt kun i 1 uke)",
    "Varm skijakke svart",
    "Vin sett i boksen",
    "Samsung Galaxy S24 128GB",
    "iPhone 11 64GB",
    "iPhone 15 Pro Max 256GB",
    "Apple Watch Series 8",
])
def test_ikke_iphone_12_14_filtreres_ut(title: str):
    assert normalize(_raw(title), Category.PHONE) is None


@pytest.mark.parametrize("title,expected_key", [
    ("iPhone 12 128GB svart",        "iphone_12_128gb"),
    ("iPhone 13 Pro 256GB",          "iphone_13_pro_256gb"),
    ("iPhone 14 Pro Max 512GB",      "iphone_14_pro_max_512gb"),
    ("Apple iPhone 14 128 GB",       "iphone_14_128gb"),
    ("iPhone 13 mini 128GB",         "iphone_13_mini_128gb"),
    ("iPhone 14 Plus 128GB",         "iphone_14_plus_128gb"),
])
def test_iphone_12_14_slipper_gjennom(title: str, expected_key: str):
    result = normalize(_raw(title), Category.PHONE)
    assert result is not None
    assert result.model_key == expected_key
