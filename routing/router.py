"""Order routing: find the nearest active branch for a delivery order."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from loguru import logger
from sqlalchemy import select

from config import settings
from database import Branch, Order
from database.session import get_session
from routing.geo_service import GeoPoint, RouteResult, geo_service


@dataclass
class BranchCandidate:
    branch: Branch
    route: Optional[RouteResult]
    straight_km: float

    @property
    def sort_key(self) -> Tuple[int, datetime]:
        minutes = self.route.duration_minutes if self.route else 9999
        last_sent = self.branch.last_order_sent_at or datetime.min
        return (minutes, last_sent)


class OrderRouter:
    """Routes delivery orders to the nearest active branch."""

    async def route(
        self, delivery_address: str
    ) -> Tuple[Optional[Branch], Optional[GeoPoint], Optional[str]]:
        """
        Resolve address → geocode → find nearest branch.
        Returns (branch, geo_point, error_message).
        error_message is set only on failure.
        """
        # 1. Geocode the delivery address
        point = await geo_service.geocode(delivery_address)
        if point is None:
            return None, None, f"Адрес не найден: «{delivery_address}»"

        # 2. Check delivery zone
        if not geo_service.is_in_delivery_zone(point):
            return (
                None,
                point,
                f"Адрес вне зоны доставки: «{point.address}» "
                f"(> {settings.DELIVERY_MAX_RADIUS_KM:.0f} км от центра)",
            )

        # 3. Load active branches
        async with get_session() as session:
            result = await session.execute(
                select(Branch).where(Branch.is_active.is_(True))
            )
            branches: List[Branch] = list(result.scalars().all())

        if not branches:
            return None, point, "Нет активных филиалов"

        # 4. Get driving times to all active branches via OSRM Table API (one request)
        candidates = await self._build_candidates_batch(point, branches)

        if not candidates:
            return None, point, "Не удалось рассчитать маршруты до филиалов"

        # 5. Sort by (duration_minutes, last_order_sent_at)
        candidates.sort(key=lambda c: c.sort_key)
        best = candidates[0]

        logger.info(
            "Routed to branch '{}' — {} min drive ({})",
            best.branch.name,
            best.sort_key[0],
            best.route.provider if best.route else "estimate",
        )
        return best.branch, point, None

    async def _build_candidates_batch(
        self, point: GeoPoint, branches: List[Branch]
    ) -> List[BranchCandidate]:
        """
        Use OSRM Table API to calculate all branch→destination times
        in a single HTTP request instead of N sequential requests.
        Falls back to Haversine estimate if the batch call fails.
        """
        origins = [GeoPoint(lat=b.lat, lon=b.lon) for b in branches]
        routes = await geo_service.get_driving_times_batch(
            destination=point, origins=origins
        )

        candidates: List[BranchCandidate] = []
        for branch, route in zip(branches, routes):
            straight_km = geo_service._haversine(
                point.lat, point.lon, branch.lat, branch.lon
            )
            if route is None:
                # Haversine fallback: 30 km/h city average
                from routing.geo_service import RouteResult
                route = RouteResult(
                    duration_minutes=max(1, int(straight_km / 30 * 60)),
                    distance_km=round(straight_km, 1),
                    provider="estimate",
                )
            candidates.append(
                BranchCandidate(branch=branch, route=route, straight_km=straight_km)
            )
        return candidates

    async def find_pickup_branch(self, branch_name: str) -> Optional[Branch]:
        """Find an active branch whose name matches the pickup location string."""
        async with get_session() as session:
            result = await session.execute(
                select(Branch).where(Branch.is_active.is_(True))
            )
            branches = list(result.scalars().all())

        name_lower = branch_name.lower()
        for branch in branches:
            if (
                branch.name.lower() in name_lower
                or (branch.short_name and branch.short_name.lower() in name_lower)
                or name_lower in branch.name.lower()
            ):
                return branch

        # Fuzzy: any token overlap
        tokens = set(name_lower.split())
        best_score = 0
        best_branch = None
        for branch in branches:
            b_tokens = set(branch.name.lower().split())
            score = len(tokens & b_tokens)
            if score > best_score:
                best_score = score
                best_branch = branch

        return best_branch if best_score > 0 else None


order_router = OrderRouter()
