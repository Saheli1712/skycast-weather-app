"""Climate rules shared with the frontend (mirrors the JS in frontend/index.html).

Pure functions: given 12 monthly highs, lows and rainfall totals, classify each
month's season, score its comfort for sightseeing and pick the best months.
"""
from __future__ import annotations

import math

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
SEASON_LABELS = {
    "summer": "Summer", "hot": "Hot summer", "winter": "Winter", "rainy": "Rainy season",
    "spring": "Spring", "autumn": "Autumn", "dry": "Dry season", "cool": "Cool season",
}


def season_of(hi: float, lo: float, rain: float, lat: float, m: int) -> str:
    """m is 0-based (0 = January)."""
    mean = (hi + lo) / 2
    if rain >= 150:
        return "rainy"
    if mean >= 29:
        return "hot"
    if abs(lat) >= 20:
        if hi <= 12 or lo <= 2:
            return "winter"
        mm = m if lat >= 0 else (m + 6) % 12  # southern hemisphere seasons are flipped
        if mm <= 1 or mm == 11:
            return "winter"
        if mm <= 4:
            return "spring"
        if mm <= 7:
            return "summer"
        return "autumn"
    return "cool" if lo <= 18 else "dry"


def comfort(hi: float, lo: float, rain: float) -> int:
    s = 100.0
    s -= max(0, 20 - hi) * 4 + max(0, hi - 28) * 5
    s -= max(0, 5 - lo) * 2
    s -= min(45, rain / 10 * 1.2)
    if lo >= 24:
        s -= 6
    return int(max(0, min(100, math.floor(s + 0.5))))  # JS Math.round semantics


def analyse(hi: list[float], lo: list[float], rain: list[float], lat: float) -> dict:
    scores = [comfort(hi[m], lo[m], rain[m]) for m in range(12)]
    top = max(scores)
    ranked = sorted(((s, m) for m, s in enumerate(scores) if s >= top - 14 and s >= 45), key=lambda x: (-x[0], x[1]))
    best = sorted(m for _, m in ranked[:5]) or [scores.index(top)]
    ratings = ["best" if m in best else "good" if s >= 65 else "fair" if s >= 45 else "poor"
               for m, s in enumerate(scores)]
    seasons = [season_of(hi[m], lo[m], rain[m], lat, m) for m in range(12)]
    return {"scores": scores, "best": best, "ratings": ratings, "seasons": seasons}


def rain_words(r: float) -> str:
    if r < 15:
        return "almost no rain"
    if r < 50:
        return f"very little rain (about {round(r)} mm)"
    if r < 100:
        return f"a few showers (about {round(r)} mm)"
    return f"some rain (about {round(r)} mm)"


def problems(hi: float, lo: float, rain: float) -> list[str]:
    out = []
    if rain >= 300:
        out.append(f"Very heavy rain, about {round(rain)} mm in the month, floods streets and disrupts travel")
    elif rain >= 150:
        out.append(f"Frequent heavy downpours, about {round(rain)} mm, interrupt sightseeing")
    elif rain >= 90 and hi < 26:
        out.append(f"Damp, with about {round(rain)} mm of rain spread over many days")
    if hi >= 38:
        out.append(f"Extreme heat, highs near {round(hi)}°C, makes daytime outings exhausting")
    elif hi >= 33:
        out.append(f"Hot afternoons with highs around {round(hi)}°C")
    if lo >= 25 and hi >= 30:
        out.append("Humid nights that barely cool down")
    if hi <= 5:
        out.append(f"Freezing, with highs of only {round(hi)}°C and ice or snow likely")
    elif hi <= 12:
        out.append(f"Cold, with highs around {round(hi)}°C and short days")
    elif lo <= 2:
        out.append(f"Frosty nights around {round(lo)}°C")
    return out


def month_reason(hi: float, lo: float, rain: float, rating: str) -> str:
    if rating == "best":
        return f"Highs near {round(hi)}°C, lows near {round(lo)}°C and {rain_words(rain)}."
    p = problems(hi, lo, rain)
    if not p:
        return (f"Comfortable, with highs near {round(hi)}°C and {rain_words(rain)}. "
                "A good alternative to the peak months.")
    return ". ".join(p) + "."


def range_text(months: list[int]) -> str:
    s = set(months)
    if not s:
        return ""
    if len(s) == 12:
        return "All year"
    runs = []
    for m in range(12):
        if m not in s or (m + 11) % 12 in s:
            continue
        e = m
        while (e + 1) % 12 in s:
            e = (e + 1) % 12
        runs.append(MONTHS[m] if e == m else f"{MONTHS[m][:3]} – {MONTHS[e][:3]}")
    return " and ".join(runs)
