from __future__ import annotations

import json
from typing import Any, List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_int_list(raw: Any) -> List[int]:
    """
    Parse a comma-separated string or JSON array into List[int].
    Handles: "123", "123,456", "[123,456]", int, list.
    """
    if isinstance(raw, list):
        return [int(x) for x in raw]
    if isinstance(raw, int):
        return [raw]
    if not isinstance(raw, str):
        return []
    raw = raw.strip()
    if not raw:
        return []
    if raw.startswith("["):
        return json.loads(raw)
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


class Settings(BaseSettings):
    # ── Userbot ───────────────────────────────────────────────
    TELEGRAM_API_ID: int
    TELEGRAM_API_HASH: str
    TELEGRAM_PHONE: str
    TELEGRAM_SESSION_NAME: str = "ragazzi_userbot"

    # ── Admin Bot ─────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str

    # ── Source groups / roles ─────────────────────────────────
    # Declared as str to prevent pydantic-settings from JSON-pre-parsing
    # list fields (it calls json.loads internally for List[T] fields,
    # which crashes on comma-separated values like "-100x,-100y").
    # model_post_init converts them to List[int] after loading.
    ORDER_SOURCE_GROUPS: str = Field(default="")
    ADMIN_IDS: str = Field(default="")
    MANAGER_IDS: str = Field(default="")
    MANAGER_GROUP_ID: int = 0

    # ── Delivery zone ─────────────────────────────────────────
    DELIVERY_CENTER_LAT: float = 43.1155
    DELIVERY_CENTER_LON: float = 131.8855
    DELIVERY_MAX_RADIUS_KM: float = 50.0

    # ── Database ──────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./ragazzi.db"

    # ── Processing ────────────────────────────────────────────
    DUPLICATE_WINDOW_MINUTES: int = 60
    ORDER_PROCESSING_WORKERS: int = 3

    # ── Logging ───────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/ragazzi.log"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    def model_post_init(self, __context: Any) -> None:
        """Convert str list-fields to List[int] after env loading."""
        object.__setattr__(self, "ORDER_SOURCE_GROUPS", _parse_int_list(self.ORDER_SOURCE_GROUPS))
        object.__setattr__(self, "ADMIN_IDS", _parse_int_list(self.ADMIN_IDS))
        object.__setattr__(self, "MANAGER_IDS", _parse_int_list(self.MANAGER_IDS))


settings = Settings()
