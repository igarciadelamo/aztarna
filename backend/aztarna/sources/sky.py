"""Moon, planets and lunar eclipses, computed locally with Skyfield."""

from datetime import datetime, timedelta
from itertools import combinations

import numpy as np
from skyfield import almanac, eclipselib
from skyfield.magnitudelib import planetary_magnitude

from aztarna.astro import Night, View, best_view, body, eph, night_near, observer, t, ts
from aztarna.models import Category, Geometry, SkyEvent, Timing

SOURCE = "SKYFIELD"
SUPERMOON_KM = 360_000
CONJUNCTION_DEG = 2.0
PLANET_SUN_DEG = -12  # PRODUCT.md §2: planets need real darkness
MOON_SUN_DEG = -6
OPPOSITION_PLANETS = {
    "MARS": "mars",
    "JUPITER": "jupiter barycenter",
    "SATURN": "saturn barycenter",
}
BRIGHT_PLANETS = {
    "MERCURY": "mercury",
    "VENUS": "venus",
    **OPPOSITION_PLANETS,
}


def _event(category, target, night: Night, view, **geometry) -> SkyEvent:
    return SkyEvent(
        id=f"{category}:{target}:{night.dusk.isoformat()}",
        category=category,
        target=target,
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
            **geometry,
        ),
    )


def _magnitude(name: str, when: datetime) -> float:
    return round(float(planetary_magnitude(body("earth").at(t(when)).observe(body(name)))), 1)


class SkySource:
    def events(self, lat, lon, start, end):
        return [
            *self._full_moons(lat, lon, start, end),
            *self._oppositions(lat, lon, start, end),
            *self._conjunctions(lat, lon, start, end),
            *self._lunar_eclipses(lat, lon, start, end),
        ]

    def _full_moons(self, lat, lon, start, end):
        times, phases = almanac.find_discrete(t(start), t(end), almanac.moon_phases(eph()))
        out = []
        for when in (tt.utc_datetime() for tt, p in zip(times, phases) if p == 2):
            night = night_near(lat, lon, when, MOON_SUN_DEG)
            if not night:
                continue
            km = (body("moon") - body("earth")).at(t(when)).distance().km
            target = "SUPERMOON" if km < SUPERMOON_KM else "FULL_MOON"
            view = best_view(lat, lon, [body("moon")], night)
            out.append(_event(Category.MOON, target, night, view, moon_illumination_percent=100))
        return out

    def _oppositions(self, lat, lon, start, end):
        out = []
        for target, name in OPPOSITION_PLANETS.items():
            f = almanac.oppositions_conjunctions(eph(), body(name))
            times, kinds = almanac.find_discrete(t(start), t(end), f)
            for when in (tt.utc_datetime() for tt, k in zip(times, kinds) if k == 1):
                night = night_near(lat, lon, when, PLANET_SUN_DEG)
                if night:
                    view = best_view(lat, lon, [body(name)], night)
                    if view.altitude_deg <= 0:
                        continue
                    mag = _magnitude(name, view.time)
                    out.append(
                        _event(Category.PLANET, f"{target}_OPPOSITION", night, view, magnitude=mag)
                    )
        return out

    def _conjunctions(self, lat, lon, start, end):
        """Local minima of topocentric separation below CONJUNCTION_DEG, sampled hourly."""
        obs = observer(lat, lon)
        hours = int((end - start) / timedelta(hours=1)) + 1
        times = ts.linspace(t(start), t(end), hours)
        bodies = {"MOON": "moon", **BRIGHT_PLANETS}
        positions = {k: obs.at(times).observe(body(v)).apparent() for k, v in bodies.items()}
        out = []
        for a, b in combinations(bodies, 2):
            sep = positions[a].separation_from(positions[b]).degrees
            for i in range(1, len(sep) - 1):
                if sep[i] < CONJUNCTION_DEG and sep[i] <= sep[i - 1] and sep[i] < sep[i + 1]:
                    when = times[i].utc_datetime()
                    night = night_near(lat, lon, when, PLANET_SUN_DEG)
                    if not night:
                        continue
                    view = best_view(lat, lon, [body(bodies[a]), body(bodies[b])], night)
                    if view.altitude_deg <= 0:  # never up in darkness: not an observable event
                        continue
                    out.append(_event(Category.PLANET, f"{a}_{b}_CONJUNCTION", night, view))
        return out

    def _lunar_eclipses(self, lat, lon, start, end):
        times, kinds, details = eclipselib.lunar_eclipses(t(start), t(end), eph())
        out = []
        for i, (peak, kind) in enumerate(zip(times, kinds)):
            if kind == 0:  # penumbral: barely visible, not worth an alert
                continue
            # Partial-phase half-length from shadow geometry. ponytail: constant Moon speed through
            # the shadow (~0.51°/h), a few minutes off; compute contact times if precision matters.
            reach = details["umbra_radius_radians"][i] + details["moon_radius_radians"][i]
            closest = details["closest_approach_radians"][i]
            half = timedelta(hours=float(np.sqrt(reach**2 - closest**2) / np.radians(0.51)))
            peak_dt = peak.utc_datetime()
            window = Night(peak_dt - half, peak_dt + half)
            alt, az, _ = observer(lat, lon).at(peak).observe(body("moon")).apparent().altaz()
            target = "TOTAL_LUNAR_ECLIPSE" if kind == 2 else "PARTIAL_LUNAR_ECLIPSE"
            view = View(peak_dt, float(alt.degrees), float(az.degrees))
            out.append(
                _event(Category.ECLIPSE, target, window, view, moon_illumination_percent=100)
            )
        return out
