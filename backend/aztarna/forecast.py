import logging
from datetime import UTC, datetime, timedelta

from aztarna.models import ForecastResponse, NormalizedSkyEvent, Tonight
from aztarna.sources import EventSource

log = logging.getLogger(__name__)

HORIZON = timedelta(days=5)
VALIDITY = timedelta(hours=12)


def build_forecast(
    lat: float, lon: float, sources: list[EventSource], now: datetime | None = None
) -> ForecastResponse:
    now = now or datetime.now(UTC)
    events: list[NormalizedSkyEvent] = []
    for source in sources:
        try:
            events += source.events(lat, lon, now, now + HORIZON)
        except Exception:
            # A failing source drops its events, never the whole response. No coordinates in logs.
            log.exception("event source %s failed", type(source).__name__)
    events.sort(key=lambda e: e.timing.window_start)
    # TODO: weather, evaluation, tonight (dusk/dawn/highlight) once sources land.
    return ForecastResponse(
        generated_at=now, valid_until=now + VALIDITY, tonight=Tonight(), events=events
    )
