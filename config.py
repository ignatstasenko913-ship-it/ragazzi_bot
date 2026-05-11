from __future__ import annotations

from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Userbot ──────────────────────────────────────────────
    TELEGRAM_API_ID: int
    TELEGRAM_API_HASH: str
    TELEGRAM_PHONE: str
    TELEGRAM_SESSION_NAME: str = "ragazzi_userbot"

    # ── Admin Bot ────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str

    # ── Source groups ────────────────────────────────────────
    ORDER_SOURCE_GROUPS: List[int] = Field(default_factory=list)

    # ── Roles ────────────────────────────────────────────────
    ADMIN_IDS: List[int] = Field(default_factory=list)
    MANAGER_IDS: List[int] = Field(default_factory=list)
    MANAGER_GROUP_ID: int = 0

    # ── Delivery zone ─────────────────────────────────────────
    DELIVERY_CENTER_LAT: float = 43.1155
    DELIVERY_CENTER_LON: float = 131.8855
    DELIVERY_MAX_RADIUS_KM: float = 50.0

    # ── Database ─────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./ragazzi.db"

    # ── Processing ───────────────────────────────────────────
    DUPLICATE_WINDOW_MINUTES: int = 60
    ORDER_PROCESSING_WORKERS: int = 3

    # ── Logging ──────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/ragazzi.log"

    @field_validator("ORDER_SOURCE_GROUPS", "ADMIN_IDS", "MANAGER_IDS", mode="before")
    @classmethod
    def parse_int_list(cls, v: object) -> List[int]:
        if isinstance(v, list):
            return [int(x) for x in v]
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return []

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
