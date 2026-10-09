# Skycast: weather and the best time to travel

A city weather app with an animated sky that changes with the weather, a month-by-month
climate view, best-time-to-visit advice and a panel of places to visit.

- **Frontend** (`frontend/index.html`): one self-contained page with a search box for any city
  in the world (with suggestions as you type). 17 popular cities load instantly from built-in data.
- **Backend** (`skycast/`): a LangGraph workflow that fetches live weather and five years of
  climate history from Open-Meteo (free, no key), scores every month, and asks Claude
  (through LangChain) to write the travel advice and place suggestions. LangSmith traces each run.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # add ANTHROPIC_API_KEY and LANGSMITH_API_KEY (both optional)
python -m skycast           # open http://127.0.0.1:8000
```

## How a typed city is looked up

1. **Built-in city** (Kolkata, Paris, Tokyo…): shown instantly, then upgraded with live data if reachable.
2. **Skycast backend running**: suggestions come from Open-Meteo geocoding (`/api/geocode`), and the
   LangGraph workflow returns live weather, a 7-day outlook, real day-by-day climate averages and Claude's advice.
   Type `Perth, Australia` to pick between places with the same name.
3. **No backend, but the browser can reach Open-Meteo** (opening the file locally): the page geocodes and
   pulls five years of climate history and the forecast itself.
4. **Published preview on claude.ai** (outside sites are blocked there): the page asks Claude for the city's
   climate averages and sights, and labels them "Climate estimated by Claude".

Without an Anthropic key the backend's advice comes from the climate rules, and places are only listed
for the built-in cities.

Try the workflow from the command line: `python -m skycast report "Kyoto"`.

## How the workflow runs

```
START → resolve_city → fetch_live ──────┐
                    └→ fetch_climate ───┴→ analyse → advise → END
```

| Node | What it does |
|---|---|
| `resolve_city` | Uses built-in coordinates for known cities, otherwise Open-Meteo geocoding |
| `fetch_live` | Current conditions and a 16-day forecast (Open-Meteo forecast API) |
| `fetch_climate` | Last 5 full years of daily ERA5 data, averaged into monthly and day-of-month normals |
| `analyse` | Classifies each month's season (summer, winter, rainy, spring, autumn, dry, cool) and scores comfort |
| `advise` | Claude writes the best-time reasoning, a verdict for every month and 6 to 8 places, as structured output. Falls back to rule-based text if there is no key or the call fails |

The two fetch nodes run in parallel. If climate history is unreachable for a built-in city,
the built-in averages are used and a note is added to the response.

### How months are rated

Comfort starts at 100 and loses points for highs below 20°C or above 28°C, frosty nights,
rainfall and humid nights. The best months are the highest scorers (within 14 points of the
top, at most five). The same rules run in Python (`skycast/analysis.py`) and in the page;
a test checks they agree for every built-in city.

## API

| Endpoint | Returns |
|---|---|
| `GET /api/health` | `{"service": "skycast"}` (the page uses this to detect the backend) |
| `GET /api/geocode?q=Lis` | up to 6 matching places worldwide, for the search suggestions |
| `GET /api/report?city=Kolkata` (optional `lat`, `lon`, `country`, `tz`) | city, current, forecast, climate (monthly + daily normals), analysis, advice, notes |
| `GET /api/cities` | the built-in city list |

Reports are cached for 30 minutes per city.

## Project layout

```
frontend/index.html     the page, including the built-in city data (single source for both sides)
skycast/graph.py        LangGraph workflow
skycast/weather.py      Open-Meteo client (traced as LangSmith tool runs)
skycast/analysis.py     season, comfort and best-month rules
skycast/advisor.py      Claude advice via langchain-anthropic structured output
skycast/server.py       FastAPI app
tests/                  15 tests with Open-Meteo and Claude faked
```

To add a city, add an entry to the `city-data` JSON block in `frontend/index.html`
(monthly highs, lows, rainfall in mm, a tip and places) and run `pytest`.

## Notes

- Built-in figures are rounded typical monthly averages for planning, not official normals.
- Weather data: [Open-Meteo](https://open-meteo.com) (CC BY 4.0).
