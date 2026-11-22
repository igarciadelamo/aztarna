# Aztarna — Android client

Kotlin + Jetpack Compose (Material 3) app, offline-first. See [`../PRODUCT.md`](../PRODUCT.md) for the
product definition and architecture.

No code yet.

## Translating Tip Codes

Each event in `GET /v1/sky-forecast` carries `tips`, a list of codes ordered most specific first:

```json
"tips": ["OPPOSITION_BRIGHTEST", "JUPITER_MOONS", "STEADY_LIGHT", "BEST_AT_PEAK_TIME", "NAKED_EYE"]
```

The server never sends text. The app turns each code into a localized string resource.

### 1. String resources
- **Naming:** each code `FOO_BAR` becomes `tip_foo_bar`, in `res/values/strings.xml` (English) plus
  `values-es/` and `values-eu/`.
- **Source of truth:** the English copy is `TEXT` in
  [`backend/aztarna/tips.py`](../backend/aztarna/tips.py). Generate ready-to-paste English entries
  (apostrophes and `&` already escaped for Android):

  ```
  cd backend && make tips-strings
  ```

  ```xml
  <string name="tip_jupiter_moons">Steady binoculars reveal Jupiter\'s four largest moons as tiny dots in a line.</string>
  ```

  Translate the same keys into `values-es/strings.xml` and `values-eu/strings.xml`.

### 2. Code → resource mapping
Use an explicit map, **not** `Resources.getIdentifier()`. That call is slow, R8 resource shrinking
can strip strings it can't see referenced, and typos only fail at runtime.

```kotlin
private val TIP_STRINGS = mapOf(
    "DARK_ADAPT" to R.string.tip_dark_adapt,
    "JUPITER_MOONS" to R.string.tip_jupiter_moons,
    // … one entry per code in tips.py
)

@Composable
fun tipTexts(codes: List<String>, max: Int = 3): List<String> =
    codes.mapNotNull { TIP_STRINGS[it] }   // unknown codes are skipped
        .take(max)
        .map { stringResource(it) }
```

- **Unknown codes are skipped, never shown raw.** The server can add new tips before an app version
  knows them, so older apps keep working and just show fewer tips.
- **Show the first 2–3** if space is tight; the list is already ordered most specific first.

### 3. Adding or changing a tip
1. Add or edit the code and its English text in `backend/aztarna/tips.py`, then attach it in
   `BY_CATEGORY`, `BY_TARGET` or `CONJUNCTION`. The backend tests fail if a used code has no text.
2. Run `make tips-strings`, paste the new entry into `values/strings.xml`, add the `es` and `eu`
   translations, and add the entry to `TIP_STRINGS`.
3. Deploying the backend first is safe: apps without the string just skip that code.
4. **Never rename or reuse a code.** Older app versions still map the old one. Add a new code and
   stop sending the old one instead.

The same pattern (explicit map, skip unknown) applies to the other codes in the API: `target`,
`reason_code`, `condition_code` and the compass `start_direction` / `end_direction`.
