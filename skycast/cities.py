"""Built-in city data. The frontend page is the single source: its embedded JSON block is read here."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent.parent / "frontend" / "index.html"


@lru_cache(maxsize=1)
def load_cities() -> list[dict]:
    html = FRONTEND.read_text(encoding="utf-8")
    m = re.search(r'<script id="city-data" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError(f"city-data block not found in {FRONTEND}")
    return json.loads(m.group(1))["cities"]


ALIASES = {"new delhi": "delhi", "calcutta": "kolkata", "bombay": "mumbai", "nyc": "newyork",
           "new york city": "newyork", "denpasar": "bali"}


def find_city(query: str) -> dict | None:
    """Match a built-in city by id, name or alias; ignores a trailing ', Country'."""
    q = " ".join(query.split(",")[0].lower().split())
    cid = ALIASES.get(q, q.replace(" ", ""))
    for c in load_cities():
        if cid == c["id"] or q == c["name"].lower():
            return c
    return None
