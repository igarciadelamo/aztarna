"""Major meteor showers from the static IMO-derived table, evaluated for the peak night."""

import json
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

import numpy as np
from skyfield.api import Star

from aztarna.astro import best_view, body, night_near, observer, t
from aztarna.models import Category, Geometry, SkyEvent, Timing

TABLE = Path(__file__).parent.parent / "data" / "meteor_showers.json"
SUN_DEG = -12  # meteors need real darkness
SOURCE = "SHOWER_TABLE"


@cache
def showers() -> list[dict]:
    return json.loads(TABLE.read_text())["showers"]


def peaks(start: datetime, end: datetime):
    """(shower, peak datetime) for peaks between start and end, across a year boundary.
    ponytail: fixed calendar date, ±1 day vs the real solar-longitude peak; peaks are broad."""
    for year in range(start.year, end.year + 1):
        for shower in showers():
            month, day = map(int, shower["peak"].split("-"))
            peak = datetime(year, month, day, tzinfo=UTC)
            if start.date() <= peak.date() <= end.date():
                yield shower, peak


class MeteorSource:
    def events(self, lat, lon, start, end):
        out = []
        for shower, peak in peaks(start, end):
            night = night_near(lat, lon, peak, SUN_DEG)
            if not night:
                continue
            radiant = Star(ra_hours=shower["radiant_ra"] / 15, dec_degrees=shower["radiant_dec"])
            view = best_view(lat, lon, [radiant], night)
            if view.altitude_deg <= 0:  # radiant never rises in darkness here
                continue
            moon = observer(lat, lon).at(t(view.time)).observe(body("moon")).apparent()
            moon_alt = moon.altaz()[0].degrees
            illumination = moon.fraction_illuminated(body("sun")) * 100
            out.append(
                SkyEvent(
                    id=f"{Category.METEOR_SHOWER}:{shower['code']}:{night.dusk.isoformat()}",
                    category=Category.METEOR_SHOWER,
                    target=shower["code"],
                    source=SOURCE,
                    timing=Timing(
                        window_start=night.dusk,
                        peak_time=view.time,
                        window_end=night.dawn,
                        duration_seconds=int((night.dawn - night.dusk).total_seconds()),
                    ),
                    geometry=Geometry(
                        max_elevation_deg=round(view.altitude_deg, 1),
                        start_azimuth_deg=round(view.azimuth_deg),
                        rate_per_hour=round(shower["zhr"] * np.sin(np.radians(view.altitude_deg))),
                        moon_illumination_percent=round(float(illumination)),
                        moon_elevation_deg=round(float(moon_alt), 1),
                    ),
                )
            )
        return out
