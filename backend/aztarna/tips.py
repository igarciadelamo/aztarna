"""Static viewing tips. The API sends codes only; the app localizes them (es, eu, en).
TEXT is the English source copy for the Android string resources: keep both in sync."""

from aztarna.models import Category, NormalizedSkyEvent

TEXT = {
    # General
    "DARK_ADAPT": "Give your eyes 15–20 minutes in the dark. Avoid your phone screen, or use red light.",
    "AWAY_FROM_LIGHTS": "Find a spot away from street lights with a wide open view of the sky.",
    "NAKED_EYE": "No equipment needed: it is visible to the naked eye.",
    "BINOCULARS": "Binoculars show much more detail. Rest them on something steady.",
    "BEST_AT_PEAK_TIME": "It is highest around the peak time: less atmosphere, sharper view.",
    "DRESS_WARM": "Dress warmly and bring a blanket or a reclining chair.",
    "PHOTO_TRIPOD": "For photos, put your phone on a tripod and use night mode or a long exposure.",
    # Satellites
    "ARRIVE_EARLY": "Be outside a few minutes early: a pass lasts only a few minutes.",
    "FACE_START_DIRECTION": "Face the start direction. It appears there and glides steadily across the sky.",
    "STEADY_MOVING_STAR": "It looks like a bright, steady star moving fast. Blinking lights are a plane.",
    "SHADOW_FADE": "It may fade out mid-sky as it enters Earth's shadow.",
    "PHOTO_TRAIL": "A 10–30 second exposure on a tripod captures its trail across the stars.",
    # Meteor showers
    "BEST_BEFORE_DAWN": "Rates rise after midnight and are best before dawn, when the radiant is high.",
    "LOOK_WIDE": "Lie back and take in as much sky as you can. Meteors appear anywhere, not only at the radiant.",
    "BE_PATIENT": "Watch for at least 30–60 minutes: meteors come in bursts.",
    # Moon
    "WATCH_MOONRISE": "Watch it rise: low on the horizon it looks bigger and more orange.",
    "MOON_LANDMARK_PHOTO": "At moonrise, frame it with a building or landscape for a striking photo.",
    "SUPERMOON_BRIGHTER": "It is only slightly larger than usual, but noticeably brighter.",
    # Eclipses
    "ECLIPSE_SAFE": "Lunar eclipses are completely safe to watch with the naked eye.",
    "TOTALITY_COLOR": "During totality the Moon turns a coppery red.",
    "PARTIAL_BITE": "Watch Earth's dark shadow slowly take a 'bite' out of the Moon.",
    # Planets
    "STEADY_LIGHT": "Planets shine with a steady light; stars twinkle.",
    "OPPOSITION_BRIGHTEST": "At opposition the planet is at its closest and brightest of the year, up all night.",
    "JUPITER_MOONS": "Steady binoculars reveal Jupiter's four largest moons as tiny dots in a line.",
    "SATURN_RINGS": "Any small telescope shows Saturn's rings.",
    "MARS_COLOR": "Look for its orange-red color.",
    "CONJUNCTION_PAIR": "Look for two bright points very close together; binoculars fit both in one view.",
    "TWILIGHT_PHOTO": "Great photo after dusk with a landscape in the foreground.",
}

# Most specific first; for_event merges target → conjunction → category and drops duplicates.
BY_CATEGORY = {
    Category.SATELLITE: [
        "ARRIVE_EARLY",
        "FACE_START_DIRECTION",
        "STEADY_MOVING_STAR",
        "SHADOW_FADE",
        "NAKED_EYE",
        "PHOTO_TRAIL",
    ],
    Category.METEOR_SHOWER: [
        "BEST_BEFORE_DAWN",
        "LOOK_WIDE",
        "AWAY_FROM_LIGHTS",
        "DARK_ADAPT",
        "BE_PATIENT",
        "DRESS_WARM",
    ],
    Category.MOON: ["WATCH_MOONRISE", "BINOCULARS", "MOON_LANDMARK_PHOTO"],
    Category.ECLIPSE: ["ECLIPSE_SAFE", "BEST_AT_PEAK_TIME", "BINOCULARS", "PHOTO_TRIPOD"],
    Category.PLANET: ["STEADY_LIGHT", "BEST_AT_PEAK_TIME", "NAKED_EYE"],
}
BY_TARGET = {
    "SUPERMOON": ["SUPERMOON_BRIGHTER"],
    "TOTAL_LUNAR_ECLIPSE": ["TOTALITY_COLOR"],
    "PARTIAL_LUNAR_ECLIPSE": ["PARTIAL_BITE"],
    "JUPITER_OPPOSITION": ["OPPOSITION_BRIGHTEST", "JUPITER_MOONS"],
    "SATURN_OPPOSITION": ["OPPOSITION_BRIGHTEST", "SATURN_RINGS"],
    "MARS_OPPOSITION": ["OPPOSITION_BRIGHTEST", "MARS_COLOR"],
}
CONJUNCTION = ["CONJUNCTION_PAIR", "TWILIGHT_PHOTO"]


def for_event(event: NormalizedSkyEvent) -> list[str]:
    codes = BY_TARGET.get(event.target, [])
    if event.target.endswith("_CONJUNCTION"):
        codes = codes + CONJUNCTION
    return list(dict.fromkeys(codes + BY_CATEGORY[event.category]))
