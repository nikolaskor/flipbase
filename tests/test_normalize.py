"""Tester for normalize._derive_model_key.

Dekker telefon, konsoll og kamera, og akseptansekravet:
  to kategorier med like marginer rangeres ulikt uten falske model_key-sammenslaainger.
"""
from __future__ import annotations

import pytest

from src.models.schemas import Category
from src.pipeline.normalize import _derive_model_key


# --- telefon (eksisterende kategori, verifiser at den ikke er brutt) ----------

@pytest.mark.parametrize("title,expected", [
    ("iPhone 13 128GB",          "iphone_13_128gb"),
    ("iPhone 13 Pro 256GB",      "iphone_13_pro_256gb"),
    ("iPhone 14 Pro Max 512GB",  "iphone_14_pro_max_512gb"),
    ("iPhone 15 128 GB",         "iphone_15_128gb"),
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
