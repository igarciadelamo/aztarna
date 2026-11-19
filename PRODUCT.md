# Aztarna — Product Definition & Technical Architecture

## 1. Identity & Purpose
- **Name:** **Aztarna** (*"footprint"* or *"trail"* in Basque). Minimalist, exotic, easy to pronounce in English, free of direct naming collisions in the astronomy space, and evocative of satellite trails and shooting stars.
- **Purpose:** Personal Android portfolio project built for continuous learning and clean publication on Google Play. No commercial monetization or ads.
- **Core Philosophy:** Zero/minimal operational cost, strict user privacy by design, and zero friction.

---

## 2. Functional Scope (MVP vs. Future)

### Version 1 (MVP)
- **Supported Events:** Bright International Space Station (ISS) and notable satellite passes, major meteor showers, and significant lunar or planetary events.
- **"Is It Worth Looking?" Filter:** Evaluates local visibility (apparent brightness/magnitude, maximum elevation above the horizon) and forecasted cloud cover to discard events that are faint or obscured by bad weather.
- **Proactive Alerts:** Silent background evaluation that triggers local notifications in advance *only* when visual and weather conditions align.
- **App Home Experience:** Clean, single-screen Material 3 interface displaying:
  - **Tonight's Hero Card:** Highlights the top worthwhile event or displays an honest rest state (*"Overcast sky or no notable events tonight"*).
  - **Upcoming Agenda:** Minimalist chronological list for the next 3–5 days with visibility indicators.
- **Location & Privacy:** Relies on approximate location (`ACCESS_COARSE_LOCATION`) with a manual city selector fallback. User coordinates are never stored on the server.
- **Monetization:** 100% ad-free (no AdMob or third-party tracking SDKs).

### Version 2 (Future Iterations)
- Home screen widget displaying the next clear-sky window.
- Lightweight sky compass orientation powered by device sensors (accelerometer/magnetometer).
- Granular user filters for event categories and minimum brightness thresholds.

---

## 3. System Architecture (Hybrid Stateless + Offline-First)

### Tech Stack
- **Android Client:** Kotlin, Jetpack Compose (Material 3), Hilt, Room, DataStore, WorkManager, and AlarmManager (following the clean architecture baseline of *Txoka*).
- **Self-Hosted Backend:** Lightweight stateless REST API.

### Division of Responsibilities
1. **Stateless Backend:**
   - Acts as an on-demand computation and weather aggregation layer.
   - Receives rounded coordinates (`lat`, `lon` rounded to 1 decimal place, ~11 km precision) and preferred language (`es`, `eu`, `en`).
   - Computes orbital passes, cross-references public weather forecasts (e.g., Open-Meteo), returns a compact JSON payload (~2 KB), and discards the request immediately without persisting coordinates or IP logs.
2. **Android Client (Offline-First):**
   - **DataStore:** Stores user settings and the last known approximate or manual location.
   - **Room:** Caches events and forecast expiration metadata so the app opens instantaneously offline.
   - **WorkManager:** Runs a periodic sync every 12 hours (when network is available) to fetch updated forecasts, refresh Room, and schedule alerts.
   - **AlarmManager:** Schedules exact local alerts (`setExactAndAllowWhileIdle`, degrading gracefully to `setAndAllowWhileIdle` if exact alarm permission is revoked) pointing to a `BroadcastReceiver` (`SkyAlertReceiver`). A `BootReceiver` restores scheduled alarms from Room upon device reboot (`BOOT_COMPLETED`).

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

    GET /v1/sky-forecast?lat=40.4&lon=-3.7&lang=en

**Response (`200 OK`):**

    {
      "generated_at": "2026-11-15T18:00:00Z",
      "valid_until": "2026-11-16T08:00:00Z",
      "tonight_summary": {
        "is_worth_going_out": true,
        "headline": "Bright ISS Pass",
        "weather_condition": "Clear",
        "cloud_cover_percent": 10
      },
      "events": [
        {
          "id": "iss_20261115_2142",
          "type": "SATELLITE",
          "title": "International Space Station (ISS)",
          "subtitle": "Very bright, easily visible to the naked eye",
          "notify_at": "2026-11-15T21:27:00Z",
          "peak_time": "2026-11-15T21:42:15Z",
          "duration_seconds": 360,
          "visibility": {
            "magnitude": -3.8,
            "max_elevation_deg": 74,
            "start_azimuth": "West",
            "end_azimuth": "Northeast",
            "cloud_cover_percent": 10,
            "is_recommended": true
          }
        }
      ]
    }

---

## 6. Local Database (Room) & UI State (Compose)

- **Room Entities:**
  - `CelestialEventEntity`: Stores individual event fields (`id`, `type`, `title`, `notifyAt`, `peakTime`, `magnitude`, `maxElevationDeg`, azimuths, `cloudCoverPercent`, `isRecommended`, `cachedAt`).
  - `ForecastCacheEntity`: Single-row table storing global forecast metadata (`validUntil`, `isWorthGoingOut`, `headline`, `weatherCondition`, `cloudCoverPercent`).
- **UI State (`HomeUiState`):** Sealed interface following Unidirectional Data Flow (`Loading`, `Success`, `Error` with cached data fallback).

---

## 7. Google Play Location Permission Strategy
1. **Approximate Location Only:** Requests `ACCESS_COARSE_LOCATION` (~3 km radius), avoiding `ACCESS_FINE_LOCATION`.
2. **Two-Step Contextual Flow:**
   - Foreground permission is requested only when the user opts into automatic location (with a manual city selector fallback if denied).
   - Background location (`ACCESS_BACKGROUND_LOCATION`) is preceded by an in-app **Prominent Disclosure** screen clearly explaining why periodic approximate location checks are needed and confirming that coordinates are never stored.

---

## 8. Competitive Positioning
- **Competitors (*Heavens-Above*, *ISS Detector*, *Sky Tonight*, *Stellarium*):** Either suffer from dated interfaces, intrusive ads, and paywalls, or act as heavy planetarium apps that overwhelm users with raw orbital data.
- **Aztarna's Differentiator:** Modern Material 3 design, zero ads, strict privacy, and smart curation—acting as a quiet filter that only alerts you when the sky is clear and an event is genuinely worth stepping outside to see.