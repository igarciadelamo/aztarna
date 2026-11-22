import pytest

from aztarna import weather
from aztarna.sources import satellites


@pytest.fixture(autouse=True)
def no_network(monkeypatch, tmp_path):
    """Tests never call CelesTrak or Open-Meteo, and never touch backend/data."""

    def offline(*_):
        raise OSError("network disabled in tests")

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(weather, "fetch", offline)
    monkeypatch.setattr(weather, "_cache", {})
    monkeypatch.setattr(weather, "_budget", {"hour_start": 0.0, "used": 0})
    monkeypatch.setattr(satellites, "refresh_tle", lambda path: None)
