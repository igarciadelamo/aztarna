from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from aztarna.forecast import build_forecast
from aztarna.main import app
from aztarna.models import Category, Geometry, NormalizedSkyEvent, Timing

client = TestClient(app)
NOW = datetime(2026, 11, 15, 18, tzinfo=UTC)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


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
    assert r.json()["events"] == []


def event(minutes: int) -> NormalizedSkyEvent:
    start = NOW + timedelta(minutes=minutes)
    return NormalizedSkyEvent(
        id=f"SATELLITE:25544:{start.isoformat()}",
        category=Category.SATELLITE,
        target="ISS",
        source="TEST",
        timing=Timing(window_start=start, peak_time=start, window_end=start, duration_seconds=0),
        geometry=Geometry(),
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
