# Aztarna — Functional Data Pipeline & External Sources Specification

## 1. Purpose
This document specifies the functional data pipeline for **Aztarna** in English, covering concrete external endpoints, registration/authentication requirements, rate limits and usage policies, returned payloads/formats, fallback behavior, and normalization into a single canonical event format.

---

## 2. External Data Sources

### 2.1 Satellites (GP / TLE Orbital Data) — CelesTrak
- **Endpoints:**
  - Base GP query endpoint: `https://celestrak.org/NORAD/elements/gp.php`
  - Examples by catalog ID or group:
    - Single object (e.g., ISS, catalog number `25544`): `https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE` (or `FORMAT=CSV` / `FORMAT=JSON`)
    - Group query (e.g., space stations): `https://celestrak.org/NORAD/elements/gp.php?GROUP=STATIONS&FORMAT=CSV` (or `TLE`, `3LE`, `XML`, `JSON`)
- **Registration / API key:** Not required (public endpoint; use `celestrak.org` over HTTPS).
- **Limitations & usage policy:**
  - Strict anti-abuse / rate limiting: repeated or high-frequency polling can cause temporary or prolonged IP blocks.
  - GP data updates roughly once every 2 hours (18 SDS GP data typically updates 2–3 times per day); CelesTrak explicitly instructs downloading only when needed and at most once per update window (e.g., once every 2 hours at most, or once daily for typical daily tracking).
  - Avoid downloading huge datasets repeatedly; request only the needed objects/groups.
- **What it returns:**
  - `TLE` / `3LE`: plain ASCII lines (3 lines per object when `3LE`/`TLE` includes name on line 0, or 2 lines for `2LE`), where column alignment is strict.
  - `CSV` / `JSON` / `XML`: OMM (Orbit Data Messages) fields for each object; `CSV` is compact (~10% smaller than TLE) and avoids 5-digit catalog number limits.
- **Handling & fallback:**
  - Fetch once per day, validate non-empty response and expected objects (such as `25544`), and atomically replace the stored file only after validation succeeds.
  - If the fetch fails, keep the previous valid file. If orbital data becomes too stale to predict accurate passes, omit satellite pass events rather than reporting inaccurate pass times.
- **Propagation:** Skyfield `EarthSatellite` (wraps `python-sgp4`): `find_events()` for rise/culminate/set and `is_sunlit()` for illumination. A pass counts as visible only when the satellite is sunlit, the observer is in darkness (Sun below -6°), and the elevation is ≥10°.
- **Brightness:** CelesTrak does not provide magnitude. MVP: hardcode the standard magnitude per tracked object (ISS ≈ -1.8, Tiangong ≈ -0.9 at 1000 km, 90% lit) and scale it by range and phase angle. Mike McCants' `qs.mag` intrinsic-magnitude list is the upgrade path if the satellite list grows.

### 2.2 Local Weather & Cloud Cover — Open-Meteo
- **Endpoint:**
  - Forecast API: `https://api.open-meteo.com/v1/forecast`
  - Key query parameters: `latitude`, `longitude`, and `hourly=cloud_cover` (plus any needed time window/timezone parameters).
- **Registration / API key:** Not required for the free non-commercial endpoint (`api.open-meteo.com`).
- **Limitations & usage policy:**
  - Free tier is strictly for non-commercial use and enforces rate/volume limits (up to 600 calls/minute, 5,000 calls/hour, 10,000 calls/day, and 300,000 calls/month on the free plan).
  - Model cloud cover is an estimate with regional/local uncertainty.
- **What it returns:**
  - JSON containing requested `hourly` arrays (such as timestamps and `cloud_cover` percentages from `0` to `100`) for the requested location.
- **Handling & fallback:**
  - Query on demand using rounded coordinates (`lat` and `lon` rounded to 1 decimal place) without storing user coordinates.
  - Cache responses briefly per rounded coordinate pair to stay well within daily/hourly call limits.
  - On Open-Meteo errors or timeouts: serve expired cached weather data if available; if no weather data is available, mark cloud cover as unknown (`null`) and do not assume clear skies.
  - Attribution is required: the data is CC BY 4.0, so show "Weather data by Open-Meteo.com" in the app's About screen.
- **Alternative (not wired):** MET Norway Locationforecast 2.0 (`https://api.met.no/weatherapi/locationforecast/2.0/compact`, `cloud_area_fraction`). It is free, including commercial use, and needs an identifying `User-Agent`. Switch to it if Open-Meteo's non-commercial terms ever stop fitting.

