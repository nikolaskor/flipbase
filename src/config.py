"""Sentral konfigurasjon. Leser fra miljovariabler / .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = ""
    supabase_service_key: str = ""
    anthropic_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    flip_score_threshold: float = 0.30
    scrape_interval_minutes: int = 7
    vision_enabled: bool = True
    vision_max_per_run: int = 10


settings = Settings()
