import logging
from datetime import UTC, datetime, timedelta

from aztarna import astro, weather
from aztarna.evaluation import evaluate
from aztarna.models import ForecastResponse, NormalizedSkyEvent, Tonight
from aztarna.sources import EventSource

log = logging.getLogger(__name__)

HORIZON = timedelta(days=5)
VALIDITY = timedelta(hours=12)
NOTIFY_LEAD = timedelta(minutes=30)
RECHECK_LEAD = timedelta(hours=2)
TONIGHT_SUN_DEG = -6  # civil dusk to civil dawn (PRODUCT.md §2)
# Reasons that can still change with a new forecast; every other failure is geometry and final.
WEATHER_REASONS = {"GOOD_CONDITIONS", "TOO_CLOUDY", "WEATHER_UNKNOWN"}


def build_forecast(
    lat: float,
    lon: float,
    sources: list[EventSource],
    now: datetime | None = None,
) -> ForecastResponse:
    now = now or datetime.now(UTC)
    events: list[NormalizedSkyEvent] = []
    for source in sources:
        try:
            events += source.events(lat, lon, now, now + HORIZON)
        except Exception:
            # A failing source drops its events, never the whole response. No coordinates in logs.
            log.exception("event source %s failed", type(source).__name__)
    events = [e for e in events if e.timing.window_end > now]
    events.sort(key=lambda e: e.timing.window_start)

    hourly = weather.hourly_cloud_cover(lat, lon)
    for e in events:
        e.weather = weather.for_window(hourly, e.timing.window_start, e.timing.window_end)
        e.evaluation = evaluate(e)
    events = [e for e in events if e.evaluation.reason_code in WEATHER_REASONS]
    for e in events:
        e.geometry.start_direction = astro.direction(e.geometry.start_azimuth_deg)
        e.geometry.end_direction = astro.direction(e.geometry.end_azimuth_deg)
        if e.evaluation.is_worth_looking:
            e.timing.notify_at = e.timing.window_start - NOTIFY_LEAD
            e.timing.recheck_at = e.timing.window_start - RECHECK_LEAD

    return ForecastResponse(
        generated_at=now,
        valid_until=now + VALIDITY,
        tonight=tonight(lat, lon, now, events, hourly),
        events=events,
    )


def tonight(lat, lon, now, events, hourly) -> Tonight:
    night = astro.night_near(lat, lon, now, TONIGHT_SUN_DEG)
    if not night or night.dawn < now:
        return Tonight()
    # Highlight: first worthwhile event peaking tonight. ponytail: earliest wins; rank by
    # brightness/rarity if users want "the best" rather than "the next".
    highlight = next(
        (
            e
            for e in events
            if e.evaluation.is_worth_looking and night.dusk <= e.timing.peak_time <= night.dawn
        ),
        None,
    )
    w = weather.for_window(hourly, night.dusk, night.dawn)
    return Tonight(
        dusk=night.dusk,
        dawn=night.dawn,
        highlight_event_id=highlight.id if highlight else None,
        cloud_cover_percent=w.cloud_cover_percent if w else None,
        condition_code=w.condition_code if w else None,
    )
