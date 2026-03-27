"""Application configuration via environment variables.

Uses pydantic-settings to load config from environment or .env files.
Override DATABASE_URL to switch from SQLite to Postgres.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    database_url: str = "sqlite+aiosqlite:///./nu_events.db"
    app_name: str = "NU Events"
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
