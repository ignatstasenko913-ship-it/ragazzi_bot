"""Geo service: geocoding via Nominatim (OSM) + routing via OSRM.

Both are completely free, require no API key, and have excellent
coverage of Vladivostok and the Russian Far East.

Nominatim: https://nominatim.org  (1 req/sec rate limit — enforced here)
OSRM:      https://project-osrm.org  (public demo server, no limits documented)
"""
from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import aiohttp
from loguru import logger

from config import settings

# Nominatim ToS require a descriptive User-Agent
_NOMINATIM_USER_AGENT = "RagazziDeliveryBot/1.0 (pizza delivery routing)"

# Vladivostok bounding box for Nominatim viewbox (improves accuracy)
# lon_min, lat_min, lon_max, lat_max
_VVO_VIEWBOX = "131.5,42.85,132.55,43.45"

# OSRM public demo server
_OSRM_BASE = "https://router.project-osrm.org/route/v1/driving"


@dataclass
class GeoPoint:
    lat: float
    lon: float
    address: str = ""


@dataclass
class RouteResult:
    duration_minutes: int
    distance_km: float
    provider: str


class _NominatimThrottle:
    """Ensures at most 1 request per second to Nominatim (per their ToS)."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._last: float = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            gap = 1.05 - (time.monotonic() - self._last)
            if gap > 0:
                await asyncio.sleep(gap)
            self._last = time.monotonic()


class GeoService:
    """Async geo service: geocoding (Nominatim) + routing (OSRM)."""

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        self._throttle = _NominatimThrottle()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"User-Agent": _NOMINATIM_USER_AGENT},
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Public API ────────────────────────────────────────────────────────────

    async def geocode(self, address: str) -> Optional[GeoPoint]:
        """Resolve a text address to coordinates via Nominatim."""
        return await self._geocode_nominatim(address)

    async def get_driving_time(
        self, origin: GeoPoint, destination: GeoPoint
    ) -> Optional[RouteResult]:
        """Return driving time between two points via OSRM."""
        return await self._route_osrm(origin, destination)

    def is_in_delivery_zone(self, point: GeoPoint) -> bool:
        dist = self._haversine(
            settings.DELIVERY_CENTER_LAT,
            settings.DELIVERY_CENTER_LON,
            point.lat,
            point.lon,
        )
        return dist <= settings.DELIVERY_MAX_RADIUS_KM

    # ── Nominatim geocoding ───────────────────────────────────────────────────

    async def _geocode_nominatim(self, address: str) -> Optional[GeoPoint]:
        """
        Geocode an address using Nominatim (OpenStreetMap).
        Prepends 'Владивосток' and restricts search to the VVO bounding box
        for best accuracy.
        """
        query = self._build_query(address)
        params = {
            "q": query,
            "format": "jsonv2",
            "limit": 1,
            "countrycodes": "ru",
            "viewbox": _VVO_VIEWBOX,
            "bounded": 0,            # prefer viewbox but fall back globally
            "accept-language": "ru",
            "addressdetails": 0,
        }
        await self._throttle.acquire()
        try:
            session = await self._get_session()
            async with session.get(
                "https://nominatim.openstreetmap.org/search", params=params
            ) as resp:
                if resp.status != 200:
                    logger.warning("Nominatim returned HTTP {}", resp.status)
                    return None
                data = await resp.json(content_type=None)
                if not data:
                    logger.warning("Nominatim: no results for «{}»", query)
                    return None
                hit = data[0]
                return GeoPoint(
                    lat=float(hit["lat"]),
                    lon=float(hit["lon"]),
                    address=hit.get("display_name", address),
                )
        except Exception as exc:
            logger.error("Nominatim geocode error: {}", exc)
            return None

    @staticmethod
    def _build_query(address: str) -> str:
        """Ensure city context in the query string."""
        low = address.lower()
        if "владивосток" in low:
            return address
        return f"Владивосток, {address}"

    # ── OSRM routing ──────────────────────────────────────────────────────────

    async def _route_osrm(
        self, origin: GeoPoint, destination: GeoPoint
    ) -> Optional[RouteResult]:
        """
        Get driving route using the public OSRM demo server.
        OSRM expects coordinates as lon,lat (not lat,lon).
        Returns duration in minutes and distance in km.
        """
        # OSRM coordinate order: longitude,latitude
        coords = (
            f"{origin.lon:.6f},{origin.lat:.6f};"
            f"{destination.lon:.6f},{destination.lat:.6f}"
        )
        url = f"{_OSRM_BASE}/{coords}"
        params = {
            "overview": "false",
            "steps": "false",
            "annotations": "false",
        }
        try:
            session = await self._get_session()
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.warning("OSRM returned HTTP {}", resp.status)
                    return None
                data = await resp.json(content_type=None)
                if data.get("code") != "Ok":
                    logger.warning("OSRM code={}", data.get("code"))
                    return None
                routes = data.get("routes", [])
                if not routes:
                    return None
                route = routes[0]
                duration_sec = route.get("duration", 0)
                distance_m = route.get("distance", 0)
                return RouteResult(
                    duration_minutes=max(1, round(duration_sec / 60)),
                    distance_km=round(distance_m / 1000, 1),
                    provider="osrm",
                )
        except Exception as exc:
            logger.error("OSRM routing error: {}", exc)
            return None

    # ── Batch routing (OSRM Table API) ────────────────────────────────────────

    async def get_driving_times_batch(
        self,
        destination: GeoPoint,
        origins: list[GeoPoint],
    ) -> list[Optional[RouteResult]]:
        """
        Fetch driving times from multiple origins to one destination
        in a single OSRM Table API request. More efficient than N calls.

        Table API: /table/v1/driving/{coords}?sources=1,2,...&destinations=0
        Coordinate 0 = destination, coordinates 1..N = origins (branches).
        """
        if not origins:
            return []

        all_points = [destination] + origins
        coords_str = ";".join(
            f"{p.lon:.6f},{p.lat:.6f}" for p in all_points
        )
        sources = ",".join(str(i) for i in range(1, len(all_points)))
        url = f"https://router.project-osrm.org/table/v1/driving/{coords_str}"
        params = {
            "sources": sources,
            "destinations": "0",
            "annotations": "duration,distance",
        }
        try:
            session = await self._get_session()
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.warning("OSRM Table API returned HTTP {}", resp.status)
                    return [None] * len(origins)
                data = await resp.json(content_type=None)
                if data.get("code") != "Ok":
                    return [None] * len(origins)

                durations = data.get("durations", [])   # shape: [N][1]
                distances = data.get("distances", [])   # shape: [N][1]
                results: list[Optional[RouteResult]] = []
                for i in range(len(origins)):
                    try:
                        sec = durations[i][0]
                        m = distances[i][0] if distances else None
                        results.append(RouteResult(
                            duration_minutes=max(1, round(sec / 60)),
                            distance_km=round((m or 0) / 1000, 1),
                            provider="osrm-table",
                        ))
                    except (IndexError, TypeError):
                        results.append(None)
                return results
        except Exception as exc:
            logger.error("OSRM Table API error: {}", exc)
            return [None] * len(origins)

    # ── Utilities ─────────────────────────────────────────────────────────────

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
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


geo_service = GeoService()
