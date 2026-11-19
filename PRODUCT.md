# Aztarna — Definición de Producto y Arquitectura Técnica

> **Aztarna** (*"huella"* o *"rastro"* en euskera) es una aplicación nativa para Android diseñada bajo principios de **privacidad estricta**, **coste operativo cero** y **mínima fricción**, cuyo objetivo es avisar proactivamente al usuario únicamente cuando ocurre un evento astronómico visible a simple vista y las condiciones meteorológicas locales permiten disfrutarlo.

---

## 1. Visión de Producto e Identidad

* **Nombre:** **Aztarna** (minimalista, eufónico en inglés, libre de colisiones en Google Play dentro del sector astronómico y evocador de las estelas celestes).
* **Propósito:** Proyecto personal de portfolio técnico y publicación limpia en Google Play, sin modelo de negocio invasivo ni publicidad.
* **Diferencial frente a la competencia** (*Heavens-Above*, *ISS Detector*, *Sky Tonight*, *Stellarium*):
  * Cero publicidad, cero muros de pago y cero ruido técnico.
  * **Curación inteligente:** En lugar de bombardear con decenas de pasos de satélites invisibles o alertas bajo cielos nublados, actúa como un filtro inteligente que responde a una única pregunta: *«¿Merece la pena salir a mirar al cielo esta noche?»*.

---

## 2. Alcance Funcional

### Versión 1 (MVP)
* **Eventos celestes monitorizados:**
  * Pasos brillantes de la Estación Espacial Internacional (**ISS**) y satélites destacados.
  * Lluvias de estrellas principales (Perseidas, Gemínidas, Leónidas, etc.).
  * Eventos lunares y acercamientos planetarios notables.
* **Motor de decisión ("¿Compensa mirar?"):** Filtra eventos descartando aquellos con baja elevación sobre el horizonte, brillo insuficiente o cobertura nubosa desfavorable.
* **Notificaciones proactivas:** Alertas locales programadas con antelación óptima únicamente cuando se cumplen las condiciones astronómicas y meteorológicas.
* **Pantalla principal accionable:**
  * *Hero Card ("Esta noche"):* Muestra el evento estrella del día si merece la pena salir, o un mensaje honesto de descanso si el cielo estará cubierto.
  * *Agenda semanal:* Lista cronológica de los próximos eventos candidatos con su indicador de visibilidad.
* **Privacidad y accesibilidad:** Ubicación aproximada sin cuentas de usuario, soporte para selección manual de ciudad como *fallback* e interfaz localizada (`es`, `eu`, `en`).

### Versión 2 (Iteraciones Futuras)
* Widget de escritorio con la próxima ventana celeste despejada.
* Brújula de cielo básica apoyada en sensores del dispositivo (acelerómetro y magnetómetro).
* Filtros granulares de brillo y categorías personalizables por el usuario.

---

## 3. Arquitectura Técnica (Modelo Híbrido *Stateless*)

Para evitar cálculos orbitales pesados en el dispositivo móvil y mantener una batería intacta sin comprometer la privacidad, el sistema adopta una arquitectura cliente-servidor **stateless** y **Offline-First**:

1. **Backend Ligero (*Stateless* en servidor propio):**
   * Descarga periódicamente los ficheros públicos de elementos orbitales (TLEs desde *Celestrak*) y consulta pronósticos meteorológicos gratuitos (*Open-Meteo API*).
   * Expone un único endpoint `GET /v1/sky-forecast?lat={lat}&lon={lon}&lang={lang}`.
   * **Cero persistencia de usuario:** Recibe las coordenadas redondeadas en memoria, calcula los pases visibles y el clima, devuelve un JSON ligero (~2 KB) y descarta la petición sin almacenar IPs ni ubicaciones en base de datos.
2. **Cliente Android (Kotlin + Jetpack Compose):**
   * Recibe el JSON procesado, lo persiste en **Room** para garantizar disponibilidad sin conexión y delega la visualización en una UI reactiva con Material 3.

### Estructura de Paquetes (Clean Architecture Feature-First)

```text
com.igarciadelamo.aztarna/
│
├── core/
│   ├── network/        # Cliente HTTP (Retrofit/Ktor) y DTOs
│   ├── database/       # Room Database, DAOs y Entidades
│   ├── datastore/      # Preferencias de usuario y ubicación redondeada
│   ├── workers/        # WorkManager, AlarmManager y BroadcastReceivers
│   └── ui/             # Tema Material 3, tipografía y componentes compartidos
│
├── feature/home/
│   ├── data/           # Repositorio Offline-First y Mappers
│   ├── domain/         # Modelos puros de dominio y Casos de Uso
│   └── presentation/   # HomeScreen (Compose), HomeViewModel y HomeUiState
│
└── feature/settings/
    ├── domain/
    └── presentation/   # Configuración de ubicación, permisos y alertas
```

