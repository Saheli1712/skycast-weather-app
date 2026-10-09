"""FastAPI server: JSON API under /api and the Skycast page at /."""
from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from . import graph, weather
from .cities import FRONTEND, load_cities

app = FastAPI(title="Skycast")
_cache: dict[str, tuple[float, dict]] = {}
CACHE_SECONDS = 30 * 60


@app.get("/api/health")
def health():
    return {"service": "skycast", "ok": True}


@app.get("/api/cities")
def cities():
    return [{"id": c["id"], "name": c["name"], "country": c["country"], "region": c["region"]} for c in load_cities()]


@app.get("/api/geocode")
def geocode(q: str = Query(..., min_length=1, max_length=80)):
    """Suggestions for the search box: any city worldwide."""
    try:
        return weather.search(q)
    except Exception as e:
        raise HTTPException(502, f"Geocoding error: {e}")


@app.get("/api/report")
def report(city: str = Query(..., min_length=1, max_length=80),
           lat: float | None = Query(None, ge=-90, le=90), lon: float | None = Query(None, ge=-180, le=180),
           country: str = "", tz: str = "UTC"):
    place = {"name": city, "country": country, "lat": lat, "lon": lon, "tz": tz} if lat is not None and lon is not None else None
    key = f"{city.strip().lower()}|{lat}|{lon}"
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    try:
        s = graph.run(city, place=place)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(502, f"Weather service error: {e}")
    body = {k: s.get(k) for k in ("city", "current", "forecast", "climate", "analysis", "advice", "notes")}
    _cache[key] = (time.time(), body)
    return body


@app.get("/")
def index():
    return FileResponse(Path(FRONTEND), media_type="text/html; charset=utf-8")
