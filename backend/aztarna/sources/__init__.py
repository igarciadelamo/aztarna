"""Event sources: every calculation backend (Skyfield, a static table, a future library) implements
EventSource and is registered in SOURCES. The forecast pipeline only knows this interface."""

from datetime import datetime
from typing import Protocol

from aztarna.models import SkyEvent


class EventSource(Protocol):
    def events(self, lat: float, lon: float, start: datetime, end: datetime) -> list[SkyEvent]:
        """Events visible from (lat, lon) whose window overlaps [start, end). UTC datetimes."""
        ...


from aztarna.sources.meteors import MeteorSource
from aztarna.sources.satellites import SatelliteSource
from aztarna.sources.sky import SkySource

# Add new sources here; order does not matter, the pipeline sorts by time.
SOURCES: list[EventSource] = [SkySource(), SatelliteSource(), MeteorSource()]
