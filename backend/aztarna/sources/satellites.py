"""ISS and Tiangong passes: CelesTrak TLEs propagated with Skyfield (SGP4)."""

import io
import logging
import os
import threading
import time
import urllib.request
from datetime import timedelta
from pathlib import Path

import numpy as np
from skyfield.api import wgs84
from skyfield.iokit import parse_tle_file

from aztarna.astro import body, eph, observer, t, ts
from aztarna.models import Category, Geometry, SkyEvent, Timing

log = logging.getLogger(__name__)

TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=TLE"
# NORAD id -> (target, standard magnitude at 1000 km and 90° phase angle). Fitted to Heavens-Above
# (27 passes over Madrid, 2026-11-22); refit if a station's configuration changes a lot.
TRACKED = {25544: ("ISS", -1.9), 48274: ("TIANGONG", -0.2)}
REFRESH_S = 24 * 3600  # CelesTrak asks for at most a few downloads a day
RETRY_S = 3600  # after a failed fetch, don't retry on every request
MAX_TLE_AGE = timedelta(days=7)  # older than this, pass times are unreliable: emit nothing
MIN_ALT_DEG = 10
SUN_DEG = -6
STEP_S = 10
SOURCE = "CELESTRAK_SGP4"


def tle_path() -> Path:
    return Path(os.environ.get("DATA_DIR", "data")) / "stations.tle"


_lock = threading.Lock()
_last_attempt = 0.0


def refresh_tle(path: Path) -> None:
    """Download when the file is missing or older than REFRESH_S. On failure keep the old file."""
    global _last_attempt
    with _lock:
        fresh = path.exists() and time.time() - path.stat().st_mtime < REFRESH_S
        if fresh or time.time() - _last_attempt < RETRY_S:
            return
        _last_attempt = time.time()
        try:
            with urllib.request.urlopen(TLE_URL, timeout=10) as response:
                text = response.read().decode()
            if "25544" not in text:
                raise ValueError("ISS missing from CelesTrak response")
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(text)
            tmp.replace(path)  # atomic: readers never see a half-written file
        except Exception:
            log.exception("CelesTrak fetch failed; keeping previous TLE file")


def tle_age_hours() -> float | None:
    """Hours since the last successful CelesTrak download; None if we never got one."""
    path = tle_path()
    return round((time.time() - path.stat().st_mtime) / 3600, 1) if path.exists() else None


def read_tle() -> str:
    path = tle_path()
    refresh_tle(path)
    return path.read_text() if path.exists() else ""


def magnitude(std_mag: float, range_km: float, phase_rad: float) -> float:
    """QuickSat/McCants model: scale by range and illuminated fraction (1 + cos φ) / 2, normalized
    to 0.5 at 90°. Matches Heavens-Above within ~0.3 mag (max 0.6); no flare modeling."""
    fraction = max((1 + np.cos(phase_rad)) / 2, 1e-6)
    return round(float(std_mag + 5 * np.log10(range_km / 1000) - 2.5 * np.log10(2 * fraction)), 1)


class SatelliteSource:
    def __init__(self, read=read_tle):
        self._read = read

    def events(self, lat, lon, start, end):
        sats = list(parse_tle_file(io.BytesIO(self._read().encode()), ts))
        out = []
        for sat in sats:
            if sat.model.satnum not in TRACKED:
                continue
            if start - sat.epoch.utc_datetime() > MAX_TLE_AGE:
                log.warning("stale TLE for %s, skipping its passes", sat.model.satnum)
                continue
            out += self._passes(sat, lat, lon, start, end)
        return out

    def _passes(self, sat, lat, lon, start, end):
        target, std_mag = TRACKED[sat.model.satnum]
        topos = wgs84.latlon(lat, lon)
        times, kinds = sat.find_events(topos, t(start), t(end), altitude_degrees=MIN_ALT_DEG)
        out, rise = [], None
        for tt, kind in zip(times, kinds):
            if kind == 0:
                rise = tt
            elif kind == 2 and rise is not None:  # a pass already in progress at `start` is skipped
                event = self._visible_part(sat, topos, lat, lon, rise, tt, target, std_mag)
                if event:
                    out.append(event)
                rise = None
        return out

    def _visible_part(self, sat, topos, lat, lon, rise, set_, target, std_mag):
        n = max(2, int((set_ - rise) * 86400 / STEP_S) + 1)
        times = ts.linspace(rise, set_, n)
        alt, az, dist = (sat - topos).at(times).altaz()
        sun_alt = observer(lat, lon).at(times).observe(body("sun")).apparent().altaz()[0].degrees
        visible = np.flatnonzero(sat.at(times).is_sunlit(eph()) & (sun_alt <= SUN_DEG))
        if visible.size == 0:
            return None
        first, last = visible[0], visible[-1]
        peak = visible[np.argmax(alt.degrees[visible])]

        tp = times[peak]
        sat_pos = sat.at(tp).position.km
        to_sun = (body("sun") - body("earth")).at(tp).position.km - sat_pos
        to_obs = topos.at(tp).position.km - sat_pos
        cos_phase = np.dot(to_sun, to_obs) / (np.linalg.norm(to_sun) * np.linalg.norm(to_obs))
        phase = float(np.arccos(np.clip(cos_phase, -1, 1)))

        window_start, window_end = times[first].utc_datetime(), times[last].utc_datetime()
        return SkyEvent(
            id=f"{Category.SATELLITE}:{target}:{window_start.isoformat()}",
            category=Category.SATELLITE,
            target=target,
            source=SOURCE,
            timing=Timing(
                window_start=window_start,
                peak_time=tp.utc_datetime(),
                window_end=window_end,
                duration_seconds=int((window_end - window_start).total_seconds()),
            ),
            geometry=Geometry(
                magnitude=magnitude(std_mag, float(dist.km[peak]), phase),
                max_elevation_deg=round(float(alt.degrees[peak]), 1),
                start_azimuth_deg=round(float(az.degrees[first])),
                end_azimuth_deg=round(float(az.degrees[last])),
            ),
        )
