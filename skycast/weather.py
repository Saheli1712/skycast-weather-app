"""Open-Meteo client (free, no API key): geocoding, current + 16-day forecast, and ERA5 climate history."""
from __future__ import annotations

import datetime as dt
from calendar import monthrange
from statistics import mean

import httpx
from langsmith import traceable

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
CLIMATE_YEARS = 5
TIMEOUT = httpx.Timeout(30.0)


def _get(url: str, params: dict) -> dict:
    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.get(url, params=params)
        r.raise_for_status()
        return r.json()


@traceable(run_type="tool", name="open_meteo_search")
def search(name: str, count: int = 6) -> list[dict]:
    """Worldwide place search; accepts 'City' or 'City, Country'."""
    city, _, country = (p.strip() for p in name.partition(","))
    data = _get(GEOCODE_URL, {"name": city, "count": 20 if country else count, "language": "en", "format": "json"})
    results = data.get("results") or []
    if country:
        c = country.lower()
        results = [r for r in results if c in (r.get("country", "").lower(), r.get("country_code", "").lower(),
                                                r.get("admin1", "").lower())] or results
    return [{"name": r["name"], "country": r.get("country", ""), "admin1": r.get("admin1", ""),
             "lat": r["latitude"], "lon": r["longitude"], "tz": r.get("timezone", "UTC")}
            for r in results[:count]]


def geocode(name: str) -> dict:
    hits = search(name, 1)
    if not hits:
        raise LookupError(f"No city found for '{name}'")
    return hits[0]


@traceable(run_type="tool", name="open_meteo_forecast")
def current_and_forecast(lat: float, lon: float) -> tuple[dict, list[dict]]:
    data = _get(FORECAST_URL, {
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 16,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,"
                   "precipitation,weather_code,is_day",
        "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max",
    })
    c, d = data["current"], data["daily"]
    current = {"temp": c["temperature_2m"], "feels": c["apparent_temperature"],
               "humidity": c["relative_humidity_2m"], "wind": c["wind_speed_10m"],
               "precip": c.get("precipitation", 0.0), "code": c["weather_code"], "is_day": c["is_day"],
               "hi": d["temperature_2m_max"][0], "lo": d["temperature_2m_min"][0], "time": c.get("time")}
    forecast = [{"date": day, "hi": d["temperature_2m_max"][i], "lo": d["temperature_2m_min"][i],
                 "code": d["weather_code"][i],
                 "rain_chance": (d.get("precipitation_probability_max") or [None] * len(d["time"]))[i]}
                for i, day in enumerate(d["time"])]
    return current, forecast


@traceable(run_type="tool", name="open_meteo_climate")
def climate(lat: float, lon: float, today: dt.date | None = None) -> dict:
    """Average the last CLIMATE_YEARS full years of daily ERA5 data into monthly and day-of-month normals."""
    today = today or dt.date.today()
    first, last = today.year - CLIMATE_YEARS, today.year - 1
    data = _get(ARCHIVE_URL, {
        "latitude": lat, "longitude": lon, "timezone": "auto",
        "start_date": f"{first}-01-01", "end_date": f"{last}-12-31",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
    })
    return summarise_daily(data["daily"], today.year)


def summarise_daily(daily: dict, year: int) -> dict:
    by_day: dict[tuple[int, int], dict[str, list[float]]] = {}
    rain_by_month_year: dict[tuple[int, int], float] = {}
    for i, day in enumerate(daily["time"]):
        y, m, d = (int(p) for p in day.split("-"))
        hi, lo = daily["temperature_2m_max"][i], daily["temperature_2m_min"][i]
        pr = daily["precipitation_sum"][i] or 0.0
        if hi is None or lo is None:
            continue
        slot = by_day.setdefault((m, d), {"hi": [], "lo": [], "wet": []})
        slot["hi"].append(hi)
        slot["lo"].append(lo)
        slot["wet"].append(1.0 if pr >= 1.0 else 0.0)
        rain_by_month_year[(y, m)] = rain_by_month_year.get((y, m), 0.0) + pr

    hi_m, lo_m, rain_m, month_days = [], [], [], []
    for m in range(1, 13):
        days = [(d, by_day[(m, d)]) for d in range(1, 32) if (m, d) in by_day]
        hi_m.append(round(mean(v for _, s in days for v in s["hi"]), 1))
        lo_m.append(round(mean(v for _, s in days for v in s["lo"]), 1))
        totals = [v for (y, mm), v in rain_by_month_year.items() if mm == m]
        rain_m.append(round(mean(totals)) if totals else 0)
        n = monthrange(year, m)[1]
        month_days.append([{"day": d, "hi": round(mean(s["hi"]), 1), "lo": round(mean(s["lo"]), 1),
                            "wet_chance": round(mean(s["wet"]), 2), "source": "climate"}
                           for d, s in days if d <= n])
    return {"hi": hi_m, "lo": lo_m, "rain": rain_m, "month_days": month_days}
