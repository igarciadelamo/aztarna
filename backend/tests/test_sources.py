"""Checks against published astronomical facts (offline: DE421 ephemeris + fixture TLE)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from aztarna import tips, weather
from aztarna.astro import direction, nights
from aztarna.evaluation import brightness_code, evaluate, height_code
from aztarna.models import Category, Geometry, SkyEvent, Timing, Weather
from aztarna.sources.meteors import MeteorSource
from aztarna.sources.satellites import SatelliteSource, magnitude
from aztarna.sources.sky import SkySource

MADRID = (40.4, -3.7)
LOS_ANGELES = (34.0, -118.2)


def utc(*args):
    return datetime(*args, tzinfo=UTC)


def by_target(events):
    return {e.target: e for e in events}


def test_full_moon_nov_2026():
    events = by_target(SkySource().events(*MADRID, utc(2026, 11, 20), utc(2026, 11, 28)))
    assert events["FULL_MOON"].timing.window_start.date() == datetime(2026, 11, 24).date()


def test_total_lunar_eclipse_mar_2026():
    e = by_target(SkySource().events(*LOS_ANGELES, utc(2026, 3, 1), utc(2026, 3, 5)))[
        "TOTAL_LUNAR_ECLIPSE"
    ]
    assert abs(e.timing.peak_time - utc(2026, 3, 3, 11, 33)) < timedelta(minutes=5)
    # Partial phase lasts ~3h27m.
    assert timedelta(hours=3, minutes=10) < e.timing.window_end - e.timing.window_start
    assert e.timing.window_end - e.timing.window_start < timedelta(hours=3, minutes=45)
    assert e.geometry.max_elevation_deg > 10  # visible from LA


def test_jupiter_opposition_jan_2026():
    e = by_target(SkySource().events(*MADRID, utc(2026, 1, 5), utc(2026, 1, 15)))[
        "JUPITER_OPPOSITION"
    ]
    assert e.timing.peak_time.date() == datetime(2026, 1, 10).date()
    assert -2.9 < e.geometry.magnitude < -2.5


def test_conjunction_never_up_in_darkness_is_dropped():
    # Venus–Mars conjunction of Jan 2026 happens next to the Sun.
    events = SkySource().events(*MADRID, utc(2026, 1, 5), utc(2026, 1, 10))
    assert "VENUS_MARS_CONJUNCTION" not in by_target(events)


def test_perseids_2026_new_moon():
    e = by_target(MeteorSource().events(*MADRID, utc(2026, 8, 10), utc(2026, 8, 14)))["PERSEIDS"]
    assert e.geometry.moon_illumination_percent < 5
    assert e.geometry.rate_per_hour > 50


def test_geminids_radiant_altitude():
    e = by_target(MeteorSource().events(*MADRID, utc(2026, 12, 10), utc(2026, 12, 16)))["GEMINIDS"]
    assert abs(e.geometry.max_elevation_deg - (90 - 40.4 + 33)) < 1


def test_quadrantids_across_year_boundary():
    events = MeteorSource().events(*MADRID, utc(2026, 12, 30), utc(2027, 1, 4))
    assert "QUADRANTIDS" in by_target(events)


def test_no_nights_in_polar_summer():
    assert nights(78, 15, utc(2026, 6, 15), utc(2026, 6, 17), -6) == []


def test_satellite_passes_are_visible_and_consistent():
    tle = (Path(__file__).parent / "stations.tle").read_text()
    events = SatelliteSource(read=lambda: tle).events(
        *MADRID, utc(2026, 11, 22, 12), utc(2026, 11, 25)
    )
    assert {e.target for e in events} == {"ISS", "TIANGONG"}
    for e in events:
        assert e.timing.window_start <= e.timing.peak_time <= e.timing.window_end
        assert e.geometry.max_elevation_deg >= 10
        assert -5 < e.geometry.magnitude < 4


# Heavens-Above, 40.4N 3.7W, same TLE epoch (2026-11-22): (target, start UTC, max alt, magnitude)
HEAVENS_ABOVE = [
    ("ISS", utc(2026, 11, 23, 17, 38, 27), 12, -1.4),
    ("ISS", utc(2026, 11, 28, 18, 27, 51), 78, -4.0),
    ("ISS", utc(2026, 11, 29, 17, 39, 49), 46, -3.4),
    ("ISS", utc(2026, 11, 29, 19, 17, 6), 19, -1.1),
    ("TIANGONG", utc(2026, 11, 24, 5, 47, 2), 81, -2.2),
    ("TIANGONG", utc(2026, 11, 25, 4, 50, 26), 21, 0.5),
    ("TIANGONG", utc(2026, 11, 30, 4, 43, 11), 15, 1.1),
    ("TIANGONG", utc(2026, 12, 1, 5, 18, 34), 37, -0.8),
]


def test_satellite_passes_match_heavens_above():
    tle = (Path(__file__).parent / "stations.tle").read_text()
    events = SatelliteSource(read=lambda: tle).events(*MADRID, utc(2026, 11, 22), utc(2026, 12, 2))
    for target, start, alt, mag in HEAVENS_ABOVE:
        e = min(
            (e for e in events if e.target == target),
            key=lambda e: abs(e.timing.window_start - start),
        )
        assert abs(e.timing.window_start - start) < timedelta(seconds=30), (target, start)
        assert abs(e.geometry.max_elevation_deg - alt) < 3, (target, start)
        assert abs(e.geometry.magnitude - mag) < 0.7, (target, start, e.geometry.magnitude)


def test_tle_newer_than_window_start_is_used():
    # Review: abs() used to drop events when the TLE epoch was more than 7 days *after* `start`.
    tle = (Path(__file__).parent / "stations.tle").read_text()
    assert SatelliteSource(read=lambda: tle).events(*MADRID, utc(2026, 11, 12), utc(2026, 11, 14))


def test_stale_tle_emits_nothing():
    tle = (Path(__file__).parent / "stations.tle").read_text()
    assert SatelliteSource(read=lambda: tle).events(*MADRID, utc(2027, 1, 1), utc(2027, 1, 2)) == []


def test_magnitude_brighter_when_closer_and_fuller():
    assert magnitude(-1.8, 420, 1.0) < magnitude(-1.8, 1500, 1.0)
    assert magnitude(-1.8, 1000, 0.5) < magnitude(-1.8, 1000, 2.5)
    assert magnitude(-1.8, 1000, 3.14159) < 20  # no -inf/NaN at full back-lighting


@pytest.mark.parametrize(("az", "code"), [(0, "N"), (11, "N"), (12, "NNE"), (270, "W"), (359, "N")])
def test_direction(az, code):
    assert direction(az) == code


def test_weather_window_and_unknown():
    hourly = {utc(2026, 11, 22, h): c for h, c in [(18, 0), (19, 40), (20, 100)]}
    w = weather.for_window(hourly, utc(2026, 11, 22, 18, 30), utc(2026, 11, 22, 19, 10))
    assert w == Weather(cloud_cover_percent=20, condition_code="CLEAR")
    assert weather.for_window(hourly, utc(2026, 11, 23), utc(2026, 11, 23, 1)) is None


def test_weather_serves_stale_cache_on_failure(monkeypatch):
    monkeypatch.setattr(weather, "fetch", lambda *_: {utc(2026, 1, 1): 10})
    assert weather.hourly_cloud_cover(1.0, 2.0) == {utc(2026, 1, 1): 10}
    monkeypatch.setattr(weather, "TTL_S", 0)
    monkeypatch.setattr(weather, "fetch", lambda *_: 1 / 0)
    assert weather.hourly_cloud_cover(1.0, 2.0) == {utc(2026, 1, 1): 10}
    assert weather.hourly_cloud_cover(3.0, 4.0) == {}


def event(category, cloud=10, **geometry):
    start = utc(2026, 11, 22, 20)
    return SkyEvent(
        id="x",
        category=category,
        target="X",
        source="TEST",
        timing=Timing(window_start=start, peak_time=start, window_end=start, duration_seconds=0),
        geometry=Geometry(**geometry),
        weather=None if cloud is None else Weather(cloud_cover_percent=cloud, condition_code="X"),
    )


@pytest.mark.parametrize(
    ("e", "reason"),
    [
        (event(Category.SATELLITE, magnitude=-3, max_elevation_deg=60), "GOOD_CONDITIONS"),
        (event(Category.SATELLITE, magnitude=-3, max_elevation_deg=20), "TOO_LOW"),
        (event(Category.SATELLITE, magnitude=1, max_elevation_deg=60), "TOO_FAINT"),
        (event(Category.SATELLITE, cloud=80, magnitude=-3, max_elevation_deg=60), "TOO_CLOUDY"),
        (
            event(Category.SATELLITE, cloud=None, magnitude=-3, max_elevation_deg=60),
            "WEATHER_UNKNOWN",
        ),
        (event(Category.PLANET, max_elevation_deg=10), "TOO_LOW"),
        (event(Category.METEOR_SHOWER, rate_per_hour=10), "TOO_FAINT"),
        (
            event(
                Category.METEOR_SHOWER,
                rate_per_hour=80,
                moon_illumination_percent=90,
                moon_elevation_deg=30,
            ),
            "MOON_GLARE",
        ),
        (
            event(
                Category.METEOR_SHOWER,
                rate_per_hour=80,
                moon_illumination_percent=90,
                moon_elevation_deg=-5,
            ),
            "GOOD_CONDITIONS",
        ),
        (event(Category.MOON, max_elevation_deg=5), "TOO_LOW"),
    ],
)
def test_evaluation(e, reason):
    assert evaluate(e).reason_code == reason


def test_weather_budget_caps_upstream_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(weather, "MAX_FETCHES_PER_HOUR", 2)
    monkeypatch.setattr(
        weather, "fetch", lambda lat, lon: calls.append(lat) or {utc(2026, 1, 1): 5}
    )
    for lat in (1.0, 2.0, 3.0, 4.0):
        weather.hourly_cloud_cover(lat, 0.0)
    assert calls == [1.0, 2.0]
    assert weather.hourly_cloud_cover(1.0, 0.0) == {utc(2026, 1, 1): 5}  # cache still served
    assert weather.hourly_cloud_cover(5.0, 0.0) == {}  # over budget: unknown, never "clear"
    assert weather.budget_left() == 0


def test_tips_cover_every_category_and_have_text():
    used = {
        c
        for codes in [*tips.BY_CATEGORY.values(), *tips.BY_TARGET.values(), tips.CONJUNCTION]
        for c in codes
    }
    assert used <= tips.TEXT.keys()  # every code has English source copy
    assert set(tips.BY_CATEGORY) == set(Category)


def test_tips_specific_first_no_duplicates():
    jupiter = tips.for_event(
        event(Category.PLANET, max_elevation_deg=50).model_copy(
            update={"target": "JUPITER_OPPOSITION"}
        )
    )
    assert jupiter[:2] == ["OPPOSITION_BRIGHTEST", "JUPITER_MOONS"]
    pair = tips.for_event(
        event(Category.PLANET).model_copy(update={"target": "MOON_VENUS_CONJUNCTION"})
    )
    assert pair[0] == "CONJUNCTION_PAIR"
    assert len(pair) == len(set(pair))


# Heavens-Above start altitudes: Tiangong often appears high up, emerging from Earth's shadow.
HEAVENS_ABOVE_START_ALT = [
    ("TIANGONG", utc(2026, 11, 23, 5, 11, 18), 45, "ESE"),
    ("TIANGONG", utc(2026, 11, 24, 5, 47, 2), 41, "W"),
    ("TIANGONG", utc(2026, 11, 30, 4, 43, 11), 15, "E"),
    ("ISS", utc(2026, 11, 28, 18, 27, 51), 10, "NW"),
]


def test_satellite_path_start_matches_heavens_above():
    tle = (Path(__file__).parent / "stations.tle").read_text()
    events = SatelliteSource(read=lambda: tle).events(*MADRID, utc(2026, 11, 22), utc(2026, 12, 2))
    for target, start, alt, compass in HEAVENS_ABOVE_START_ALT:
        e = min(
            (e for e in events if e.target == target),
            key=lambda e: abs(e.timing.window_start - start),
        )
        g = e.geometry
        assert abs(g.start_elevation_deg - alt) < 3, (target, start, g.start_elevation_deg)
        assert direction(g.start_azimuth_deg) == compass, (target, start, g.start_azimuth_deg)
        assert g.start_elevation_deg <= g.max_elevation_deg >= g.end_elevation_deg
        assert g.peak_azimuth_deg is not None


def test_sky_and_meteor_events_have_peak_position_not_a_path():
    events = [
        *SkySource().events(*MADRID, utc(2026, 11, 20), utc(2026, 11, 28)),
        *MeteorSource().events(*MADRID, utc(2026, 12, 10), utc(2026, 12, 16)),
    ]
    assert events
    for e in events:
        assert e.geometry.peak_azimuth_deg is not None
        assert e.geometry.start_azimuth_deg is None and e.geometry.end_azimuth_deg is None


@pytest.mark.parametrize(
    ("e", "brightness", "height"),
    [
        (event(Category.SATELLITE, magnitude=-3.5, max_elevation_deg=75), "VERY_BRIGHT", "HIGH"),
        (event(Category.SATELLITE, magnitude=-1, max_elevation_deg=45), "BRIGHT", "MID"),
        (event(Category.SATELLITE, magnitude=0.5, max_elevation_deg=20), "VISIBLE", "LOW"),
        (event(Category.MOON, max_elevation_deg=60), "VERY_BRIGHT", "HIGH"),
        (event(Category.METEOR_SHOWER, max_elevation_deg=59.9), None, "MID"),
    ],
)
def test_display_labels(e, brightness, height):
    assert (brightness_code(e), height_code(e)) == (brightness, height)
