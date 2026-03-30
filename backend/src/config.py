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
    cors_origins: list[str] = [
        "http://localhost:3000", "http://localhost:3001", "http://localhost:3002",
        "https://nu-events.vercel.app", "https://nu-events-*.vercel.app",
    ]
    api_key: str | None = None

    # Gmail IMAP Poller settings
    gmail_credentials_file: str = "credentials.json"
    gmail_token_file: str = "token.json"
    gmail_user_email: str = ""  # Your Gmail address (e.g. graceshao@u.northwestern.edu)
    gmail_label: str = "NU-Events"
    gmail_poll_interval_seconds: int = 900  # 15 minutes
    gmail_imap_host: str = "imap.gmail.com"
    gmail_imap_port: int = 993

    # Instagram scraper settings
    instagram_session_user: str = ""  # Instagram username for session file (optional)
    instagram_days_back: int = 14  # How far back to scrape
    instagram_max_posts_per_org: int = 10  # Max posts per org

    # Ollama LLM settings
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "gemma3:12b"
    use_llm_parser: bool = True  # Set to False to disable LLM parsing

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