---

## 4. Contrato de API (`GET /v1/sky-forecast`)

### Petición
```http
GET /v1/sky-forecast?lat=40.4&lon=-3.7&lang=es
```

### Respuesta (`200 OK`)
```json
{
  "generated_at": "2026-11-15T18:00:00Z",
  "valid_until": "2026-11-16T08:00:00Z",
  "tonight_summary": {
    "is_worth_going_out": true,
    "headline": "Paso brillante de la ISS",
    "weather_condition": "Despejado",
    "cloud_cover_percent": 10
  },
  "events": [
    {
      "id": "iss_20261115_2142",
      "type": "SATELLITE",
      "title": "Estación Espacial Internacional (ISS)",
      "subtitle": "Muy brillante, fácil de ver a simple vista",
      "notify_at": "2026-11-15T21:27:00Z",
      "peak_time": "2026-11-15T21:42:15Z",
      "duration_seconds": 360,
      "visibility": {
        "magnitude": -3.8,
        "max_elevation_deg": 74,
        "start_azimuth": "Oeste",
        "end_azimuth": "Noreste",
        "cloud_cover_percent": 10,
        "is_recommended": true
      }
    }
  ]
}
```

---

## 5. Persistencia Local (Room) y Estado de UI (Compose)

### Entidades de Base de Datos
* **`CelestialEventEntity` (`celestial_events`):** Almacena cada evento con su identificador único, tipo (`SATELLITE`, `METEOR_SHOWER`, `PLANET`, `MOON`, `ECLIPSE`), timestamps ISO-8601 (`notifyAt`, `peakTime`), parámetros de visibilidad (`magnitude`, `maxElevationDeg`, `startAzimuth`, `endAzimuth`, `cloudCoverPercent`) y el flag `isRecommended`.
* **`ForecastCacheEntity` (`forecast_cache`):** Registro único (`id = 1`) que almacena el resumen global de la noche (`isWorthGoingOut`, `headline`, `weatherCondition`, `validUntil`) para alimentar la *Hero Card* incluso sin red.

### Estado Unidireccional de la UI (`HomeUiState`)
```kotlin
sealed interface HomeUiState {
    data object Loading : HomeUiState
    data class Success(
        val topEvent: CelestialEvent?,
        val forecastSummary: String,
        val upcomingEvents: List<CelestialEvent>,
        val isWorthGoingOut: Boolean
    ) : HomeUiState
    data class Error(
        val message: String,
        val hasCachedData: Boolean
    ) : HomeUiState
}
```

---

## 6. Planificación en Segundo Plano y Permisos (Google Play Compliance)

### Sincronización y Alertas (`WorkManager` + `AlarmManager`)
1. **Sincronización periódica (`WorkManager`):** Ejecuta cada 12 horas con restricción de red, consulta `/v1/sky-forecast` con coordenadas redondeadas a 1 decimal (~11 km), actualiza transaccionalmente **Room** y programa alarmas para eventos con `isRecommended == true`.
2. **Disparo exacto (`AlarmManager`):** Utiliza `setExactAndAllowWhileIdle()` (con degradación elegante a `setAndAllowWhileIdle()` si no hay permiso de alarma exacta en Android 14+) para despertar un `BroadcastReceiver` (`SkyAlertReceiver`) en el instante exacto de `notifyAt`.
3. **Persistencia tras reinicio:** Un `BootReceiver` (`ACTION_BOOT_COMPLETED`) restaura las alarmas futuras pendientes leyendo directamente desde **Room** sin depender de conexión a internet.

### Política de Ubicación y Privacidad
* **Minimización de precisión:** Se solicita exclusivamente `ACCESS_COARSE_LOCATION` (ubicación aproximada), suficiente para cálculos astronómicos y meteorológicos.
* **Flujo en dos fases:**
  1. *Primer plano:* Solicitado de forma contextual al activar la ubicación automática (con selector manual de ciudad como alternativa si se deniega).
  2. *Segundo plano (`ACCESS_BACKGROUND_LOCATION`):* Precedido obligatoriamente por una pantalla explicativa propia (*Prominent Disclosure*) que detalla por qué se requiere el acceso periódico y garantiza que las coordenadas nunca se almacenan ni comparten.