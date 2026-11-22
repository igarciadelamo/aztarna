"""Open-Meteo hourly cloud cover, cached per rounded coordinate. Weather data by Open-Meteo.com
(CC BY 4.0): the app must show this attribution."""

import json
import logging
import threading
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from aztarna.models import Weather

log = logging.getLogger(__name__)

URL = "https://api.open-meteo.com/v1/forecast"
TTL_S = 3600
# ponytail: per-process dict, one worker/instance only; Redis if we scale out. Keys are rounded
# coordinates (~11 km), never stored anywhere else.
_cache: dict[tuple[float, float], tuple[float, dict[datetime, int]]] = {}

# Global cap on upstream calls, so one client cycling through coordinates can't exhaust the free
# tier (5,000/h, 10,000/day) for everyone. 300/h = 7,200/day worst case. No per-IP state needed.
MAX_FETCHES_PER_HOUR = 300
_budget_lock = threading.Lock()
_budget = {"hour_start": 0.0, "used": 0}


def _take_budget() -> bool:
    with _budget_lock:
        now = time.time()
        if now - _budget["hour_start"] >= 3600:
            _budget.update(hour_start=now, used=0)
        if _budget["used"] >= MAX_FETCHES_PER_HOUR:
            return False
        _budget["used"] += 1
        return True


def budget_left() -> int:
    with _budget_lock:
        if time.time() - _budget["hour_start"] >= 3600:
            return MAX_FETCHES_PER_HOUR
        return MAX_FETCHES_PER_HOUR - _budget["used"]


def fetch(lat: float, lon: float) -> dict[datetime, int]:
    query = urllib.parse.urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "hourly": "cloud_cover",
            "forecast_days": 7,
            "timezone": "UTC",
        }
    )
    with urllib.request.urlopen(f"{URL}?{query}", timeout=10) as response:
        hourly = json.load(response)["hourly"]
    return {
        datetime.fromisoformat(ts).replace(tzinfo=UTC): cover
        for ts, cover in zip(hourly["time"], hourly["cloud_cover"])
        if cover is not None
    }


def hourly_cloud_cover(lat: float, lon: float) -> dict[datetime, int]:
    """Fresh cache → it; else fetch; on failure or spent budget → stale cache, else {} (unknown,
    never 'clear')."""
    key = (lat, lon)
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < TTL_S:
        return cached[1]
    if not _take_budget():
        log.warning("Open-Meteo hourly budget spent; serving cached/unknown weather")
        return cached[1] if cached else {}
    try:
        data = fetch(lat, lon)
        _cache[key] = (time.time(), data)
        return data
    except Exception:
        log.exception("Open-Meteo fetch failed")
        return cached[1] if cached else {}


def condition(cloud_cover: int) -> str:
    if cloud_cover <= 25:
        return "CLEAR"
    if cloud_cover <= 70:
        return "PARTLY_CLOUDY"
    return "OVERCAST"


def for_window(hourly: dict[datetime, int], start: datetime, end: datetime) -> Weather | None:
    """Mean cloud cover over the hours touching [start, end]; None if no data."""
    first = start.replace(minute=0, second=0, microsecond=0)
    values = [v for h, v in hourly.items() if first <= h <= end]
    if not values:
        return None
    mean = round(sum(values) / len(values))
    return Weather(cloud_cover_percent=mean, condition_code=condition(mean))
