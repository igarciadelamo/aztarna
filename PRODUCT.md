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
- **"Is It Worth Looking?" Filter:** Evaluates local visibility (apparent brightness/magnitude, maximum elevation above the horizon) and forecasted cloud cover to discard events that are faint or obscured by bad weather. Initial thresholds (defaults, to be tuned after field testing):

  | Category | Worth looking when |
  |---|---|
  | All | Cloud cover ≤ 30% in the event window. Unknown weather → not recommended (`WEATHER_UNKNOWN`). |
  | Satellite | Magnitude ≤ 0, max elevation ≥ 30°, Sun ≤ −6° (observer in darkness), satellite sunlit. |
  | Planet | Elevation ≥ 15° during darkness (Sun ≤ −12°). |
  | Meteor shower | Effective rate ≥ 20/h **and** (moon illumination ≤ 50% **or** Moon below horizon at peak). |
  | Moon / eclipse | Moon elevation ≥ 10° during the event. |

  Assumes a suburban sky (~Bortle 5); light pollution is not modeled.
- **"Tonight" definition:** From local civil dusk (Sun at −6°) to the next civil dawn, using the device time zone. The API returns UTC; the client converts it.
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

### Tech Stack
- **Android Client:** Kotlin, Jetpack Compose (Material 3), Hilt, Room, DataStore, WorkManager, and AlarmManager (following the clean architecture baseline of *Txoka*, TODO: link repo). Min SDK 26 (proposed), target the latest SDK.
- **Self-Hosted Backend:** Lightweight stateless REST API.

### Division of Responsibilities
1. **Stateless Backend:**
   - Acts as an on-demand computation and weather aggregation layer.
   - Receives rounded coordinates (`lat`, `lon` rounded to 1 decimal place, ~11 km precision). Returns codes only; the client localizes (`es`, `eu`, `en`).
   - Computes orbital passes, cross-references public weather forecasts (e.g., Open-Meteo), returns a compact JSON payload (~2 KB), and does not persist coordinates. **Hosting requirement:** access logs disabled at every layer (reverse proxy, platform), because "no IP logs" depends on the host, not only on our code.
2. **Android Client (Offline-First):**
   - **DataStore:** Stores user settings and the last known approximate or manual location.
   - **Room:** Caches events and forecast expiration metadata so the app opens instantaneously offline.
   - **WorkManager:** Runs a periodic sync every 12 hours (when network is available) to fetch updated forecasts, refresh Room, and schedule alerts. It uses the last saved location and never requests location in the background.
   - **Weather re-check:** For each candidate event, a one-off `WorkManager` job runs ~2 h before `window_start` to re-sync. If the fresh forecast flips `is_worth_looking` to false, the alert is cancelled. This keeps alerts from relying on a forecast up to 12 h old.
   - **AlarmManager:** Alerts fire 30 min before `window_start`. Uses `setExactAndAllowWhileIdle` when the user has granted exact alarms (`SCHEDULE_EXACT_ALARM`, denied by default on Android 14+), otherwise `setAndAllowWhileIdle`. The 30-min lead absorbs Doze delays, so the app works without the exact-alarm grant. Alarms go to `SkyAlertReceiver`.
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

## 5. Stateless API Contract (`GET /v1/sky-forecast`)

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
            "window_end": "2026-11-15T21:45:15Z"
          },
          "geometry": {
            "magnitude": -3.8,
            "max_elevation_deg": 74,
            "start_azimuth_deg": 270,
            "end_azimuth_deg": 45,
            "rate_per_hour": null,
            "moon_illumination_percent": null
          },
          "weather": { "cloud_cover_percent": 10, "condition_code": "CLEAR" },
          "evaluation": { "is_worth_looking": true, "reason_code": "BRIGHT_HIGH_CLEAR" }
        }
      ]
    }

Derived on the client, not sent: the hero card (first `is_worth_looking` event tonight, else the rest
state from `tonight`), compass labels from azimuth degrees, duration (`window_end - window_start`), and
`notify_at` (`window_start` minus 30 min).

Event `id`s are unique within one response but **not stable across syncs** (orbit updates shift pass times by seconds). Clients must not rely on them across syncs (see the rescheduling rule in §3).

**Errors:** `400` with `{"error": "INVALID_COORDINATES"}` when `lat`/`lon` are missing, not numeric, or out of range. Upstream failures (weather, CelesTrak) never cause an error: the response is still `200`, with `weather: null` or the affected events omitted, as described in the pipeline doc.

---

## 6. Local Database (Room) & UI State (Compose)

- **Room Entities:**
  - `CelestialEventEntity`: Flattened `NormalizedSkyEvent` (`id`, `category`, `target`, `windowStart`, `peakTime`, `windowEnd`, `magnitude`, `maxElevationDeg`, `startAzimuthDeg`, `endAzimuthDeg`, `ratePerHour`, `moonIlluminationPercent`, `cloudCoverPercent`, `conditionCode`, `isWorthLooking`, `reasonCode`).
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

### Do we need the backend at all?
Since the data sources were reconciled, every input is either computed locally or available from a
free public API that can be called from the device:

- **Moon, planets, eclipses:** Astronomy Engine has a Kotlin port and runs offline on the device.
- **Satellites:** CelesTrak orbit data (one small fetch per day) plus SGP4 propagation on the device.
- **Weather:** Open-Meteo (or MET Norway), queried with rounded coordinates.
- **Meteor showers:** a static table shipped in the app.

**Option A: keep the backend.** It caches CelesTrak and weather requests for all users, can change
the evaluation logic without an app release, and keeps the client thin.

**Option B: on-device only.** No server to host, pay for or keep running, so cost really is zero.
Coordinates never reach our infrastructure, and the app works fully offline once the day's data has
been fetched. Downsides: changing the evaluation logic needs an app release, each device hits
CelesTrak and Open-Meteo directly (still well within their limits at portfolio scale), and the
backend stops being part of the portfolio.

To decide: is the backend there for the product, or because we want to build a backend?

### Is the module structure too heavy for the MVP?
§4 sets out five `core/` modules plus data/domain/presentation layers per feature, for one screen and a
settings page. The alternative is one Gradle module with the same package layout, split into modules
later when build times or boundaries call for it. The trade-off is learning value (the stated purpose
of the project) against setup and maintenance overhead.
