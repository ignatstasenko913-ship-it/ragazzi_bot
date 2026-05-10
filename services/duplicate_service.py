"""Duplicate order detection."""
from __future__ import annotations

from typing import Optional

from loguru import logger
from sqlalchemy import select

from config import settings
from database import Order, DuplicateOrder
from database.session import get_session
from services.order_service import order_service


class DuplicateService:

    async def check_and_record(self, new_order: Order) -> Optional[Order]:
        """
        Check if `new_order` is a duplicate of a recent order.
        If yes, records the duplicate and returns the original order.
        Returns None if not a duplicate.
        """
        original = await order_service.find_existing(
            order_number=new_order.order_number,
            customer_phone=new_order.customer_phone,
            window_minutes=settings.DUPLICATE_WINDOW_MINUTES,
        )

        if original is None or original.id == new_order.id:
            return None

        logger.warning(
            "Duplicate detected: order {} is a duplicate of order {}",
            new_order.id,
            original.id,
        )

        async with get_session() as session:
            dup = DuplicateOrder(
                order_id=new_order.id,
                original_order_id=original.id,
            )
            session.add(dup)

        await order_service.mark_duplicate(new_order.id)
        return original


duplicate_service = DuplicateService()
