# Aztarna — Product Definition & Technical Architecture

## 1. Identity & Purpose
- **Name:** **Aztarna** (*"footprint"* or *"trail"* in Basque). Minimalist, exotic, easy to pronounce in English, free of direct naming collisions in the astronomy space, and evocative of satellite trails and shooting stars.
- **Purpose:** Personal Android portfolio project built for continuous learning and clean publication on Google Play. No commercial monetization or ads.
- **Core Philosophy:** Zero/minimal operational cost, strict user privacy by design, and zero friction.

---

## 2. Functional Scope (MVP vs. Future)

### Version 1 (MVP)
- **Supported Events (fixed MVP list):**
  - Satellites: ISS and Tiangong passes.
  - Meteor showers: the ~10 major showers in the static table (see pipeline doc §2.4).
  - Moon: full moon, supermoon, lunar eclipses.
  - Planets: oppositions of Mars, Jupiter and Saturn; conjunctions closer than 2° between bright planets or with the Moon.
- **"Is It Worth Looking?" Filter:** Runs on the server only. Evaluates local visibility (apparent brightness/magnitude, maximum elevation above the horizon) and forecasted cloud cover to discard events that are faint or obscured by bad weather. Initial thresholds (defaults, to be tuned after field testing):

  | Category | Worth looking when |
  |---|---|
  | All | Cloud cover ≤ 30% in the event window. Unknown weather → not recommended (`WEATHER_UNKNOWN`). |
  | Satellite | Magnitude ≤ 0, max elevation ≥ 30°, Sun ≤ −6° (observer in darkness), satellite sunlit. |
  | Planet | Elevation ≥ 15° during darkness (Sun ≤ −12°). |
  | Meteor shower | Effective rate ≥ 20/h **and** (moon illumination ≤ 50% **or** Moon below horizon at peak). |
  | Moon / eclipse | Moon elevation ≥ 10° during the event. |

  Assumes a suburban sky (~Bortle 5); light pollution is not modeled.
- **"Tonight" definition:** From local civil dusk (Sun at −6°) to the next civil dawn, computed by the server for the rounded location and returned as `tonight.dusk` / `tonight.dawn` (UTC). The client only formats them in the device time zone. During the day, "tonight" is the coming night. During a night, it stays that night until dawn, because many satellite passes happen just before dawn. In that case `valid_until` is set to that dawn, so the app re-syncs instead of showing an ended night all day.
- **Proactive Alerts:** Silent background evaluation that triggers local notifications in advance *only* when visual and weather conditions align.
- **App Home Experience:** Clean, single-screen Material 3 interface displaying:
  - **Tonight's Hero Card:** Highlights the top worthwhile event or displays an honest rest state (*"Overcast sky or no notable events tonight"*).
  - **Upcoming Agenda:** Minimalist chronological list for the next 3–5 days with visibility indicators.
- **Location & Privacy:** Relies on approximate location (`ACCESS_COARSE_LOCATION`) with a manual city selector fallback. Coordinates are rounded to 1 decimal (~11 km) before leaving the device. The backend forwards them only to the weather provider, keeps them only in an in-memory cache with a TTL, and never writes them to disk or logs.
- **Monetization:** 100% ad-free (no AdMob or third-party tracking SDKs).

### Version 2 (Future Iterations)
- Home screen widget displaying the next clear-sky window.
- Lightweight sky compass orientation powered by device sensors (accelerometer/magnetometer).
- Granular user filters for event categories and minimum brightness thresholds.

---

## 3. System Architecture (Hybrid Stateless + Offline-First)

