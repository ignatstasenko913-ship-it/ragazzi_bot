"""CRUD and queries for orders."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from loguru import logger
from sqlalchemy import select, desc, func

from database import Order, OrderStatus, OrderSource, OrderType, ProblematicReason
from database.session import get_session
from parsers.base import ParsedOrder


class OrderService:

    async def create_from_parsed(
        self,
        parsed: ParsedOrder,
        raw_text: str,
        source_group_id: str = "",
        source_message_id: int = 0,
    ) -> Order:
        async with get_session() as session:
            items_data = [i.to_dict() for i in parsed.items]
            order = Order(
                order_number=parsed.order_number,
                source=parsed.source,
                order_type=parsed.order_type,
                status=OrderStatus.PENDING,
                customer_name=parsed.customer_name,
                customer_phone=parsed.customer_phone,
                delivery_address=parsed.delivery_address,
                pickup_branch_name=parsed.pickup_branch_name,
                items=items_data,
                total_amount=parsed.total_amount,
                discount=parsed.discount,
                comment=parsed.comment,
                payment_method=parsed.payment_method,
                payment_status=parsed.payment_status,
                delivery_time=parsed.delivery_time,
                order_date=parsed.order_date,
                raw_text=raw_text,
                source_group_id=source_group_id,
                source_message_id=source_message_id,
            )
            session.add(order)
            await session.flush()
            await session.refresh(order)
            logger.info("Created order #{} (id={})", order.order_number, order.id)
            return order

    async def create_parse_error(
        self,
        raw_text: str,
        error: str,
        source_group_id: str = "",
        source_message_id: int = 0,
    ) -> Order:
        async with get_session() as session:
            order = Order(
                status=OrderStatus.PARSE_ERROR,
                source=OrderSource.UNKNOWN,
                raw_text=raw_text,
                problem_reason=ProblematicReason.PARSE_ERROR,
                problem_detail=error,
                source_group_id=source_group_id,
                source_message_id=source_message_id,
            )
            session.add(order)
            await session.flush()
            await session.refresh(order)
            return order

    async def mark_routed(
        self,
        order_id: int,
        branch_id: int,
        formatted_text: str,
        travel_time: Optional[int] = None,
        delivery_lat: Optional[float] = None,
        delivery_lon: Optional[float] = None,
    ) -> None:
        async with get_session() as session:
            result = await session.execute(select(Order).where(Order.id == order_id))
            order = result.scalar_one_or_none()
            if order:
                order.status = OrderStatus.ROUTED
                order.branch_id = branch_id
                order.formatted_text = formatted_text
                order.travel_time_minutes = travel_time
                order.routed_at = datetime.utcnow()
                if delivery_lat:
                    order.delivery_lat = delivery_lat
                if delivery_lon:
                    order.delivery_lon = delivery_lon

    async def mark_problematic(
        self,
        order_id: int,
        reason: ProblematicReason,
        detail: str = "",
    ) -> None:
        async with get_session() as session:
            result = await session.execute(select(Order).where(Order.id == order_id))
            order = result.scalar_one_or_none()
            if order:
                order.status = OrderStatus.PROBLEMATIC
                order.problem_reason = reason
                order.problem_detail = detail

    async def mark_duplicate(self, order_id: int) -> None:
        async with get_session() as session:
            result = await session.execute(select(Order).where(Order.id == order_id))
            order = result.scalar_one_or_none()
            if order:
                order.status = OrderStatus.DUPLICATE

    async def mark_manually_routed(
        self,
        order_id: int,
        branch_id: int,
        formatted_text: str,
        resolver_tg_id: int,
    ) -> None:
        from database import TelegramUser
        async with get_session() as session:
            result = await session.execute(select(Order).where(Order.id == order_id))
            order = result.scalar_one_or_none()
            if not order:
                return
            order.status = OrderStatus.MANUALLY_ROUTED
            order.branch_id = branch_id
            order.formatted_text = formatted_text
            order.routed_at = datetime.utcnow()
            order.is_resolved = True
            order.resolved_at = datetime.utcnow()

            user_result = await session.execute(
                select(TelegramUser).where(TelegramUser.telegram_id == resolver_tg_id)
            )
            user = user_result.scalar_one_or_none()
            if user:
                order.resolved_by_id = user.id

    async def mark_cancelled(self, order_id: int) -> None:
        async with get_session() as session:
            result = await session.execute(select(Order).where(Order.id == order_id))
            order = result.scalar_one_or_none()
            if order:
                order.status = OrderStatus.CANCELLED
                order.is_resolved = True
                order.resolved_at = datetime.utcnow()

    async def get_by_id(self, order_id: int) -> Optional[Order]:
        async with get_session() as session:
            result = await session.execute(select(Order).where(Order.id == order_id))
            return result.scalar_one_or_none()

    async def get_recent(self, limit: int = 20) -> List[Order]:
        async with get_session() as session:
            result = await session.execute(
                select(Order)
                .order_by(desc(Order.created_at))
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_problematic(self, unresolved_only: bool = True) -> List[Order]:
        async with get_session() as session:
            q = select(Order).where(
                Order.status.in_([OrderStatus.PROBLEMATIC, OrderStatus.PARSE_ERROR])
            )
            if unresolved_only:
                q = q.where(Order.is_resolved.is_(False))
            result = await session.execute(q.order_by(desc(Order.created_at)))
            return list(result.scalars().all())

    async def get_duplicates(self) -> List[Order]:
        async with get_session() as session:
            result = await session.execute(
                select(Order)
                .where(Order.status == OrderStatus.DUPLICATE)
                .order_by(desc(Order.created_at))
                .limit(50)
            )
            return list(result.scalars().all())

    async def find_existing(
        self,
        order_number: Optional[str],
        customer_phone: Optional[str],
        window_minutes: int,
    ) -> Optional[Order]:
        """Find a recent order with same number or phone (duplicate detection)."""
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
        async with get_session() as session:
            if order_number:
                result = await session.execute(
                    select(Order)
                    .where(Order.order_number == order_number)
                    .where(Order.created_at >= cutoff)
                    .where(Order.status != OrderStatus.DUPLICATE)
                    .order_by(desc(Order.created_at))
                    .limit(1)
                )
                existing = result.scalar_one_or_none()
                if existing:
                    return existing
            return None

    async def get_today_stats(self) -> dict:
        from datetime import date
        today_start = datetime.combine(date.today(), datetime.min.time())
        async with get_session() as session:
            total = (await session.execute(
                select(func.count(Order.id)).where(Order.created_at >= today_start)
            )).scalar() or 0
            routed = (await session.execute(
                select(func.count(Order.id))
                .where(Order.created_at >= today_start)
                .where(Order.status.in_(["routed", "manually_routed"]))
            )).scalar() or 0
            problematic = (await session.execute(
                select(func.count(Order.id))
                .where(Order.created_at >= today_start)
                .where(Order.status.in_(["problematic", "parse_error"]))
            )).scalar() or 0
            duplicates = (await session.execute(
                select(func.count(Order.id))
                .where(Order.created_at >= today_start)
                .where(Order.status == "duplicate")
            )).scalar() or 0

        return {
            "total": total,
            "routed": routed,
            "problematic": problematic,
            "duplicates": duplicates,
        }


order_service = OrderService()
