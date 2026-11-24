from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from aztarna.forecast import build_forecast
from aztarna.main import app
from aztarna.models import Category, Geometry, SkyEvent, Timing
from aztarna.sources import satellites

client = TestClient(app)
NOW = datetime(2026, 11, 15, 18, tzinfo=UTC)


def test_health_degraded_without_tle():
    body = client.get("/health").json()
    assert body == {"status": "degraded", "tle_age_hours": None, "weather_budget_left": 300}


def test_health_ok_with_fresh_tle():
    satellites.tle_path().parent.mkdir(parents=True)
    satellites.tle_path().write_text("x")
    assert client.get("/health").json()["status"] == "ok"


@pytest.mark.parametrize(
    ("version_code", "action"),
    [(3, "FORCE_UPDATE"), (5, "SUGGEST_UPDATE"), (7, "NONE"), (9, "NONE")],
)
def test_app_version(monkeypatch, version_code, action):
    monkeypatch.setenv("MIN_VERSION_CODE", "4")
    monkeypatch.setenv("LATEST_VERSION_CODE", "7")
    body = client.get("/v1/app-version", params={"version_code": version_code}).json()
    assert body == {"min_version_code": 4, "latest_version_code": 7, "action": action}


@pytest.mark.parametrize("params", [{}, {"version_code": 0}, {"version_code": "x"}])
def test_app_version_invalid(params):
    r = client.get("/v1/app-version", params=params)
    assert (r.status_code, r.json()) == (400, {"error": "INVALID_VERSION_CODE"})


@pytest.mark.parametrize("params", [{}, {"lat": 91, "lon": 0}, {"lat": 0, "lon": "x"}])
def test_sky_forecast_invalid(params):
    r = client.get("/v1/sky-forecast", params=params)
    assert (r.status_code, r.json()) == (400, {"error": "INVALID_COORDINATES"})


def test_sky_forecast_ok():
    r = client.get("/v1/sky-forecast", params={"lat": 40.4, "lon": -3.7})
    assert r.status_code == 200
    # Network is off in tests: weather is unknown, so nothing can be recommended.
    for e in r.json()["events"]:
        assert e["evaluation"]["is_worth_looking"] is False
        assert e["timing"]["notify_at"] is None


def event(minutes: int) -> SkyEvent:
    start = NOW + timedelta(minutes=minutes)
    return SkyEvent(
        id=f"SATELLITE:25544:{start.isoformat()}",
        category=Category.SATELLITE,
        target="ISS",
        source="TEST",
        timing=Timing(window_start=start, peak_time=start, window_end=start, duration_seconds=0),
        geometry=Geometry(magnitude=-3, max_elevation_deg=60),
    )


class FixedSource:
    def __init__(self, *events):
        self._events = list(events)

    def events(self, lat, lon, start, end):
        return self._events


class BrokenSource:
    def events(self, lat, lon, start, end):
        raise RuntimeError("upstream down")


def test_forecast_merges_sorts_and_survives_failing_source():
    sources = [FixedSource(event(30)), BrokenSource(), FixedSource(event(10))]
    forecast = build_forecast(40.4, -3.7, sources, now=NOW)
    assert [e.timing.window_start for e in forecast.events] == [
        NOW + timedelta(minutes=10),
        NOW + timedelta(minutes=30),
    ]
    assert forecast.valid_until == NOW + timedelta(hours=12)


def test_forecast_drops_geometry_failures_keeps_weather_failures():
    low = event(5)
    low.geometry.max_elevation_deg = 15  # TOO_LOW: no forecast can fix it
    forecast = build_forecast(40.4, -3.7, [FixedSource(low, event(10))], now=NOW)
    assert [e.evaluation.reason_code for e in forecast.events] == ["WEATHER_UNKNOWN"]


def test_dev_console_off_by_default():
    assert client.get("/dev").status_code == 404


def test_dev_console_when_enabled(monkeypatch):
    import importlib

    from aztarna import main

    monkeypatch.setenv("AZTARNA_DEV_UI", "1")
    r = TestClient(importlib.reload(main).app).get("/dev")
    assert r.status_code == 200
    assert "Aztarna Dev Console" in r.text
    monkeypatch.delenv("AZTARNA_DEV_UI")
    importlib.reload(main)  # back to the default app for other tests


def test_tonight_in_the_morning_is_the_coming_night():
    # Review bug: at 10:00 UTC `tonight` used to be all null (it looked at the night that had ended).
    f = build_forecast(40.4, -3.7, [], now=datetime(2026, 11, 24, 10, tzinfo=UTC))
    assert f.tonight.dusk.date() == datetime(2026, 11, 24).date()
    assert f.tonight.dusk > f.generated_at
    assert f.valid_until == f.generated_at + timedelta(hours=12)


def test_tonight_before_dawn_keeps_current_night_and_expires_at_dawn():
    # Pre-dawn passes are common, so the ending night stays "tonight" until dawn, then the response
    # expires so the app re-syncs.
    f = build_forecast(40.4, -3.7, [], now=datetime(2026, 11, 24, 6, tzinfo=UTC))
    assert f.tonight.dusk.date() == datetime(2026, 11, 23).date()
    assert f.valid_until == f.tonight.dawn


def test_highlight_never_points_at_a_finished_event():
    now = datetime(2026, 11, 24, 21, tzinfo=UTC)
    done, upcoming = event(-90), event(30)  # relative to NOW (2026-11-15 18:00)
    for e, start in ((done, now - timedelta(minutes=30)), (upcoming, now + timedelta(minutes=30))):
        e.timing.window_start = e.timing.peak_time = start
        e.timing.window_end = start + timedelta(minutes=5)
    from aztarna import weather

    weather._cache[(40.4, -3.7)] = (
        float("inf"),
        {now.replace(minute=0) + timedelta(hours=h): 0 for h in range(-2, 3)},
    )
    f = build_forecast(40.4, -3.7, [FixedSource(done, upcoming)], now=now)
    assert f.tonight.highlight_event_id == upcoming.id


def test_openapi_event_evaluation_is_required_and_not_null():
    schema = app.openapi()["components"]["schemas"]["NormalizedSkyEvent"]
    assert "evaluation" in schema["required"]
    assert schema["properties"]["evaluation"] == {"$ref": "#/components/schemas/Evaluation"}
