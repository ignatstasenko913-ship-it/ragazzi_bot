"""Userbot event handler: reads order messages from source groups and processes them."""
from __future__ import annotations

import asyncio
from typing import Optional

from loguru import logger
from telethon import TelegramClient, events

from config import settings
from database import ProblematicReason, OrderType
from parsers.registry import ParserRegistry
from routing.geo_service import GeoPoint
from routing.router import order_router
from services.branch_service import branch_service
from services.duplicate_service import duplicate_service
from services.notification_service import notification_service
from services.order_service import order_service
from utils.formatters import (
    format_order,
    format_duplicate_notification,
    format_manager_notification,
    format_parse_error_notification,
)
from utils.validators import is_suspicious_address


class OrderHandler:
    """Wires Telethon event handlers for incoming order messages."""

    def __init__(self, client: TelegramClient, parser_registry: ParserRegistry) -> None:
        self._client = client
        self._registry = parser_registry
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._workers: list[asyncio.Task] = []

    def register(self) -> None:
        """Register Telethon event handlers."""

        @self._client.on(events.NewMessage(chats=settings.ORDER_SOURCE_GROUPS))
        async def on_new_message(event: events.NewMessage.Event) -> None:
            text = event.message.text or ""
            if not text.strip():
                return
            await self._queue.put(
                {
                    "text": text,
                    "group_id": str(event.chat_id),
                    "message_id": event.message.id,
                }
            )

        logger.info(
            "OrderHandler registered for {} source groups: {}",
            len(settings.ORDER_SOURCE_GROUPS),
            settings.ORDER_SOURCE_GROUPS,
        )

    async def start_workers(self) -> None:
        for i in range(settings.ORDER_PROCESSING_WORKERS):
            task = asyncio.create_task(self._worker(i), name=f"order-worker-{i}")
            self._workers.append(task)
        logger.info("Started {} order processing workers", settings.ORDER_PROCESSING_WORKERS)

    async def stop_workers(self) -> None:
        for _ in self._workers:
            await self._queue.put(None)  # poison pill
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def _worker(self, worker_id: int) -> None:
        logger.info("Worker {} started", worker_id)
        while True:
            item = await self._queue.get()
            if item is None:
                break
            try:
                await self._process(
                    item["text"],
                    item["group_id"],
                    item["message_id"],
                )
            except Exception as exc:
                logger.exception("Worker {} unhandled error: {}", worker_id, exc)
            finally:
                self._queue.task_done()
        logger.info("Worker {} stopped", worker_id)

    # ── Core processing pipeline ──────────────────────────────────────────────

    async def _process(self, text: str, group_id: str, message_id: int) -> None:
        logger.debug("Processing message {} from group {}", message_id, group_id)

        # ── 1. Parse ──────────────────────────────────────────────────────────
        parsed, parser_name, parse_error = self._registry.parse(text)

        if parsed is None:
            db_order = await order_service.create_parse_error(
                raw_text=text,
                error=parse_error or "Unknown error",
                source_group_id=group_id,
                source_message_id=message_id,
            )
            notification_text = format_parse_error_notification(
                text, parse_error or "Unknown", db_order.id
            )
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            markup = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="📤 Отправить вручную",
                    callback_data=f"manual_route:{db_order.id}",
                ),
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data=f"cancel_order:{db_order.id}",
                ),
            ]])
            await notification_service.notify_manager_group(notification_text, reply_markup=markup)
            return

        logger.info(
            "Parsed order #{} via {} parser (confidence={:.0%})",
            parsed.order_number, parser_name, parsed.confidence
        )

        # ── 2. Save to DB ─────────────────────────────────────────────────────
        db_order = await order_service.create_from_parsed(
            parsed=parsed,
            raw_text=text,
            source_group_id=group_id,
            source_message_id=message_id,
        )

        # ── 3. Duplicate check ────────────────────────────────────────────────
        original = await duplicate_service.check_and_record(db_order)
        if original is not None:
            dup_text = format_duplicate_notification(parsed, original.id, db_order.id)
            await notification_service.notify_manager_group(dup_text)
            return

        # ── 4. Route ──────────────────────────────────────────────────────────
        if parsed.order_type == OrderType.PICKUP:
            await self._handle_pickup(db_order.id, parsed)
        else:
            await self._handle_delivery(db_order.id, parsed)

    # ── Pickup ────────────────────────────────────────────────────────────────

    async def _handle_pickup(self, order_id: int, parsed) -> None:
        branch_name = parsed.pickup_branch_name or ""
        branch = await order_router.find_pickup_branch(branch_name)

        if branch is None:
            await order_service.mark_problematic(
                order_id,
                ProblematicReason.ROUTING_FAILED,
                f"Не найден филиал для самовывоза: «{branch_name}»",
            )
            formatted = format_order(parsed)
            notification_text = format_manager_notification(
                parsed,
                reason=f"Не найден филиал: «{branch_name}»",
                order_db_id=order_id,
            )
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            markup = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="📤 Выбрать филиал",
                    callback_data=f"manual_route:{order_id}",
                ),
            ]])
            await notification_service.notify_manager_group(notification_text, reply_markup=markup)
            return

        formatted = format_order(parsed, branch_name=branch.name)
        await self._send_and_record(order_id, branch, formatted, parsed)

    # ── Delivery ──────────────────────────────────────────────────────────────

    async def _handle_delivery(self, order_id: int, parsed) -> None:
        address = parsed.delivery_address or ""

        # Pre-check: suspicious address names
        if is_suspicious_address(address):
            await order_service.mark_problematic(
                order_id,
                ProblematicReason.SUSPICIOUS_ADDRESS,
                f"Подозрительный адрес: «{address}»",
            )
            formatted = format_order(parsed)
            notification_text = format_manager_notification(
                parsed,
                reason=f"Подозрительный адрес: «{address}»",
                order_db_id=order_id,
            )
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            markup = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="📤 Отправить вручную",
                    callback_data=f"manual_route:{order_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data=f"cancel_order:{order_id}",
                ),
            ]])
            await notification_service.notify_manager_group(notification_text, reply_markup=markup)
            return

        branch, geo_point, route_error = await order_router.route(address)

        if route_error:
            reason = (
                ProblematicReason.ADDRESS_NOT_FOUND
                if "не найден" in route_error.lower()
                else ProblematicReason.ADDRESS_OUT_OF_ZONE
            )
            await order_service.mark_problematic(order_id, reason, route_error)
            notification_text = format_manager_notification(
                parsed,
                reason=route_error,
                order_db_id=order_id,
            )
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            markup = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="📤 Отправить вручную",
                    callback_data=f"manual_route:{order_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data=f"cancel_order:{order_id}",
                ),
            ]])
            await notification_service.notify_manager_group(notification_text, reply_markup=markup)
            return

        formatted = format_order(parsed, branch_name=branch.name)
        travel = None
        delivery_lat = delivery_lon = None
        if geo_point:
            delivery_lat = geo_point.lat
            delivery_lon = geo_point.lon
            # Calculate travel time from the selected branch
            from routing.geo_service import GeoPoint, geo_service
            branch_point = GeoPoint(lat=branch.lat, lon=branch.lon)
            route = await geo_service.get_driving_time(branch_point, geo_point)
            if route:
                travel = route.duration_minutes

        await self._send_and_record(
            order_id, branch, formatted, parsed,
            travel_time=travel,
            delivery_lat=delivery_lat,
            delivery_lon=delivery_lon,
        )

    # ── Shared send logic ─────────────────────────────────────────────────────

    async def _send_and_record(
        self,
        order_id: int,
        branch,
        formatted: str,
        parsed,
        travel_time: Optional[int] = None,
        delivery_lat: Optional[float] = None,
        delivery_lon: Optional[float] = None,
    ) -> None:
        ok = await notification_service.send_to_branch(branch.telegram_group_id, formatted)
        if ok:
            await order_service.mark_routed(
                order_id,
                branch.id,
                formatted,
                travel_time=travel_time,
                delivery_lat=delivery_lat,
                delivery_lon=delivery_lon,
            )
            await branch_service.mark_order_sent(branch.id)
            # Send duplicate copy to manager group
            manager_copy = f"📋 Копия заказа → *{branch.name}*\n\n{formatted}"
            await notification_service.notify_manager_group(manager_copy)
        else:
            await order_service.mark_problematic(
                order_id,
                ProblematicReason.ROUTING_FAILED,
                f"Не удалось отправить в группу филиала {branch.name}",
            )
            error_text = (
                f"❌ Не удалось отправить заказ в группу филиала *{branch.name}*\n\n"
                f"{formatted}"
            )
            await notification_service.notify_manager_group(error_text)
