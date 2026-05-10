"""Entry point: starts the Telethon userbot and aiogram admin bot concurrently."""
from __future__ import annotations

import asyncio
import signal
import sys
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger
from telethon import TelegramClient

from config import settings
from database.session import init_db
from handlers.admin_bot.admin_handler import router as admin_router
from handlers.userbot.order_handler import OrderHandler
from parsers.registry import build_registry
from routing.geo_service import geo_service
from services.notification_service import notification_service
from utils.logger import setup_logging


async def start_admin_bot(bot: Bot, dp: Dispatcher) -> None:
    logger.info("Starting admin bot (long polling)...")
    await dp.start_polling(bot, handle_signals=False)


async def start_userbot(
    client: TelegramClient,
    order_handler: OrderHandler,
) -> None:
    logger.info("Connecting userbot...")
    await client.start(phone=settings.TELEGRAM_PHONE)
    me = await client.get_me()
    logger.info("Userbot connected as @{} ({})", me.username, me.id)

    order_handler.register()
    await order_handler.start_workers()

    logger.info("Userbot running — watching {} source groups", len(settings.ORDER_SOURCE_GROUPS))
    await client.run_until_disconnected()


async def shutdown(
    client: TelegramClient,
    order_handler: OrderHandler,
    bot: Bot,
) -> None:
    logger.info("Shutting down...")
    await order_handler.stop_workers()
    await geo_service.close()
    if client.is_connected():
        await client.disconnect()
    await bot.session.close()
    logger.info("Shutdown complete.")


async def main() -> None:
    setup_logging()
    logger.info("Ragazzi order routing system starting up...")

    # ── Database ───────────────────────────────────────────────────────────────
    await init_db()
    logger.info("Database initialized")

    # ── Parser registry ────────────────────────────────────────────────────────
    parser_registry = build_registry()
    logger.info("Parsers loaded: {}", parser_registry.parser_names)

    # ── Admin bot setup ────────────────────────────────────────────────────────
    bot = Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="Markdown"),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(admin_router)

    # ── Userbot setup ──────────────────────────────────────────────────────────
    client = TelegramClient(
        settings.TELEGRAM_SESSION_NAME,
        settings.TELEGRAM_API_ID,
        settings.TELEGRAM_API_HASH,
    )

    order_handler = OrderHandler(client=client, parser_registry=parser_registry)

    # ── Wire notification service ──────────────────────────────────────────────
    notification_service.setup(bot=bot, userbot=client)

    # ── Run both concurrently ──────────────────────────────────────────────────
    loop = asyncio.get_running_loop()

    def _signal_handler() -> None:
        logger.info("Signal received, initiating shutdown...")
        loop.create_task(shutdown(client, order_handler, bot))

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass  # Windows

    try:
        await asyncio.gather(
            start_admin_bot(bot, dp),
            start_userbot(client, order_handler),
        )
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await shutdown(client, order_handler, bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
