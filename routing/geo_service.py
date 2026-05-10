"""Geo service: geocoding, address validation, driving time calculation.

Supports 2GIS (primary) and Yandex Maps (fallback).
"""
from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import Optional, Tuple

import aiohttp
from loguru import logger

from config import settings


@dataclass
class GeoPoint:
    lat: float
    lon: float
    address: str = ""


@dataclass
class RouteResult:
    duration_minutes: int       # with traffic
    distance_km: float
    provider: str


class GeoService:
    """Async geo service: geocoding + traffic-aware routing."""

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Public API ────────────────────────────────────────────────────────────

    async def geocode(self, address: str) -> Optional[GeoPoint]:
        """Resolve a text address to coordinates. Tries 2GIS then Yandex."""
        point = await self._geocode_2gis(address)
        if point is None and settings.YANDEX_MAPS_API_KEY:
            point = await self._geocode_yandex(address)
        return point

    async def get_driving_time(
        self, origin: GeoPoint, destination: GeoPoint
    ) -> Optional[RouteResult]:
        """Return driving time with traffic between two points."""
        result = await self._route_2gis(origin, destination)
        if result is None and settings.YANDEX_MAPS_API_KEY:
            result = await self._route_yandex(origin, destination)
        return result

    def is_in_delivery_zone(self, point: GeoPoint) -> bool:
        """Check if a coordinate is within the maximum delivery radius."""
        dist = self._haversine(
            settings.DELIVERY_CENTER_LAT,
            settings.DELIVERY_CENTER_LON,
            point.lat,
            point.lon,
        )
        return dist <= settings.DELIVERY_MAX_RADIUS_KM

    # ── 2GIS ──────────────────────────────────────────────────────────────────

    async def _geocode_2gis(self, address: str) -> Optional[GeoPoint]:
        if not settings.TWOGIS_API_KEY:
            return None
        url = "https://catalog.api.2gis.com/3.0/items/geocode"
        params = {
            "q": address,
            "fields": "items.geometry.centroid,items.full_name",
            "key": settings.TWOGIS_API_KEY,
            "locale": "ru_RU",
            "region_id": "41",  # Vladivostok region
        }
        try:
            session = await self._get_session()
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.warning("2GIS geocode returned {}", resp.status)
                    return None
                data = await resp.json()
                items = data.get("result", {}).get("items", [])
                if not items:
                    return None
                first = items[0]
                centroid = first.get("geometry", {}).get("centroid", "")
                # centroid format: "POINT(lon lat)"
                coords = self._parse_wkt_point(centroid)
                if coords is None:
                    return None
                full_name = first.get("full_name", address)
                return GeoPoint(lat=coords[1], lon=coords[0], address=full_name)
        except Exception as exc:
            logger.error("2GIS geocode error: {}", exc)
            return None

    async def _route_2gis(
        self, origin: GeoPoint, destination: GeoPoint
    ) -> Optional[RouteResult]:
        if not settings.TWOGIS_API_KEY:
            return None
        url = "https://routing.api.2gis.com/routing/7.0.0/global"
        body = {
            "points": [
                {"type": "stop", "x": origin.lon, "y": origin.lat},
                {"type": "stop", "x": destination.lon, "y": destination.lat},
            ],
            "transport": "car",
            "traffic_mode": "statistics",  # use statistical traffic data
            "output": "simplified",
            "locale": "ru",
        }
        params = {"key": settings.TWOGIS_API_KEY}
        try:
            session = await self._get_session()
            async with session.post(url, json=body, params=params) as resp:
                if resp.status != 200:
                    logger.warning("2GIS routing returned {}", resp.status)
                    return None
                data = await resp.json()
                routes = (
                    data.get("result", [{}])[0]
                    .get("routes", [{}])
                )
                if not routes:
                    return None
                route = routes[0]
                duration_sec = route.get("duration", 0)
                distance_m = route.get("length", 0)
                return RouteResult(
                    duration_minutes=max(1, round(duration_sec / 60)),
                    distance_km=round(distance_m / 1000, 1),
                    provider="2gis",
                )
        except Exception as exc:
            logger.error("2GIS routing error: {}", exc)
            return None

    # ── Yandex Maps ───────────────────────────────────────────────────────────

    async def _geocode_yandex(self, address: str) -> Optional[GeoPoint]:
        url = "https://geocode-maps.yandex.ru/1.x/"
        params = {
            "apikey": settings.YANDEX_MAPS_API_KEY,
            "geocode": f"Владивосток, {address}",
            "format": "json",
            "results": 1,
            "lang": "ru_RU",
        }
        try:
            session = await self._get_session()
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                members = (
                    data.get("response", {})
                    .get("GeoObjectCollection", {})
                    .get("featureMember", [])
                )
                if not members:
                    return None
                geo = members[0].get("GeoObject", {})
                pos = geo.get("Point", {}).get("pos", "")
                if not pos:
                    return None
                lon_str, lat_str = pos.split()
                full_address = (
                    geo.get("metaDataProperty", {})
                    .get("GeocoderMetaData", {})
                    .get("text", address)
                )
                return GeoPoint(lat=float(lat_str), lon=float(lon_str), address=full_address)
        except Exception as exc:
            logger.error("Yandex geocode error: {}", exc)
            return None

    async def _route_yandex(
        self, origin: GeoPoint, destination: GeoPoint
    ) -> Optional[RouteResult]:
        url = "https://router.api.maps.yandex.ru/v2/route"
        params = {
            "apikey": settings.YANDEX_MAPS_API_KEY,
            "waypoints": f"{origin.lat},{origin.lon}|{destination.lat},{destination.lon}",
            "mode": "driving",
            "avoid_tolls": "true",
        }
        try:
            session = await self._get_session()
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                legs = (
                    data.get("route", {})
                    .get("legs", [{}])
                )
                if not legs:
                    return None
                leg = legs[0]
                duration = leg.get("duration", {})
                duration_sec = duration.get("value", 0)
                distance = leg.get("distance", {})
                distance_m = distance.get("value", 0)
                return RouteResult(
                    duration_minutes=max(1, round(duration_sec / 60)),
                    distance_km=round(distance_m / 1000, 1),
                    provider="yandex",
                )
        except Exception as exc:
            logger.error("Yandex routing error: {}", exc)
            return None

    # ── Utilities ─────────────────────────────────────────────────────────────

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Return great-circle distance in km."""
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        return R * 2 * math.asin(math.sqrt(a))

    @staticmethod
    def _parse_wkt_point(wkt: str) -> Optional[Tuple[float, float]]:
        """Parse 'POINT(lon lat)' → (lon, lat)."""
        m = __import__("re").search(r"POINT\(\s*([\d.+-]+)\s+([\d.+-]+)\s*\)", wkt)
        if m:
            return float(m.group(1)), float(m.group(2))
        return None


geo_service = GeoService()
