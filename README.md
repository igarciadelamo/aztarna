# Aztarna

Native Android app for astronomy alerts with strict privacy. It only notifies you when a celestial
event is visible to the naked eye and the local weather allows you to enjoy it.

The product definition and technical architecture live in [`PRODUCT.md`](PRODUCT.md).

## Repository layout

Monorepo with two projects:

- [`android/`](android/) — Kotlin + Jetpack Compose client, offline-first.
- [`backend/`](backend/) — stateless REST API for sky forecasts.

## Quick Start (backend)

```
cd backend
make setup   # needs uv: brew install uv
make run
```

Then open the **dev console at http://127.0.0.1:8000/dev**: search a place by name (or use your
location, or type coordinates) and see tonight's summary and every event the API returns, with
weather, verdict, alert times and tips. API docs are at `/docs`.

## Status

- **Backend:** working. Sky, satellite and meteor sources, weather evaluation, app-version gate,
  CI. See [`backend/README.md`](backend/README.md).
- **Android:** not started.
