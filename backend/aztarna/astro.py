"""Shared Skyfield helpers: ephemeris, timescale, nights and best-view search."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cache
from pathlib import Path

import numpy as np
from skyfield import almanac
from skyfield.api import Loader, wgs84

DATA = Path(__file__).parent / "data"
load = Loader(DATA, verbose=False)
ts = load.timescale(builtin=True)

DIRECTIONS = [
    "N",
    "NNE",
    "NE",
    "ENE",
    "E",
    "ESE",
    "SE",
    "SSE",
    "S",
    "SSW",
    "SW",
    "WSW",
    "W",
    "WNW",
    "NW",
    "NNW",
]


@cache
def eph():
    """JPL DE421 (1900–2050). Downloaded once by `make setup` / the Docker build."""
    return load("de421.bsp")


def body(name: str):
    return eph()[name]


def observer(lat: float, lon: float):
    return body("earth") + wgs84.latlon(lat, lon)


def direction(azimuth_deg: float | None) -> str | None:
    if azimuth_deg is None:
        return None
    return DIRECTIONS[round(azimuth_deg / 22.5) % 16]


def t(dt: datetime):
    return ts.from_datetime(dt)


@dataclass
class Night:
    dusk: datetime
    dawn: datetime


def nights(lat: float, lon: float, start: datetime, end: datetime, sun_deg: float) -> list[Night]:
    """Dark periods (Sun below sun_deg) overlapping [start, end]. Polar day/night yields none."""
    obs, sun = observer(lat, lon), body("sun")
    t0, t1 = t(start - timedelta(days=1)), t(end + timedelta(days=1))
    # The boolean arrays are False when the Sun never actually crosses sun_deg that day (polar).
    dusks, real_dusk = almanac.find_settings(obs, sun, t0, t1, horizon_degrees=sun_deg)
    dawns, real_dawn = almanac.find_risings(obs, sun, t0, t1, horizon_degrees=sun_deg)
    dawn_list = [d.utc_datetime() for d, ok in zip(dawns, real_dawn) if ok]
    result = []
    for dusk in (d.utc_datetime() for d, ok in zip(dusks, real_dusk) if ok):
        dawn = next((d for d in dawn_list if d > dusk), None)
        if dawn and dawn > start and dusk < end:
            result.append(Night(dusk, dawn))
    return result


def night_near(lat: float, lon: float, when: datetime, sun_deg: float) -> Night | None:
    """The night containing `when`, else the one whose middle is closest to it."""
    candidates = nights(lat, lon, when - timedelta(days=1), when + timedelta(days=1), sun_deg)
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda n: (
            timedelta(0)
            if n.dusk <= when <= n.dawn
            else abs(when - (n.dusk + (n.dawn - n.dusk) / 2))
        ),
    )


@dataclass
class View:
    time: datetime
    altitude_deg: float
    azimuth_deg: float


def best_view(lat: float, lon: float, targets: list, night: Night, step_min: int = 10) -> View:
    """Time in `night` that maximizes the lowest altitude among `targets` (one target = its peak).
    ponytail: 10-min sampling, ±0.5° error on peak altitude; refine with find_maxima if it matters."""
    obs = observer(lat, lon)
    n = max(2, int((night.dawn - night.dusk) / timedelta(minutes=step_min)) + 1)
    times = ts.linspace(t(night.dusk), t(night.dawn), n)
    alts, azs = [], []
    for target in targets:
        alt, az, _ = obs.at(times).observe(target).apparent().altaz()
        alts.append(alt.degrees)
        azs.append(az.degrees)
    lowest = np.min(alts, axis=0)
    i = int(np.argmax(lowest))
    return View(times[i].utc_datetime(), float(lowest[i]), float(azs[0][i]))
