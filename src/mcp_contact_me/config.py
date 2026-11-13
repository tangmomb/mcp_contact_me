from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration chargée depuis l'environnement ou le fichier .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CONTACT_",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8000
    allowed_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["127.0.0.1:*", "localhost:*"]
    )
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://127.0.0.1:*", "http://localhost:*"]
    )
    token_registry_path: Path = Path("data/tokens.json")
    rate_limit_db_path: Path = Path("data/rate_limits.db")
    audit_log_path: Path = Path("data/audit.log")
    rate_limit_per_minute: int = Field(default=5, ge=1, le=1000)
    rate_limit_per_day: int = Field(default=50, ge=1, le=100_000)

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    email_from: str | None = None
    email_to: str | None = None

    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None

    @field_validator("allowed_hosts", "allowed_origins", mode="before")
    @classmethod
    def split_comma_separated(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
