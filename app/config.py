from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "disclosure-fundamental-mvp"
    app_env: str = "development"
    debug: bool = True
    database_url: str = "sqlite:///./data/app.db"
    log_level: str = "INFO"
    web_base_url: str = "https://example.com/app"
    notification_channel: str = "dummy"
    notification_destination: str = "dummy-channel"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    discord_webhook_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return True
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on", "debug", "development"}:
            return True
        if normalized in {"0", "false", "no", "off", "release", "prod", "production"}:
            return False
        raise ValueError(f"Unsupported debug value: {value}")


@lru_cache
def get_settings() -> Settings:
    return Settings()
