"""Travel advice: Claude (via LangChain) when ANTHROPIC_API_KEY is set, otherwise the climate rules."""
from __future__ import annotations

import logging
import os
from typing import Literal

from pydantic import BaseModel, Field

from . import analysis as A

log = logging.getLogger(__name__)
DEFAULT_MODEL = "claude-opus-5-5"


class MonthAdvice(BaseModel):
    month: int = Field(description="1-12")
    rating: Literal["best", "good", "fair", "poor"]
    why: str = Field(description="One or two plain sentences on what the weather is like and why it does or does not suit a visit")


class Place(BaseModel):
    name: str
    type: str = Field(description="One word category, e.g. Heritage, Nature, Food, Market, Beach, Spiritual, Viewpoint, Culture")
    desc: str = Field(description="One sentence, under 110 characters, with a practical tip")


class TravelAdvice(BaseModel):
    best_months: list[int] = Field(description="Best months to visit, 1-12")
    best_why: str = Field(description="2-3 sentences explaining why those months are best, citing temperatures and rain")
    tip: str = Field(description="One practical seasonal tip: a festival, closure or weather hazard")
    months: list[MonthAdvice] = Field(description="All 12 months")
    places: list[Place] = Field(description="6-8 important places to visit")


SYSTEM = (
    "You are a travel climatologist. Using only the climate table you are given, advise when to visit a city "
    "and why, and explain for every other month what the weather is like and why it is less suitable. "
    "Be concrete: cite highs, lows and rainfall. Then list the city's most important places to visit. "
    "Write plainly, no marketing language."
)


def _table(city: dict, climate: dict, an: dict) -> str:
    rows = ["month | high °C | low °C | rain mm | season | comfort score"]
    for m in range(12):
        rows.append(f"{A.MONTHS[m]} | {climate['hi'][m]} | {climate['lo'][m]} | {climate['rain'][m]} | "
                    f"{A.SEASON_LABELS[an['seasons'][m]]} | {an['scores'][m]}")
    return (f"City: {city['name']}, {city.get('country', '')} (lat {city['lat']}, lon {city['lon']})\n"
            + "\n".join(rows)
            + f"\nRule-based best months: {', '.join(A.MONTHS[m] for m in an['best'])}")


def rule_advice(city: dict, climate: dict, an: dict, places: list[dict] | None = None) -> dict:
    best = an["best"]
    avg = lambda key: sum(climate[key][m] for m in best) / len(best)
    worst = an["scores"].index(min(an["scores"]))
    worst_why = A.problems(climate["hi"][worst], climate["lo"][worst], climate["rain"][worst])
    why = (f"{A.range_text(best)} {'bring' if len(best) > 1 else 'brings'} the most comfortable weather in "
           f"{city['name']}: days around {round(avg('hi'))}°C, nights around {round(avg('lo'))}°C and "
           f"{A.rain_words(avg('rain'))}. {A.MONTHS[worst]} is the hardest month to visit"
           + (f": {worst_why[0][0].lower() + worst_why[0][1:]}." if worst_why else "."))
    return {
        "generated_by": "rules",
        "best_months": [m + 1 for m in best],
        "best_why": why,
        "tip": city.get("tip", ""),
        "months": [{"month": m + 1, "rating": an["ratings"][m],
                    "why": A.month_reason(climate["hi"][m], climate["lo"][m], climate["rain"][m], an["ratings"][m])}
                   for m in range(12)],
        "places": places or [],
    }


def make_llm():
    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(model=os.getenv("SKYCAST_MODEL", DEFAULT_MODEL), max_tokens=4096, temperature=0.3)


def claude_advice(city: dict, climate: dict, an: dict, llm=None) -> dict:
    llm = llm or make_llm()
    structured = llm.with_structured_output(TravelAdvice)
    result: TravelAdvice = structured.invoke([("system", SYSTEM), ("human", _table(city, climate, an))])
    out = result.model_dump()
    out["generated_by"] = "claude"
    out["best_months"] = sorted({m for m in out["best_months"] if 1 <= m <= 12}) or [m + 1 for m in an["best"]]
    return out


def advise(city: dict, climate: dict, an: dict, places: list[dict] | None = None, llm=None) -> dict:
    fallback = rule_advice(city, climate, an, places)
    if llm is None and not os.getenv("ANTHROPIC_API_KEY"):
        return fallback
    try:
        out = claude_advice(city, climate, an, llm)
    except Exception as e:  # network, auth or parsing problems: keep the app working
        log.warning("Claude advice failed, using rules: %s", e)
        fallback["error"] = str(e)[:200]
        return fallback
    if not out.get("places"):
        out["places"] = fallback["places"]
    return out
