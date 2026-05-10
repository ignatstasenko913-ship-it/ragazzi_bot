"""Sends Telegram notifications via the admin bot and userbot."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from loguru import logger

from config import settings

if TYPE_CHECKING:
    from telethon import TelegramClient
    from aiogram import Bot


class NotificationService:
    """Thin wrapper that sends messages to branches and managers."""

    def __init__(self) -> None:
        self._bot: Optional["Bot"] = None
        self._userbot: Optional["TelegramClient"] = None

    def setup(self, bot: "Bot", userbot: "TelegramClient") -> None:
        self._bot = bot
        self._userbot = userbot

    # ── Send to branch ────────────────────────────────────────────────────────

    async def send_to_branch(self, group_id: str, text: str) -> bool:
        """Send the formatted order to the branch Telegram group."""
        try:
            entity = int(group_id) if group_id.lstrip("-").isdigit() else group_id
            await self._userbot.send_message(entity, text)
            logger.info("Order sent to branch group {}", group_id)
            return True
        except Exception as exc:
            logger.error("Failed to send to branch {}: {}", group_id, exc)
            return False

    # ── Manager notifications ─────────────────────────────────────────────────

    async def notify_manager_group(self, text: str, reply_markup=None) -> bool:
        if not settings.MANAGER_GROUP_ID:
            return await self._notify_managers_individually(text, reply_markup)
        try:
            await self._bot.send_message(
                settings.MANAGER_GROUP_ID,
                text,
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )
            return True
        except Exception as exc:
            logger.error("Failed to notify manager group: {}", exc)
            return await self._notify_managers_individually(text, reply_markup)

    async def _notify_managers_individually(self, text: str, reply_markup=None) -> bool:
        if not settings.MANAGER_IDS:
            logger.warning("No manager IDs configured — dropping notification")
            return False
        success = False
        for manager_id in settings.MANAGER_IDS:
            try:
                await self._bot.send_message(
                    manager_id,
                    text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown",
                )
                success = True
            except Exception as exc:
                logger.error("Failed to notify manager {}: {}", manager_id, exc)
        return success

    async def notify_admins(self, text: str) -> None:
        for admin_id in settings.ADMIN_IDS:
            try:
                await self._bot.send_message(admin_id, text, parse_mode="Markdown")
            except Exception as exc:
                logger.error("Failed to notify admin {}: {}", admin_id, exc)


notification_service = NotificationService()
