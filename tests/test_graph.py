"""Graph tests with Open-Meteo and Claude replaced by fakes (no network or API key needed)."""
import datetime as dt
import math

import pytest
from fastapi.testclient import TestClient

from skycast import advisor, graph, server, weather


def fake_daily(lat=22.57):
    days, hi, lo, pr = [], [], [], []
    d = dt.date(2021, 1, 1)
    while d <= dt.date(2025, 12, 31):
        phase = math.cos((d.timetuple().tm_yday - 120) / 365 * 2 * math.pi)
        days.append(d.isoformat()); hi.append(30 + 6 * phase); lo.append(20 + 6 * phase)
        pr.append(12.0 if 6 <= d.month <= 9 else 0.2)
        d += dt.timedelta(days=1)
    return {"time": days, "temperature_2m_max": hi, "temperature_2m_min": lo, "precipitation_sum": pr}


@pytest.fixture
def fake_weather(monkeypatch):
    calls = []
    pune = {"name": "Pune", "country": "India", "admin1": "Maharashtra", "lat": 18.52, "lon": 73.86, "tz": "Asia/Kolkata"}
    monkeypatch.setattr(weather, "search", lambda name, count=6: calls.append(("geo", name)) or [pune][:count])
    monkeypatch.setattr(weather, "current_and_forecast", lambda lat, lon: (
        {"temp": 29.0, "feels": 32.0, "humidity": 70, "wind": 9.0, "precip": 0.0, "code": 2, "is_day": 1, "hi": 31, "lo": 24},
        [{"date": "2026-10-09", "hi": 31, "lo": 24, "code": 2, "rain_chance": 20}]))
    monkeypatch.setattr(weather, "climate", lambda lat, lon: weather.summarise_daily(fake_daily(), 2026))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return calls


def test_summarise_daily():
    c = weather.summarise_daily(fake_daily(), 2026)
    assert len(c["hi"]) == 12 and len(c["month_days"]) == 12
    assert len(c["month_days"][1]) == 28 and len(c["month_days"][0]) == 31
    assert c["rain"][6] > 300 and c["rain"][0] < 10
    assert c["hi"][4] > c["hi"][11]


def test_graph_builtin_city_rules(fake_weather):
    s = graph.run("Kolkata")
    assert s["city"]["name"] == "Kolkata" and not fake_weather       # built-in coords, no geocoding
    assert s["current"]["temp"] == 29.0
    assert s["advice"]["generated_by"] == "rules"
    assert len(s["advice"]["months"]) == 12
    assert s["advice"]["places"][0]["name"] == "Victoria Memorial"


def test_graph_unknown_city_geocodes(fake_weather):
    s = graph.run("Pune")
    assert fake_weather == [("geo", "Pune")]
    assert s["city"]["name"] == "Pune" and s["advice"]["places"] == []


def test_climate_failure_falls_back_for_builtin(fake_weather, monkeypatch):
    def boom(lat, lon): raise RuntimeError("blocked")
    monkeypatch.setattr(weather, "climate", boom)
    s = graph.run("London")
    assert s["climate"]["hi"][6] == 23
    assert any("built-in" in n for n in s["notes"])


class FakeStructured:
    def invoke(self, messages):
        assert "climate" in messages[0][1].lower() and "Kolkata" in messages[1][1]
        return advisor.TravelAdvice(
            best_months=[11, 12, 1, 2], best_why="Cool and dry.", tip="Durga Puja in October.",
            months=[advisor.MonthAdvice(month=m, rating="best" if m in (11, 12, 1, 2) else "poor", why="x") for m in range(1, 13)],
            places=[advisor.Place(name="Victoria Memorial", type="Heritage", desc="Museum.")])


class FakeLLM:
    def with_structured_output(self, schema):
        assert schema is advisor.TravelAdvice
        return FakeStructured()


def test_graph_with_claude(fake_weather):
    s = graph.run("Kolkata", llm=FakeLLM())
    assert s["advice"]["generated_by"] == "claude"
    assert s["advice"]["best_months"] == [1, 2, 11, 12]


def test_claude_error_falls_back(fake_weather):
    class Broken:
        def with_structured_output(self, schema): raise RuntimeError("401")
    s = graph.run("Kolkata", llm=Broken())
    assert s["advice"]["generated_by"] == "rules" and "401" in s["advice"]["error"]


def test_api(fake_weather):
    server._cache.clear()
    client = TestClient(server.app)
    assert client.get("/api/health").json()["service"] == "skycast"
    r = client.get("/api/report", params={"city": "Tokyo"}).json()
    assert r["city"]["name"] == "Tokyo" and len(r["climate"]["month_days"]) == 12
    page = client.get("/")
    assert page.status_code == 200 and "Skycast" in page.text
    assert len(client.get("/api/cities").json()) >= 15


def test_search_box_place_is_used(fake_weather):
    place = {"name": "Paris", "country": "United States", "lat": 33.66, "lon": -95.56, "tz": "America/Chicago"}
    s = graph.run("Paris", place=place)
    assert not fake_weather                       # no geocoding when the search box already picked a place
    assert s["city"]["country"] == "United States"
    assert s["advice"]["places"] == []            # not mixed up with Paris, France


def test_api_geocode_and_any_city(fake_weather):
    server._cache.clear()
    client = TestClient(server.app)
    hits = client.get("/api/geocode", params={"q": "Pun"}).json()
    assert hits[0]["name"] == "Pune" and hits[0]["admin1"] == "Maharashtra"
    r = client.get("/api/report", params={"city": "Pune", "lat": 18.52, "lon": 73.86, "country": "India", "tz": "Asia/Kolkata"}).json()
    assert r["city"]["name"] == "Pune" and len(r["advice"]["months"]) == 12


def test_search_country_filter(monkeypatch):
    monkeypatch.setattr(weather, "_get", lambda url, params: {"results": [
        {"name": "Perth", "country": "United Kingdom", "country_code": "GB", "admin1": "Scotland", "latitude": 56.4, "longitude": -3.4, "timezone": "Europe/London"},
        {"name": "Perth", "country": "Australia", "country_code": "AU", "admin1": "Western Australia", "latitude": -31.95, "longitude": 115.86, "timezone": "Australia/Perth"}]})
    assert weather.search("Perth, Australia")[0]["country"] == "Australia"
    assert weather.geocode("Perth")["country"] == "United Kingdom"
