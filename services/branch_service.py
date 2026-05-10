"""CRUD and business logic for branches."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from loguru import logger
from sqlalchemy import select, update

from database import Branch
from database.session import get_session


class BranchService:

    async def get_all(self) -> List[Branch]:
        async with get_session() as session:
            result = await session.execute(select(Branch).order_by(Branch.id))
            return list(result.scalars().all())

    async def get_active(self) -> List[Branch]:
        async with get_session() as session:
            result = await session.execute(
                select(Branch).where(Branch.is_active.is_(True)).order_by(Branch.id)
            )
            return list(result.scalars().all())

    async def get_by_id(self, branch_id: int) -> Optional[Branch]:
        async with get_session() as session:
            result = await session.execute(
                select(Branch).where(Branch.id == branch_id)
            )
            return result.scalar_one_or_none()

    async def create(
        self,
        name: str,
        address: str,
        lat: float,
        lon: float,
        telegram_group_id: str,
        short_name: str = "",
    ) -> Branch:
        async with get_session() as session:
            branch = Branch(
                name=name,
                short_name=short_name or name,
                address=address,
                lat=lat,
                lon=lon,
                telegram_group_id=telegram_group_id,
                is_active=True,
            )
            session.add(branch)
            await session.flush()
            await session.refresh(branch)
            logger.info("Created branch '{}' (id={})", name, branch.id)
            return branch

    async def toggle_active(self, branch_id: int) -> Optional[Branch]:
        async with get_session() as session:
            result = await session.execute(
                select(Branch).where(Branch.id == branch_id)
            )
            branch = result.scalar_one_or_none()
            if branch is None:
                return None
            branch.is_active = not branch.is_active
            branch.updated_at = datetime.utcnow()
            await session.flush()
            await session.refresh(branch)
            logger.info(
                "Branch '{}' is now {}", branch.name, "active" if branch.is_active else "inactive"
            )
            return branch

    async def set_active(self, branch_id: int, active: bool) -> Optional[Branch]:
        async with get_session() as session:
            result = await session.execute(
                select(Branch).where(Branch.id == branch_id)
            )
            branch = result.scalar_one_or_none()
            if branch is None:
                return None
            branch.is_active = active
            branch.updated_at = datetime.utcnow()
            return branch

    async def mark_order_sent(self, branch_id: int) -> None:
        async with get_session() as session:
            await session.execute(
                update(Branch)
                .where(Branch.id == branch_id)
                .values(last_order_sent_at=datetime.utcnow())
            )

    async def get_load_stats(self) -> List[dict]:
        """Return today's order count per branch."""
        from datetime import date
        from sqlalchemy import func
        from database import Order, OrderStatus

        today_start = datetime.combine(date.today(), datetime.min.time())
        async with get_session() as session:
            branches = (await session.execute(select(Branch).order_by(Branch.id))).scalars().all()
            stats = []
            for branch in branches:
                count_result = await session.execute(
                    select(func.count(Order.id))
                    .where(Order.branch_id == branch.id)
                    .where(Order.created_at >= today_start)
                    .where(Order.status.in_(["routed", "manually_routed"]))
                )
                count = count_result.scalar() or 0
                stats.append({
                    "branch": branch,
                    "orders_today": count,
                    "last_order_sent": branch.last_order_sent_at,
                })
            return stats


branch_service = BranchService()
