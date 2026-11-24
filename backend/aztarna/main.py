import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from aztarna import tips, weather
from aztarna.forecast import build_forecast
from aztarna.models import AppVersionResponse, ForecastResponse, UpdateAction
from aztarna.sources import SOURCES
from aztarna.sources.satellites import refresh_tle, tle_age_hours, tle_path


@asynccontextmanager
async def lifespan(_: FastAPI):
    refresh_tle(tle_path())  # Warm the TLE file so the first request doesn't wait on CelesTrak.
    yield


app = FastAPI(title="Aztarna", lifespan=lifespan)

ERROR_CODES = {
    "/v1/sky-forecast": "INVALID_COORDINATES",
    "/v1/app-version": "INVALID_VERSION_CODE",
}


@app.exception_handler(RequestValidationError)
async def bad_request(request: Request, _: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        {"error": ERROR_CODES.get(request.url.path, "INVALID_REQUEST")}, status_code=400
    )


TLE_STALE_HOURS = 48  # daily refresh failing for 2 days: satellite events will soon disappear


@app.get("/health")
def health() -> dict:
    """Always 200 while the process serves requests. `status: degraded` is for the uptime monitor
    (keyword alert): CelesTrak refresh failing, or the weather budget spent this hour."""
    age = tle_age_hours()
    budget = weather.budget_left()
    degraded = age is None or age > TLE_STALE_HOURS or budget == 0
    return {
        "status": "degraded" if degraded else "ok",
        "tle_age_hours": age,
        "weather_budget_left": budget,
    }


@app.get("/v1/app-version")
def app_version(version_code: Annotated[int, Query(gt=0)]) -> AppVersionResponse:
    min_code = int(os.environ.get("MIN_VERSION_CODE", "1"))
    latest_code = int(os.environ.get("LATEST_VERSION_CODE", "1"))
    if version_code < min_code:
        action = UpdateAction.FORCE_UPDATE
    elif version_code < latest_code:
        action = UpdateAction.SUGGEST_UPDATE
    else:
        action = UpdateAction.NONE
    return AppVersionResponse(
        min_version_code=min_code, latest_version_code=latest_code, action=action
    )


@app.get("/v1/sky-forecast")
def sky_forecast(
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
) -> ForecastResponse:
    # Re-round server-side: never trust the client to have done it (privacy, PRODUCT.md §3).
    return build_forecast(round(lat, 1), round(lon, 1), SOURCES)


# Manual testing page, only when AZTARNA_DEV_UI=1 (set by `make run`); never in Docker/production.
if os.environ.get("AZTARNA_DEV_UI") == "1":

    @app.get("/dev", include_in_schema=False)
    def dev_console() -> HTMLResponse:
        # Inject the English tip copy so the concept preview shows real sentences, not codes.
        tips_json = json.dumps(tips.TEXT).replace("</", "<\\/")
        html = (Path(__file__).parent / "dev.html").read_text()
        return HTMLResponse(html.replace('"__TIPS__"', tips_json))
