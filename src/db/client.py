"""Supabase-klient (singleton)."""
from __future__ import annotations

from supabase import Client, create_client

from src.config import settings

_client: Client | None = None


def db() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_key)
    return _client