### Principle: Thin Client
**The app computes nothing.** All astronomy, weather evaluation, filtering, ranking and timing
decisions (which event is tonight's highlight, when to notify, when to re-check the weather) happen on
the server and arrive as ready-to-use fields. The client only:
- displays server data, localizing codes (`target`, `reason_code`, `condition_code`, directions) with Android string resources;
- formats UTC timestamps in the device time zone;
- schedules alarms and jobs at the exact times the server provides;
- stores the last response in Room so it works offline.

This lets us fix or tune evaluation logic without an app release. Any new client-side rule needs a
reason why the server cannot provide it.

### Tech Stack
- **Android Client:** Kotlin, Jetpack Compose (Material 3), Hilt, Room, DataStore, WorkManager, and AlarmManager (following the clean architecture baseline of *Txoka*, TODO: link repo). Min SDK 26 (proposed), target the latest SDK.
- **Self-Hosted Backend:** Lightweight stateless REST API in **Python (FastAPI + Skyfield)**. Managed with uv and shipped as a single Docker image; setup plan, routes and code layout are in [`backend/README.md`](backend/README.md).

### Backend Language Decision
We keep a backend: it lets evaluation logic change without app releases and gives a place for version
control (§5). Language comparison:

| | Python | Go | Kotlin (Ktor) |
|---|---|---|---|
| Astronomy libraries | **Skyfield**: best in class (SGP4, satellite sunlit check, rise/set, twilight, moon phases, oppositions/conjunctions, lunar eclipses) | Weak: `go-satellite` is a thinly maintained SGP4 port; no Astronomy Engine port | Astronomy Engine Kotlin; SGP4 only via Orekit (heavy) |
| Deployment | Runtime needed, ~100 MB RAM | Single binary, ~15 MB RAM, cheapest | JVM, ~200 MB RAM |
| Code sharing with Android | None | None | Possible, but irrelevant because the client computes nothing |

**Choice: Python.** The hard part of this project is astronomy, and Skyfield makes it the least code
to write. Go would only win on hosting cost, at the price of writing astronomy code ourselves. Kotlin's
advantage (sharing code with the app) disappears with the thin-client principle.

### Division of Responsibilities
1. **Stateless Backend:**
   - Acts as an on-demand computation and weather aggregation layer.
   - Receives rounded coordinates (`lat`, `lon` rounded to 1 decimal place, ~11 km precision). Returns codes only; the client localizes (`es`, `eu`, `en`).
   - Computes orbital passes, cross-references public weather forecasts (e.g., Open-Meteo), returns a compact JSON payload (~2 KB), and does not persist coordinates. **Hosting requirement:** access logs disabled at every layer (reverse proxy, platform), because "no IP logs" depends on the host, not only on our code.
2. **Android Client (Offline-First):**
   - **DataStore:** Stores user settings and the last known approximate or manual location.
   - **Room:** Caches events and forecast expiration metadata so the app opens instantaneously offline.
   - **WorkManager:** Runs a periodic sync every 12 hours (when network is available) to fetch updated forecasts, refresh Room, and schedule alerts. It uses the last saved location and never requests location in the background.
   - **Weather re-check:** For each candidate event, a one-off `WorkManager` job runs at the server-provided `recheck_at` (~2 h before `window_start`) to re-sync. If the fresh forecast flips `is_worth_looking` to false, the alert is cancelled. This keeps alerts from relying on a forecast up to 12 h old.
   - **AlarmManager:** Alerts fire at the server-provided `notify_at` (30 min before `window_start`). Uses `setExactAndAllowWhileIdle` when the user has granted exact alarms (`SCHEDULE_EXACT_ALARM`, denied by default on Android 14+), otherwise `setAndAllowWhileIdle`. The 30-min lead absorbs Doze delays, so the app works without the exact-alarm grant. Alarms go to `SkyAlertReceiver`.
   - **Rescheduling rule:** Each sync cancels **all** pending alerts and reschedules only events whose alert time is still in the future. Event ids shift as orbit data updates, so this rule, not id matching, prevents duplicate notifications; an event that already alerted is in the past and is never rescheduled. `BootReceiver` (`BOOT_COMPLETED`) applies the same rule from Room.

---

## 4. Project Structure (Clean Architecture / Feature-First)

    com.igarciadelamo.aztarna/
    │
    ├── core/
    │   ├── network/        # HTTP client (Ktor/Retrofit) & API DTOs
    │   ├── database/       # Room database, Entities, DAOs, Mappers
    │   ├── datastore/      # User preferences & approximate location storage
    │   ├── workers/        # WorkManager sync & AlarmManager/BroadcastReceivers
    │   └── ui/             # Shared Material 3 theme, dark sky palette & components
    │
    ├── feature/home/
    │   ├── data/           # Repository implementation (Offline-First coordination)
    │   ├── domain/         # Pure Kotlin domain models & Use Cases
    │   └── presentation/   # HomeScreen (Compose), ViewModel & HomeUiState
    │
    └── feature/settings/
        ├── domain/
        └── presentation/   # Notification toggles & manual location picker

---

## 5. Stateless API Contract

### Sky Forecast (`GET /v1/sky-forecast`)

**Request:**

    GET /v1/sky-forecast?lat=40.4&lon=-3.7

No `lang` parameter: the API returns codes only and the client localizes them with Android string
resources (`es`, `eu`, `en`). Each item in `events` is exactly a `NormalizedSkyEvent` (see
[`backend/docs/data-pipeline-and-sources.md`](backend/docs/data-pipeline-and-sources.md) §3), so the
backend has one model end to end.

**Response (`200 OK`):**

    {
      "generated_at": "2026-11-15T18:00:00Z",
      "valid_until": "2026-11-16T08:00:00Z",
      "tonight": {
        "dusk": "2026-11-15T17:21:00Z",
        "dawn": "2026-11-16T06:52:00Z",
        "highlight_event_id": "SATELLITE:25544:2026-11-15T21:39:15Z",
        "cloud_cover_percent": 10,
        "condition_code": "CLEAR"
      },
      "events": [
        {
          "id": "SATELLITE:25544:2026-11-15T21:39:15Z",
          "category": "SATELLITE",
          "target": "ISS",
          "source": "CELESTRAK_SGP4",
          "timing": {
            "window_start": "2026-11-15T21:39:15Z",
            "peak_time": "2026-11-15T21:42:15Z",
            "window_end": "2026-11-15T21:45:15Z",
            "duration_seconds": 360,
            "notify_at": "2026-11-15T21:09:15Z",
            "recheck_at": "2026-11-15T19:39:15Z"
          },
          "geometry": {
            "magnitude": -3.8,
            "max_elevation_deg": 74,
            "start_azimuth_deg": 270,
            "end_azimuth_deg": 45,
            "start_direction": "W",
            "end_direction": "NE",
            "rate_per_hour": null,
            "moon_illumination_percent": null,
            "moon_elevation_deg": null
          },
          "weather": { "cloud_cover_percent": 10, "condition_code": "CLEAR" },
          "evaluation": { "is_worth_looking": true, "reason_code": "GOOD_CONDITIONS" },
          "tips": ["ARRIVE_EARLY", "FACE_START_DIRECTION", "STEADY_MOVING_STAR", "SHADOW_FADE", "NAKED_EYE", "PHOTO_TRAIL"]
        }
      ]
    }

Everything is precomputed (thin-client principle, §3):
- **Only events that weather could make worth looking are returned.** Events that fail on geometry (`TOO_LOW`, `TOO_FAINT`, `MOON_GLARE`) are dropped, so every `reason_code` the app sees is `GOOD_CONDITIONS`, `TOO_CLOUDY` or `WEATHER_UNKNOWN`.
- **Hero card:** `tonight.highlight_event_id`. If it is `null`, the app shows the rest state using the `tonight` weather.
- **Tips:** static viewing-tip codes per event type, most specific first (e.g. `JUPITER_MOONS` before the generic planet tips). The English source copy for each code is in `backend/aztarna/tips.py` (`TEXT`); the app translates them like other codes.
- **Directions:** 16-point compass codes (`N`, `NNE`, … `NW`, `NNW`). Degrees are kept for the v2 sky compass.
- **Alert timing:** `notify_at` and `recheck_at`. Both are `null` for events that are not `is_worth_looking`.

Event `id`s are unique within one response but **not stable across syncs** (orbit updates shift pass times by seconds). Clients must not rely on them across syncs (see the rescheduling rule in §3).

**Errors:** `400` with `{"error": "INVALID_COORDINATES"}` when `lat`/`lon` are missing, not numeric, or out of range. Upstream failures (weather, CelesTrak) never cause an error: the response is still `200`, with `weather: null` or the affected events omitted, as described in the pipeline doc.

### App Version Check (`GET /v1/app-version`)

Both version values live on the backend (environment variables, see `backend/README.md`), so we can
force or suggest updates without shipping code.

**Request:** the app sends its own Android `versionCode`.

    GET /v1/app-version?version_code=5

**Response (`200 OK`):**

    {
      "min_version_code": 4,
      "latest_version_code": 7,
      "action": "SUGGEST_UPDATE"
    }

- `action` is decided by the server (thin-client principle):
  - `FORCE_UPDATE` when `version_code < min_version_code`. The app blocks all use and starts a Google Play In-App Updates `IMMEDIATE` flow.
  - `SUGGEST_UPDATE` when `version_code < latest_version_code`. The app shows a dismissible call to action that starts a `FLEXIBLE` update flow.
  - `NONE` otherwise.
- Both values are also returned, so the app can show them on the About screen.
- **When it is called:** on every app start (foreground) and before each background sync. If `FORCE_UPDATE` comes back during a sync, the sync stops and no alerts are scheduled.
- **Offline:** the last response is cached in DataStore. If the check fails, the app uses the cached `action`, and with no cache it uses `NONE`, so a network failure never locks a user out.
- **Errors:** `400` with `{"error": "INVALID_VERSION_CODE"}` when `version_code` is missing or not a positive integer.

---

## 6. Local Database (Room) & UI State (Compose)

- **Room Entities:**
  - `CelestialEventEntity`: Flattened `NormalizedSkyEvent` (`id`, `category`, `target`, `windowStart`, `peakTime`, `windowEnd`, `magnitude`, `maxElevationDeg`, `startAzimuthDeg`, `endAzimuthDeg`, `ratePerHour`, `moonIlluminationPercent`, `moonElevationDeg`, `cloudCoverPercent`, `conditionCode`, `isWorthLooking`, `reasonCode`, `tips` as a comma-separated string).
  - `ForecastCacheEntity`: Single-row table storing forecast metadata (`generatedAt`, `validUntil`, `tonightCloudCoverPercent`, `tonightConditionCode`).
- **UI State (`HomeUiState`):** Sealed interface following Unidirectional Data Flow (`Loading`, `Success`, `Error` with cached data fallback).

---

## 7. Google Play Permission Strategy
1. **Approximate location, foreground only:** Requests `ACCESS_COARSE_LOCATION` (~3 km radius) only when the user opts into automatic location; never `ACCESS_FINE_LOCATION`. The location refreshes while the app is open and is saved to DataStore; background sync reuses it.
2. **No background location:** `ACCESS_BACKGROUND_LOCATION` is not requested. It would bring a Play policy declaration, a review video and a disclosure screen, for little gain: at ~11 km rounding, the saved location is rarely stale.
3. **Manual city fallback:** If location is denied, the user searches for a city through the Open-Meteo Geocoding API (`https://geocoding-api.open-meteo.com/v1/search`, free, no key). Only the chosen city's rounded coordinates are stored.
4. **Notifications:** `POST_NOTIFICATIONS` (runtime permission on Android 13+) is requested in context, when the user turns alerts on. Without it the app still works as a read-only agenda.
5. **Exact alarms:** `SCHEDULE_EXACT_ALARM` is optional; the app degrades to inexact alarms (see §3). `USE_EXACT_ALARM` is not used, because Play only allows it for alarm-clock and calendar apps.

---

## 8. Competitive Positioning
- **Competitors (*Heavens-Above*, *ISS Detector*, *Sky Tonight*, *Stellarium*):** Either suffer from dated interfaces, intrusive ads, and paywalls, or act as heavy planetarium apps that overwhelm users with raw orbital data.
- **Aztarna's Differentiator:** Modern Material 3 design, zero ads, strict privacy, and smart curation—acting as a quiet filter that only alerts you when the sky is clear and an event is genuinely worth stepping outside to see.

---

## 9. Open Questions

### Is the module structure too heavy for the MVP?
§4 sets out five `core/` modules plus data/domain/presentation layers per feature, for one screen and a
settings page. The alternative is one Gradle module with the same package layout, split into modules
later when build times or boundaries call for it. The trade-off is learning value (the stated purpose
of the project) against setup and maintenance overhead.

With the thin-client principle (§3), the `domain/` layer and its use cases would contain almost no
logic, which strengthens the case for the single module.
