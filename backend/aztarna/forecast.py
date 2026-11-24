import logging
from datetime import UTC, datetime, timedelta

from aztarna import astro, tips, weather
from aztarna.evaluation import brightness_code, evaluate, height_code
from aztarna.models import ForecastResponse, NormalizedSkyEvent, SkyEvent, Tonight
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
    events: list[SkyEvent] = []
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
        e.tips = tips.for_event(e)
        e.geometry.start_direction = astro.direction(e.geometry.start_azimuth_deg)
        e.geometry.end_direction = astro.direction(e.geometry.end_azimuth_deg)
        e.geometry.peak_direction = astro.direction(e.geometry.peak_azimuth_deg)
        e.geometry.brightness_code = brightness_code(e)
        e.geometry.height_code = height_code(e)
        if e.evaluation.is_worth_looking:
            e.timing.notify_at = e.timing.window_start - NOTIFY_LEAD
            e.timing.recheck_at = e.timing.window_start - RECHECK_LEAD

    night = current_or_next_night(lat, lon, now)
    valid_until = now + VALIDITY
    if night and night.dusk <= now:
        # Inside a night, `tonight` describes a night that ends at dawn: expire with it so the app
        # re-syncs and gets the next night instead of showing an ended one all day.
        valid_until = min(valid_until, night.dawn)
    return ForecastResponse(
        generated_at=now,
        valid_until=valid_until,
        tonight=tonight(night, now, events, hourly),
        events=[NormalizedSkyEvent.model_validate(e.model_dump()) for e in events],
    )


def current_or_next_night(lat: float, lon: float, now: datetime) -> astro.Night | None:
    """The night we're in (until its dawn), else the next one. Keeping the current night until dawn
    matters: many Tiangong/ISS passes happen in the last hour before dawn."""
    upcoming = astro.nights(lat, lon, now, now + timedelta(days=2), TONIGHT_SUN_DEG)
    return next((n for n in upcoming if n.dawn > now), None)


def next_worthwhile(now, events) -> str | None:
    """First worthwhile event not over yet, any night: the rest state's "next clear chance"."""
    e = next(
        (e for e in events if e.evaluation.is_worth_looking and e.timing.window_end > now), None
    )
    return e.id if e else None


def tonight(night: astro.Night | None, now, events, hourly) -> Tonight:
    if not night:
        return Tonight(next_worthwhile_event_id=next_worthwhile(now, events))  # polar: no dusk/dawn
    # Highlight: first worthwhile event peaking tonight. ponytail: earliest wins; rank by
    # brightness/rarity if users want "the best" rather than "the next".
    highlight = next(
        (
            e
            for e in events
            if e.evaluation.is_worth_looking
            and e.timing.window_end > now  # never point at an event that's already over
            and night.dusk <= e.timing.peak_time <= night.dawn
        ),
        None,
    )
    w = weather.for_window(hourly, night.dusk, night.dawn)
    return Tonight(
        dusk=night.dusk,
        dawn=night.dawn,
        highlight_event_id=highlight.id if highlight else None,
        next_worthwhile_event_id=next_worthwhile(now, events),
        cloud_cover_percent=w.cloud_cover_percent if w else None,
        condition_code=w.condition_code if w else None,
    )
