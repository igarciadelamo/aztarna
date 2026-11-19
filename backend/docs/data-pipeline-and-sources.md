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

### 2.3 Lunar, Solar & Eclipse Ephemerides — USNO Astronomical Applications API
- **Endpoints:**
  - Moon phases for a year: `https://aa.usno.navy.mil/api/moon/phases/year?year=YEAR`
  - Moon phases starting from a date (`nump` from `1` to `99`): `https://aa.usno.navy.mil/api/moon/phases/date?date=DATE&nump=NUMP`
  - Sun and Moon data for one day (`date`, `coords=lat,lon`, optional `tz`, `dst`): `https://aa.usno.navy.mil/api/rstt/oneday?date=DATE&coords=COORDS`
  - Solar eclipses for a year (`1800`–`2050`): `https://aa.usno.navy.mil/api/eclipses/solar/year?year=YEAR`
- **Registration / API key:** Not required (public GET JSON / GeoJSON endpoints).
- **Limitations & usage policy:**
  - Public government service; avoid excessive or uncached repeated requests and cache results appropriately.
  - Specific endpoints have range constraints (e.g., phases cover `1700`–`2100`, `nump` is `1`–`99`, and solar eclipse year listings cover `1800`–`2050`).
- **What it returns:**
  - JSON / GeoJSON containing lunar phase timestamps/types, current phase (`curphase`), fraction illuminated (`fracillum`), lunar/solar phenomena (`moondata`, `sundata`), or eclipse dates/circumstances.
- **Handling & fallback:**
  - Cache phase and calendar lookups so future dates do not trigger repeated calls; if an external lookup fails, fall back to cached data or omit that specific ephemeris item rather than guessing times.

### 2.4 Meteor Showers — Public Calendars & Dynamic Moon/Weather Evaluation
- **Sources:**
  - Public meteor shower schedules/lists such as the International Meteor Organization (IMO) meteor shower calendar (`https://www.imo.net/calendar/`) or open meteor shower datasets/catalogs (such as shower activity/peak listings).
- **Registration / API key:** Not required for public calendars/feeds.
- **Limitations & usage policy:**
  - Annual/seasonal calendars are published on a yearly or seasonal cycle and may be published as web pages, tables, CSVs, or JSON feeds rather than a single standardized real-time REST API.
  - Because calendars are not real-time weather/visibility feeds, active dates and peak nights must be crossed dynamically with lunar illumination (from the lunar source) and cloud cover (from Open-Meteo).
- **What it returns:**
  - Meteor shower names, active date ranges, peak dates/times, and expected activity/rates.
- **Handling & fallback:**
  - Refresh periodically via an automated scheduled job and store a validated local copy; keep the last valid copy if a refresh fails, and evaluate visibility dynamically against moon illumination and weather.

---

## 3. Unification into a Single Canonical Format (`NormalizedSkyEvent`)
All sources produce different shapes of data (orbital elements propagated into passes, lunar/solar/eclipse data, and meteor shower windows). To let the forecast service query and return all phenomena for a given day and rounded location uniformly, every item is mapped to a single structure (`NormalizedSkyEvent`):

- **`id`**: Deterministic unique identifier for the event and time window.
- **`category`**: Unified event type (`SATELLITE`, `METEOR_SHOWER`, `MOON`, `PLANET`, `ECLIPSE`).
- **`source`**: Origin identifier (`CELESTRAK_SGP4`, `USNO_API`, `SHOWER_FEED`, etc.).
- **`target`**: Internal target code and localization keys (`name_key`, `subtitle_key`) so localized text is resolved cleanly without hardcoding sentences in the event schema.
- **`timing`**: Normalized UTC timestamps (`window_start`, `peak_time`, `window_end`) and `duration_seconds` when applicable.
- **`geometry`**: Normalized observational metrics (`magnitude`, `max_elevation_deg`, `start_azimuth_deg`, `end_azimuth_deg`, `rate_per_hour`, `moon_illumination_percent`), set to `null` whenever a field does not apply to that phenomenon type.
- **`weather`**: `cloud_cover_percent` and `condition_code` matched to the event's time window, or `null` if weather data is unavailable.
- **`evaluation`**: `is_worth_looking` (boolean) and `reason_code` summarizing whether visibility, elevation, moon glare, and cloud cover make the event worth watching.