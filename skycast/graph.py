"""LangGraph workflow: resolve city -> (live weather || climate history) -> analyse -> advise."""

import operator
from typing import Annotated, TypedDict

from langchain_core.runnables import RunnableConfig

from langgraph.graph import END, START, StateGraph

from . import analysis, advisor, weather
from .cities import find_city


class State(TypedDict, total=False):
    query: str
    place: dict | None  # optional pre-resolved {name, country, lat, lon, tz} from the search box
    city: dict
    builtin: dict | None
    current: dict | None
    forecast: list[dict]
    climate: dict
    analysis: dict
    advice: dict
    notes: Annotated[list[str], operator.add]


def resolve_city(state: State) -> dict:
    place = state.get("place")
    if place:
        base = find_city(place["name"])
        if base and abs(base["lat"] - place["lat"]) > 1:
            base = None  # same name, different place (e.g. Paris, Texas)
        return {"city": {k: place.get(k, "") for k in ("name", "country", "lat", "lon", "tz")},
                "builtin": base, "notes": ["Using the place picked in the search box"]}
    base = find_city(state["query"])
    if base:
        city = {k: base[k] for k in ("name", "country", "lat", "lon", "tz")}
        return {"city": city, "builtin": base, "notes": [f"Using built-in coordinates for {base['name']}"]}
    return {"city": weather.geocode(state["query"]), "builtin": None, "notes": ["Geocoded with Open-Meteo"]}


def fetch_live(state: State) -> dict:
    try:
        current, forecast = weather.current_and_forecast(state["city"]["lat"], state["city"]["lon"])
        return {"current": current, "forecast": forecast}
    except Exception as e:
        return {"current": None, "forecast": [], "notes": [f"Live weather unavailable: {e}"]}


def fetch_climate(state: State) -> dict:
    try:
        return {"climate": weather.climate(state["city"]["lat"], state["city"]["lon"])}
    except Exception as e:
        base = state.get("builtin")
        if not base:
            raise
        return {"climate": {"hi": base["hi"], "lo": base["lo"], "rain": base["rain"], "month_days": None},
                "notes": [f"Climate history unavailable, using built-in normals: {e}"]}


def analyse(state: State) -> dict:
    c = state["climate"]
    return {"analysis": analysis.analyse(c["hi"], c["lo"], c["rain"], state["city"]["lat"])}


def advise(state: State, config: RunnableConfig | None = None) -> dict:
    base = state.get("builtin") or {}
    llm = ((config or {}).get("configurable") or {}).get("llm")
    city = {**state["city"], "tip": base.get("tip", "")}
    return {"advice": advisor.advise(city, state["climate"], state["analysis"], base.get("places"), llm=llm)}


def build_graph():
    g = StateGraph(State)
    g.add_node("resolve_city", resolve_city)
    g.add_node("fetch_live", fetch_live)
    g.add_node("fetch_climate", fetch_climate)
    g.add_node("analyse", analyse)
    g.add_node("advise", advise)
    g.add_edge(START, "resolve_city")
    g.add_edge("resolve_city", "fetch_live")      # these two run in parallel
    g.add_edge("resolve_city", "fetch_climate")
    g.add_edge(["fetch_live", "fetch_climate"], "analyse")
    g.add_edge("analyse", "advise")
    g.add_edge("advise", END)
    return g.compile()


GRAPH = build_graph()


def run(query: str, llm=None, place: dict | None = None) -> State:
    config = {"run_name": f"skycast:{query}", "tags": ["skycast"], "metadata": {"city": query}}
    if llm is not None:
        config["configurable"] = {"llm": llm}
    return GRAPH.invoke({"query": query, "place": place, "notes": []}, config=config)
