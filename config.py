"""
Secure configuration management using pydantic-settings.

All secrets and config are loaded from environment variables / .env file.
The application will fail fast at startup if any required variable is missing.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """Application settings — loaded from .env and validated at startup."""

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Discord ──────────────────────────────────────────────────────────
    discord_token: str = Field(..., description="Discord bot token")
    guild_id: int = Field(..., description="Primary guild (server) ID")
    verified_role_id: int = Field(..., description="Role ID for verified users")
    mod_channel_id: int = Field(..., description="Channel ID for mod alerts")
    mod_role_id: int = Field(0, description="Role ID to ping on mod alerts (0 to disable)")
    welcome_channel_id: int = Field(0, description="Channel ID for welcome banners (0 to disable)")

    # ── Database ─────────────────────────────────────────────────────────
    database_url: str = Field(
        ...,
        description="Async database URL (e.g. postgresql+asyncpg://…)",
    )

    # ── hCaptcha ─────────────────────────────────────────────────────────
    hcaptcha_site_key: str = Field(..., description="hCaptcha site key")
    hcaptcha_secret_key: str = Field(..., description="hCaptcha secret key")

    # ── Captcha Web Server ───────────────────────────────────────────────
    captcha_server_url: str = Field(
        "http://localhost:8080",
        description="Public URL of the captcha verification server",
    )
    captcha_server_port: int = Field(
        default_factory=lambda: int(__import__("os").environ.get("PORT", 8080)),
        description="Port for captcha server",
    )
    signing_secret: str = Field(
        ..., description="Secret for signing verification tokens"
    )

    # ── Bot Behaviour ────────────────────────────────────────────────────
    command_prefix: str = Field("!", description="Legacy command prefix")
    log_level: str = Field("INFO", description="Logging level")

    # ── Validators ───────────────────────────────────────────────────────
    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        v = v.upper()
        if v not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"Invalid log level: {v}")
        return v

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, v: str) -> str:
        if not v:
            raise ValueError("DATABASE_URL must not be empty")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached, validated application settings."""
    return Settings()  # type: ignore[call-arg]


def configure_logging(level: str = "INFO") -> None:
    """Set up structured logging for the entire application."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Silence noisy libraries
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
