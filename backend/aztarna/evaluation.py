"""Worth-looking thresholds (PRODUCT.md §2). First failing rule gives the reason_code."""

from aztarna.models import Category, Evaluation, NormalizedSkyEvent

MAX_CLOUD = 30
SATELLITE_MAX_MAG = 0
SATELLITE_MIN_ALT = 30
PLANET_MIN_ALT = 15
METEOR_MIN_RATE = 20
METEOR_MAX_MOON = 50
MOON_MIN_ALT = 10


def evaluate(event: NormalizedSkyEvent) -> Evaluation:
    g, w = event.geometry, event.weather
    alt = g.max_elevation_deg or 0
    match event.category:
        case Category.SATELLITE:
            if alt < SATELLITE_MIN_ALT:
                return _no("TOO_LOW")
            if g.magnitude is None or g.magnitude > SATELLITE_MAX_MAG:
                return _no("TOO_FAINT")
        case Category.PLANET:
            if alt < PLANET_MIN_ALT:
                return _no("TOO_LOW")
        case Category.METEOR_SHOWER:
            if (g.rate_per_hour or 0) < METEOR_MIN_RATE:
                return _no("TOO_FAINT")
            moon_up = (g.moon_elevation_deg or 0) > 0
            if moon_up and (g.moon_illumination_percent or 0) > METEOR_MAX_MOON:
                return _no("MOON_GLARE")
        case Category.MOON | Category.ECLIPSE:
            if alt < MOON_MIN_ALT:
                return _no("TOO_LOW")
    # Weather last: geometry failures are permanent, weather may still change.
    if w is None:
        return _no("WEATHER_UNKNOWN")
    if w.cloud_cover_percent > MAX_CLOUD:
        return _no("TOO_CLOUDY")
    return Evaluation(is_worth_looking=True, reason_code="GOOD_CONDITIONS")


def _no(reason: str) -> Evaluation:
    return Evaluation(is_worth_looking=False, reason_code=reason)