### 2.3 Moon, Planets & Eclipses — Skyfield (local computation, no network)
- **Library:** Skyfield (`https://rhodesmill.org/skyfield/`), MIT-licensed. It is the same library used for satellites, so the backend has a single astronomy dependency.
- **Ephemeris:** JPL `de421.bsp` (~17 MB, covers 1900–2050), downloaded once at build time and shipped with the deployment. Nothing is fetched at runtime.
- **Registration / API key / rate limits:** None. Everything is computed in-process, so there is no external call to fail.
- **Covers:**
  - moon phases (`almanac.moon_phases`) and illumination (`fraction_illuminated`)
  - rise/set for the Sun, Moon and planets
  - twilight and dusk/dawn (`almanac.dark_twilight_day`)
  - oppositions and conjunctions (`almanac.oppositions_conjunctions`)
  - lunar eclipses (`eclipselib.lunar_eclipses`)
- **Not covered:** solar eclipses. They are not in the MVP list. Add Astronomy Engine (Python port) if they are ever needed.
- **Why not USNO AA API:** it adds an outage risk and range-limited endpoints for data we can compute ourselves.
- **Handling:** Compute per request for the rounded location. Results are deterministic, so no cache is needed.

### 2.4 Meteor Showers — Static Table (from IMO Working List)
- **Source:** IMO Meteor Shower Calendar (`https://www.imo.net/resources/calendar/`). It is published yearly as a PDF, and Table 5 is the working list. There is no CSV, JSON or API.
- **Approach:** A hand-maintained table in the repo of the ~10 major showers (Quadrantids, Lyrids, Eta Aquariids, Perseids, Orionids, Leonids, Geminids, Ursids, Southern Delta Aquariids, Draconids), with `code`, active window, solar-longitude peak, ZHR, and radiant RA/Dec. Update it by hand once a year from the new IMO PDF.
- **Evaluation:** Compute the radiant elevation and moon illumination with Skyfield, take cloud cover from 2.2, and derive the effective rate from ZHR × sin(radiant elevation).
- **Fallback:** None needed, because the data is static.

---

## 3. Unification into a Single Canonical Format (`NormalizedSkyEvent`)
All sources produce different shapes of data (orbital elements propagated into passes, lunar/solar/eclipse data, and meteor shower windows). Every item is mapped to a single structure (`NormalizedSkyEvent`), and that structure **is** the item type of `events` in the public API (`PRODUCT.md` §5). No separate DTO. The payload carries codes only and the client localizes them. Every derived value the app shows or acts on is computed here; the client does no calculation (`PRODUCT.md` §3, thin-client principle).

- **`id`**: `{category}:{target_or_norad_id}:{window_start}`. Unique within one response, but **not stable across syncs**: orbit updates shift `window_start`. Clients reschedule alerts by time, not by id (`PRODUCT.md` §3).
- **`category`**: `SATELLITE`, `METEOR_SHOWER`, `MOON`, `PLANET`, `ECLIPSE`.
- **`target`**: Stable code (`ISS`, `TIANGONG`, `GEMINIDS`, `JUPITER`, `FULL_MOON`, …). The client maps it to a localized name, and unknown codes are shown raw.
- **`source`**: `CELESTRAK_SGP4`, `SKYFIELD`, `SHOWER_TABLE`. Used for attribution and debugging.
- **`timing`**: UTC `window_start`, `peak_time`, `window_end`, plus `duration_seconds`. `notify_at` (`window_start` − 30 min) and `recheck_at` (`window_start` − 2 h) are set only when `is_worth_looking` is true, and are `null` otherwise.
- **`geometry`**: `magnitude`, `max_elevation_deg`, `start_azimuth_deg`, `end_azimuth_deg` (0–360, N=0, clockwise), `start_direction`, `end_direction` (16-point compass codes), `rate_per_hour`, `moon_illumination_percent`, `moon_elevation_deg` (Moon altitude at peak; meteor moon-glare only counts when the Moon is up). A field is `null` when it does not apply.
- **`weather`**: `cloud_cover_percent` and `condition_code` (`CLEAR`, `PARTLY_CLOUDY`, `OVERCAST`) for the event window, or `null` if unknown.
- **`evaluation`**: `is_worth_looking` and `reason_code` (`GOOD_CONDITIONS`, `TOO_LOW`, `TOO_FAINT`, `MOON_GLARE`, `TOO_CLOUDY`, `WEATHER_UNKNOWN`; geometry rules are checked before weather, see `backend/aztarna/evaluation.py`). Events that fail on geometry are dropped from the API response; only `GOOD_CONDITIONS`, `TOO_CLOUDY` and `WEATHER_UNKNOWN` reach the client. The client turns `reason_code` into the localized subtitle.