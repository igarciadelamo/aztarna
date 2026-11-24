"""API models. Sources produce SkyEvent; the pipeline adds weather, evaluation and tips and returns
NormalizedSkyEvent (the API event shape, same fields with `evaluation` required)."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class Category(StrEnum):
    SATELLITE = "SATELLITE"
    METEOR_SHOWER = "METEOR_SHOWER"
    MOON = "MOON"
    PLANET = "PLANET"
    ECLIPSE = "ECLIPSE"


class Timing(BaseModel):
    window_start: datetime
    peak_time: datetime
    window_end: datetime
    duration_seconds: int
    notify_at: datetime | None = None
    recheck_at: datetime | None = None


class Geometry(BaseModel):
    magnitude: float | None = None
    max_elevation_deg: float | None = None
    # Satellites have a path (start → peak → end); other events only a peak position.
    start_azimuth_deg: float | None = None
    start_elevation_deg: float | None = None
    peak_azimuth_deg: float | None = None
    end_azimuth_deg: float | None = None
    end_elevation_deg: float | None = None
    start_direction: str | None = None
    peak_direction: str | None = None
    end_direction: str | None = None
    # Human-scale labels (server-side thresholds, app only localizes):
    brightness_code: str | None = None  # VERY_BRIGHT | BRIGHT | VISIBLE; null without magnitude
    height_code: str | None = None  # HIGH | MID | LOW
    rate_per_hour: float | None = None
    moon_illumination_percent: float | None = None
    moon_elevation_deg: float | None = None


class Weather(BaseModel):
    cloud_cover_percent: int
    condition_code: str


class Evaluation(BaseModel):
    is_worth_looking: bool
    reason_code: str


class SkyEvent(BaseModel):
    id: str
    category: Category
    target: str
    source: str
    timing: Timing
    geometry: Geometry
    # Filled by the forecast pipeline after the sources run.
    weather: Weather | None = None
    evaluation: Evaluation | None = None
    tips: list[str] = []  # static viewing-tip codes, localized by the app (aztarna/tips.py)


class NormalizedSkyEvent(SkyEvent):
    """API shape of an event. The pipeline always evaluates, so `evaluation` is never null here
    (sources build SkyEvent, which has no evaluation yet)."""

    evaluation: Evaluation


class Tonight(BaseModel):
    dusk: datetime | None = None
    dawn: datetime | None = None
    highlight_event_id: str | None = None
    next_worthwhile_event_id: str | None = (
        None  # first worthwhile event in the horizon (rest state)
    )
    cloud_cover_percent: int | None = None
    condition_code: str | None = None


class ForecastResponse(BaseModel):
    generated_at: datetime
    valid_until: datetime
    tonight: Tonight
    events: list[NormalizedSkyEvent]


class UpdateAction(StrEnum):
    FORCE_UPDATE = "FORCE_UPDATE"
    SUGGEST_UPDATE = "SUGGEST_UPDATE"
    NONE = "NONE"


class AppVersionResponse(BaseModel):
    min_version_code: int
    latest_version_code: int
    action: UpdateAction
